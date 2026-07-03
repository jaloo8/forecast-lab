"""HAR-RV math pins (Phase C index-brackets benchmark).

The tests use synthetic series with KNOWN volatility structure so the
assertions pin behavior, not luck: a vol-clustered series must move the
predicted sigma in the right direction, and the Normal plumbing must
partition probability mass exactly across a bracket ladder.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import pytest

from kq.backtest.index_brackets import build_ladder
from kq.models.har_rv import (
    MIN_TRAIN_RETURNS,
    MONTHLY_WINDOW,
    HarRVFit,
    constant_vol_sigma,
    fit_har_rv,
    log_returns,
    make_prob_gt,
    pit_value,
    predict_sigma,
)


def _clustered_returns(rng: np.random.Generator, *, n_calm: int, n_wild: int) -> np.ndarray:
    """Calm regime (sigma=0.5%) followed by a wild regime (sigma=2.5%)."""
    calm = rng.normal(0.0, 0.005, n_calm)
    wild = rng.normal(0.0, 0.025, n_wild)
    return np.concatenate([calm, wild])


# --------------------------- returns ---------------------------


def test_log_returns_basic() -> None:
    closes = np.array([100.0, 110.0, 99.0])
    r = log_returns(closes)
    assert r == pytest.approx([math.log(1.1), math.log(99.0 / 110.0)])


def test_log_returns_rejects_nonpositive_closes() -> None:
    with pytest.raises(ValueError, match="strictly positive"):
        log_returns(np.array([100.0, 0.0, 99.0]))


# --------------------------- fitting + prediction ---------------------------


def test_fit_requires_enough_history() -> None:
    with pytest.raises(ValueError, match=str(MIN_TRAIN_RETURNS)):
        fit_har_rv(np.full(MIN_TRAIN_RETURNS - 1, 0.01))


def test_sigma_responds_to_vol_clustering() -> None:
    """THE HAR-RV property this lane is betting on: after a burst of large
    returns the forecast sigma must sit far above the calm-period forecast
    (and the constant-vol baseline can't tell the difference by
    construction)."""
    rng = np.random.default_rng(7)
    returns = _clustered_returns(rng, n_calm=400, n_wild=60)
    fit = fit_har_rv(returns)
    sigma_calm = predict_sigma(fit, returns[:400])  # history ends inside the calm regime
    sigma_wild = predict_sigma(fit, returns)  # history ends after the wild burst
    assert sigma_wild > 2.0 * sigma_calm
    assert 0.001 < sigma_calm < 0.02
    assert 0.005 < sigma_wild < 0.10


def test_fit_recovers_persistence_on_har_generated_data() -> None:
    """On data GENERATED from a persistent vol process, the fitted HAR
    coefficients must load positively on the vol cascade overall (the
    individual daily/weekly/monthly split is not identified with a noisy
    RV proxy — only the sum is a stable pin)."""
    rng = np.random.default_rng(11)
    n = 2000
    sigma = np.empty(n)
    sigma[0] = 0.01
    for t in range(1, n):  # AR(1) log-vol: strong persistence
        sigma[t] = math.exp(0.94 * math.log(sigma[t - 1]) + 0.06 * math.log(0.01)) * math.exp(
            rng.normal(0.0, 0.10)
        )
    returns = rng.normal(0.0, 1.0, n) * sigma
    fit = fit_har_rv(returns)
    total_load = fit.beta_daily + fit.beta_weekly + fit.beta_monthly
    assert total_load > 0.2
    assert fit.n_regression_rows == n - MONTHLY_WINDOW


def test_predicted_rv_is_floored_never_zero() -> None:
    """A dead-flat stretch must not collapse sigma to zero (overconfident
    ladders are worse than diffuse ones)."""
    fit = HarRVFit(
        beta0=-1.0,  # pathological OLS output: negative prediction everywhere
        beta_daily=0.0,
        beta_weekly=0.0,
        beta_monthly=0.0,
        rv_floor=1e-6,
        n_regression_rows=100,
    )
    sigma = predict_sigma(fit, np.full(MONTHLY_WINDOW, 0.0))
    assert sigma == pytest.approx(1e-3)


def test_predict_sigma_needs_a_full_monthly_window() -> None:
    fit = fit_har_rv(np.random.default_rng(0).normal(0, 0.01, 200))
    with pytest.raises(ValueError, match="trailing returns"):
        predict_sigma(fit, np.full(MONTHLY_WINDOW - 1, 0.01))


def test_constant_vol_sigma_is_rms() -> None:
    returns = np.array([0.01, -0.01, 0.02, -0.02])
    expected = math.sqrt(np.mean(returns**2))
    assert constant_vol_sigma(returns) == pytest.approx(expected)


# --------------------------- distribution plumbing ---------------------------


def test_prob_gt_is_a_valid_exceedance_function() -> None:
    prob_gt = make_prob_gt(prev_close=7800.0, sigma=0.008)
    assert prob_gt(0.0) == pytest.approx(1.0)
    assert prob_gt(-5.0) == pytest.approx(1.0)
    # mu = 0: the previous close is the distribution median.
    assert prob_gt(7800.0) == pytest.approx(0.5)
    # Monotone non-increasing across the ladder span.
    xs = np.linspace(7000.0, 8600.0, 200)
    ps = [prob_gt(float(x)) for x in xs]
    assert all(a >= b - 1e-12 for a, b in itertools.pairwise(ps))
    # ±1 sigma in log space ≈ 16/84.
    assert prob_gt(7800.0 * math.exp(0.008)) == pytest.approx(0.1587, abs=1e-3)


def test_ladder_probs_partition_unity_before_clipping() -> None:
    """The bracket ladder is a partition of the reals: raw CDF mass across
    less | betweens | greater must sum to 1 (the half-width offsets are
    measure-zero for a continuous distribution)."""
    prob_gt = make_prob_gt(prev_close=7812.0, sigma=0.009)
    ladder = build_ladder(7812.0, symbol="SPX", half_brackets=7)
    total = 0.0
    for s in ladder:  # unclipped mass, computed straight from the CDF
        if s.kind == "less":
            assert s.cap is not None
            total += 1.0 - prob_gt(s.cap)
        elif s.kind == "greater":
            assert s.floor is not None
            total += prob_gt(s.floor)
        else:
            assert s.floor is not None and s.cap is not None
            total += prob_gt(s.floor) - prob_gt(s.cap)
    # The venue's epsilon cap-encoding leaves ~1e-4-wide gaps between
    # brackets; their total mass bounds the partition defect.
    assert total == pytest.approx(1.0, abs=1e-3)


def test_pit_value_is_the_forecast_cdf() -> None:
    assert pit_value(7800.0, 0.01, 7800.0) == pytest.approx(0.5)
    assert pit_value(7800.0, 0.01, 7800.0 * math.exp(0.01)) == pytest.approx(0.8413, abs=1e-3)
    assert pit_value(7800.0, 0.01, 7000.0) < 0.01


def test_make_prob_gt_validates_inputs() -> None:
    with pytest.raises(ValueError, match="prev_close"):
        make_prob_gt(0.0, 0.01)
    with pytest.raises(ValueError, match="sigma"):
        make_prob_gt(7800.0, 0.0)
