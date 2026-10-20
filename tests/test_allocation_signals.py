"""Artificial allocation fixtures; no historical return evidence."""

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from kq.equities.allocation_signals import (
    STATIC_POLICIES,
    SYMBOLS,
    build_signals,
    equal_risk_weights,
    exponentiated_update,
    minimum_variance_weights,
    universal_experts,
)
from kq.equities.allocation_study import Prices


def fixture_prices(end="2008-04-15"):
    dates = pd.bdate_range("2007-05-30", end)
    rng = np.random.default_rng(1947)
    returns = rng.normal(0.0002, 0.01, size=(len(dates), len(SYMBOLS)))
    closes = pd.DataFrame(100 * np.exp(np.cumsum(returns, axis=0)), dates, SYMBOLS)
    return Prices(closes.copy(), closes)


@pytest.fixture(scope="module")
def fixture_books():
    prices = fixture_prices()
    return prices, build_signals(prices)


def test_minimum_variance_diagonal_inverse_variance_oracle():
    covariance = np.diag([1.0, 2.0, 3.0, 4.0, 5.0])
    expected = 1 / np.diag(covariance)
    expected /= expected.sum()
    actual = minimum_variance_weights(covariance)
    np.testing.assert_allclose(actual, expected, atol=1e-12)
    np.testing.assert_array_equal(covariance, np.diag([1, 2, 3, 4, 5]))


def test_minimum_variance_binding_cap_and_remaining_inverse_variance():
    actual = minimum_variance_weights(np.diag([0.01, 1.0, 1.0, 1.0, 1.0]))
    np.testing.assert_allclose(actual, [0.5, 0.125, 0.125, 0.125, 0.125], atol=1e-12)


def test_minimum_variance_correlation_changes_allocation():
    covariance = np.array(
        [[1, 0.8, 0, 0, 0], [0.8, 1, 0, 0, 0], [0, 0, 1, 0, 0], [0, 0, 0, 1, 0], [0, 0, 0, 0, 1.0]]
    )
    actual = minimum_variance_weights(covariance)
    assert actual[0] == pytest.approx(actual[1])
    assert actual[0] < actual[2]
    np.testing.assert_allclose(covariance @ actual, np.repeat(actual[2], 5), atol=1e-10)


def test_minimum_variance_can_reject_an_asset_and_accepts_two_cap_assets():
    covariance = np.array([[1.0, 0.9, 0], [0.9, 2.0, 0], [0, 0, 0.01]])
    actual = minimum_variance_weights(covariance)
    np.testing.assert_allclose(actual, [0.4583333333333333, 0.0416666666666667, 0.5])
    covariance[0, 1] = covariance[1, 0] = 1.2
    np.testing.assert_allclose(minimum_variance_weights(covariance), [0.5, 0, 0.5])
    np.testing.assert_allclose(minimum_variance_weights(np.eye(2)), [0.5, 0.5])


def test_equal_risk_diagonal_inverse_volatility_oracle():
    covariance = np.diag([1.0, 4.0, 9.0, 16.0, 25.0])
    expected = 1 / np.sqrt(np.diag(covariance))
    expected /= expected.sum()
    np.testing.assert_allclose(equal_risk_weights(covariance), expected, atol=1e-10)


def test_equal_risk_full_covariance_contributions_and_scale():
    covariance = np.array([[1.0, -0.2, 0.3], [-0.2, 2.0, 0.1], [0.3, 0.1, 3.0]])
    weights = equal_risk_weights(covariance)
    contributions = weights * (covariance @ weights)
    np.testing.assert_allclose(contributions, contributions.mean(), rtol=1e-8)
    np.testing.assert_allclose(equal_risk_weights(covariance * 1e-12), weights, atol=1e-12)
    np.testing.assert_allclose(
        minimum_variance_weights(covariance * 1e12),
        minimum_variance_weights(covariance),
        atol=1e-12,
    )


@pytest.mark.parametrize(
    "matrix",
    [
        np.zeros((5, 5)),
        np.ones((5, 5)),
        np.array([[1, 2], [2, 1]]),
        np.array([[1, 0.1], [0.2, 1]]),
        np.array([[1, np.nan], [np.nan, 1]]),
        np.ones((2, 3)),
        np.eye(2) * 1j,
    ],
)
def test_invalid_covariance_fails_visibly(matrix):
    with pytest.raises(ValueError):
        minimum_variance_weights(matrix)
    with pytest.raises(ValueError):
        equal_risk_weights(matrix)


def test_equal_risk_nonconvergence_is_not_a_fallback():
    with pytest.raises(RuntimeError, match="did not converge"):
        equal_risk_weights(np.eye(5), max_iterations=0)


def test_exact_universal_grid_and_uniform_prior():
    experts = universal_experts()
    assert experts.shape == (126, 6)
    assert len(np.unique(experts, axis=0)) == 126
    np.testing.assert_allclose(experts.sum(axis=1), 1)
    np.testing.assert_allclose(experts.mean(axis=0), 1 / 6)
    assert (experts >= 0).all()
    assert np.equal(experts * 4, np.floor(experts * 4)).all()


def test_eg_update_manual_ratio_and_common_scaling():
    weights = np.array([0.2, 0.3, 0.5])
    relatives = np.array([1.2, 0.7, 1.0])
    actual = exponentiated_update(weights, relatives)
    ratio = (weights[0] / weights[1]) * np.exp(
        0.05 * (relatives[0] - relatives[1]) / (weights @ relatives)
    )
    assert actual[0] / actual[1] == pytest.approx(ratio)
    np.testing.assert_allclose(exponentiated_update(weights, relatives * 7), actual)


