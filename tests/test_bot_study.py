"""Artificial causal/accounting checks; not evidence of trading profitability."""

import numpy as np
import pandas as pd
import pytest

from kq.equities.bot_study import (
    COLUMNS,
    RULES,
    adjusted_prices,
    annual_returns,
    build_signals,
    metrics,
    simulate,
)


def fixture_prices(length=600):
    rng = np.random.default_rng(21)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.018, length)))
    o = c * np.exp(rng.normal(0, 0.007, length))
    return pd.DataFrame(
        {
            "Open": o,
            "High": np.maximum(o, c) * 1.01,
            "Low": np.minimum(o, c) * 0.99,
            "Close": c,
            "Adj Close": c * 0.8,
            "Volume": rng.integers(100, 2000, length),
        },
        index=pd.bdate_range("2000-01-03", periods=length),
    )


@pytest.mark.parametrize("prefix", [252, 300, 450])
def test_future_data_never_changes_signals(prefix):
    prices = adjusted_prices(fixture_prices())
    whole = build_signals(prices)
    short = build_signals(prices.iloc[:prefix])
    pd.testing.assert_frame_equal(whole.iloc[:prefix], short)
    assert not whole.iloc[:251][list(RULES)].to_numpy().any()


def test_self_financed_entry_and_costed_terminal():
    result = simulate(
        np.array([100.0, 110.0]), np.array([105.0, 120.0]), np.array([True, True]), 10
    )
    frame = pd.DataFrame(result.values, columns=COLUMNS)
    notional = 980 / 1.001
    units = notional / 100
    assert frame.iloc[0].cash_open == pytest.approx(20)
    assert frame.iloc[0].units_open == pytest.approx(units)
    assert frame.iloc[-1].cash_close == pytest.approx(20 + units * 120 * 0.999)
    assert frame.iloc[-1].units_close == 0
    assert frame.iloc[1].notional_open == 0
    assert frame.iloc[-1].notional_close == pytest.approx(-120 * units)


def test_exit_open_and_terminal_cannot_double_sell():
    result = simulate(
        np.array([100.0, 110.0]), np.array([100.0, 110.0]), np.array([True, False]), 25
    )
    assert result.values[-1, 9] == 0
    assert result.values[-1, 6] == 0
    assert result.values[-1, 7] < 0


def test_gap_loss_and_cost_marks_count_in_drawdown():
    dates = pd.bdate_range("2000-01-03", periods=3)
    result = simulate(
        np.array([100.0, 40.0, 80.0]),
        np.array([100.0, 80.0, 80.0]),
        np.array([True, True, False]),
        10,
    )
    summary = metrics(dates, result)
    assert summary["drawdown"] < -0.58
    assert summary["trades"] == 2
    assert summary["ending_cash"] == result.values[-1, 5]


def test_zero_trade_period_retained():
    dates = pd.bdate_range("2000-01-03", periods=3)
    result = simulate(
        np.array([100.0, 40.0, 80.0]), np.array([100.0, 80.0, 80.0]), np.array([False] * 3), 50
    )
    summary = metrics(dates, result)
    assert summary["return"] == summary["cagr"] == summary["drawdown"] == summary["trades"] == 0


def test_dust_skip_and_terminal_sweep():
    result = simulate(
        np.array([100.0, 0.00001]), np.array([100.0, 0.00001]), np.array([True, False]), 10
    )
    assert result.skipped_tickets == 1
    assert result.values[-1, 7] == 0
    assert result.values[-1, 9] < 0
    assert result.values[-1, 6] == 0


def test_annual_cash_account_linkage():
    dates = pd.to_datetime(["2020-01-02", "2020-12-31", "2021-01-04", "2021-12-31"])
    result = simulate(
        np.array([100.0, 110.0, 110.0, 121.0]),
        np.array([100.0, 110.0, 110.0, 121.0]),
        np.array([True] * 4),
        10,
    )
    years = annual_returns(dates, result, dates)
    assert all(x["complete_calendar_year"] for x in years)
    assert (1 + years[0]["return"]) * (1 + years[1]["return"]) == pytest.approx(
        result.values[-1, 4] / 1000
    )


def test_terminal_fee_drawdown_includes_new_peak_before_liquidation():
    dates = pd.to_datetime(["2020-01-02"])
    result = simulate(np.array([100.0]), np.array([200.0]), np.array([True]), 50)
    pre, post = result.values[-1, 11], result.values[-1, 4]
    assert metrics(dates, result)["drawdown"] == pytest.approx(post / pre - 1)


def test_partial_january_is_not_complete_year():
    dates = pd.to_datetime(["2020-01-03", "2020-12-31"])
    calendar = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-12-31"])
    result = simulate(
        np.array([100.0, 100.0]), np.array([100.0, 100.0]), np.array([False, False]), 10
    )
    assert not annual_returns(dates, result, calendar)[0]["complete_calendar_year"]


@pytest.mark.parametrize("problem", ["nan", "negative", "infinity", "duplicate", "high", "volume"])
def test_bad_prices_refused(problem):
    frame = fixture_prices(10)
    if problem == "duplicate":
        frame.index = pd.DatetimeIndex([frame.index[0]] * 10)
    elif problem == "high":
        frame.loc[frame.index[0], "High"] = 1
    elif problem == "volume":
        frame.loc[frame.index[0], "Volume"] = -1
    else:
        frame.loc[frame.index[0], "Close"] = {"nan": np.nan, "negative": -1, "infinity": np.inf}[
            problem
        ]
    with pytest.raises(ValueError):
        adjusted_prices(frame)


@pytest.mark.parametrize("cost", [0, -10, 1, 100])
def test_unregistered_cost_refused(cost):
    with pytest.raises(ValueError):
        simulate(np.array([100.0]), np.array([100.0]), np.array([True]), cost)


def test_unregistered_initial_balance_refused():
    with pytest.raises(ValueError):
        simulate(np.array([100.0]), np.array([100.0]), np.array([True]), 10, initial=100.0)


def test_signal_flat_range_does_not_generate_spurious_entry():
    prices = fixture_prices(300)
    for col in ["Open", "High", "Low", "Close", "Adj Close"]:
        prices[col] = 100.0
    signals = build_signals(adjusted_prices(prices))
    assert not signals[list(RULES[1:])].to_numpy().any()
