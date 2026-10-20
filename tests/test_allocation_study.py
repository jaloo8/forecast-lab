"""Artificial allocation/accounting fixtures, not historical performance."""

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from kq.equities import stock_family_study as old
from kq.equities.allocation_study import (
    INSURANCE_POLICIES,
    SYMBOLS,
    Prices,
    as_of,
    insurance_target,
    simulate,
    summarize,
    validate_prices,
)


def prices_fixture(symbols=SYMBOLS, end="2020-01-10"):
    dates = pd.bdate_range("2019-12-30", end)
    frame = pd.DataFrame(100.0, index=dates, columns=symbols)
    return Prices(frame.copy(), frame.copy())


def static_signals(prices, weights=None, every_day=False):
    dates = prices.closed.index
    symbols = list(prices.closed.columns)
    frame = pd.DataFrame(0.0, index=dates, columns=symbols)
    frame.iloc[1:] = np.ones(len(symbols)) / len(symbols) if weights is None else np.array(weights)
    frame["rebalance"] = every_day
    frame["warmup_ready"] = True
    frame.iloc[0, frame.columns.get_loc("warmup_ready")] = False
    frame["decision_date"] = pd.Series(dates, index=dates).shift(1)
    frame["as_of"] = frame.decision_date.map(
        lambda value: as_of(value) if pd.notna(value) else pd.NaT
    )
    return frame


def test_static_round_trip_matches_analytic_cost_and_reserve():
    prices = prices_fixture()
    signals = static_signals(prices, [1, 0, 0, 0, 0, 0])
    daily, ledger = simulate(prices, signals, "C03", 50, "2020-01-01", "2020-01-10")
    after_entry = 1000 / (1 + 0.98 * 0.005)
    expected = after_entry * (0.02 + 0.98 * (1 - 0.005))
    assert daily.iloc[-1].nav == pytest.approx(expected)
    assert ledger.iloc[0].cash == pytest.approx(after_entry * 0.02)
    assert list(ledger.reason) == ["initial", "terminal_prescheduled_close"]
    assert ledger.iloc[0].weight_SPY == 0.98


@pytest.mark.parametrize("policy", INSURANCE_POLICIES)
def test_insurance_initial_floor_weights_and_funded_cash(policy):
    prices = prices_fixture()
    daily, ledger = simulate(prices, None, policy, 25, "2020-01-01", "2020-01-03")
    first = ledger.iloc[0]
    assert first.reference_nav == first.reference_peak == 1000
    assert first.floor == 800
    assert first.risky_fraction == pytest.approx(0.6)
    assert first.weight_BIL == pytest.approx(0.4 * 0.98)
    assert sum(first[f"weight_{s}"] for s in SYMBOLS[:-1]) == pytest.approx(0.6 * 0.98)
    if policy in {"I02", "I04"}:
        assert all(first[f"weight_{s}"] == pytest.approx(0.6 * 0.98 / 5) for s in SYMBOLS[:-1])
    else:
        assert first.weight_SPY == pytest.approx(0.6 * 0.98)
    assert (daily.cash >= 0).all()
    assert daily.cost.sum() == pytest.approx(ledger.cost.sum())


def test_insurance_reference_is_previous_actual_costed_close_not_current_open():
    prices = prices_fixture()
    prices.closed.loc["2020-01-01", "SPY"] = 125
    prices.opened.loc["2020-01-02", "SPY"] = 190
    low, low_ledger = simulate(prices, None, "I01", 10, "2020-01-01", "2020-01-03")
    high, high_ledger = simulate(prices, None, "I01", 50, "2020-01-01", "2020-01-03")
    second = low_ledger.iloc[1]
    assert second.reference_nav == pytest.approx(low.iloc[0].nav)
    assert second.reference_nav != pytest.approx(second.pre_nav)
    assert second.risky_fraction == pytest.approx(3 * (low.iloc[0].nav - 800) / low.iloc[0].nav)
    assert high_ledger.iloc[1].reference_nav == pytest.approx(high.iloc[0].nav)
    assert high_ledger.iloc[1].risky_fraction < second.risky_fraction
    changed = Prices(prices.opened.copy(), prices.closed.copy())
    changed.opened.loc["2020-01-02", "SPY"] = 400
    _, changed_ledger = simulate(changed, None, "I01", 10, "2020-01-01", "2020-01-03")
    assert changed_ledger.iloc[1].risky_fraction == second.risky_fraction


def test_insurance_ratcheting_uses_closing_peak_and_fresh_accounts_reset():
    prices = prices_fixture()
    prices.closed.loc["2020-01-01", "SPY"] = 160
    prices.opened.loc["2020-01-02", "SPY"] = 300
    _, constant = simulate(prices, None, "I01", 25, "2020-01-01", "2020-01-03")
    daily, ratchet = simulate(prices, None, "I03", 25, "2020-01-01", "2020-01-03")
    assert constant.iloc[1].floor == 800
    assert ratchet.iloc[1].floor == pytest.approx(0.8 * daily.iloc[0].nav)
    assert ratchet.iloc[1].reference_peak == pytest.approx(daily.iloc[0].nav)
    assert ratchet.iloc[1].floor < 0.8 * ratchet.iloc[1].pre_nav
    _, fresh = simulate(prices, None, "I03", 25, "2020-01-02", "2020-01-03")
    assert fresh.iloc[0].reference_nav == 1000
    assert fresh.iloc[0].floor == 800
    assert fresh.iloc[0].risky_fraction == pytest.approx(0.6)


