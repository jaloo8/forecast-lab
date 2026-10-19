"""Artificial fixtures only; these are not historical performance evidence."""

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from scripts.run_stock_family_study import choose_training

from kq.equities.stock_family_study import (
    ACTIVE_POLICIES,
    POLICIES,
    SYMBOLS,
    Prices,
    build_signals,
    prepare_prices,
    rebalance,
    simulate,
    simulate_integer_spy,
    summarize,
)


def fixture_prices(end="2006-03-31"):
    dates = pd.bdate_range("2004-01-01", end)
    closed = pd.DataFrame(100.0, index=dates, columns=SYMBOLS)
    return Prices(closed.copy(), closed)


@pytest.fixture(scope="module")
def fixture_books():
    prices = fixture_prices()
    return prices, build_signals(prices)


def test_exact_inventory_zero_vol_and_strict_equality(fixture_books):
    _, books = fixture_books
    assert len(books) == len(POLICIES) == 28
    assert len(ACTIVE_POLICIES) == 23
    assert set(books) == set(POLICIES)
    for policy in ("T01", "T04", "B01", "V01", "V02", "V03", "V04", "R03", "M04"):
        assert books[policy].loc["2006-01-02", list(SYMBOLS)].sum() == 0
    assert books["M01"].loc["2006-01-02", ["XLB", "XLE", "XLF"]].sum() == pytest.approx(0.98)
    for book in books.values():
        weights = book[list(SYMBOLS)].to_numpy(float)
        assert (weights >= 0).all()
        assert (weights.sum(axis=1) <= 0.98 + 1e-12).all()
        assert book.loc["2006-01-02":, "warmup_ready"].all()


def test_roundtrip_friction_and_reserve_oracle(fixture_books):
    prices, books = fixture_books
    daily, ledger = simulate(prices, books["C02"], 50, "2006-01-01", "2006-01-31")
    post_entry = 1000 / (1 + 0.005 * 0.98)
    final = post_entry * (0.02 + 0.98 * 0.995)
    assert daily.iloc[0].nav == pytest.approx(post_entry)
    assert daily.iloc[-1].nav == pytest.approx(final)
    assert ledger.iloc[0].cash == pytest.approx(post_entry * 0.02)
    assert list(ledger.reason) == ["initial", "terminal_prescheduled_close"]
    assert (ledger.decision_date < ledger.execution_date).all()


def test_rebalance_conservation_independent_arithmetic():
    old = np.array([3.0, 2.0, 0.0])
    prices = np.array([120.0, 80.0, 55.0])
    weights = np.array([0.1, 0.2, 0.68])
    new, cash, turnover, cost = rebalance(old, 20.0, prices, weights, 0.005)
    delta = new - old
    expected_cash = 20.0 - sum(float(d) * float(p) for d, p in zip(delta, prices, strict=True))
    expected_cost = sum(
        abs(float(d)) * float(p) * 0.005 for d, p in zip(delta, prices, strict=True)
    )
    assert cost == pytest.approx(expected_cost)
    assert cash == pytest.approx(expected_cash - expected_cost)
    assert cash >= 0
    assert turnover == pytest.approx(expected_cost / 0.005)
    assert sum(new * prices) + cash + cost == pytest.approx(sum(old * prices) + 20)


def test_future_shock_and_truncated_prefix_cannot_change_targets_or_nav(fixture_books):
    original, books = fixture_books
    changed = Prices(original.opened.copy(), original.closed.copy())
    changed.opened.loc["2006-02-16":] *= 8
    changed.closed.loc["2006-02-16":] *= 7
    shocked = build_signals(changed)
    prefix = Prices(original.opened.loc[:"2006-02-15"], original.closed.loc[:"2006-02-15"])
    prefix_books = build_signals(prefix)
    for policy in POLICIES:
        assert_frame_equal(books[policy].loc[:"2006-02-15"], shocked[policy].loc[:"2006-02-15"])
        assert_frame_equal(books[policy].loc[:"2006-02-15"], prefix_books[policy])
        before, _ = simulate(original, books[policy], 25, "2006-01-01", "2006-02-15")
        after, _ = simulate(changed, shocked[policy], 25, "2006-01-01", "2006-02-15")
        assert_frame_equal(before, after)


def test_breakout_current_close_excluded_and_next_open_execution():
    prices = fixture_prices("2006-01-05")
    prices.closed.loc["2005-12-30", "SPY"] = 110
    prices.opened.loc["2006-01-02", "SPY"] = 200
    books = build_signals(prices)
    assert books["B01"].loc["2005-12-30", "SPY"] == 0
    assert books["B01"].loc["2006-01-02", "SPY"] == 0.98
    _, ledger = simulate(prices, books["B01"], 0, "2006-01-01", "2006-01-05")
    assert ledger.iloc[0].price_SPY == 200
    assert ledger.iloc[0].units_SPY == pytest.approx(4.9)
    assert ledger.iloc[0].decision_date == pd.Timestamp("2005-12-30")


