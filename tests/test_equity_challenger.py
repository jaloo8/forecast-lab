"""Prospective earnings screen, with no future outcomes in selection."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from kq.equities.challenger import screen


def _series(symbol: str, *, closes: list[float] | None = None,
            volume: int = 1_000_000) -> dict[str, object]:
    days = pd.bdate_range("2026-08-28", periods=21)
    values = closes or [100 + i for i in range(21)]
    return {"symbol": symbol, "interval": "day", "bounds": "regular", "bars": [
        {"begins_at": day.strftime("%Y-%m-%dT00:00:00Z"), "open_price": str(price),
         "close_price": str(price), "high_price": str(price), "low_price": str(price),
         "volume": volume, "session": "reg"}
        for day, price in zip(days, values, strict=True)
    ]}


def _earn(symbol: str, *, actual: str | None = "1.10", verified: bool = True,
          date: str = "2026-09-24") -> dict[str, object]:
    return {"symbol": symbol, "year": 2026, "quarter": 3,
            "eps": {"estimate": "1.00", "actual": actual},
            "report": {"date": date, "verified": verified}}


def _snapshot() -> dict[str, object]:
    return {"captured_at": "2026-09-28T05:00:00Z", "benchmark": "SPY",
            "adjustment_type": "split",
            "universe": ["AAA", "BBB", "CCC"],
            "bars": [_series("SPY", closes=[100.0] * 21), _series("AAA"),
                     _series("BBB"), _series("CCC", volume=100)],
            "earnings": [_earn("AAA"), _earn("BBB", actual=None), _earn("CCC")]}


def test_screen_uses_reported_eps_and_same_universe_momentum_ablation() -> None:
    frame = screen(_snapshot()).set_index("symbol")
    assert set(frame.index) == {"AAA", "BBB", "CCC"}
    assert frame.at["AAA", "challenger_selected"] == True  # noqa: E712
    assert frame.at["BBB", "challenger_selected"] == False  # noqa: E712
    assert frame.at["BBB", "momentum_selected"] == True  # noqa: E712
    assert frame.at["BBB", "reason"] == "unreported_eps"
    assert frame.at["CCC", "reason"] == "illiquid"
    assert frame.at["CCC", "momentum_selected"] == False  # noqa: E712
    assert str(frame["as_of"].dt.tz) == "UTC"


def test_all_exclusion_reasons_remain_visible() -> None:
    snapshot = _snapshot()
    snapshot["earnings"][-1]["eps"]["actual"] = "1.01"
    frame = screen(snapshot).set_index("symbol")
    assert frame.at["CCC", "reasons"] == "illiquid;insufficient_earnings_beat"


def test_missing_history_and_future_or_unverified_reports_fail_closed() -> None:
    snapshot = _snapshot()
    snapshot["universe"] = ["AAA", "BBB", "DDD"]
    snapshot["earnings"] = [_earn("AAA", verified=False),
                            _earn("BBB", date="2026-09-28"), _earn("DDD")]
    frame = screen(snapshot).set_index("symbol")
    assert frame.at["AAA", "reason"] == "unverified_report"
    assert frame.at["BBB", "reason"] == "report_not_yet_available"
    assert frame.at["DDD", "reason"] == "missing_history"


def test_conflicting_duplicate_quarter_rejected() -> None:
    snapshot = _snapshot()
    snapshot["earnings"].append(_earn("AAA", actual="1.20"))
    with pytest.raises(ValueError, match="conflicting"):
        screen(snapshot)


def test_future_calendar_row_retained_but_prior_report_wins() -> None:
    snapshot = _snapshot()
    snapshot["universe"] = ["AAA", "BBB", "EEE"]
    snapshot["bars"].append(_series("EEE"))
    future = _earn("EEE", actual=None, date="2026-09-29")
    snapshot["earnings"].extend([future, _earn("AAA", actual=None, date="2026-09-29")])
    snapshot["earnings"][-1]["quarter"] = 4
    frame = screen(snapshot).set_index("symbol")
    assert frame.at["EEE", "reason"] == "report_not_yet_available"
    assert frame.at["AAA", "challenger_selected"] == True  # noqa: E712


def test_screen_rejects_naive_or_future_capture() -> None:
    snapshot = _snapshot()
    snapshot["captured_at"] = datetime.now(UTC).replace(tzinfo=None).isoformat()
    with pytest.raises(ValueError, match="captured_at"):
        screen(snapshot)


def test_source_time_and_synthetic_flag_types_fail_closed() -> None:
    snapshot = _snapshot()
    snapshot["earnings_as_of"] = "2026-09-29T00:00:00Z"
    with pytest.raises(ValueError, match="earnings_as_of"):
        screen(snapshot)
    snapshot.pop("earnings_as_of")
    snapshot["bars"][1]["bars"][0]["synthetic"] = 1
    with pytest.raises(ValueError, match="synthetic flag"):
        screen(snapshot)


def test_future_report_cannot_include_actual_eps() -> None:
    snapshot = _snapshot()
    snapshot["earnings"].append(_earn("EEE", date="2026-09-29"))
    with pytest.raises(ValueError, match="future earnings actual"):
        screen(snapshot)
