"""Synthetic point-in-time and accounting checks for long-history research."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
import pytest

from kq.equities.strategy_lab import long_study


def bars(count: int = 90, start: str = "2020-01-01") -> pd.DataFrame:
    """Return genuine-like daily OHLCV, symbol/date and simulated UTC as_of."""
    rows = []
    for symbol in ("SPY", "A", "B", "C", "D", "E", "F"):
        for day in pd.bdate_range(start, periods=count):
            rows.append(
                dict(
                    symbol=symbol,
                    session_date=day.date(),
                    open=100.0,
                    high=101.0,
                    low=99.0,
                    close=100.0,
                    volume=1_000_000,
                    as_of=day.tz_localize("America/New_York") + pd.Timedelta(hours=16),
                )
            )
    return pd.DataFrame(rows)


def cohort(
    report: dict[str, Any],
    arm: str = "M",
    size: int = 1,
    hold: int = 21,
    cost: int = 10,
    offset: int = 0,
) -> dict[str, Any]:
    return [
        row
        for row in report["cohorts"]
        if row["arm"] == arm
        and row["size"] == size
        and row["hold_sessions"] == hold
        and row["cost_bps"] == cost
    ][offset]


def test_grid_cash_budget_next_open_costs_and_matched_spy() -> None:
    frame = bars()
    dates = sorted(frame.session_date.unique())
    frame.loc[(frame.symbol == "A") & (frame.session_date == dates[61]), ["open", "high"]] = [
        125.0,
        126.0,
    ]
    report = long_study.compare_long(frame)
    assert len(report["results"]) == 189
    row = cohort(report)
    assert row["selected_symbols"] == ["A"]
    assert row["entry_date"] == dates[61].isoformat()
    assert row["exit_date"] == dates[81].isoformat()
    assert row["exposure"] == 0.1
    assert row["idle_cash_dollars"] == 90
    assert row["net_return"] == pytest.approx(0.1 * (100 / 125 * 0.999 / 1.001 - 1))
    assert row["matched_spy_return"] == pytest.approx(0.1 * (0.999 / 1.001 - 1))
    assert row["excess_vs_spy"] == pytest.approx(row["net_return"] - row["matched_spy_return"])
    assert cohort(report, size=5)["exposure"] == 0.5
    assert cohort(report, cost=50)["net_return"] < row["net_return"]
    assert cohort(report, offset=1)["status"] == "pending"


def test_shared_eligibility_blends_and_future_changes() -> None:
    frame = bars(130)
    dates = sorted(frame.session_date.unique())
    for index, symbol in enumerate("ABCDEF"):
        chosen = frame.symbol.eq(symbol)
        price = 100 * np.exp(np.arange(130) * 0.001 * index)
        frame.loc[chosen, "close"] = price
        frame.loc[chosen, "high"] = price + 100
    frame = frame[~(frame.symbol.eq("F") & frame.session_date.eq(dates[30]))]
    report = long_study.compare_long(frame)
    decision = report["decisions"][0]
    assert decision["eligible_count"] == 5
    assert decision["excluded_by_reason"]["insufficient_history"] == ["F"]
    selected = cohort(report, "MRV")["selections"][0]
    assert cohort(report, "M")["selected_symbols"] == ["E"]
    assert cohort(report, "R")["selected_symbols"] == ["A"]
    momentum = cohort(report, "M")["selections"][0]
    assert momentum["components"]["M"] == pytest.approx(55 * 0.004)
    assert momentum["components"]["R"] == pytest.approx(-5 * 0.004)
    assert momentum["components"]["V"] == pytest.approx(0, abs=1e-14)
    assert momentum["ranks"]["M"] == 1
    assert momentum["ranks"]["R"] == 0.2
    assert selected["score"] == pytest.approx(sum(selected["ranks"].values()) / 3)
    assert set(selected["components"]) == {"M", "R", "V"}
    assert pd.Timestamp(selected["as_of"]) == pd.Timestamp(
        frame.loc[
            frame.symbol.eq(selected["symbol"]) & frame.session_date.eq(dates[60]), "as_of"
        ].iloc[0]
    )
    future = frame.session_date.gt(dates[60]) & frame.symbol.ne("SPY")
    frame.loc[future, ["open", "high", "low", "close"]] *= 7
    changed = long_study.compare_long(frame)
    assert changed["decisions"][0] == decision
    assert cohort(changed, "MRV")["selections"] == cohort(report, "MRV")["selections"]


def test_missing_held_bar_makes_whole_variant_unavailable() -> None:
    frame = bars()
    date = sorted(frame.session_date.unique())[70]
    report = long_study.compare_long(frame[~(frame.symbol.eq("A") & frame.session_date.eq(date))])
    assert cohort(report)["status"] == "unavailable"
    assert cohort(report)["missing_symbols"] == ["A"]
    result = next(row for row in report["results"] if row["protocol_id"] == "M_n1_h21_c10")
    assert result["unavailable_count"] == 1
    assert result["mean_net_return"] is None


def test_ipo_enters_after_61_actual_observations_and_small_universe_stays_cash() -> None:
    frame = bars(130)
    dates = sorted(frame.session_date.unique())
    frame = frame[~(frame.symbol.isin(["E", "F"]) & frame.session_date.lt(dates[22]))]
    report = long_study.compare_long(frame)
    assert cohort(report)["selected_symbols"] == []
    assert cohort(report)["net_return"] == 0
    assert cohort(report)["matched_spy_return"] == 0
    assert cohort(report, offset=1)["selected_symbols"] == []
    assert cohort(report, offset=2)["eligible_count"] == 6
    assert cohort(report, offset=2)["selected_symbols"] == ["A"]


def test_price_and_liquidity_exclusions_are_shared_and_ties_are_averaged() -> None:
    frame = bars()
    frame.loc[frame.symbol.eq("F"), ["open", "high", "low", "close"]] /= 100
    frame.loc[frame.symbol.eq("E"), "volume"] = 1
    report = long_study.compare_long(frame)
    first = report["decisions"][0]
    assert first["excluded_by_reason"] == {"price_below_5": ["F"], "dollar_volume_below_20m": ["E"]}
    assert first["eligible_count"] == 4
    assert first["scores"][0]["ranks"] == {"M": 0.625, "R": 0.625, "V": 0.625}
    assert all(cohort(report, arm)["selected_symbols"] == [] for arm in long_study.ARMS)


def test_nonoverlap_and_json_serialization() -> None:
    report = long_study.compare_long(bars(190))
    json.dumps(report, allow_nan=False)
    for hold in long_study.HOLDS:
        first = cohort(report, hold=hold)
        second = cohort(report, hold=hold, offset=1)
        assert first["exit_date"] == second["decision_date"]
        assert second["entry_date"] > first["exit_date"]


def test_epoch_excludes_cross_boundary_outcomes_but_keeps_overall() -> None:
    report = long_study.compare_long(bars(90, "2019-09-02"))
    row = next(row for row in report["results"] if row["protocol_id"] == "M_n1_h21_c10")
    assert row["cohort_count"] == 1
    assert row["epochs"]["2013-2019"]["cohort_count"] == 1
    crossed = long_study.compare_long(bars(90, "2019-09-20"))
    row = next(row for row in crossed["results"] if row["protocol_id"] == "M_n1_h21_c10")
    assert row["cohort_count"] == 1
    assert row["epochs"]["2013-2019"]["cohort_count"] == 0


@pytest.mark.parametrize("defect", ["duplicate", "invalid", "future_as_of"])
def test_invalid_observations_fail_closed(defect: str) -> None:
    frame = bars()
    if defect == "duplicate":
        frame = pd.concat([frame, frame.iloc[[0]]])
    elif defect == "invalid":
        frame.loc[0, "close"] = -1
    else:
        frame.loc[0, "as_of"] += pd.Timedelta(days=1)
    with pytest.raises(ValueError):
        long_study.compare_long(frame)
