"""Tests for `kq paper-summary`. Read-only flow against an isolated DuckDB
seeded with synthetic paper-trade rows.

The 2026-06-11 audit caught the old output labeling the Phase 2 exit
numbers (50 settled / 14 days) as "Phase 5 gates" (Phase 5 #1 is 500) and
calling distinct UTC dates "active days". The rendering tests here pin the
honest labels.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pytest

from kq.flows.paper_summary import (
    PHASE2_MIN_DISTINCT_DAYS,
    PHASE2_MIN_SETTLED,
    PHASE5_MIN_SETTLED,
    PaperSummary,
    PerStation,
    render_human,
    summarize,
)
from kq.storage.duckdb_store import bootstrap


def _to_naive_utc(dt: datetime) -> datetime:
    """Strip tz before DuckDB insert. DuckDB TIMESTAMP is naive and would otherwise
    apply the system's local-clock conversion to a tz-aware value (subtracting
    7h in PDT, e.g.) — corrupting the stored UTC instant. The production code
    in `kq.storage.repositories.paper_trades` does the same thing for the same
    reason."""
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt


def _seed_signal_and_trade(
    con: duckdb.DuckDBPyConnection,
    *,
    trade_id: str,
    ticker: str,
    submitted_at: datetime,
    pnl_usd: float | None,
    settled: bool,
) -> None:
    """Insert a paired signal + paper_trade row. Tests use deterministic IDs."""
    signal_id = f"sig-{trade_id}"
    naive = _to_naive_utc(submitted_at)
    con.execute(
        """
        INSERT INTO signal (signal_id, as_of, ticker, model_prob_yes, market_prob_yes,
                            edge_bps, model_name, source_urls, reasoning)
        VALUES (?, ?, ?, 0.6, 0.5, 1000.0, 'test', [], 'unit-test seed')
        """,
        [signal_id, naive, ticker],
    )
    con.execute(
        """
        INSERT INTO paper_trade
        (trade_id, signal_id, submitted_at, ticker, side, limit_price, qty, fee_usd,
         filled_at, fill_price, settled_at, settlement, pnl_usd)
        VALUES (?, ?, ?, ?, 'BUY_YES', 0.50, 10, 0.20, ?, 0.50, ?, ?, ?)
        """,
        [
            trade_id,
            signal_id,
            naive,
            ticker,
            naive,
            naive if settled else None,
            "YES" if (settled and (pnl_usd or 0) > 0) else ("NO" if settled else None),
            pnl_usd,
        ],
    )


def _make_db(tmp_path: Path) -> Path:
    db = tmp_path / "paper.duckdb"
    bootstrap(db)
    return db


# ----------------------------------------------------------- summarize


def test_empty_db_returns_zero_summary(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    con = duckdb.connect(str(db), read_only=True)
    try:
        s = summarize(con, starting_bankroll_usd=1_000.0)
    finally:
        con.close()
    assert s.n_signals == 0
    assert s.n_filled == 0
    assert s.n_settled == 0
    assert s.n_distinct_trade_days == 0
    assert s.win_rate == 0.0
    assert s.total_pnl_usd == 0.0
    assert s.current_bankroll_usd == 1_000.0
    assert s.roi_pct == 0.0
    assert s.phase2_passes_settled_count is False
    assert s.phase2_passes_distinct_days is False
    assert s.phase5_settled_target == PHASE5_MIN_SETTLED
    assert s.phase5_settled_progress_pct == 0.0
    assert s.per_station == []


def test_settled_trades_aggregate_correctly(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    con = duckdb.connect(str(db))
    try:
        # 3 settled (2 wins), 1 unsettled, all in one day, all KLAX
        base = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        _seed_signal_and_trade(
            con,
            trade_id="t1",
            ticker="KXHIGHLAX-25-0601-A",
            submitted_at=base,
            pnl_usd=4.0,
            settled=True,
        )
        _seed_signal_and_trade(
            con,
            trade_id="t2",
            ticker="KXHIGHLAX-25-0601-B",
            submitted_at=base,
            pnl_usd=3.0,
            settled=True,
        )
        _seed_signal_and_trade(
            con,
            trade_id="t3",
            ticker="KXHIGHLAX-25-0601-C",
            submitted_at=base,
            pnl_usd=-2.0,
            settled=True,
        )
        _seed_signal_and_trade(
            con,
            trade_id="t4",
            ticker="KXHIGHLAX-25-0601-D",
            submitted_at=base,
            pnl_usd=None,
            settled=False,
        )
    finally:
        con.close()

    con = duckdb.connect(str(db), read_only=True)
    try:
        s = summarize(con)
    finally:
        con.close()

    assert s.n_filled == 4
    assert s.n_settled == 3
    assert s.n_won == 2
    assert s.win_rate == pytest.approx(2 / 3)
    assert s.total_pnl_usd == pytest.approx(4.0 + 3.0 - 2.0)  # +5.0 (unsettled NULL drops in SUM)
    assert s.n_distinct_trade_days == 1
    assert s.phase5_settled_progress_pct == pytest.approx(100.0 * 3 / PHASE5_MIN_SETTLED, abs=0.1)
    assert len(s.per_station) == 1
    klax = s.per_station[0]
    assert klax.station == "KLAX"
    assert klax.n_filled == 4
    assert klax.n_settled == 3
    assert klax.n_won == 2
    assert klax.total_pnl_usd == pytest.approx(5.0)


def test_per_station_groups_by_event_ticker_prefix(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    con = duckdb.connect(str(db))
    try:
        base = datetime(2025, 6, 1, tzinfo=UTC)
        _seed_signal_and_trade(
            con,
            trade_id="lax",
            ticker="KXHIGHLAX-25-0601-A",
            submitted_at=base,
            pnl_usd=5.0,
            settled=True,
        )
        _seed_signal_and_trade(
            con,
            trade_id="den",
            ticker="KXHIGHDEN-25-0601-B",
            submitted_at=base,
            pnl_usd=-3.0,
            settled=True,
        )
        _seed_signal_and_trade(
            con,
            trade_id="other",
            ticker="KXOTHER-25-0601-C",
            submitted_at=base,
            pnl_usd=1.0,
            settled=True,
        )
    finally:
        con.close()

    con = duckdb.connect(str(db), read_only=True)
    try:
        s = summarize(con)
    finally:
        con.close()

    by_st = {p.station: p for p in s.per_station}
    assert by_st["KLAX"].total_pnl_usd == pytest.approx(5.0)
    assert by_st["KDEN"].total_pnl_usd == pytest.approx(-3.0)
    assert by_st["OTHER"].total_pnl_usd == pytest.approx(1.0)
    assert by_st["KLAX"].n_won == 1
    assert by_st["KDEN"].n_won == 0


def test_distinct_trade_days_counted_correctly(tmp_path: Path) -> None:
    """Multiple trades on the same day count as one distinct trade day."""
    db = _make_db(tmp_path)
    con = duckdb.connect(str(db))
    try:
        d1 = datetime(2025, 6, 1, tzinfo=UTC)
        d2 = datetime(2025, 6, 2, tzinfo=UTC)
        _seed_signal_and_trade(
            con,
            trade_id="a",
            ticker="KXHIGHLAX-25-0601-A",
            submitted_at=d1,
            pnl_usd=1.0,
            settled=True,
        )
        _seed_signal_and_trade(
            con,
            trade_id="b",
            ticker="KXHIGHLAX-25-0601-B",
            submitted_at=d1,
            pnl_usd=1.0,
            settled=True,
        )
        _seed_signal_and_trade(
            con,
            trade_id="c",
            ticker="KXHIGHLAX-25-0602-C",
            submitted_at=d2,
            pnl_usd=1.0,
            settled=True,
        )
    finally:
        con.close()

    con = duckdb.connect(str(db), read_only=True)
    try:
        s = summarize(con)
    finally:
        con.close()
    assert s.n_distinct_trade_days == 2
    assert s.n_filled == 3


def test_distinct_days_are_not_a_consecutive_streak(tmp_path: Path) -> None:
    """A month-long gap between two trade days still counts 2 distinct
    days — pinning that the computation matches the (new) label, which
    explicitly disclaims consecutiveness."""
    db = _make_db(tmp_path)
    con = duckdb.connect(str(db))
    try:
        _seed_signal_and_trade(
            con,
            trade_id="a",
            ticker="KXHIGHLAX-25-0601-A",
            submitted_at=datetime(2025, 6, 1, tzinfo=UTC),
            pnl_usd=1.0,
            settled=True,
        )
        _seed_signal_and_trade(
            con,
            trade_id="b",
            ticker="KXHIGHLAX-25-0701-B",
            submitted_at=datetime(2025, 7, 1, tzinfo=UTC),
            pnl_usd=1.0,
            settled=True,
        )
    finally:
        con.close()

    con = duckdb.connect(str(db), read_only=True)
    try:
        s = summarize(con)
    finally:
        con.close()
    assert s.n_distinct_trade_days == 2


def test_phase2_exit_criteria_flip_at_thresholds(tmp_path: Path) -> None:
    """At exactly the documented Phase 2 thresholds, the exit criteria
    flip to PASS — and the Phase 5 #1 gate (500) does NOT."""
    db = _make_db(tmp_path)
    con = duckdb.connect(str(db))
    try:
        # Seed exactly PHASE2_MIN_SETTLED settled trades across
        # PHASE2_MIN_DISTINCT_DAYS distinct days.
        for i in range(PHASE2_MIN_SETTLED):
            day_offset = i % PHASE2_MIN_DISTINCT_DAYS
            ts = datetime(2025, 6, 1, tzinfo=UTC).replace(day=1 + day_offset)
            _seed_signal_and_trade(
                con,
                trade_id=f"trade-{i}",
                ticker="KXHIGHLAX-25-0601-X",
                submitted_at=ts,
                pnl_usd=0.5,
                settled=True,
            )
    finally:
        con.close()

    con = duckdb.connect(str(db), read_only=True)
    try:
        s = summarize(con)
    finally:
        con.close()
    assert s.n_settled == PHASE2_MIN_SETTLED
    assert s.n_distinct_trade_days == PHASE2_MIN_DISTINCT_DAYS
    assert s.phase2_passes_settled_count is True
    assert s.phase2_passes_distinct_days is True
    # 50 settled is 10% of the Phase 5 #1 gate, nowhere near passing it.
    assert s.n_settled < PHASE5_MIN_SETTLED
    assert s.phase5_settled_progress_pct == pytest.approx(10.0)


