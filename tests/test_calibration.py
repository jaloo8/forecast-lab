"""Tests for Brier + reliability primitives."""

from __future__ import annotations

import numpy as np
import pytest

from kq.models.calibration import brier_score, reliability_bins


def test_brier_perfect_is_zero() -> None:
    probs = np.array([1.0, 0.0, 1.0, 0.0])
    outcomes = np.array([1, 0, 1, 0])
    assert brier_score(probs, outcomes) == 0.0


def test_brier_always_wrong_is_one() -> None:
    probs = np.array([0.0, 1.0, 0.0, 1.0])
    outcomes = np.array([1, 0, 1, 0])
    assert brier_score(probs, outcomes) == 1.0


def test_brier_coin_flip_model_is_quarter() -> None:
    probs = np.full(1000, 0.5)
    rng = np.random.default_rng(42)
    outcomes = rng.integers(0, 2, size=1000)
    assert brier_score(probs, outcomes) == pytest.approx(0.25, abs=0.05)


def test_reliability_bins_count_matches() -> None:
    probs = np.array([0.05, 0.15, 0.25, 0.55, 0.95])
    outcomes = np.array([0, 0, 0, 1, 1])
    bins = reliability_bins(probs, outcomes, n_bins=10)
    assert len(bins) == 10
    assert sum(b.n for b in bins) == 5


def test_brier_shape_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        brier_score(np.array([0.5, 0.5]), np.array([1]))
