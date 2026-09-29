from __future__ import annotations

import importlib
import json
from datetime import date
from typing import Any

import pandas as pd
import pytest


def _bars(count: int = 86) -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-01", periods=count)
    return pd.DataFrame(
        [
            {
                "symbol": symbol,
                "session_date": day.date(),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 1_000_000.0,
                "as_of": pd.Timestamp(day.date(), tz="America/New_York") + pd.Timedelta(hours=16),
            }
            for symbol in ("AAA", "BBB", "SPY")
            for day in dates
        ]
    )


def _run(bars: pd.DataFrame, size: int = 1, family: str = "low_volatility") -> dict[str, Any]:
    engine = importlib.import_module("kq.equities.strategy_lab.engine")
    registry = importlib.import_module("kq.equities.strategy_lab.registry")
    return engine.compare(bars, (registry.SelectionSpec(family, 10, size),))


def _cohort(report: dict[str, Any], hold: int = 5, cost: int = 10) -> dict[str, Any]:
    return next(
        row for row in report["cohorts"] if row["hold_sessions"] == hold and row["cost_bps"] == cost
    )


def _summary(report: dict[str, Any], hold: int = 5) -> dict[str, Any]:
    return next(
        row for row in report["results"] if row["hold_sessions"] == hold and row["cost_bps"] == 10
    )


def test_flat_prices_lose_entry_and_exit_costs() -> None:
    row = _cohort(_run(_bars()))
    assert row["gross_return"] == 0
    assert row["entry_cost"] == pytest.approx(0.001 / 1.001)
    assert row["exit_cost"] == pytest.approx(0.001 / 1.001)
    assert row["net_return"] == pytest.approx(-0.002 / 1.001)
    assert row["selected_symbols"] == ["AAA"]


def test_unfilled_slots_stay_cash() -> None:
    row = _cohort(_run(_bars(), size=5))
    assert row["selected_symbols"] == ["AAA", "BBB"]
    assert row["exposure"] == pytest.approx(0.4)
    assert row["net_return"] == pytest.approx(-0.0008 / 1.001)


def test_next_open_and_entry_session_is_day_one() -> None:
    bars = _bars()
    dates = sorted(bars.session_date.unique())
    bars.loc[
        (bars.symbol == "AAA") & (bars.session_date == dates[61]), ["open", "high", "low", "close"]
    ] = [110, 111, 109, 110]
    bars.loc[
        (bars.symbol == "AAA") & (bars.session_date == dates[65]), ["open", "high", "low", "close"]
    ] = [120, 122, 119, 121]
    row = _cohort(_run(bars))
    assert row["decision_date"] == dates[60].isoformat()
    assert row["entry_date"] == dates[61].isoformat()
    assert row["exit_date"] == dates[65].isoformat()
    assert row["gross_return"] == pytest.approx(0.1 / 1.001)
    assert row["net_return"] == pytest.approx((0.1 - 0.001 - 0.0011) / 1.001)


def test_missing_mature_outcome_invalidates_summary() -> None:
    bars = _bars()
    exit_date = sorted(bars.session_date.unique())[65]
    bars = bars[~((bars.symbol == "AAA") & (bars.session_date == exit_date))]
    report = _run(bars)
    assert _cohort(report)["status"] == "unavailable"
    assert _cohort(report)["net_return"] is None
    summary = _summary(report)
    assert summary["unavailable_count"] == 1
    assert summary["status"] == "incomplete"
    assert summary["mean_net_return"] is None
    assert summary["worst_cohort_return"] is None


def test_invalid_entry_bar_cannot_supply_fill() -> None:
    bars = _bars()
    entry = sorted(bars.session_date.unique())[61]
    bars.loc[(bars.symbol == "AAA") & (bars.session_date == entry), "volume"] = 0
    assert _cohort(_run(bars))["status"] == "unavailable"


def test_full_registry_has_600_rows_even_without_history() -> None:
    engine = importlib.import_module("kq.equities.strategy_lab.engine")
    report = engine.compare(_bars(20))
    assert len(report["results"]) == 600
    assert all(row["status"] == "no_outcomes" for row in report["results"])
    assert all(row["mean_net_return"] is None for row in report["results"])


def test_no_signal_is_explicit_cash_and_controls_pay_costs() -> None:
    report = _run(_bars(), family="momentum")
    row = _cohort(report)
    assert row["selected_symbols"] == []
    assert row["net_return"] == 0
    assert _summary(report)["status"] == "no_selections"
    controls = [
        row
        for row in report["controls"]
        if row["decision_date"] == _cohort(report)["decision_date"]
        and row["hold_sessions"] == 5
        and row["cost_bps"] == 10
    ]
    assert {row["control"] for row in controls} == {"cash", "spy", "eligible_universe"}
    for control in controls:
        expected = 0 if control["control"] == "cash" else -0.002 / 1.001
        assert control["net_return"] == pytest.approx(expected)


