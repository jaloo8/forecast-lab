"""Tests for the NGR weather model.

Strategy: synthesize data with a *known* bias and variance, fit, and check
the recovered parameters land within Monte-Carlo tolerance. Then a few
black-box invariants for predict_proba and brier_score.
"""

from __future__ import annotations

import numpy as np
import pytest

from kq.models.weather_ngr import (
    PROB_CLIP_HIGH,
    PROB_CLIP_LOW,
    NGRParameters,
    WeatherNGRModel,
    raw_brier_score,
)


def _synth_degenerate(
    *,
    n: int,
    a: float,
    b: float,
    sigma: float,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """T_obs = a + b * forecast + N(0, sigma)."""
    rng = np.random.default_rng(seed)
    forecast = rng.normal(70.0, 10.0, size=n)  # forecasts spread around 70F
    obs = a + b * forecast + rng.normal(0.0, sigma, size=n)
    return forecast, obs


def test_fit_recovers_known_bias_and_slope() -> None:
    """Generate data with a=2 (cold bias), b=1, sigma=3. Fit should recover ~these."""
    forecast, obs = _synth_degenerate(n=500, a=2.0, b=1.0, sigma=3.0, seed=42)
    m = WeatherNGRModel()
    params = m.fit(forecast, obs)

    assert params.is_degenerate
    assert params.a == pytest.approx(2.0, abs=0.5)
    assert params.b == pytest.approx(1.0, abs=0.05)
    # c is variance; sqrt(c) should approximate sigma=3
    assert np.sqrt(params.c) == pytest.approx(3.0, abs=0.3)
    assert m.fit_metadata["form"] == "degenerate"
    assert m.fit_metadata["n_samples"] == 500


def test_fit_with_ensemble_variance_uses_full_form() -> None:
    """When ens_vars is non-zero anywhere, fit uses the 4-parameter form."""
    rng = np.random.default_rng(7)
    n = 300
    forecast = rng.normal(70.0, 10.0, size=n)
    spreads = rng.uniform(0.5, 5.0, size=n)
    # True relationship: T_obs ~ N(forecast, 1 + 0.5 * spread^2)
    sigma_true = np.sqrt(1.0 + 0.5 * spreads**2)
    obs = forecast + rng.normal(0.0, sigma_true)

    m = WeatherNGRModel()
    params = m.fit(forecast, obs, ens_vars=spreads**2)

    assert not params.is_degenerate
    assert params.d > 0.0
    assert m.fit_metadata["form"] == "full"


def test_fit_rejects_size_mismatch() -> None:
    m = WeatherNGRModel()
    with pytest.raises(ValueError, match="shape"):
        m.fit(np.array([1.0, 2.0]), np.array([1.0, 2.0, 3.0]))


def test_fit_rejects_too_few_samples() -> None:
    m = WeatherNGRModel()
    with pytest.raises(ValueError, match="at least 2"):
        m.fit(np.array([70.0]), np.array([72.0]))


def test_predict_distribution_returns_mu_sigma() -> None:
    m = WeatherNGRModel(params=NGRParameters(a=1.0, b=1.0, c=4.0, d=0.0))
    mu, sigma = m.predict_distribution(np.array([70.0, 80.0]))
    assert mu == pytest.approx(np.array([71.0, 81.0]))
    assert sigma == pytest.approx(np.array([2.0, 2.0]))


def test_predict_proba_clipped_to_calibration_range() -> None:
    """Even if the Gaussian says 0.0001 or 0.9999, we clip to [0.01, 0.99]."""
    m = WeatherNGRModel(params=NGRParameters(a=0.0, b=1.0, c=1.0, d=0.0))
    # Forecast 70, threshold 100 → astronomically low P(T > 100); clipped to 0.01
    p_low = m.predict_proba(70.0, threshold=100.0)
    assert p_low == pytest.approx(PROB_CLIP_LOW)
    # Forecast 70, threshold 0 → astronomically high P(T > 0); clipped to 0.99
    p_high = m.predict_proba(70.0, threshold=0.0)
    assert p_high == pytest.approx(PROB_CLIP_HIGH)


def test_predict_proba_monotone_in_threshold() -> None:
    """For a fixed forecast, lower thresholds → higher P(T > t).

    Use thresholds inside the unclipped Gaussian range so we test the
    monotonicity of the CDF, not the clip ceiling.
    """
    m = WeatherNGRModel(params=NGRParameters(a=0.0, b=1.0, c=4.0, d=0.0))
    probs = [
        float(m.predict_proba(np.array([70.0]), t)[0]) for t in [68.0, 69.0, 70.0, 71.0, 72.0]
    ]
    assert probs == sorted(probs, reverse=True)


def test_brier_score_perfect_model_is_low() -> None:
    """Fit on noiseless data → Brier should be near zero."""
    forecast = np.linspace(60.0, 80.0, 50)
    obs = forecast.copy()
    m = WeatherNGRModel()
    m.fit(forecast, obs + np.random.default_rng(0).normal(0, 0.01, size=50))
    bs = m.brier_score(forecast, obs, np.array([65.0, 70.0, 75.0]))
    assert 0.0 <= bs < 0.05


def test_brier_score_random_model_near_quarter() -> None:
    """A model whose prob is always ~0.5 should land near the 0.25 coin-flip Brier."""
    rng = np.random.default_rng(1)
    forecast = rng.normal(70, 10, size=300)
    obs = rng.normal(70, 10, size=300)  # uncorrelated → no edge
    m = WeatherNGRModel()
    m.fit(forecast, obs)
    bs = m.brier_score(forecast, obs, np.array([70.0]))
    assert 0.15 < bs < 0.35


def test_predict_requires_fit() -> None:
    m = WeatherNGRModel()
    with pytest.raises(RuntimeError, match="not fit"):
        m.predict_distribution(70.0)


def test_raw_brier_baseline_runs() -> None:
    """Raw baseline shouldn't crash and returns a finite value."""
    forecast, obs = _synth_degenerate(n=100, a=2.0, b=1.0, sigma=3.0, seed=0)
    bs = raw_brier_score(forecast, obs, np.array([70.0]), raw_sigma=3.0)
    assert 0.0 <= bs <= 1.0


def test_calibrated_beats_raw_on_biased_data() -> None:
    """The whole point of NGR: a known bias should make calibrated < raw on Brier."""
    forecast, obs = _synth_degenerate(n=500, a=5.0, b=0.95, sigma=3.0, seed=11)
    m = WeatherNGRModel()
    m.fit(forecast, obs)
    thresholds = np.array([65.0, 70.0, 75.0, 80.0])
    bs_calibrated = m.brier_score(forecast, obs, thresholds)
    bs_raw = raw_brier_score(forecast, obs, thresholds, raw_sigma=3.0)
    # Calibrated should be lower (better) than raw on biased data.
    assert bs_calibrated < bs_raw
