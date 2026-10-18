"""Frozen adaptive signal arithmetic and evidence boundaries."""

from __future__ import annotations

import copy
import math
import statistics
from datetime import UTC, datetime

import pandas as pd
import pytest

from kq.equities.adaptive import METHOD_HASH, signals

NOW = datetime(2026, 9, 28, 12, tzinfo=UTC)
DAYS = [
    d
    for d in pd.bdate_range("2026-06-29", "2026-09-25")
    if d.strftime("%Y-%m-%d") not in {"2026-07-03", "2026-09-07"}
]


def _series(symbol: str, closes: list[float], volume: int = 1_000_000) -> dict[str, object]:
    return {
        "symbol": symbol,
        "interval": "day",
        "bounds": "regular",
        "bars": [
            {
                "begins_at": day.strftime("%Y-%m-%dT00:00:00Z"),
                "open_price": str(price),
                "close_price": str(price),
                "high_price": str(price),
                "low_price": str(price),
                "volume": volume,
                "session": "reg",
            }
            for day, price in zip(DAYS, closes, strict=True)
        ],
    }


def _snapshot() -> dict[str, object]:
    assert len(DAYS) >= 61
    base = [100.0] * len(DAYS)
    rise = [100 * math.exp(i * 0.009 + (0.012 if i % 2 else 0)) for i in range(len(DAYS))]
    fall = list(reversed(rise))
    return {
        "captured_at": "2026-09-28T11:00:00Z",
        "price_as_of": "2026-09-28T10:00:00Z",
        "benchmark": "SPY",
        "adjustment_type": "split",
        "universe": ["RISE", "FALL", "FLAT"],
        "bars": [
            _series("SPY", base),
            _series("RISE", rise),
            _series("FALL", fall),
            _series("FLAT", base),
        ],
    }


def test_hand_reference_and_position_band() -> None:
    snapshot = _snapshot()
    snapshot["universe"] = ["RISE", "FALL"]
    frame = signals(snapshot, {"RISE": "flat", "FALL": "held", "FLAT": "held"}, now=NOW)
    rows = frame.set_index("symbol")
    closes = [float(bar["close_price"]) for bar in snapshot["bars"][1]["bars"]]
    returns = [math.log(b / a) for a, b in zip(closes[-21:-1], closes[-20:], strict=True)]
    vol = statistics.stdev(returns)
    e20 = math.log(closes[-1] / closes[-21])
    e60 = math.log(closes[-1] / closes[-61])
    expected = 0.5 * (e20 / (vol * math.sqrt(20)) + e60 / (vol * math.sqrt(60)))
    assert rows.at["RISE", "score"] == pytest.approx(expected)
    assert rows.at["RISE", "excess20"] == pytest.approx(e20)
    assert rows.at["RISE", "volatility20"] == pytest.approx(vol)
    assert rows.at["RISE", "action"] == "BUY"
    assert rows.at["FALL", "action"] == "SELL"
    assert rows.at["FLAT", "action"] == "WAIT_DATA"
    assert rows.at["FLAT", "candidate_eligible"] == False  # noqa: E712
    assert frame["as_of"].dt.tz is not None
    assert frame.at[0, "session_date"] == "2026-09-25"
    assert frame["method_hash"].eq(METHOD_HASH).all()


def test_entry_filters_do_not_hide_held_exit_and_pending_is_idempotent() -> None:
    snapshot = _snapshot()
    snapshot["universe"] = ["RISE", "FALL"]
    snapshot["bars"][2] = _series(
        "FALL", [float(b["close_price"]) for b in snapshot["bars"][2]["bars"]], volume=1
    )
    rows = signals(snapshot, {"FALL": "held", "RISE": "pending_entry"}, now=NOW).set_index("symbol")
    assert rows.at["FALL", "action"] == "SELL"
    assert rows.at["FALL", "candidate_eligible"] == False  # noqa: E712
    assert rows.at["RISE", "action"] == "PENDING"
    assert rows.at["RISE", "score"] > 0.5


def test_missing_session_and_invalid_evidence_fail_closed() -> None:
    snapshot = _snapshot()
    snapshot["bars"][1]["bars"].pop(-8)
    row = signals(snapshot, {"RISE": "flat"}, now=NOW).set_index("symbol").loc["RISE"]
    assert row.action == "WAIT_DATA"
    assert math.isnan(row.score)
    assert "session" in row.reason
    stale = _snapshot()
    assert signals(stale, {}, now=datetime(2026, 9, 30, tzinfo=UTC)).action.eq("WAIT_DATA").all()
    future = _snapshot()
    future["price_as_of"] = "2026-09-29T00:00:00Z"
    assert signals(future, {}, now=NOW).action.eq("WAIT_DATA").all()


def test_unverified_weekday_gap_vs_verified_holiday_and_flags() -> None:
    snapshot = _snapshot()
    assert signals(snapshot, {}, now=NOW).set_index("symbol").at["RISE", "action"] == "BUY"
    missing = copy.deepcopy(snapshot)
    for series in missing["bars"]:
        series["bars"] = [b for b in series["bars"] if not b["begins_at"].startswith("2026-09-24")]
    assert signals(missing, {}, now=NOW).action.eq("WAIT_DATA").all()
    malformed = _snapshot()
    malformed["bars"][1]["bars"][-1]["synthetic"] = "false"
    with pytest.raises(ValueError, match="synthetic flag"):
        signals(malformed, {}, now=NOW)
    synthetic = _snapshot()
    synthetic["bars"][1]["bars"][-1]["synthetic"] = True
    assert signals(synthetic, {}, now=NOW).set_index("symbol").at["RISE", "action"] == "WAIT_DATA"


def test_invalid_now_and_states_rejected() -> None:
    with pytest.raises(ValueError, match="aware"):
        signals(_snapshot(), {}, now=datetime(2026, 9, 28))
    with pytest.raises(ValueError, match="state"):
        signals(_snapshot(), {"RISE": "short"}, now=NOW)


def test_watch_hold_and_quarantine_keep_score_visible() -> None:
    snapshot = _snapshot()
    prices = [100 * math.exp(i * 0.001 + (0.02 if i % 2 else 0)) for i in range(len(DAYS))]
    snapshot["bars"].append(_series("MILD", prices))
    snapshot["universe"].append("MILD")
    snapshot["quarantined_symbols"] = ["RISE"]
    rows = signals(snapshot, {"MILD": "held"}, now=NOW).set_index("symbol")
    assert 0 < rows.at["MILD", "score"] < 0.5
    assert rows.at["MILD", "action"] == "HOLD"
    assert rows.at["RISE", "action"] == "WAIT_DATA"
    assert rows.at["RISE", "score"] > 0.5
    assert rows.at["RISE", "reason"] == "quarantined"
    rows = signals(snapshot, {}, now=NOW).set_index("symbol")
    assert rows.at["MILD", "action"] == "WATCH"