def test_future_prices_cannot_change_first_selection() -> None:
    bars = _bars()
    before = _cohort(_run(bars))
    dates = sorted(bars.session_date.unique())
    mask = (bars.symbol == "AAA") & (bars.session_date > dates[60])
    bars.loc[mask, ["open", "high", "low", "close"]] *= 0.5
    after = _cohort(_run(bars))
    assert before["selected_symbols"] == after["selected_symbols"]


def test_pending_cohort_is_visible_without_zero_outcome() -> None:
    report = _run(_bars(63))
    assert _cohort(report)["status"] == "pending"
    assert _cohort(report)["net_return"] is None
    assert _summary(report)["status"] == "no_outcomes"


def test_nonoverlapping_common_decision_grid() -> None:
    report = _run(_bars())
    dates = sorted(_bars().session_date.unique())
    actual = [
        date.fromisoformat(row["decision_date"])
        for row in report["cohorts"]
        if row["hold_sessions"] == 5 and row["cost_bps"] == 10
    ]
    assert actual == dates[60::5]


def test_regular_session_marker_is_accepted() -> None:
    bars = _bars()
    bars["session"] = "reg"
    assert _cohort(_run(bars))["net_return"] == pytest.approx(-0.002 / 1.001)


def test_late_exit_revision_cannot_supply_historical_outcome() -> None:
    bars = _bars()
    exit_date = sorted(bars.session_date.unique())[65]
    bars.loc[(bars.symbol == "AAA") & (bars.session_date == exit_date), "as_of"] = pd.Timestamp(
        "2027-01-01", tz="UTC"
    )
    assert _cohort(_run(bars))["status"] == "unavailable"


def test_excluded_symbols_are_reported_per_decision() -> None:
    report = _run(_bars(), family="momentum")
    row = next(row for row in report["exclusions"] if row["family"] == "momentum")
    assert row["symbols_by_reason"]["signal_not_positive"] == ["AAA", "BBB"]


@pytest.mark.parametrize("defect", ["missing_spy", "duplicate_spy", "stock_only_date"])
def test_invalid_benchmark_calendar_is_rejected(defect: str) -> None:
    bars = _bars()
    if defect == "missing_spy":
        bars = bars[bars.symbol != "SPY"]
    elif defect == "duplicate_spy":
        bars = pd.concat([bars, bars[bars.symbol == "SPY"].head(1)], ignore_index=True)
    else:
        extra = bars[bars.symbol == "AAA"].head(1).copy()
        extra["session_date"] = date(2026, 1, 3)
        bars = pd.concat([bars, extra], ignore_index=True)
    with pytest.raises(ValueError, match=r"benchmark|Duplicate"):
        _run(bars)


@pytest.mark.parametrize(
    "field,value",
    [("volume", 0), ("high", 50), ("close", float("nan")), ("synthetic", True), ("open", True)],
)
def test_invalid_held_session_is_unavailable(field: str, value: object) -> None:
    bars = _bars()
    day = sorted(bars.session_date.unique())[63]
    if field not in bars:
        bars[field] = False
    bars[field] = bars[field].astype(object)
    bars.loc[(bars.symbol == "AAA") & (bars.session_date == day), field] = value
    assert _cohort(_run(bars))["status"] == "unavailable"


def test_full_manifest_remains_reproducible_and_json_serializable() -> None:
    engine = importlib.import_module("kq.equities.strategy_lab.engine")
    bars = _bars(66)
    first = engine.compare(bars)
    second = engine.compare(bars.sample(frac=1, random_state=17))
    assert len(first["results"]) == 600
    assert len({row["protocol_id"] for row in first["results"]}) == 600
    assert json.dumps(first, allow_nan=False, sort_keys=True) == json.dumps(
        second, allow_nan=False, sort_keys=True
    )


def test_unavailable_benchmark_history_is_not_a_cash_signal() -> None:
    bars = _bars()
    decision = sorted(bars.session_date.unique())[60]
    bars.loc[(bars.symbol == "SPY") & (bars.session_date == decision), "volume"] = 0
    report = _run(bars)
    assert _cohort(report)["status"] == "unavailable"
    assert _cohort(report)["net_return"] is None
    assert _summary(report)["status"] == "incomplete"
    assert _summary(report)["mean_net_return"] is None
    universe = next(row for row in report["controls"] if row["control"] == "eligible_universe")
    assert universe["status"] == "unavailable"
    assert universe["net_return"] is None
