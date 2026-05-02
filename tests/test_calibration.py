"""Tests for Brier + reliability primitives + the n-aware summary used to
evaluate Phase 5 readiness criterion #3."""

from __future__ import annotations

import math

import numpy as np
import pytest

from kq.models.calibration import (
    DEFAULT_MIN_N,
    DEFAULT_TOLERANCE_PP,
    ReliabilityBin,
    brier_score,
    reliability_bins,
    summarize_reliability,
)


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


# --------------- summarize_reliability — Phase 5 #3 evaluation


def _bin(lower: float, upper: float, n: int, pred: float, obs: float) -> ReliabilityBin:
    return ReliabilityBin(lower=lower, upper=upper, n=n, mean_predicted=pred, mean_observed=obs)


def test_summarize_passes_when_all_qualifying_within_tolerance() -> None:
    """Three large buckets, all within 5pp of perfect — passes the bar."""
    bins = [
        _bin(0.0, 0.1, 1000, 0.05, 0.06),  # delta=1pp
        _bin(0.1, 0.2, 200, 0.15, 0.18),  # delta=3pp
        _bin(0.2, 0.3, 500, 0.25, 0.20),  # delta=5pp
    ]
    s = summarize_reliability(bins, min_n=100, tolerance_pp=10.0)
    assert s.n_bins_qualifying == 3
    assert s.n_bins_failing == 0
    assert s.max_delta_pp == pytest.approx(5.0)
    assert s.passes_bar is True


def test_summarize_fails_when_any_qualifying_bin_exceeds_tolerance() -> None:
    bins = [
        _bin(0.0, 0.1, 1000, 0.05, 0.06),  # delta=1pp
        _bin(0.4, 0.5, 200, 0.45, 0.65),  # delta=20pp — fails
    ]
    s = summarize_reliability(bins, min_n=100, tolerance_pp=10.0)
    assert s.n_bins_failing == 1
    assert s.max_delta_pp == pytest.approx(20.0)
    assert s.max_delta_bin == 1
    assert s.passes_bar is False


def test_summarize_excludes_small_n_buckets_from_failing_count() -> None:
    """A 30pp deviation in a sub-min_n bucket must not flip pass→fail.

    This is the core motivation for the n-aware summary: at sharp
    forecasts, mid-range buckets often have n=10-50 with binomial-noise
    deviations of 30-60pp purely by chance. The summary must not penalize
    a station for those.
    """
    bins = [
        _bin(0.0, 0.1, 1000, 0.05, 0.05),  # large, perfectly calibrated
        _bin(0.4, 0.5, 30, 0.45, 0.75),  # SMALL, 30pp off — shouldn't count
        _bin(0.9, 1.0, 1000, 0.95, 0.96),  # large, 1pp off
    ]
    s = summarize_reliability(bins, min_n=100, tolerance_pp=10.0)
    assert s.n_bins_qualifying == 2  # the small-n one excluded
    assert s.n_bins_failing == 0
    assert s.max_delta_pp == pytest.approx(1.0)  # measured only on the qualifying pair
    assert s.passes_bar is True


def test_summarize_does_not_pass_with_zero_qualifying_buckets() -> None:
    """Silence isn't success — a station that never gets a bucket up to
    min_n hasn't been tested; we must NOT auto-clear it for Phase 5."""
    bins = [
        _bin(0.0, 0.1, 50, 0.05, 0.10),
        _bin(0.4, 0.5, 30, 0.45, 0.55),
    ]
    s = summarize_reliability(bins, min_n=100, tolerance_pp=10.0)
    assert s.n_bins_qualifying == 0
    assert s.n_bins_failing == 0
    assert math.isnan(s.max_delta_pp)
    assert s.max_delta_bin is None
    assert s.passes_bar is False


def test_summarize_records_threshold_and_tolerance_used() -> None:
    """Custom min_n/tolerance must be reflected in the summary for audit trail."""
    bins = [_bin(0.0, 0.1, 50, 0.05, 0.20)]  # 15pp off, n=50
    s = summarize_reliability(bins, min_n=25, tolerance_pp=5.0)
    assert s.min_n_threshold == 25
    assert s.tolerance_pp == 5.0
    assert s.n_bins_qualifying == 1
    assert s.n_bins_failing == 1
    assert s.max_delta_pp == pytest.approx(15.0)
    assert s.passes_bar is False


def test_summarize_uses_module_defaults() -> None:
    """Module defaults wire through the no-arg call site."""
    bins = [_bin(0.0, 0.1, DEFAULT_MIN_N, 0.05, 0.06)]
    s = summarize_reliability(bins)
    assert s.min_n_threshold == DEFAULT_MIN_N
    assert s.tolerance_pp == DEFAULT_TOLERANCE_PP


def test_summarize_rejects_negative_min_n() -> None:
    with pytest.raises(ValueError, match="min_n"):
        summarize_reliability([], min_n=-1)


def test_summarize_rejects_negative_tolerance() -> None:
    with pytest.raises(ValueError, match="tolerance_pp"):
        summarize_reliability([], tolerance_pp=-1.0)


def test_summarize_picks_worst_bin_index_correctly() -> None:
    """When multiple qualifying bins fail, max_delta_bin points at the worst."""
    bins = [
        _bin(0.0, 0.1, 1000, 0.05, 0.06),  # 1pp
        _bin(0.1, 0.2, 1000, 0.15, 0.30),  # 15pp
        _bin(0.2, 0.3, 1000, 0.25, 0.50),  # 25pp <- worst
        _bin(0.3, 0.4, 1000, 0.35, 0.20),  # 15pp
    ]
    s = summarize_reliability(bins, min_n=100, tolerance_pp=10.0)
    assert s.max_delta_bin == 2
    assert s.max_delta_pp == pytest.approx(25.0)
    assert s.n_bins_failing == 3
