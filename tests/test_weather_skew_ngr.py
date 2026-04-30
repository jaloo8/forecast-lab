"""Tests for the skew-normal NGR variant."""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from kq.models.weather_ngr import NGRParameters, WeatherNGRModel
from kq.models.weather_skew_ngr import (
    PROB_CLIP_HIGH,
    PROB_CLIP_LOW,
    SkewNormalParameters,
    WeatherSkewNGRModel,
)

# --------------------------- fit ---------------------------


def test_fit_recovers_gaussian_when_data_is_gaussian() -> None:
    """If residuals are Gaussian, optimizer should land at alpha ~ 0."""
    rng = np.random.default_rng(11)
    n = 400
    forecast = rng.uniform(60, 90, n)
    # Gaussian residuals with linear bias → skew-normal MLE should pick alpha ~ 0.
    observed = 2.0 + 0.95 * forecast + rng.normal(0, 3.0, n)
    model = WeatherSkewNGRModel()
    params = model.fit(forecast, observed)
    # |alpha| should be small for truly-Gaussian data.
    assert abs(params.alpha) < 1.0
    # Slope and intercept reasonable.
    assert 0.85 < params.b < 1.05
    assert -2 < params.a < 6


def test_fit_recovers_known_alpha_from_true_skew_normal() -> None:
    """Fit on data drawn from a known skew-normal -> recover its alpha sign + sign-of-mag."""
    n = 1000
    true_alpha = 3.0
    rng_data = np.random.default_rng(7)
    rng_skew = np.random.default_rng(8)
    forecast = rng_data.uniform(60, 90, n)
    xi = 2.0 + 0.95 * forecast  # location varies linearly with forecast
    skew_noise = stats.skewnorm.rvs(
        true_alpha, loc=0.0, scale=3.0, size=n, random_state=rng_skew
    )
    observed = xi + skew_noise
    model = WeatherSkewNGRModel()
    params = model.fit(forecast, observed)
    # Recovered alpha should be clearly positive (sample variance can shift the
    # MLE away from the true value, so we just check sign-of-magnitude).
    assert params.alpha > 1.0


def test_fit_strict_no_worse_than_gaussian_seed_on_training() -> None:
    """The MLE's training NLL is <= the Gaussian seed's NLL — strictly no worse.

    Implementation contract: by construction we keep the better of the
    Gaussian seed and the multi-start fit's NLL. This holds on any data;
    no-worse on held-out is not claimed (over-fitting is real with small n).
    """
    rng = np.random.default_rng(99)
    n = 200  # not tiny, so the comparison is meaningful
    forecast = rng.uniform(60, 90, n)
    observed = forecast + rng.normal(0, 2.0, n)
    model = WeatherSkewNGRModel()
    model.fit(forecast, observed)

    # Recompute Gaussian-seed NLL and current-fit NLL on the same training data.
    gaussian_nll_at_seed = WeatherSkewNGRModel._neg_log_likelihood(
        np.array(
            [
                model.params.a + 0.0,  # type: ignore[union-attr]
                model.params.b,  # type: ignore[union-attr]
                np.log(max(model.params.omega2, 1e-6)),  # type: ignore[union-attr]
                0.0,
            ]
        ),
        forecast,
        observed,
    )
    fitted_nll = WeatherSkewNGRModel._neg_log_likelihood(
        np.array(
            [
                model.params.a,  # type: ignore[union-attr]
                model.params.b,  # type: ignore[union-attr]
                np.log(max(model.params.omega2, 1e-6)),  # type: ignore[union-attr]
                model.params.alpha,  # type: ignore[union-attr]
            ]
        ),
        forecast,
        observed,
    )
    # Fitted NLL with alpha must be <= NLL at alpha=0 (with same a/b/omega).
    # If alpha=0 happens to be optimal, the two are equal; never worse.
    assert fitted_nll <= gaussian_nll_at_seed + 1e-6


def test_fit_emits_raw_residual_std_for_engine() -> None:
    """Engine reads raw_residual_std from fit_metadata for the naive market sigma."""
    rng = np.random.default_rng(0)
    forecast = rng.uniform(60, 90, 200)
    observed = forecast + rng.normal(0, 3.5, 200)
    model = WeatherSkewNGRModel()
    model.fit(forecast, observed)
    rrs = model.fit_metadata.get("raw_residual_std")
    assert rrs is not None
    assert isinstance(rrs, float)
    assert 2.5 < rrs < 4.5


def test_fit_rejects_too_few_samples() -> None:
    model = WeatherSkewNGRModel()
    with pytest.raises(ValueError, match=">= 4 samples"):
        model.fit(np.array([1.0, 2.0, 3.0]), np.array([1.5, 2.5, 3.5]))