def test_midweek_fresh_account_uses_last_scheduled_weekly_target():
    prices = fixture_prices()
    prices.closed.loc["2005-12-30", ["XLP", "XLU", "XLV"]] = 80
    prices.closed.loc["2006-01-03", ["XLB", "XLE", "XLF"]] = 50
    books = build_signals(prices)
    row = books["R01"].loc["2006-01-04"]
    assert row[["XLP", "XLU", "XLV"]].sum() == pytest.approx(0.98)
    assert row.decision_date == pd.Timestamp("2005-12-30")
    assert row.as_of == pd.Timestamp("2005-12-30 21:00Z")
    _, ledger = simulate(prices, books["R01"], 25, "2006-01-04", "2006-01-06")
    assert ledger.iloc[0].decision_date == row.decision_date
    assert ledger.iloc[0].as_of == row.as_of
    assert ledger.iloc[0].units_XLP > 0
    assert ledger.iloc[0].units_XLB == 0


def test_selection_uses_exact_training_keyset_and_registered_tie_breaks():
    rows = [
        {
            "panel": "fractional",
            "window": "training",
            "cost_bps": 25,
            "policy": p,
            "worst_year": -0.1,
            "cagr": 0.05,
            "max_drawdown": -0.2,
        }
        for p in ACTIVE_POLICIES
    ]
    assert choose_training(rows)["selected_policy"] == "B01"
    rows[-1]["max_drawdown"] = -0.1
    assert choose_training(rows)["selected_policy"] == rows[-1]["policy"]
    rows[-2]["worst_year"] = 0.01
    assert choose_training(rows)["selected_policy"] == rows[-2]["policy"]
    with pytest.raises(ValueError, match="incomplete or duplicated"):
        choose_training(rows[:-1])
    with pytest.raises(ValueError, match="incomplete or duplicated"):
        choose_training(rows + rows[:1])


def test_missing_price_and_duplicate_fail_closed():
    dates = pd.bdate_range("2004-01-01", "2004-01-03")
    frame = pd.MultiIndex.from_product([dates, SYMBOLS], names=["session_date", "symbol"]).to_frame(
        index=False
    )
    frame = frame.assign(open=100.0, close=100.0)
    prepare_prices(frame)
    with pytest.raises(ValueError, match="Missing, nonfinite"):
        prepare_prices(frame.iloc[1:])
    with pytest.raises(ValueError, match="coverage"):
        prepare_prices(pd.concat([frame, frame.iloc[:1]]))


def nominal_fixture(fixture_books, price=100.0):
    prices, books = fixture_books
    raw = pd.DataFrame(
        {"Open": price, "Close": price, "Dividends": 0.0, "Stock Splits": 0.0},
        index=prices.closed.index,
    )
    return raw, books["C02"]


def test_integer_dividends_locked_prior_holders_and_no_initial_entitlement(fixture_books):
    raw, signals = nominal_fixture(fixture_books)
    raw.loc["2006-01-02", "Dividends"] = 50
    raw.loc["2006-01-03", "Dividends"] = 2
    raw.loc["2006-01-03":, ["Open", "Close"]] = 98
    daily, ledger = simulate_integer_spy(raw, signals, 0, "2006-01-01", "2006-01-03")
    assert daily.iloc[0].shares == 9
    assert daily.iloc[0].locked_receivable == 0
    assert daily.iloc[-1].locked_receivable == 18
    assert daily.iloc[-1].cash == 982
    assert daily.iloc[-1].nav == 1000
    assert ledger.iloc[0].delta == 9
    assert ledger.iloc[-1].delta == -9


def test_integer_affordability_and_exact_boundary(fixture_books):
    for price, expected in ((2000.0, 0), (98.0, 10)):
        raw, signals = nominal_fixture(fixture_books, price)
        daily, ledger = simulate_integer_spy(raw, signals, 0, "2006-01-01", "2006-01-03")
        assert ledger.iloc[0].shares == expected
        assert (daily.cash >= 0).all()
        assert daily.iloc[-1].nav == pytest.approx(1000)


def test_integer_split_and_capital_gain_rejected(fixture_books):
    raw, signals = nominal_fixture(fixture_books)
    raw.iloc[0, raw.columns.get_loc("Stock Splits")] = 2
    with pytest.raises(ValueError, match="corporate action"):
        simulate_integer_spy(raw, signals, 25, "2006-01-01", "2006-01-03")
    raw["Stock Splits"] = 0
    raw["Capital Gains"] = 1
    with pytest.raises(ValueError, match="corporate action"):
        simulate_integer_spy(raw, signals, 25, "2006-01-01", "2006-01-03")


def test_calendar_returns_include_cash_years_and_opening_drawdown():
    daily = pd.DataFrame(
        {
            "session_date": pd.to_datetime(["2006-12-29", "2007-12-31", "2008-12-31"]),
            "open_before": [1000, 800, 1000],
            "open_after": [1000, 800, 1000],
            "close_before": [1100, 1000, 1000],
            "nav": [1100, 1000, 1000],
            "cash": [10, 10, 1000],
            "cost": [0, 0, 0],
        }
    )
    result = summarize(daily)
    assert result["annual"]["2006"] == pytest.approx(0.1)
    assert result["annual"]["2007"] == pytest.approx(1000 / 1100 - 1)
    assert result["annual"]["2008"] == 0
    assert result["all_years_ge_10pct"] is False
    assert result["max_drawdown"] == pytest.approx(800 / 1100 - 1)
    assert result["close_max_drawdown"] == pytest.approx(1000 / 1100 - 1)