def test_date_range_filter_excludes_out_of_window_trades(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    con = duckdb.connect(str(db))
    try:
        before = datetime(2025, 5, 25, tzinfo=UTC)
        in_range = datetime(2025, 6, 1, tzinfo=UTC)
        after = datetime(2025, 6, 30, tzinfo=UTC)
        _seed_signal_and_trade(
            con,
            trade_id="a",
            ticker="KXHIGHLAX-25-0525",
            submitted_at=before,
            pnl_usd=10.0,
            settled=True,
        )
        _seed_signal_and_trade(
            con,
            trade_id="b",
            ticker="KXHIGHLAX-25-0601",
            submitted_at=in_range,
            pnl_usd=20.0,
            settled=True,
        )
        _seed_signal_and_trade(
            con,
            trade_id="c",
            ticker="KXHIGHLAX-25-0630",
            submitted_at=after,
            pnl_usd=30.0,
            settled=True,
        )
    finally:
        con.close()

    con = duckdb.connect(str(db), read_only=True)
    try:
        s = summarize(con, start_date=date(2025, 6, 1), end_date=date(2025, 6, 7))
    finally:
        con.close()
    assert s.n_filled == 1
    assert s.total_pnl_usd == pytest.approx(20.0)
    assert s.start_date == date(2025, 6, 1)
    assert s.end_date == date(2025, 6, 7)


def test_starting_bankroll_drives_roi_and_current(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    con = duckdb.connect(str(db))
    try:
        _seed_signal_and_trade(
            con,
            trade_id="a",
            ticker="KXHIGHLAX-X",
            submitted_at=datetime(2025, 6, 1, tzinfo=UTC),
            pnl_usd=50.0,
            settled=True,
        )
    finally:
        con.close()
    con = duckdb.connect(str(db), read_only=True)
    try:
        s = summarize(con, starting_bankroll_usd=500.0)
    finally:
        con.close()
    assert s.current_bankroll_usd == pytest.approx(550.0)
    assert s.roi_pct == pytest.approx(10.0)


# ----------------------------------------------------------- render


def _render_fixture(*, n_settled: int, n_days: int) -> PaperSummary:
    return PaperSummary(
        start_date=date(2025, 6, 1),
        end_date=date(2025, 6, 14),
        n_signals=60,
        n_filled=55,
        n_settled=n_settled,
        n_won=30,
        win_rate=0.6,
        total_pnl_usd=87.45,
        starting_bankroll_usd=1_000.0,
        current_bankroll_usd=1_087.45,
        roi_pct=8.745,
        n_distinct_trade_days=n_days,
        phase2_passes_settled_count=n_settled >= PHASE2_MIN_SETTLED,
        phase2_passes_distinct_days=n_days >= PHASE2_MIN_DISTINCT_DAYS,
        phase5_settled_target=PHASE5_MIN_SETTLED,
        phase5_settled_progress_pct=round(100.0 * n_settled / PHASE5_MIN_SETTLED, 1),
        per_station=[
            PerStation(
                "KLAX", n_filled=20, n_settled=18, n_won=11, win_rate=0.611, total_pnl_usd=32.10
            ),
        ],
    )


def test_render_human_labels_phase2_exit_criteria_honestly() -> None:
    """The 50-settled / 14-day bars are the PHASE 2 exit criteria and
    must be labeled as such — the old output called them 'Phase 5
    gates' (2026-06-11 audit)."""
    out = render_human(
        _render_fixture(n_settled=PHASE2_MIN_SETTLED, n_days=PHASE2_MIN_DISTINCT_DAYS)
    )
    assert "Phase 2 exit criteria" in out
    assert f"{PHASE2_MIN_SETTLED:>5} / {PHASE2_MIN_SETTLED}   PASS" in out
    assert f"{PHASE2_MIN_DISTINCT_DAYS:>5} / {PHASE2_MIN_DISTINCT_DAYS}   PASS" in out
    # The 50/14 numbers must never be presented as Phase 5 gates.
    assert "Phase 5 gate >= 50" not in out
    assert "Phase 5 gate >= 14" not in out
    assert "KLAX" in out
    assert "+8.74%" in out  # ROI line, formatted to 2 decimals


def test_render_human_shows_phase5_progress_separately() -> None:
    """Phase 5 #1 (>= 500 settled) appears as an explicit progress
    counter with the 500 denominator."""
    out = render_human(_render_fixture(n_settled=50, n_days=14))
    assert "Phase 5 gate #1 progress" in out
    assert f"/ {PHASE5_MIN_SETTLED}" in out
    assert "10.0%" in out  # 50 of 500


def test_render_human_labels_distinct_days_as_distinct() -> None:
    """'Active days' is gone; the label says distinct UTC dates and
    disclaims consecutiveness, matching the computation."""
    out = render_human(_render_fixture(n_settled=10, n_days=3))
    assert "Distinct trade days" in out
    assert "not a consecutive streak" in out
    assert "Active days" not in out
    assert "not yet" in out  # unmet criteria are 'not yet', not scary FAIL


def test_to_dict_round_trips_through_json() -> None:
    """JSON-safety guarantee — the `--json` flag relies on this."""
    s = PaperSummary(
        start_date=date(2025, 6, 1),
        end_date=None,
        n_signals=1,
        n_filled=1,
        n_settled=0,
        n_won=0,
        win_rate=0.0,
        total_pnl_usd=0.0,
        starting_bankroll_usd=1_000.0,
        current_bankroll_usd=1_000.0,
        roi_pct=0.0,
        n_distinct_trade_days=1,
        phase2_passes_settled_count=False,
        phase2_passes_distinct_days=False,
        phase5_settled_target=PHASE5_MIN_SETTLED,
        phase5_settled_progress_pct=0.0,
        per_station=[],
    )
    d = s.to_dict()
    blob = json.dumps(d)
    parsed = json.loads(blob)
    assert parsed["start_date"] == "2025-06-01"
    assert parsed["end_date"] is None
    assert parsed["n_signals"] == 1
    assert parsed["phase2_passes_settled_count"] is False
    assert parsed["phase5_settled_target"] == PHASE5_MIN_SETTLED
