"""Tests for the analog-ensemble weather model."""

from __future__ import annotations

import numpy as np
import pytest

from kq.models.analog_ensemble import AnalogEnsembleModel

# Perfect-forecast pool: observed == forecast, evenly spaced.
_FC = np.array([60.0, 62.0, 64.0, 66.0, 68.0, 70.0, 72.0, 74.0, 76.0, 78.0])
_OBS = _FC.copy()


def _fit(k: int = 3, kernel: str = "uniform") -> AnalogEnsembleModel:
    return AnalogEnsembleModel(k=k, kernel=kernel).fit(_FC, _OBS)


def test_exceedance_fraction_is_exact_for_k3() -> None:
    # Query 70, k=3 -> nearest are {70, 68, 72} (dist 0,2,2; next is 4).
    # exceed 69? 70>69 T, 68>69 F, 72>69 T -> 2/3.
    m = _fit(k=3)
    assert m.predict_proba(70.0, 69.0)[0] == pytest.approx(2 / 3)


def test_monotonic_in_threshold() -> None:
    m = _fit(k=3)
    lo = m.predict_proba(70.0, 60.0)[0]  # all analogs exceed
    mid = m.predict_proba(70.0, 69.0)[0]
    hi = m.predict_proba(70.0, 80.0)[0]  # none exceed
    assert lo >= mid >= hi
    assert lo == pytest.approx(0.99)  # clipped from 1.0
    assert hi == pytest.approx(0.01)  # clipped from 0.0


def test_clip_bounds() -> None:
    m = _fit(k=3)
    p = m.predict_proba(70.0, 69.0)[0]
    assert 0.01 <= p <= 0.99


def test_multi_query_returns_array() -> None:
    m = _fit(k=3)
    out = m.predict_proba(np.array([66.0, 74.0]), 69.0)
    assert isinstance(out, np.ndarray)
    assert out.shape == (2,)


def test_k_capped_at_pool_size() -> None:
    # k larger than the pool uses the whole pool, no error.
    m = AnalogEnsembleModel(k=999).fit(_FC, _OBS)
    p = m.predict_proba(70.0, 69.0)[0]
    # whole-pool exceed 69: {70,72,74,76,78} = 5 of 10 -> 0.5
    assert p == pytest.approx(0.5)


def test_gaussian_kernel_valid_prob() -> None:
    m = _fit(k=5, kernel="gaussian")
    p = m.predict_proba(70.0, 69.0)[0]
    assert 0.01 <= p <= 0.99


def test_nan_pairs_dropped() -> None:
    fc = np.array([60.0, np.nan, 70.0, 72.0])
    obs = np.array([60.0, 65.0, np.nan, 72.0])
    m = AnalogEnsembleModel(k=2).fit(fc, obs)  # only (60,60) and (72,72) survive
    assert m.is_fit
    assert m.predict_proba(72.0, 70.0)[0] == pytest.approx(0.5)  # {72>70 T, 60>70 F}


def test_predict_before_fit_raises() -> None:
    with pytest.raises(RuntimeError, match="before fit"):
        AnalogEnsembleModel().predict_proba(70.0, 69.0)


def test_validation() -> None:
    with pytest.raises(ValueError, match="k must be"):
        AnalogEnsembleModel(k=0)
    with pytest.raises(ValueError, match="kernel must be"):
        AnalogEnsembleModel(kernel="shin")
    with pytest.raises(ValueError, match="shape mismatch"):
        AnalogEnsembleModel().fit(np.array([1.0, 2.0]), np.array([1.0]))
    with pytest.raises(ValueError, match="no valid"):
        AnalogEnsembleModel().fit(np.array([np.nan]), np.array([np.nan]))
