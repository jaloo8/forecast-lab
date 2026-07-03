"""Hermetic end-to-end tests for `kq.flows.study_nowcast_edge`.

The study replays settled weather markets against orderbook history on a
seeded tmp DuckDB — no network, no repo-level models (the router config /
models_dir point at empty tmp dirs so the raw-sigma fallback prior is used
and results stay deterministic across machines).

The seeded scenario (KLAX, LST = UTC-8, settlement day ends 08:00 UTC):

    market  KXHIGHLAX-26JUN20-T85  greater@85  (YES iff observed high >= 85.5)
    truth   weather_observed high_f = 90 -> settles YES
    prior   3 GEFS members, as_of 2026-06-20 12:00, mean 80F
            + a LATE batch, as_of 2026-06-21 03:00, mean 95F (leak bait)
    metar   01:30 -> 75F ; 02:30 -> 90F (leak bait) ; 06:00 -> 88F
    snaps   01:00 (bucket 7, two-sided 0.25/0.29)   no obs yet -> prior only
            02:00 (bucket 6, 0.30/0.34)             t_so_far=75 -> prob ~0.01
            05:30 (bucket 2, 0.80/0.84)             t_so_far=90 -> locked 0.99
            06:30 (bucket 1, one-sided 0.0/0.97)    unusable book -> skipped
            07:30 + 07:45 (bucket 0, last one wins) locked 0.99

PIT discipline is the heart of it: the 02:00 snapshot must see NEITHER the
02:30 90F METAR (which would lock the prob at 0.99) NOR the 03:00 forecast
batch (mean 95F). If either leaks, the bucket-6 probability jumps from
~0.01 to >0.9 and the assertion fails loudly.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kq.__main__ import app
from kq.dashboard.panels import (
    format_nowcast_edge_summary,
    format_nowcast_edge_table,
    nowcast_edge_caveats,
    read_nowcast_edge_manifest,
)
from kq.flows.study_nowcast_edge import (
    EMPTY_DATA_MESSAGE,
    EdgeRecord,
    StudyResult,
    aggregate,
    main,
    run_study,
    write_manifest,
)
from kq.storage.duckdb_store import bootstrap, connect

TICKER = "KXHIGHLAX-26JUN20-T85"
STATION = "KLAX"
VALID_DATE = date(2026, 6, 20)
# KLAX LST is UTC-8: the 2026-06-20 settlement day spans 08:00 UTC -> 08:00 UTC.
DAY_END_UTC = datetime(2026, 6, 21, 8, 0)
NOW_AFTER_SETTLEMENT = datetime(2026, 6, 22, 0, 0, tzinfo=UTC)


def _seed_full_scenario(db_path: Path) -> None:
    bootstrap(db_path)
    with connect(db_path) as con:
        # Prior: on-time batch (mean 80F) + leak-bait late batch (mean 95F).
        for member, high in enumerate([79.0, 80.0, 81.0]):
            con.execute(
                "INSERT INTO weather_forecast VALUES (?, ?, 'gefs', ?, ?, ?, ?, NULL)",
                [
                    datetime(2026, 6, 20, 12, 0),
                    datetime(2026, 6, 20, 12, 0),
                    member,
                    STATION,
                    VALID_DATE,
                    high,
                ],
            )
        for member, high in enumerate([94.0, 95.0, 96.0]):
            con.execute(
                "INSERT INTO weather_forecast VALUES (?, ?, 'gefs', ?, ?, ?, ?, NULL)",
                [
                    datetime(2026, 6, 21, 3, 0),
                    datetime(2026, 6, 21, 3, 0),
                    member,
                    STATION,
                    VALID_DATE,
                    high,
                ],
            )
        # METAR: 75F before the early snap, 90F AFTER it (the PIT leak bait).
        for obs_time, temp in [
            (datetime(2026, 6, 21, 1, 30), 75.0),
            (datetime(2026, 6, 21, 2, 30), 90.0),
            (datetime(2026, 6, 21, 6, 0), 88.0),
        ]:
            con.execute(
                "INSERT INTO metar_obs (obs_time, station, temp_f) VALUES (?, ?, ?)",
                [obs_time, STATION, temp],
            )
        # Settlement truth: high 90F -> greater@85 settles YES.
        con.execute(
            "INSERT INTO weather_observed (station, valid_date, high_f, fetched_at) "
            "VALUES (?, ?, 90.0, ?)",
            [STATION, VALID_DATE, datetime(2026, 6, 22, 0, 0)],
        )
        # Stored strike semantics (prod-shaped): greater, floor 85.
        con.execute(
            "INSERT INTO kalshi_market (ticker, strike_type, floor_strike) "
            "VALUES (?, 'greater', 85.0)",
            [TICKER],
        )
        # Book snapshots across the final hours.
        snaps = [
            (datetime(2026, 6, 21, 1, 0), 0.25, 0.29),  # bucket 7 (no obs yet)
            (datetime(2026, 6, 21, 2, 0), 0.30, 0.34),  # bucket 6 (PIT target)
            (datetime(2026, 6, 21, 5, 30), 0.80, 0.84),  # bucket 2 (locked)
            (datetime(2026, 6, 21, 6, 30), 0.0, 0.97),  # bucket 1 one-sided -> skip
            (datetime(2026, 6, 21, 7, 30), 0.90, 0.94),  # bucket 0, superseded
            (datetime(2026, 6, 21, 7, 45), 0.95, 0.97),  # bucket 0, last usable
        ]
        for snap_time, bid, ask in snaps:
            con.execute(
                "INSERT INTO kalshi_book_snap (snap_time, ticker, yes_bid, yes_ask) "
                "VALUES (?, ?, ?, ?)",
                [snap_time, TICKER, bid, ask],
            )


def _run_seeded_study(tmp_path: Path) -> StudyResult:
    db_path = tmp_path / "study.duckdb"
    _seed_full_scenario(db_path)
    with connect(db_path, read_only=True) as con:
        return run_study(
            con,
            router_config_path=tmp_path / "no_router_config.json",
            models_dir=tmp_path,
            now_utc=NOW_AFTER_SETTLEMENT,
        )


def _by_bucket(result: StudyResult) -> dict[int, EdgeRecord]:
    out = {r.hours_to_settlement: r for r in result.records}
    assert len(out) == len(result.records), "expected one record per hour bucket"
    return out


# --------------------------------------------------------------- end-to-end


def test_end_to_end_produces_one_record_per_usable_hour_bucket(tmp_path: Path) -> None:
    result = _run_seeded_study(tmp_path)
    assert result.n_markets_studied == 1
    assert result.prior_source == "raw_fallback"
    recs = _by_bucket(result)
    assert set(recs) == {0, 2, 6, 7}
    # Bucket 1 had only a one-sided book (bid 0.0 sentinel) -> counted, not graded.
    assert result.skips["no_usable_book"] == 1
    # Outcome is strike-aware: high 90 >= 85.5 -> YES for every record.
    assert all(r.outcome_yes for r in result.records)


def test_pit_discipline_future_obs_and_forecasts_do_not_leak(tmp_path: Path) -> None:
    """The 02:00 snapshot's prob must reflect only what was knowable at 02:00.

    t_so_far is 75F (the 01:30 obs) and the prior mean is 80F: with the raw
    sigma shrunk by sqrt(fraction_day_remaining), P(high > 85.5) clips to
    ~0.01. If the 02:30 90F obs leaked, the threshold is exceeded and the
    prob locks at 0.99; if the 03:00 forecast batch (mean 95F) leaked, the
    prior alone pushes it >0.9. Either leak fails this assertion.
    """
    recs = _by_bucket(_run_seeded_study(tmp_path))
    assert recs[6].model_prob < 0.05
    # Later snapshots legitimately DO see the 90F obs -> locked near-certainty.
    assert recs[2].model_prob == pytest.approx(0.99)
    assert recs[0].model_prob == pytest.approx(0.99)


def test_last_snapshot_in_each_hour_bucket_wins(tmp_path: Path) -> None:
    recs = _by_bucket(_run_seeded_study(tmp_path))
    # Bucket 0 had snaps at 07:30 (mid 0.92) and 07:45 (mid 0.96) — last wins.
    assert recs[0].market_mid == pytest.approx(0.96)
    assert recs[0].snap_time == datetime(2026, 6, 21, 7, 45, tzinfo=UTC)


def test_money_view_uses_taker_fees_and_the_4pp_gate(tmp_path: Path) -> None:
    recs = _by_bucket(_run_seeded_study(tmp_path))
    # Bucket 2: BUY_YES at ask 0.84, fee 1c, edge 14pp >= 4pp -> actionable;
    # outcome YES -> realized capture = 1 - 0.84 - 0.01.
    assert recs[2].actionable
    assert recs[2].after_fee_capture_usd == pytest.approx(0.15)
    # Bucket 6: model 0.01 < bid 0.30 -> BUY_NO at 0.70 (fee 2c, edge 27pp),
    # actionable — and the YES settlement makes the capture NEGATIVE. The
    # money view carries the outcome; the edge metrics never do.
    assert recs[6].actionable
    assert recs[6].after_fee_capture_usd == pytest.approx(-0.72)
    # Bucket 0: BUY_YES at 0.97 leaves 1pp after fees — below the gate.
    assert not recs[0].actionable
    assert recs[0].after_fee_capture_usd is None


# --------------------------------------------------- outcome-free metric pin


def test_mean_edge_is_outcome_free(tmp_path: Path) -> None:
    """The PR-E lesson pin: mean_edge is mean(model - mid) and flipping every
    outcome must not move it (Brier moves; the edge diagnostic must not)."""
    result = _run_seeded_study(tmp_path)
    _, overall = aggregate(result)
    expected = sum(r.model_prob - r.market_mid for r in result.records) / len(result.records)
    assert overall.mean_edge == pytest.approx(expected)

    flipped = StudyResult(
        window_hours=result.window_hours,
        prior_source=result.prior_source,
        n_markets_studied=result.n_markets_studied,
        records=[
            EdgeRecord(
                ticker=r.ticker,
                station=r.station,
                valid_date=r.valid_date,
                snap_time=r.snap_time,
                hours_to_settlement=r.hours_to_settlement,
                model_prob=r.model_prob,
                market_mid=r.market_mid,
                outcome_yes=not r.outcome_yes,
                edge=r.edge,
                actionable=r.actionable,
                after_fee_capture_usd=r.after_fee_capture_usd,
            )
            for r in result.records
        ],
        skips=result.skips,
    )
    _, flipped_overall = aggregate(flipped)
    assert flipped_overall.mean_edge == pytest.approx(overall.mean_edge)
    assert flipped_overall.mean_abs_edge == pytest.approx(overall.mean_abs_edge)
    assert flipped_overall.brier_model != pytest.approx(overall.brier_model)


# ------------------------------------------------------------ manifest shape


EXPECTED_TOP_LEVEL_KEYS = {
    "generated_at",
    "window_hours",
    "prior_source",
    "min_edge_gate_pct",
    "fee_side",
    "n_markets_studied",
    "n_records",
    "skips",
    "by_hours_to_settlement",
    "overall",
    "message",
    "honest_caveats",
}
EXPECTED_BUCKET_KEYS = {
    "n",
    "mean_abs_edge",
    "mean_edge",
    "brier_model",
    "brier_market",
    "n_actionable",
    "mean_after_fee_capture_usd",
}


def test_manifest_schema_and_contents(tmp_path: Path) -> None:
    result = _run_seeded_study(tmp_path)
    out = write_manifest(result, out_path=tmp_path / "manifest.json")
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert set(payload) == EXPECTED_TOP_LEVEL_KEYS
    assert payload["window_hours"] == 8
    assert payload["min_edge_gate_pct"] == 4.0
    assert payload["fee_side"] == "taker"
    assert payload["n_records"] == 4
    assert payload["message"] is None
    assert set(payload["by_hours_to_settlement"]) == {str(h) for h in range(8)}
    for entry in payload["by_hours_to_settlement"].values():
        assert set(entry) == EXPECTED_BUCKET_KEYS
    assert set(payload["overall"]) == EXPECTED_BUCKET_KEYS
    assert payload["overall"]["n"] == 4
    # Buckets 7, 6, 2 cleared the 4pp gate; bucket 0's 1pp edge did not.
    assert payload["overall"]["n_actionable"] == 3
    # Empty buckets are explicit n=0 rows, not missing keys.
    assert payload["by_hours_to_settlement"]["5"]["n"] == 0
    assert payload["by_hours_to_settlement"]["5"]["brier_model"] is None
    # The retired outcome-conditioned metric must never reappear.
    assert "mean_signed_edge" not in out.read_text(encoding="utf-8")


# ------------------------------------------------------------- zero-data path


def test_empty_db_writes_clean_manifest_and_exits_zero(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.duckdb"
    bootstrap(db_path)
    manifest_path = tmp_path / "manifest.json"
    n = main(
        db_path=db_path,
        manifest_path=manifest_path,
        router_config_path=tmp_path / "no_router.json",
        models_dir=tmp_path,
        now_utc=NOW_AFTER_SETTLEMENT,
    )
    assert n == 0
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(payload) == EXPECTED_TOP_LEVEL_KEYS
    assert payload["n_records"] == 0
    assert payload["message"] == EMPTY_DATA_MESSAGE
    assert payload["overall"]["n"] == 0


def test_missing_db_file_writes_clean_manifest_and_exits_zero(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    n = main(
        db_path=tmp_path / "does_not_exist.duckdb",
        manifest_path=manifest_path,
        router_config_path=tmp_path / "no_router.json",
        models_dir=tmp_path,
    )
    assert n == 0
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["n_records"] == 0
    assert payload["message"] == EMPTY_DATA_MESSAGE


def test_market_without_truth_or_day_still_running_is_skipped(tmp_path: Path) -> None:
    """A market whose settlement day hasn't elapsed must not be graded even
    if snapshots exist — settlement is unknown until the LST day closes."""
    db_path = tmp_path / "study.duckdb"
    _seed_full_scenario(db_path)
    with connect(db_path, read_only=True) as con:
        result = run_study(
            con,
            router_config_path=tmp_path / "no_router.json",
            models_dir=tmp_path,
            now_utc=datetime(2026, 6, 21, 7, 0, tzinfo=UTC),  # mid-window
        )
    assert result.records == []
    assert result.skips["day_not_elapsed"] == 1


# --------------------------------------------------------------- CLI wiring


def test_cli_registration_and_help_text() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["study-nowcast-edge", "--help"])
    assert result.exit_code == 0
    assert "final hours" in result.stdout
    assert "#1 hypothesized edge" in result.stdout


# --------------------------------------------------------- dashboard panels


def test_dashboard_panel_reads_manifest_and_formats_table(tmp_path: Path) -> None:
    result = _run_seeded_study(tmp_path)
    out = write_manifest(result, out_path=tmp_path / "manifest.json")
    summary = read_nowcast_edge_manifest(out)
    assert summary is not None
    assert summary.n_records == 4
    assert summary.overall is not None
    assert summary.overall.n == 4
    header = format_nowcast_edge_summary(summary)
    assert "4 market-hours graded" in header
    assert "4pp after-fee" in header
    table = format_nowcast_edge_table(summary)
    assert "Hours to settlement" in table
    assert "| 0 |" in table and "| 6 |" in table
    gloss = nowcast_edge_caveats()
    assert "lower is better" in gloss
    assert "no outcome in the formula" in gloss


def test_dashboard_panel_empty_states_point_at_the_command(tmp_path: Path) -> None:
    assert read_nowcast_edge_manifest(tmp_path / "missing.json") is None
    assert "kq study-nowcast-edge" in format_nowcast_edge_summary(None)

    empty = StudyResult(
        window_hours=8, prior_source="raw_fallback", n_markets_studied=0, records=[], skips={}
    )
    out = write_manifest(empty, out_path=tmp_path / "empty.json")
    summary = read_nowcast_edge_manifest(out)
    assert summary is not None
    assert summary.n_records == 0
    text = format_nowcast_edge_summary(summary)
    assert "nothing to grade yet" in text
    assert "settle" in text
