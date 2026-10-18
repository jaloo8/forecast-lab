"""Immutable forward decisions and matched benchmark evaluation."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from kq.equities.forward_study import METHOD_HASH, PROTOCOL, evaluate, write_decision


def _series(symbol: str, days: pd.DatetimeIndex, *, close: float) -> dict[str, object]:
    return {
        "symbol": symbol,
        "interval": "day",
        "bounds": "regular",
        "bars": [
            {
                "begins_at": day.strftime("%Y-%m-%dT00:00:00Z"),
                "open_price": "100",
                "close_price": str(close),
                "high_price": str(max(100, close)),
                "low_price": str(min(100, close)),
                "volume": 1_000_000,
                "session": "reg",
            }
            for day in days
        ],
    }


def _decision() -> dict[str, object]:
    anchors = {
        symbol: [
            {
                "session_date": day.date().isoformat(),
                "open": 100.0,
                "close": close,
                "volume": 1_000_000.0,
            }
            for day in pd.bdate_range("2026-07-06", periods=21)
        ]
        for symbol, close in (("SPY", 100.0), ("AAA", 80.0))
    }
    return {
        "created_at": "2026-08-03T22:00:00Z",
        "input_captured_at": "2026-08-03T21:00:00Z",
        "method_hash": METHOD_HASH,
        "protocol": PROTOCOL,
        "anchors": anchors,
        "selected": {"challenger": ["AAA"], "momentum": ["AAA"]},
    }


def _future(days: pd.DatetimeIndex, *, stock_close: float = 80) -> dict[str, object]:
    all_days = pd.bdate_range("2026-07-06", periods=21).append(days)
    observed = (days[-1].date() + timedelta(days=1)).isoformat() + "T05:00:00Z"
    return {
        "captured_at": observed,
        "benchmark": "SPY",
        "adjustment_type": "split",
        "bars": [_series("SPY", all_days, close=100), _series("AAA", all_days, close=stock_close)],
    }


def test_losing_challenger_uses_next_open_and_matched_spy() -> None:
    days = pd.bdate_range("2026-08-04", periods=20)
    frame = evaluate(_decision(), _future(days))
    assert set(frame["lane"]) == {"challenger", "momentum"}
    row = frame.iloc[0]
    assert row["status"] == "mature"
    assert row["entry_date"] == days[0].date().isoformat()
    assert row["exit_date"] == days[19].date().isoformat()
    assert row["net_return"] < 0
    assert row["excess_vs_spy"] < 0
    assert str(frame["as_of"].dt.tz) == "UTC"


def test_pending_and_missing_interior_session() -> None:
    days = pd.bdate_range("2026-08-04", periods=20)
    assert set(evaluate(_decision(), _future(days[:19]))["status"]) == {"pending"}
    future = _future(days)
    future["bars"][1]["bars"].pop(26)
    assert set(evaluate(_decision(), future)["status"]) == {"invalid_missing_session"}


def test_missing_stock_session_invalid_before_maturity() -> None:
    days = pd.bdate_range("2026-08-04", periods=3)
    future = _future(days)
    future["bars"][1]["bars"].pop(22)
    assert set(evaluate(_decision(), future)["status"]) == {"invalid_missing_session"}


def test_missing_benchmark_weekday_is_calendar_unverified() -> None:
    days = pd.bdate_range("2026-08-04", periods=21).delete(7)
    assert set(evaluate(_decision(), _future(days))["status"]) == {"unverified_calendar"}


def test_pending_gap_is_calendar_unverified_before_maturity() -> None:
    days = pd.bdate_range("2026-08-05", periods=3)
    assert set(evaluate(_decision(), _future(days))["status"]) == {"unverified_calendar"}


def test_previous_capture_detects_revised_future_bar() -> None:
    days = pd.bdate_range("2026-08-04", periods=20)
    prior = _future(days)
    revised = deepcopy(prior)
    revised["bars"][1]["bars"][21]["close_price"] = "90"
    assert set(evaluate(_decision(), revised, previous_snapshot=prior)["status"]) == {
        "invalid_revision"
    }


def test_future_or_modified_decision_and_unadjusted_bars_rejected() -> None:
    days = pd.bdate_range("2026-08-04", periods=20)
    decision = _decision()
    future = _future(days)
    decision["created_at"] = "2099-01-01T00:00:00Z"
    with pytest.raises(ValueError, match="chronology"):
        evaluate(decision, future)
    decision = _decision()
    decision["protocol"] = {"name": "different"}
    with pytest.raises(ValueError, match="protocol"):
        evaluate(decision, future)
    decision = _decision()
    future["adjustment_type"] = "none"
    with pytest.raises(ValueError, match="adjustment_type"):
        evaluate(decision, future)


def test_write_once_decision_has_real_time_and_hashes(tmp_path: Path) -> None:
    days = pd.bdate_range("2026-08-28", periods=21)
    source = {
        "captured_at": "2026-09-28T05:00:00Z",
        "benchmark": "SPY",
        "adjustment_type": "split",
        "universe": [],
        "earnings": [],
        "bars": [_series("SPY", days, close=100)],
    }
    target = tmp_path / "decision.json"
    artifact = write_decision(source, target)
    assert artifact["created_at"] >= source["captured_at"]
    assert artifact["input_hash"] and artifact["method_hash"]
    assert artifact["selected"] == {"challenger": [], "momentum": []}
    assert json.loads(target.read_text()) == artifact
    with pytest.raises(FileExistsError):
        write_decision(source, target)
    assert datetime.fromisoformat(artifact["created_at"]).tzinfo == UTC


def test_decision_rejects_future_capture(tmp_path: Path) -> None:
    days = pd.bdate_range("2026-08-28", periods=21)
    source = {
        "captured_at": "2099-01-01T00:00:00Z",
        "benchmark": "SPY",
        "adjustment_type": "split",
        "universe": [],
        "earnings": [],
        "bars": [_series("SPY", days, close=100)],
    }
    with pytest.raises(ValueError, match="future"):
        write_decision(source, tmp_path / "decision.json")


def test_initial_input_is_pending_and_revised_anchor_invalid(tmp_path: Path) -> None:
    days = pd.bdate_range("2026-08-28", periods=21)
    stock = _series("AAA", days, close=100)
    for index, bar in enumerate(stock["bars"]):
        bar["close_price"] = str(100 + index)
        bar["high_price"] = str(100 + index)
    source = {
        "captured_at": "2026-09-28T05:00:00Z",
        "benchmark": "SPY",
        "adjustment_type": "split",
        "universe": ["AAA"],
        "earnings": [
            {
                "symbol": "AAA",
                "year": 2026,
                "quarter": 3,
                "eps": {"estimate": "1.0", "actual": "1.1"},
                "report": {"date": "2026-09-24", "verified": True},
            }
        ],
        "bars": [_series("SPY", days, close=100), stock],
    }
    decision = write_decision(source, tmp_path / "decision.json")
    assert set(evaluate(decision, source)["status"]) == {"pending"}
    revised = deepcopy(source)
    revised["captured_at"] = datetime.now(UTC).isoformat()
    revised["bars"][1]["bars"][-1]["close_price"] = "119"
    assert set(evaluate(decision, revised)["status"]) == {"invalid_anchor"}