def test_insurance_state_does_not_reset_at_calendar_year_boundary():
    prices = prices_fixture()
    prices.closed.loc["2019-12-31", "SPY"] = 160
    daily, ledger = simulate(prices, {}, "I03", 25, "2019-12-31", "2020-01-03")
    assert ledger.iloc[1].reference_nav == pytest.approx(daily.iloc[0].nav)
    assert ledger.iloc[1].reference_peak > 1000
    assert ledger.iloc[1].floor > 800
    assert ledger.iloc[1].decision_date == pd.Timestamp("2019-12-31")


def test_gap_can_breach_floor_and_next_exposure_falls_to_zero():
    prices = prices_fixture()
    prices.opened.loc["2020-01-02":, "SPY"] = 10
    prices.closed.loc["2020-01-02":, "SPY"] = 10
    daily, ledger = simulate(prices, None, "I01", 25, "2020-01-01", "2020-01-06")
    assert daily.iloc[1].open_before < 800
    assert daily.iloc[1].floor_breached_open_before
    assert ledger.iloc[1].risky_fraction > 0
    assert ledger.iloc[2].risky_fraction == 0
    assert ledger.iloc[2].weight_BIL == 0.98
    assert ledger.iloc[2].weight_SPY == 0
    assert daily.iloc[-1].nav < 800
    assert (daily.cash >= 0).all()


def test_insurance_clip_zero_and_full_risk():
    weights, floor, exposure = insurance_target("I01", 700, 1000)
    assert exposure == 0
    assert weights[-1] == 1
    assert floor == 800
    weights, _, exposure = insurance_target("I02", 1600, 1600)
    assert exposure == 1
    assert np.array_equal(weights, [0.2, 0.2, 0.2, 0.2, 0.2, 0])
    with pytest.raises(ValueError, match="reference"):
        insurance_target("I01", 2000, 1000)


@pytest.mark.parametrize("policy", INSURANCE_POLICIES)
def test_future_price_shocks_do_not_change_prior_insurance_account(policy):
    prices = prices_fixture()
    changed = Prices(prices.opened.copy(), prices.closed.copy())
    changed.opened.loc["2020-01-07":] *= 7
    changed.closed.loc["2020-01-07":] *= 9
    before, trades_before = simulate(prices, None, policy, 25, "2020-01-01", "2020-01-06")
    after, trades_after = simulate(changed, None, policy, 25, "2020-01-01", "2020-01-06")
    assert_frame_equal(before, after)
    assert_frame_equal(trades_before, trades_after)


def test_generic_static_accounting_equals_frozen_eleven_asset_engine():
    prices = prices_fixture(old.SYMBOLS)
    prices.opened.loc["2020-01-03", "SPY"] = 110
    prices.closed.loc["2020-01-03", "QQQ"] = 115
    signals = static_signals(prices, every_day=True)
    old_signals = signals.copy()
    old_signals[list(old.SYMBOLS)] *= 0.98
    before, old_ledger = old.simulate(
        old.Prices(prices.opened, prices.closed), old_signals, 25, "2020-01-01", "2020-01-06"
    )
    after, new_ledger = simulate(prices, signals, "C04", 25, "2020-01-01", "2020-01-06")
    assert_frame_equal(before, after[list(before)])
    assert_frame_equal(old_ledger, new_ledger[list(old_ledger)])


def test_static_buy_hold_does_not_rebalance_even_with_schedule_flags():
    prices = prices_fixture()
    signals = static_signals(prices, every_day=True)
    for policy in ("C02", "C03"):
        _, ledger = simulate(prices, {policy: signals}, policy, 25, "2020-01-01", "2020-01-06")
        assert list(ledger.reason) == ["initial", "terminal_prescheduled_close"]


def test_static_noncausal_and_unfunded_targets_fail_closed():
    prices = prices_fixture()
    signals = static_signals(prices)
    signals.loc["2020-01-01", "decision_date"] = pd.Timestamp("2020-01-01")
    with pytest.raises(ValueError, match="Noncausal"):
        simulate(prices, signals, "C04", 25, "2020-01-01", "2020-01-06")
    signals = static_signals(prices)
    signals.loc["2020-01-01", "SPY"] = 2
    with pytest.raises(ValueError, match="unscaled"):
        simulate(prices, signals, "C04", 25, "2020-01-01", "2020-01-06")
    signals = static_signals(prices)
    signals.loc["2020-01-01", "warmup_ready"] = False
    with pytest.raises(ValueError, match="warmup"):
        simulate(prices, signals, "C04", 25, "2020-01-01", "2020-01-06")


def test_missing_prices_and_symbol_order_fail_closed():
    prices = prices_fixture()
    bad = Prices(prices.opened.iloc[1:], prices.closed)
    with pytest.raises(ValueError, match="misaligned"):
        validate_prices(bad)
    prices.opened.iloc[1, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        validate_prices(prices)
    prices = prices_fixture(tuple(reversed(SYMBOLS)))
    with pytest.raises(ValueError, match="order"):
        simulate(prices, None, "I01", 25, "2020-01-01", "2020-01-06")


def test_cash_and_zero_year_remain_in_summary():
    prices = prices_fixture(end="2020-12-31")
    signals = static_signals(prices, np.zeros(len(SYMBOLS)))
    daily, ledger = simulate(prices, signals, "C01", 50, "2020-01-01", "2020-12-31")
    result = summarize(daily)
    assert result["annual"] == {"2020": 0.0}
    assert result["all_years_ge_10pct"] is False
    assert result["ending_nav"] == pytest.approx(1000)
    assert ledger.cost.sum() == 0
