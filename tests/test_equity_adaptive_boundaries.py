"""Decision thresholds and source-integrity regressions."""

from __future__ import annotations

import copy
import math
from datetime import UTC, datetime

import pytest

from kq.equities.adaptive import _action, signals
from tests.test_equity_adaptive import DAYS, NOW, _series, _snapshot


def test_frozen_decision_thresholds_and_reasons() -> None:
    assert _action("flat", 0.5, True, None) == ("BUY", "buy_threshold_met")
    assert _action("flat", 0.499999, True, None) == ("WATCH", "below_buy_threshold")
    assert _action("held", 0.0, False, "illiquid") == ("SELL", "nonpositive_exit")
    assert _action("held", 0.000001, False, "illiquid") == ("HOLD", "positive_hold_band")
    assert _action("pending_exit", None, False, "missing_stock_session") == (
        "PENDING",
        "missing_stock_session",
    )


def test_higher_risk_reduces_score_with_endpoints_fixed() -> None:
    low = _snapshot()
    high = copy.deepcopy(low)
    original = [float(b["close_price"]) for b in low["bars"][1]["bars"]]
    noisy = original.copy()
    for index in range(len(noisy) - 20, len(noisy) - 1):
        noisy[index] *= math.exp(0.06 if index % 2 else -0.06)
    high["bars"][1] = _series("RISE", noisy)
    a = signals(low, {}, now=NOW).set_index("symbol").loc["RISE"]
    b = signals(high, {}, now=NOW).set_index("symbol").loc["RISE"]
    assert a.excess20 == pytest.approx(b.excess20)
    assert a.excess60 == pytest.approx(b.excess60)
    assert b.volatility20 > a.volatility20
    assert b.score < a.score


def test_future_earnings_time_and_non_session_bar_fail_closed() -> None:
    future = _snapshot()
    future["earnings_as_of"] = "2026-09-29T00:00:00Z"
    row = signals(future, {}, now=NOW).set_index("symbol").loc["RISE"]
    assert row.action == "WAIT_DATA"
    assert "future" in row.reason
    weekend = _snapshot()
    extra = copy.deepcopy(weekend["bars"][1]["bars"][-1])
    extra["begins_at"] = "2026-09-26T00:00:00Z"
    weekend["bars"][1]["bars"].append(extra)
    row = signals(weekend, {}, now=NOW).set_index("symbol").loc["RISE"]
    assert row.action == "WAIT_DATA"
    assert "session" in row.reason
    assert row.session_date != "2026-09-26"


def test_valid_session_date_is_calendar_anchor() -> None:
    row = signals(_snapshot(), {}, now=NOW).set_index("symbol").loc["RISE"]
    assert row.session_date == DAYS[-1].date().isoformat()
    assert row.as_of.to_pydatetime() == datetime(2026, 9, 28, 11, tzinfo=UTC)


def test_valid_entry_exclusions_watch_while_quarantine_waits_and_held_exits() -> None:
    snapshot = _snapshot()
    rise = [float(bar["close_price"]) for bar in snapshot["bars"][1]["bars"]]
    snapshot["bars"].append(_series("Q", rise))
    snapshot["universe"].append("Q")
    low = [price / 50 for price in rise]
    snapshot["bars"][1] = _series("RISE", low)
    snapshot["bars"][2]["bars"] = _series(
        "FALL", [float(bar["close_price"]) for bar in snapshot["bars"][2]["bars"]], volume=1
    )["bars"]
    snapshot["quarantined_symbols"] = ["Q"]
    rows = signals(snapshot, {"FALL": "held"}, now=NOW).set_index("symbol")
    assert (rows.at["RISE", "action"], rows.at["RISE", "reason"]) == ("WATCH", "low_price")
    assert (rows.at["Q", "action"], rows.at["Q", "reason"]) == ("WAIT_DATA", "quarantined")
    assert rows.at["FALL", "action"] == "SELL"
    assert rows.at["FALL", "reason"] == "nonpositive_exit"
    rows = signals(snapshot, {}, now=NOW).set_index("symbol")
    assert (rows.at["FALL", "action"], rows.at["FALL", "reason"]) == ("WATCH", "illiquid")


def test_zero_volume_and_unsupported_calendar_fail_closed() -> None:
    snapshot = _snapshot()
    snapshot["bars"][1]["bars"][-1]["volume"] = 0
    row = signals(snapshot, {}, now=NOW).set_index("symbol").loc["RISE"]
    assert row.action == "WAIT_DATA"
    assert math.isnan(row.score)
    old = _snapshot()
    old["captured_at"] = "2027-01-04T11:00:00Z"
    old["price_as_of"] = "2027-01-04T10:00:00Z"
    result = signals(old, {}, now=datetime(2027, 1, 4, 12, tzinfo=UTC))
    assert result.action.eq("WAIT_DATA").all()
    assert result.reason.eq("unsupported_exchange_calendar_year").all()