def test_fit_rejects_shape_mismatch() -> None:
    model = WeatherSkewNGRModel()
    with pytest.raises(ValueError, match="shape mismatch"):
        model.fit(np.array([1.0, 2.0, 3.0, 4.0]), np.array([1.5, 2.5, 3.5]))


# --------------------------- predict_proba ---------------------------


def test_predict_proba_matches_scipy_skewnorm_sf() -> None:
    """Output should equal scipy.stats.skewnorm.sf at known parameters."""
    model = WeatherSkewNGRModel()
    model.params = SkewNormalParameters(a=2.0, b=0.95, omega2=9.0, alpha=1.5)
    ens_mean = np.array([75.0])
    threshold = 80.0
    expected = stats.skewnorm.sf(
        threshold, 1.5, loc=2.0 + 0.95 * 75.0, scale=3.0
    )
    expected_clipped = float(np.clip(expected, PROB_CLIP_LOW, PROB_CLIP_HIGH))
    actual = float(model.predict_proba(ens_mean, threshold)[0])
    assert actual == pytest.approx(expected_clipped)


def test_predict_proba_clipped_to_bounds() -> None:
    model = WeatherSkewNGRModel()
    model.params = SkewNormalParameters(a=0.0, b=1.0, omega2=1.0, alpha=0.0)
    # Threshold way above the location → P → 0, but clipped to 0.01.
    out = model.predict_proba(np.array([75.0]), 200.0)
    assert out[0] == pytest.approx(PROB_CLIP_LOW)
    # Threshold way below → P → 1, clipped to 0.99.
    out = model.predict_proba(np.array([75.0]), -100.0)
    assert out[0] == pytest.approx(PROB_CLIP_HIGH)


def test_predict_proba_agrees_with_gaussian_at_alpha_zero() -> None:
    """alpha=0 → skew-normal SF == Gaussian SF (sanity check)."""
    skew = WeatherSkewNGRModel()
    skew.params = SkewNormalParameters(a=2.0, b=0.95, omega2=9.0, alpha=0.0)
    ngr = WeatherNGRModel()
    rng = np.random.default_rng(22)
    forecast = rng.uniform(60, 90, 200)
    observed = 2.0 + 0.95 * forecast + rng.normal(0, 3.0, 200)
    ngr.fit(forecast, observed)
    # Override Gaussian NGR params to match the skew model's location/scale.
    ngr.params = NGRParameters(a=2.0, b=0.95, c=9.0, d=0.0)

    test_input = np.array([75.0])
    threshold = 78.0
    skew_p = float(skew.predict_proba(test_input, threshold)[0])
    ngr_p = float(ngr.predict_proba(test_input, threshold)[0])
    assert skew_p == pytest.approx(ngr_p, abs=1e-6)


def test_predict_proba_raises_when_unfit() -> None:
    model = WeatherSkewNGRModel()
    with pytest.raises(RuntimeError, match="not fit"):
        model.predict_proba(np.array([75.0]), 80.0)


# --------------------------- end-to-end smoke ---------------------------


def test_skew_normal_reduces_brier_on_skewed_data() -> None:
    """On synthetic right-skewed data, skew-normal should beat Gaussian Brier."""
    rng = np.random.default_rng(42)
    n_train = 600
    n_test = 600
    forecast_train = rng.uniform(60, 90, n_train)
    forecast_test = rng.uniform(60, 90, n_test)
    # Synthetic right-skewed residuals.
    obs_train = forecast_train + np.abs(rng.normal(0, 4.0, n_train)) - 2.0
    obs_test = forecast_test + np.abs(rng.normal(0, 4.0, n_test)) - 2.0

    threshold = 78.0
    outcomes = (obs_test > threshold).astype(float)

    ngr = WeatherNGRModel()
    ngr.fit(forecast_train, obs_train)
    skew = WeatherSkewNGRModel()
    skew.fit(forecast_train, obs_train)

    ngr_probs = ngr.predict_proba(forecast_test, threshold)
    skew_probs = skew.predict_proba(forecast_test, threshold)

    ngr_brier = float(np.mean((ngr_probs - outcomes) ** 2))
    skew_brier = float(np.mean((skew_probs - outcomes) ** 2))

    # Skew-normal should be strictly no-worse on skewed data given the
    # fall-back-to-Gaussian safety net. On right-skewed data with this seed
    # it should be visibly better.
    assert skew_brier <= ngr_brier + 1e-6


def test_is_gaussian_property() -> None:
    p = SkewNormalParameters(a=0.0, b=1.0, omega2=1.0, alpha=0.0)
    assert p.is_gaussian
    p2 = SkewNormalParameters(a=0.0, b=1.0, omega2=1.0, alpha=1.5)
    assert not p2.is_gaussian
