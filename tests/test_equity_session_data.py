"""Completed-session evidence must unblock paper execution without inventing data."""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

import pytest

from kq.equities.session_data import complete_session

NOW = datetime(2026, 9, 29, 1, 30, tzinfo=UTC)


def inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    placeholder = dict(
        begins_at="2026-09-28T00:00:00Z",
        open_price="100",
        close_price="100",
        high_price="100",
        low_price="100",
        volume=0,
        session="reg",
        interpolated=True,
    )
    snapshot = dict(
        captured_at="2026-09-29T01:00:00+00:00",
        adjustment_type="split",
        benchmark="SPY",
        universe=["AAA"],
        bars=[
            dict(symbol=s, interval="day", bounds="regular", bars=[copy.deepcopy(placeholder)])
            for s in ("AAA", "SPY")
        ],
    )
    evidence = dict(
        fundamentals_as_of="2026-09-29T01:10:00+00:00",
        quotes_as_of="2026-09-29T01:11:00+00:00",
        fundamentals=[
            dict(
                symbol=s,
                bounds="regular",
                market_date="2026-09-28",
                open="101",
                high="104",
                low="99",
                volume="500000",
            )
            for s in ("AAA", "SPY")
        ],
        quotes=[
            dict(
                quote=dict(symbol=s),
                close=dict(
                    symbol=s,
                    date="2026-09-28",
                    price="103",
                    interpolated=False,
                    source="sip-list-exchange-close",
                ),
            )
            for s in ("AAA", "SPY")
        ],
    )
    return snapshot, evidence


def test_verified_session_replaces_placeholder_and_preserves_inputs() -> None:
    snapshot, evidence = inputs()
    original = copy.deepcopy(snapshot)
    result = complete_session(snapshot, evidence, required={"AAA", "SPY"}, now=NOW)
    assert snapshot == original
    assert result["bars"][0]["bars"][0]["open_price"] == "101"
    assert result["bars"][0]["bars"][0]["close_price"] == "103"
    assert result["bars"][0]["bars"][0]["volume"] == 500000
    assert len(result["session_repairs"]) == 2
    assert result["captured_at"] == NOW.isoformat()


@pytest.mark.parametrize(
    "field,value",
    [
        ("market_date", "2026-09-25"),
        ("bounds", "extended"),
        ("open", "nan"),
        ("volume", "0"),
        ("low", "102"),
        ("high", "102"),
    ],
)
def test_bad_session_statistics_fail_required_symbol(field: str, value: str) -> None:
    snapshot, evidence = inputs()
    evidence["fundamentals"][0][field] = value
    with pytest.raises(ValueError, match="AAA"):
        complete_session(snapshot, evidence, required={"AAA", "SPY"}, now=NOW)


@pytest.mark.parametrize(
    "field,value",
    [
        ("date", "2026-09-25"),
        ("interpolated", True),
        ("source", "unknown"),
        ("price", "105"),
        ("symbol", "BBB"),
    ],
)
def test_bad_official_close_fails_required_symbol(field: str, value: Any) -> None:
    snapshot, evidence = inputs()
    evidence["quotes"][0]["close"][field] = value
    with pytest.raises(ValueError, match="AAA"):
        complete_session(snapshot, evidence, required={"AAA", "SPY"}, now=NOW)


@pytest.mark.parametrize(
    "stamp", ["2026-09-29T02:00:00+00:00", "2026-09-28T19:00:00+00:00", "2026-09-29T01:00:00"]
)
def test_preclose_future_or_naive_evidence_rejected(stamp: str) -> None:
    snapshot, evidence = inputs()
    evidence["fundamentals_as_of"] = stamp
    with pytest.raises(ValueError):
        complete_session(snapshot, evidence, required={"SPY"}, now=NOW)


def test_later_batch_cannot_cross_the_next_open() -> None:
    snapshot, evidence = inputs()
    evidence["fundamentals_as_of"] = "2026-09-29T13:29:00+00:00"
    evidence["fundamentals_latest_as_of"] = "2026-09-29T13:31:00+00:00"
    with pytest.raises(ValueError, match="before next open"):
        complete_session(snapshot, evidence, required={"SPY"}, now=NOW.replace(hour=13, minute=32))


def test_real_daily_bar_is_never_replaced() -> None:
    snapshot, evidence = inputs()
    bar = snapshot["bars"][0]["bars"][0]
    bar.update(interpolated=False, volume=700000)
    result = complete_session(snapshot, evidence, required={"AAA", "SPY"}, now=NOW)
    assert result["bars"][0]["bars"][0] == bar
    assert [r["symbol"] for r in result["session_repairs"]] == ["SPY"]


def test_missing_optional_symbol_remains_unusable_with_reason() -> None:
    snapshot, evidence = inputs()
    evidence["quotes"] = evidence["quotes"][1:]
    result = complete_session(snapshot, evidence, required={"SPY"}, now=NOW)
    assert result["bars"][0]["bars"][0]["interpolated"] is True
    assert "AAA" in result["source_errors"][-1]


def test_duplicate_evidence_is_not_arbitrarily_selected() -> None:
    snapshot, evidence = inputs()
    evidence["fundamentals"].append(evidence["fundamentals"][0])
    with pytest.raises(ValueError, match="duplicate"):
        complete_session(snapshot, evidence, required={"SPY"}, now=NOW)


def test_missing_required_series_fails_even_if_quote_exists() -> None:
    snapshot, evidence = inputs()
    snapshot["bars"] = snapshot["bars"][1:]
    with pytest.raises(ValueError, match="AAA"):
        complete_session(snapshot, evidence, required={"AAA", "SPY"}, now=NOW)


def test_original_intraday_capture_cannot_be_relabelled_as_completed() -> None:
    snapshot, evidence = inputs()
    snapshot["captured_at"] = "2026-09-28T18:00:00+00:00"
    for series in snapshot["bars"]:
        series["bars"][0].update(interpolated=False, volume=123)
    with pytest.raises(ValueError, match="completed"):
        complete_session(snapshot, evidence, required={"SPY"}, now=NOW)


def test_required_nonregular_daily_bar_cannot_claim_coverage() -> None:
    snapshot, evidence = inputs()
    snapshot["bars"][1]["bars"][0].update(interpolated=False, volume=123, session="post")
    with pytest.raises(ValueError, match="SPY"):
        complete_session(snapshot, evidence, required={"SPY"}, now=NOW)
