"""Tests for the IsotonicCalibrator post-hoc recalibrator."""

from __future__ import annotations

import numpy as np
import pytest

from kq.models.calibration import brier_score
from kq.models.isotonic_calibration import (
    DEFAULT_MIN_PAIRS,
    PROB_CLIP_HIGH,
    PROB_CLIP_LOW,
    IsotonicCalibrator,
)

# --------------------------- identity fallback ---------------------------


def test_unfit_calibrator_is_identity() -> None:
    """Pre-fit, predict returns input clipped — never raises."""
    cal = IsotonicCalibrator()
    assert cal.is_identity
    out = cal.predict(np.array([0.05, 0.5, 0.95]))
    assert np.allclose(out, [0.05, 0.5, 0.95])


def test_identity_clips_extremes() -> None:
    cal = IsotonicCalibrator()
    out = cal.predict(np.array([-0.5, 0.005, 0.999, 1.5]))
    assert np.all(out >= PROB_CLIP_LOW)
    assert np.all(out <= PROB_CLIP_HIGH)


def test_below_min_pairs_falls_back_to_identity() -> None:
    """Fewer than min_pairs valid samples -> identity fallback."""
    cal = IsotonicCalibrator(min_pairs=DEFAULT_MIN_PAIRS)
    raw = np.linspace(0.01, 0.99, 50)  # 50 < 150
    outcomes = (raw > 0.5).astype(float)
    cal.fit(raw, outcomes)
    assert cal.is_identity
    # Output equals clipped input — no remapping.
    out = cal.predict(raw)
    assert np.allclose(out, np.clip(raw, PROB_CLIP_LOW, PROB_CLIP_HIGH))


def test_min_pairs_boundary_at_default() -> None:
    """At exactly min_pairs we fit; below we fall back."""
    rng = np.random.default_rng(0)
    n = DEFAULT_MIN_PAIRS
    raw = rng.uniform(0.01, 0.99, n)
    outcomes = (rng.uniform(0, 1, n) < raw).astype(float)
    cal = IsotonicCalibrator()
    cal.fit(raw, outcomes)
    assert not cal.is_identity
    # Drop one to land below the boundary -> identity.
    cal2 = IsotonicCalibrator()
    cal2.fit(raw[:-1], outcomes[:-1])
    assert cal2.is_identity


# --------------------------- correctness ---------------------------


def test_isotonic_remap_is_monotone() -> None:
    """PAVA solver guarantees monotone non-decreasing output."""
    rng = np.random.default_rng(42)
    n = 500
    # Synthetic miscalibrated forecaster: prob 0.3 actually fires 60% of the time.
    raw = rng.uniform(0, 1, n)
    outcomes = (rng.uniform(0, 1, n) < (raw * 1.5).clip(0, 1)).astype(float)
    cal = IsotonicCalibrator()
    cal.fit(raw, outcomes)
    grid = np.linspace(0.01, 0.99, 100)
    out = cal.predict(grid)
    diffs = np.diff(out)
    assert np.all(diffs >= -1e-9)  # monotone non-decreasing within float tolerance


def test_isotonic_reduces_brier_on_miscalibrated_input() -> None:
    """Synthetic miscalibrated prob -> isotonic should reduce Brier on a holdout."""
    rng = np.random.default_rng(123)
    n_train = 1000
    n_test = 1000
    # Miscalibrated: model always says 0.3 when threshold is barely exceeded.
    raw_train = np.full(n_train, 0.3)
    outcomes_train = rng.uniform(0, 1, n_train) < 0.7  # actually fires 70% of the time
    outcomes_train = outcomes_train.astype(float)
    raw_test = np.full(n_test, 0.3)
    outcomes_test = rng.uniform(0, 1, n_test) < 0.7
    outcomes_test = outcomes_test.astype(float)

    raw_brier = brier_score(np.clip(raw_test, 0.01, 0.99), outcomes_test)

    cal = IsotonicCalibrator()
    cal.fit(raw_train, outcomes_train)
    calibrated = cal.predict(raw_test)
    cal_brier = brier_score(calibrated, outcomes_test)

    # Calibrated should be much closer to 0.7 -> Brier ~ 0.21
    # Raw stays at 0.3 -> Brier ~ 0.49 (off by a lot).
    assert cal_brier < raw_brier


def test_clips_to_bounds() -> None:
    """Even after fit, predictions are clipped to [0.01, 0.99]."""
    rng = np.random.default_rng(7)
    n = 500
    raw = rng.uniform(0.0, 1.0, n)
    # Outcomes deterministic by raw -> would push isotonic to 0/1 at extremes.
    outcomes = (raw > 0.5).astype(float)
    cal = IsotonicCalibrator()
    cal.fit(raw, outcomes)
    out = cal.predict(np.array([0.01, 0.05, 0.5, 0.95, 0.99]))
    assert np.all(out >= PROB_CLIP_LOW - 1e-9)
    assert np.all(out <= PROB_CLIP_HIGH + 1e-9)


def test_drops_nan_rows_during_fit() -> None:
    """NaN in either array disqualifies the row before counting min_pairs."""
    rng = np.random.default_rng(9)
    n = 200  # > min_pairs
    raw = rng.uniform(0, 1, n)
    outcomes = (raw > 0.5).astype(float)
    # Inject NaN — total still well above min_pairs.
    raw[0] = np.nan
    outcomes[1] = np.nan
    cal = IsotonicCalibrator()
    cal.fit(raw, outcomes)
    assert not cal.is_identity


# --------------------------- input validation ---------------------------


def test_shape_mismatch_raises() -> None:
    cal = IsotonicCalibrator()
    with pytest.raises(ValueError, match="shape mismatch"):
        cal.fit(np.array([0.1, 0.2, 0.3]), np.array([0.0, 1.0]))


def test_predict_handles_scalar_array() -> None:
    """``predict(np.array([x]))`` returns a 1-element array."""
    cal = IsotonicCalibrator()
    out = cal.predict(np.array([0.42]))
    assert out.shape == (1,)
    assert pytest.approx(out[0]) == 0.42