@pytest.mark.parametrize(
    "weights,relatives",
    [
        ([0.5, 0.5], [1, 0]),
        ([0.5, -0.5], [1, 1]),
        ([0.2, 0.2], [1, 1]),
        ([0.5, 0.5], [1, np.nan]),
    ],
)
def test_online_invalid_state_fails(weights, relatives):
    with pytest.raises(ValueError):
        exponentiated_update(np.array(weights), np.array(relatives))


def test_inventory_unscaled_bounds_and_control_semantics(fixture_books):
    _, books = fixture_books
    assert tuple(books) == STATIC_POLICIES
    assert len(books) == 8
    for policy, frame in books.items():
        weights = frame[list(SYMBOLS)].to_numpy(float)
        assert weights.min() >= 0
        assert weights.sum(axis=1).max() <= 1 + 1e-12
        if policy != "C01":
            np.testing.assert_allclose(weights[frame.warmup_ready].sum(axis=1), 1)
        assert (
            frame.loc[frame.warmup_ready, "decision_date"] < frame.index[frame.warmup_ready]
        ).all()
    for policy in ("C01", "C02", "C03"):
        assert not books[policy].rebalance.any()
        assert books[policy].warmup_ready.iloc[1:].all()
    assert books["C01"][list(SYMBOLS)].to_numpy().sum() == 0
    assert books["C02"].BIL.iloc[1:].eq(1).all()
    assert books["C03"].SPY.iloc[1:].eq(1).all()
    np.testing.assert_allclose(
        books["C04"].loc["2008-01-02", list(SYMBOLS)], [0.2, 0.2, 0.2, 0.2, 0.2, 0]
    )


def test_covariance_warmup_and_month_boundary(fixture_books):
    prices, books = fixture_books
    for policy in ("A01", "A02"):
        frame = books[policy]
        first = frame.index[frame.warmup_ready][0]
        position = prices.closed.index.get_loc(first)
        assert position - 1 >= 126
        assert first.month != prices.closed.index[position - 1].month
        assert not frame.warmup_ready.loc[:"2007-10-31"].any()
        assert frame.loc[first, "rebalance"]
        assert frame.loc[first, "decision_date"] == prices.closed.index[position - 1]
    assert books["A01"].loc[books["A01"].warmup_ready, list(SYMBOLS)].max().max() <= 0.5 + 1e-12
    assert books["A02"].BIL.eq(0).all()


def test_online_first_completed_interval_and_independent_expert_oracle():
    prices = fixture_prices("2007-07-04")
    books = build_signals(prices)
    for policy in ("O01", "O02"):
        np.testing.assert_allclose(books[policy].loc["2007-06-01", list(SYMBOLS)], 1 / 6)
        assert books[policy].loc["2007-06-01", "decision_date"] == pd.Timestamp("2007-05-31")
        assert books[policy].loc["2007-06-04", "as_of"] == pd.Timestamp("2007-05-31 20:00Z")
    ratios = (prices.closed.loc["2007-06-29"] / prices.closed.loc["2007-05-31"]).to_numpy()
    experts = universal_experts()
    wealth = np.array(
        [sum(float(a) * float(b) for a, b in zip(e, ratios, strict=True)) for e in experts]
    )
    expected = sum((float(s) * e for s, e in zip(wealth, experts, strict=True))) / wealth.sum()
    np.testing.assert_allclose(books["O01"].loc["2007-07-02", list(SYMBOLS)], expected)
    np.testing.assert_allclose(
        books["O02"].loc["2007-07-02", list(SYMBOLS)], exponentiated_update(np.ones(6) / 6, ratios)
    )
    assert not books["O01"].loc["2007-07-03", "rebalance"]


def test_prefix_and_future_prices_do_not_rewrite_existing_signals(fixture_books):
    original, books = fixture_books
    prefix = Prices(original.opened.loc[:"2008-02-15"], original.closed.loc[:"2008-02-15"])
    prefix_books = build_signals(prefix)
    changed = Prices(original.opened.copy(), original.closed.copy())
    changed.opened.loc["2008-02-18":, "SPY"] *= 10
    changed.closed.loc["2008-02-18":, "SPY"] *= 11
    changed_books = build_signals(changed)
    for policy in STATIC_POLICIES:
        assert_frame_equal(books[policy].loc[:"2008-02-15"], prefix_books[policy])
        assert_frame_equal(
            books[policy].loc[:"2008-02-15"], changed_books[policy].loc[:"2008-02-15"]
        )


def test_open_prices_do_not_enter_signals(fixture_books):
    original, books = fixture_books
    changed = Prices(original.opened * 7, original.closed.copy())
    changed_books = build_signals(changed)
    for policy in STATIC_POLICIES:
        assert_frame_equal(books[policy], changed_books[policy])


def test_degenerate_real_signal_covariance_is_refused():
    dates = pd.bdate_range("2007-05-30", "2008-01-02")
    flat = pd.DataFrame(100.0, dates, SYMBOLS)
    with pytest.raises(ValueError, match="positive definite"):
        build_signals(Prices(flat.copy(), flat))


def test_missing_or_misaligned_prices_are_refused():
    prices = fixture_prices("2007-07-04")
    invalid = Prices(prices.opened, prices.closed.iloc[1:])
    with pytest.raises(ValueError, match="aligned"):
        build_signals(invalid)
    invalid = Prices(prices.opened.copy(), prices.closed.copy())
    invalid.closed.iloc[0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        build_signals(invalid)
