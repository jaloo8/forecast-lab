"""Tests for ``kq doctor`` — the reality-contact diagnostics.

Testing philosophy (post-2026-06-11 audit): these tests cover the
EVALUATION LOGIC using recorded prod payloads, where the test author
cannot bias what the venue returned. The live-probe path is deliberately
NOT unit-tested — it runs against reality itself (weekly via
``scripts/reality-probe.sh``), and mocking it here would recreate the
exact self-confirmation failure the doctor exists to prevent.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb

from kq.flows.doctor import (
    check_observed_truth,
    check_parser_coverage,
    check_payload_shape,
    check_phase5_clocks,
    check_settlement_source,
)
from kq.storage.duckdb_store import bootstrap

_FIXTURES = Path(__file__).parent / "fixtures"


def _recorded_lax_payload() -> dict[str, object]:
    return json.loads((_FIXTURES / "kalshi_prod_markets_weather.json").read_text(encoding="utf-8"))


# --------------------------- payload-shape ---------------------------


def test_payload_shape_ok_on_recorded_prod_payload() -> None:
    checks = check_payload_shape({"KXHIGHLAX": _recorded_lax_payload()})
    assert len(checks) == 1
    assert checks[0].severity == "ok"
    assert "12/12 priced" in checks[0].detail


def test_payload_shape_crit_when_wire_format_drifts() -> None:
    """Simulate the audit-finding-#1 failure class: markets present but no
    field the parser understands carries a price."""
    drifted = {
        "markets": [
            {"ticker": "KXHIGHLAX-X-T75", "status": "active", "yes_bid_v3": "0.42"},
        ]
    }
    checks = check_payload_shape({"KXHIGHLAX": drifted})
    assert checks[0].severity == "crit"
    assert "wire format drifted" in checks[0].detail


def test_payload_shape_warns_on_fetch_failure_and_empty_series() -> None:
    checks = check_payload_shape({"KXHIGHAUS": RuntimeError("boom"), "KXHIGHMIA": {"markets": []}})
    by_name = {c.name: c for c in checks}
    assert by_name["payload-shape.KXHIGHAUS"].severity == "warn"
    assert by_name["payload-shape.KXHIGHMIA"].severity == "warn"


# --------------------------- parser-coverage ---------------------------


def test_parser_coverage_full_book_tradeable_since_pr_b() -> None:
    """PR-B: the strike-aware matcher admits the ENTIRE recorded prod book
    (greater + less + between), not just the 2 T-greater tail markets the
    PR-A interim guard allowed."""
    checks = check_parser_coverage({"KXHIGHLAX": _recorded_lax_payload()})
    assert checks[0].severity == "ok"
    assert "12/12 tradeable" in checks[0].detail
    assert "'between': 8" in checks[0].detail


def test_parser_coverage_crit_when_nothing_tradeable() -> None:
    """A book whose strike fields are missing on unguessable tickers (a
    between-market without API semantics) is untradeable -> crit."""
    between_without_strike_fields = {
        "markets": [
            {
                "ticker": "KXHIGHLAX-26JUN11-B74.5",
                "status": "active",
                "yes_bid_dollars": "0.40",
                "yes_ask_dollars": "0.41",
            }
        ]
    }
    checks = check_parser_coverage({"KXHIGHLAX": between_without_strike_fields})
    assert checks[0].severity == "crit"
    assert "0/1 tradeable" in checks[0].detail


# --------------------------- settlement-source ---------------------------


def _ny_payload(rules: str) -> dict[str, object]:
    return {"markets": [{"ticker": "KXHIGHNY-26JUN11-T95", "rules_primary": rules}]}


def test_settlement_source_crit_on_station_mismatch() -> None:
    """The Central Park finding, encoded permanently: contract names a
    station the pipeline does not model -> CRIT until actually fixed."""
    rules = (
        "If the highest temperature recorded in Central Park, New York for "
        "June 11, 2026 ... is greater than 95°, then the market resolves to Yes."
    )
    checks = check_settlement_source({"KXHIGHNY": _ny_payload(rules)})
    assert checks[0].severity == "crit"
    assert "Central Park" in checks[0].detail


def test_settlement_source_crit_when_kalshi_changes_the_source() -> None:
    rules = "If the highest temperature recorded at LaGuardia Airport ..."
    checks = check_settlement_source({"KXHIGHNY": _ny_payload(rules)})
    assert checks[0].severity == "crit"
    assert "no longer mentions" in checks[0].detail


def test_settlement_source_ok_when_aligned() -> None:
    payload = {
        "markets": [
            {
                "ticker": "KXHIGHDEN-26JUN11-T93",
                "rules_primary": "If the highest temperature recorded in Denver ...",
            }
        ]
    }
    checks = check_settlement_source({"KXHIGHDEN": payload})
    assert checks[0].severity == "ok"


# --------------------------- observed-truth + clocks ---------------------------


def test_observed_truth_crit_when_empty_and_when_stale(tmp_path: Path) -> None:
    db = tmp_path / "t.duckdb"
    bootstrap(db)
    checks = check_observed_truth(db)
    assert checks[0].severity == "crit"
    assert "EMPTY" in checks[0].detail

    con = duckdb.connect(str(db))
    try:
        stale = (datetime.now(tz=UTC) - timedelta(days=30)).date()
        con.execute(
            "INSERT INTO weather_observed (station, valid_date, high_f, low_f, fetched_at) "
            "VALUES ('KLAX', ?, 75.0, 60.0, now())",
            [stale],
        )
    finally:
        con.close()
    checks = check_observed_truth(db)
    assert checks[0].severity == "crit"
    assert "stale" in checks[0].detail


def test_observed_truth_ok_when_fresh(tmp_path: Path) -> None:
    db = tmp_path / "t.duckdb"
    bootstrap(db)
    con = duckdb.connect(str(db))
    try:
        con.execute(
            "INSERT INTO weather_observed (station, valid_date, high_f, low_f, fetched_at) "
            "VALUES ('KLAX', ?, 75.0, 60.0, now())",
            [datetime.now(tz=UTC).date() - timedelta(days=1)],
        )
    finally:
        con.close()
    checks = check_observed_truth(db)
    assert checks[0].severity == "ok"


def test_phase5_clocks_reports_zero_state(tmp_path: Path) -> None:
    db = tmp_path / "t.duckdb"
    bootstrap(db)
    checks = check_phase5_clocks(db)
    assert checks[0].severity == "info"
    assert "settled_trades=0/500" in checks[0].detail
