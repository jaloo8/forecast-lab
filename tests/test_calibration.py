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
    hosmer_lemeshow_chi_squared,
    reliability_bins,
    reliability_bins_quantile,
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


# --------------- reliability_bins_quantile (Hosmer-Lemeshow binning)


def test_quantile_bins_distribute_equal_n_per_bucket() -> None:
    """1000 samples / 10 bins → 100 per bin. The whole point of HL binning."""
    rng = np.random.default_rng(0)
    probs = rng.uniform(0.0, 1.0, size=1000)
    outcomes = rng.integers(0, 2, size=1000).astype(float)
    bins = reliability_bins_quantile(probs, outcomes, n_bins=10)
    assert len(bins) == 10
    counts = [b.n for b in bins]
    # array_split distributes the remainder; with 1000/10 the split is exact.
    assert all(c == 100 for c in counts)


def test_quantile_bins_handle_uneven_split() -> None:
    """When probs.size isn't divisible by n_bins, np.array_split spreads
    the remainder across the first few bins. Counts should still be
    near-balanced (within 1 of each other)."""
    probs = np.linspace(0.0, 1.0, 1003)  # 1003/10 → 101*3 + 100*7
    outcomes = np.zeros_like(probs)
    bins = reliability_bins_quantile(probs, outcomes, n_bins=10)
    counts = [b.n for b in bins]
    assert sum(counts) == 1003
    assert max(counts) - min(counts) <= 1  # balanced within 1


def test_quantile_bin_edges_match_data_extremes() -> None:
    """The lower/upper of each bucket should be the actual min/max of the
    chunk's prob values, not arbitrary [0, 1] divisions."""
    probs = np.array([0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95])
    outcomes = np.zeros_like(probs)
    bins = reliability_bins_quantile(probs, outcomes, n_bins=5)
    # 10 samples / 5 bins → 2 per bin. First bin: probs [0.05, 0.15].
    assert bins[0].lower == pytest.approx(0.05)
    assert bins[0].upper == pytest.approx(0.15)
    assert bins[-1].lower == pytest.approx(0.85)
    assert bins[-1].upper == pytest.approx(0.95)


def test_quantile_bins_empty_input_returns_n_bins_empty_buckets() -> None:
    """Empty input produces n_bins empty buckets, matching reliability_bins'
    shape so summarize_reliability works without special-casing."""
    bins = reliability_bins_quantile(np.array([]), np.array([]), n_bins=10)
    assert len(bins) == 10
    assert all(b.n == 0 for b in bins)


def test_quantile_bins_smaller_than_n_bins_emits_empty_for_remainder() -> None:
    """When n_samples < n_bins, the first n_samples get one each + rest empty."""
    bins = reliability_bins_quantile(
        np.array([0.1, 0.5, 0.9]), np.array([0.0, 1.0, 1.0]), n_bins=10
    )
    assert len(bins) == 10
    counts = [b.n for b in bins]
    assert sum(counts) == 3


def test_quantile_bins_summary_compatible() -> None:
    """The summarize_reliability aggregator should work on quantile bins
    just as it does on equal-width bins."""
    rng = np.random.default_rng(0)
    # Well-calibrated forecast: probs and outcomes match in expectation.
    probs = rng.uniform(0.0, 1.0, size=1000)
    outcomes = (rng.uniform(0.0, 1.0, size=1000) < probs).astype(float)
    bins = reliability_bins_quantile(probs, outcomes, n_bins=10)
    s = summarize_reliability(bins, min_n=50, tolerance_pp=10.0)
    # All 10 bins have n=100; well-calibrated → all should pass.
    assert s.n_bins_qualifying == 10
    assert s.passes_bar is True


def test_quantile_bins_rejects_invalid_n_bins() -> None:
    with pytest.raises(ValueError, match="n_bins"):
        reliability_bins_quantile(np.array([0.5]), np.array([1.0]), n_bins=0)


# --------------- hosmer_lemeshow_chi_squared


def test_hl_chi_squared_zero_for_perfect_calibration() -> None:
    """When predictions exactly match outcomes (deterministic), HL stat = 0."""
    probs = np.array([0.0] * 50 + [1.0] * 50)
    outcomes = np.array([0.0] * 50 + [1.0] * 50)
    stat, dof = hosmer_lemeshow_chi_squared(probs, outcomes, n_bins=10)
    # Bins with all-0 or all-1 predictions skip per the HL convention; stat = 0.
    assert stat == pytest.approx(0.0)
    assert dof == 8  # n_bins - 2


def test_hl_chi_squared_large_for_miscalibrated() -> None:
    """Predict 0.9 always but observe 0.1 always → large HL statistic."""
    rng = np.random.default_rng(42)
    probs = rng.uniform(0.85, 0.95, size=200)  # all "high" predictions
    outcomes = rng.uniform(0.0, 1.0, size=200) < 0.10  # but only 10% positive
    stat, dof = hosmer_lemeshow_chi_squared(probs, outcomes.astype(float), n_bins=10)
    # With heavy mis-calibration, stat should be large (> 100 typically).
    assert stat > 100.0
    assert dof == 8


def test_hl_chi_squared_dof_with_small_n_bins() -> None:
    """dof floor is 1, even when n_bins-2 would be 0 or negative."""
    probs = np.array([0.5, 0.5])
    outcomes = np.array([1.0, 0.0])
    _stat, dof = hosmer_lemeshow_chi_squared(probs, outcomes, n_bins=2)
    assert dof == 1  # max(2-2, 1) = max(0, 1) = 1


def test_hl_chi_squared_returns_zero_dof_floor_on_empty() -> None:
    """Empty input → stat = 0, dof at floor."""
    stat, dof = hosmer_lemeshow_chi_squared(np.array([]), np.array([]), n_bins=10)
    assert stat == pytest.approx(0.0)
    assert dof == 8
