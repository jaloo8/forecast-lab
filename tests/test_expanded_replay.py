"""Independent arithmetic and causality checks for the research-only replay."""

import numpy as np
import pandas as pd
import pytest

from kq.equities.expanded_replay import monthly_targets, replay_path, require_sessions


def test_flat_round_trip_charges_both_sides_and_preserves_cash():
    dates = pd.bdate_range("2020-01-01", periods=4)
    prices = np.full((4, 1), 100.0)
    daily = replay_path(dates, prices, prices, {0: np.array([0.98])}, 10)
    invested = 1000 * 0.98 / 1.00098
    assert daily.nav.iloc[-1] == pytest.approx(1000 - 2 * invested * 0.001)
    assert daily.cash.min() >= 0
    assert daily.cost.sum() == pytest.approx(2 * invested * 0.001)


def test_next_open_gap_is_not_a_free_profit():
    dates = pd.bdate_range("2020-01-01", periods=3)
    prices = np.array([[100.0], [200.0], [220.0]])
    daily = replay_path(dates, prices, prices, {1: np.array([1.0])}, 0)
    assert daily.nav.iloc[-1] == pytest.approx(1100)
    assert daily.nav.iloc[0] == 1000


def test_missing_held_price_blocks_path_but_missing_unheld_price_does_not():
    dates = pd.bdate_range("2020-01-01", periods=3)
    prices = np.array([[100.0, np.nan], [110.0, np.nan], [120.0, np.nan]])
    assert replay_path(dates, prices, prices, {0: np.array([1.0, 0.0])}, 0).nav.iloc[
        -1
    ] == pytest.approx(1200)
    prices[1, 0] = np.nan
    with pytest.raises(ValueError, match="held"):
        replay_path(dates, prices, prices, {0: np.array([1.0, 0.0])}, 0)


def test_switching_assets_deducts_sale_and_purchase_cost():
    dates = pd.bdate_range("2020-01-01", periods=2)
    prices = np.full((2, 2), 100.0)
    daily = replay_path(
        dates, prices, prices, {0: np.array([1.0, 0.0]), 1: np.array([0.0, 1.0])}, 100
    )
    assert daily.nav.iloc[-1] == pytest.approx(1000 * (0.99 / 1.01) ** 2)


def test_future_prices_do_not_change_earlier_signals():
    dates = pd.bdate_range("2010-01-01", periods=450)
    columns = ["A", "B", "C", "D", "E", "F", "SPY"]
    rng = np.random.default_rng(51)
    close = pd.DataFrame(
        100 * np.exp(np.cumsum(rng.normal(0.001, 0.01, (450, 7)), axis=0)),
        index=dates,
        columns=columns,
    )
    volume = close * 0 + 1_000_000
    original = monthly_targets(close, close, volume)
    changed = close.copy()
    changed.iloc[350:] *= 10
    modified = monthly_targets(changed, changed, volume)
    for arm in original:
        assert original[arm]
        for i, weights in original[arm].items():
            if i < 350:
                np.testing.assert_array_equal(weights, modified[arm][i])
            assert dates[i - 1].month != dates[i].month
            assert weights.sum() <= 0.98000001


def test_insufficient_history_remains_cash():
    dates = pd.bdate_range("2020-01-01", periods=80)
    close = pd.DataFrame(100.0, index=dates, columns=["A", "B", "C", "D", "E", "SPY"])
    targets = monthly_targets(close, close, close * 10_000)
    assert all(not weights.any() for arm in targets.values() for weights in arm.values())


@pytest.mark.parametrize("missing", [0, 100, -1])
def test_missing_benchmark_session_cannot_be_labeled_complete(missing):
    expected = pd.bdate_range("2006-01-03", "2025-12-31")
    with pytest.raises(ValueError, match="coverage"):
        require_sessions(expected.delete(missing), expected)


def test_truncated_year_cannot_be_called_twenty_years():
    expected = pd.bdate_range("2006-01-03", "2025-12-31")
    with pytest.raises(ValueError, match="coverage"):
        require_sessions(expected[expected.year == 2025], expected)
    require_sessions(expected, expected)
