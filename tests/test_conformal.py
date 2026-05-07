"""Tests for the split-conformal calibrator (kq.models.conformal)."""

from __future__ import annotations

import numpy as np
import pytest

from kq.models.conformal import (
    DEFAULT_ALPHA,
    DEFAULT_MIN_CALIBRATION,
    ConformalCalibrator,
    ConformalSummary,
    split_conformal_evaluation,
)

# --------------------------- threshold math ---------------------------


def test_threshold_uses_finite_sample_correction() -> None:
    """``q = scores[ceil((n+1)*(1-alpha)) - 1]`` on the sorted score array.

    With n=100 and alpha=0.1: k = ceil(101 * 0.9) = 91, so q = scores[90].
    """
    rng = np.random.default_rng(0)
    n = 100
    probs = rng.uniform(0.0, 1.0, n)
    outcomes = (rng.uniform(0.0, 1.0, n) < probs).astype(float)
    cal = ConformalCalibrator(min_calibration=10).fit(probs, outcomes)
    scores_sorted = np.sort(np.where(outcomes == 1, 1.0 - probs, probs))
    expected = float(scores_sorted[90])  # 91st order statistic, 0-indexed.
    assert cal.threshold(alpha=0.1) == pytest.approx(expected)


def test_threshold_saturates_at_one_when_index_exceeds_n() -> None:
    """Tiny calibration sets force q=1.0 — set is always {0, 1}."""
    cal = ConformalCalibrator(min_calibration=5)
    cal.fit(np.linspace(0.1, 0.9, 5), np.array([1.0, 0.0, 1.0, 0.0, 1.0]))
    # n=5, alpha=0.1 -> k = ceil(6 * 0.9) = 6 > n. Saturates.
    assert cal.threshold(alpha=0.1) == pytest.approx(1.0)


def test_threshold_alpha_validation() -> None:
    cal = ConformalCalibrator(min_calibration=10)
    cal.fit(np.linspace(0.01, 0.99, 60), (np.arange(60) % 2).astype(float))
    with pytest.raises(ValueError, match="alpha must be in"):
        cal.threshold(alpha=0.0)
    with pytest.raises(ValueError, match="alpha must be in"):
        cal.threshold(alpha=1.0)
    with pytest.raises(ValueError, match="alpha must be in"):
        cal.threshold(alpha=-0.1)


def test_threshold_monotone_in_alpha() -> None:
    """Tighter coverage (smaller alpha) -> larger threshold q."""
    rng = np.random.default_rng(7)
    n = 200
    probs = rng.uniform(0.0, 1.0, n)
    outcomes = (rng.uniform(0.0, 1.0, n) < probs).astype(float)
    cal = ConformalCalibrator(min_calibration=50).fit(probs, outcomes)
    qs = [cal.threshold(a) for a in (0.5, 0.2, 0.1, 0.05)]
    assert qs == sorted(qs)  # monotone non-decreasing as alpha shrinks


# --------------------------- coverage guarantees ---------------------------


def test_marginal_coverage_at_target_under_exchangeability() -> None:
    """Conformal's marginal-coverage guarantee: empirical coverage on iid
    holdout should be >= 1 - alpha (modulo finite-sample noise).

    Generate well-calibrated synthetic data, split-conformal, and assert
    coverage >= 1 - alpha - 5pp slack across a few alphas. The slack
    accommodates the discrete jump in the conformal threshold at small
    test sizes; we use n=2000 to keep the variance bounded.
    """
    rng = np.random.default_rng(123)
    n = 2000
    probs = rng.uniform(0.05, 0.95, n)
    outcomes = (rng.uniform(0.0, 1.0, n) < probs).astype(float)
    for alpha, seed in ((0.05, 50), (0.1, 100), (0.2, 200)):
        summary = split_conformal_evaluation(
            probs, outcomes, alpha=alpha, rng=np.random.default_rng(seed)
        )
        # Marginal coverage should be near (or above) 1 - alpha.
        assert summary.empirical_coverage >= 1.0 - alpha - 0.05


def test_evaluate_summary_fields_consistent() -> None:
    """``size = singleton + 2 * full + 0 * empty``, fractions sum to 1."""
    rng = np.random.default_rng(11)
    n = 400
    probs = rng.uniform(0.0, 1.0, n)
    outcomes = (rng.uniform(0.0, 1.0, n) < probs).astype(float)
    n_split = n // 2
    cal = ConformalCalibrator(min_calibration=50).fit(probs[:n_split], outcomes[:n_split])
    summary = cal.evaluate(probs[n_split:], outcomes[n_split:], alpha=0.1)
    assert summary.pct_singleton + summary.pct_full + summary.pct_empty == pytest.approx(1.0)
    expected_avg = summary.pct_singleton + 2.0 * summary.pct_full  # empty contributes 0
    assert summary.avg_set_size == pytest.approx(expected_avg, abs=1e-9)
    assert 0.0 <= summary.empirical_coverage <= 1.0


# --------------------------- predict_set behaviour ---------------------------


def test_predict_set_contains_class_one_when_p_high() -> None:
    """At p=0.95 with a calibrator fit on near-calibrated data, the set
    should contain class 1."""
    rng = np.random.default_rng(2)
    n = 500
    probs = rng.uniform(0.0, 1.0, n)
    outcomes = (rng.uniform(0.0, 1.0, n) < probs).astype(float)
    cal = ConformalCalibrator(min_calibration=50).fit(probs, outcomes)
    in_one, _in_zero = cal.predict_set(np.array([0.95]), alpha=0.1)
    assert bool(in_one[0]) is True


def test_predict_set_indecisive_band_around_half() -> None:
    """At alpha=0.1 with a well-calibrated synthetic generator, p=0.5
    typically falls in the indecisive band -> set = {0, 1}."""
    rng = np.random.default_rng(3)
    n = 500
    probs = rng.uniform(0.0, 1.0, n)
    outcomes = (rng.uniform(0.0, 1.0, n) < probs).astype(float)
    cal = ConformalCalibrator(min_calibration=50).fit(probs, outcomes)
    in_one, in_zero = cal.predict_set(np.array([0.5]), alpha=0.1)
    assert bool(in_one[0]) is True and bool(in_zero[0]) is True


def test_predict_set_shapes_match_input() -> None:
    rng = np.random.default_rng(4)
    n = 200
    probs = rng.uniform(0.0, 1.0, n)
    outcomes = (rng.uniform(0.0, 1.0, n) < probs).astype(float)
    cal = ConformalCalibrator(min_calibration=50).fit(probs, outcomes)
    test = np.linspace(0.0, 1.0, 25)
    in_one, in_zero = cal.predict_set(test, alpha=0.1)
    assert in_one.shape == test.shape
    assert in_zero.shape == test.shape
    assert in_one.dtype == np.bool_
    assert in_zero.dtype == np.bool_


def test_predict_set_widens_with_smaller_alpha() -> None:
    """Tighter coverage -> larger set -> more inputs land in {0, 1}."""
    rng = np.random.default_rng(5)
    n = 500
    probs = rng.uniform(0.0, 1.0, n)
    outcomes = (rng.uniform(0.0, 1.0, n) < probs).astype(float)
    cal = ConformalCalibrator(min_calibration=50).fit(probs, outcomes)
    test = np.linspace(0.05, 0.95, 200)
    sizes_loose = sum(cal.predict_set(test, alpha=0.3))
    sizes_tight = sum(cal.predict_set(test, alpha=0.05))
    assert int(sizes_tight.sum()) >= int(sizes_loose.sum())


# --------------------------- error handling ---------------------------


def test_unfitted_threshold_raises() -> None:
    cal = ConformalCalibrator(min_calibration=10)
    with pytest.raises(RuntimeError, match=r"call \.fit"):
        cal.threshold()


def test_unfitted_predict_set_raises() -> None:
    cal = ConformalCalibrator(min_calibration=10)
    with pytest.raises(RuntimeError, match=r"call \.fit"):
        cal.predict_set(np.array([0.5]))


def test_unfitted_evaluate_raises() -> None:
    cal = ConformalCalibrator(min_calibration=10)
    with pytest.raises(RuntimeError, match=r"call \.fit"):
        cal.evaluate(np.array([0.5]), np.array([1.0]))


def test_fit_shape_mismatch_raises() -> None:
    cal = ConformalCalibrator(min_calibration=10)
    with pytest.raises(ValueError, match="shape mismatch"):
        cal.fit(np.array([0.1, 0.2]), np.array([1.0, 0.0, 1.0]))


def test_fit_below_min_calibration_raises() -> None:
    cal = ConformalCalibrator(min_calibration=DEFAULT_MIN_CALIBRATION)
    with pytest.raises(ValueError, match="at least"):
        cal.fit(np.linspace(0.1, 0.9, 10), (np.arange(10) % 2).astype(float))


def test_fit_drops_nan_rows() -> None:
    """NaN rows are excluded from the count and from scores."""
    rng = np.random.default_rng(6)
    n = 70
    probs = rng.uniform(0.0, 1.0, n)
    outcomes = (rng.uniform(0.0, 1.0, n) < probs).astype(float)
    probs[0] = np.nan
    outcomes[1] = np.nan
    cal = ConformalCalibrator(min_calibration=50).fit(probs, outcomes)
    assert cal.is_fitted
    assert cal.n_calibration == n - 2  # two rows dropped


def test_fit_rejects_non_binary_outcomes() -> None:
    cal = ConformalCalibrator(min_calibration=10)
    probs = np.linspace(0.01, 0.99, 60)
    bad = np.full(60, 0.5)
    with pytest.raises(ValueError, match="binary"):
        cal.fit(probs, bad)


def test_evaluate_rejects_non_binary_outcomes() -> None:
    rng = np.random.default_rng(8)
    probs = rng.uniform(0.0, 1.0, 100)
    outcomes = (rng.uniform(0.0, 1.0, 100) < probs).astype(float)
    cal = ConformalCalibrator(min_calibration=50).fit(probs, outcomes)
    with pytest.raises(ValueError, match="binary"):
        cal.evaluate(np.array([0.5]), np.array([0.5]))


def test_evaluate_empty_test_raises() -> None:
    rng = np.random.default_rng(9)
    probs = rng.uniform(0.0, 1.0, 100)
    outcomes = (rng.uniform(0.0, 1.0, 100) < probs).astype(float)
    cal = ConformalCalibrator(min_calibration=50).fit(probs, outcomes)
    with pytest.raises(ValueError, match="empty"):
        cal.evaluate(np.array([]), np.array([]))


def test_evaluate_shape_mismatch_raises() -> None:
    rng = np.random.default_rng(10)
    probs = rng.uniform(0.0, 1.0, 100)
    outcomes = (rng.uniform(0.0, 1.0, 100) < probs).astype(float)
    cal = ConformalCalibrator(min_calibration=50).fit(probs, outcomes)
    with pytest.raises(ValueError, match="shape mismatch"):
        cal.evaluate(np.array([0.5, 0.6]), np.array([1.0]))


# --------------------------- split_conformal_evaluation ---------------------------


def test_split_conformal_one_shot_returns_summary() -> None:
    rng = np.random.default_rng(12)
    n = 500
    probs = rng.uniform(0.0, 1.0, n)
    outcomes = (rng.uniform(0.0, 1.0, n) < probs).astype(float)
    summary = split_conformal_evaluation(probs, outcomes, alpha=0.1)
    assert isinstance(summary, ConformalSummary)
    assert summary.alpha == 0.1
    assert summary.n_calibration + summary.n_test == n


def test_split_conformal_reproducible_with_seeded_rng() -> None:
    rng = np.random.default_rng(13)
    n = 400
    probs = rng.uniform(0.0, 1.0, n)
    outcomes = (rng.uniform(0.0, 1.0, n) < probs).astype(float)
    s1 = split_conformal_evaluation(probs, outcomes, alpha=0.1, rng=np.random.default_rng(99))
    s2 = split_conformal_evaluation(probs, outcomes, alpha=0.1, rng=np.random.default_rng(99))
    assert s1 == s2


def test_split_conformal_too_few_points_raises() -> None:
    with pytest.raises(ValueError, match="at least"):
        split_conformal_evaluation(np.array([0.1, 0.2]), np.array([0.0, 1.0]), alpha=0.1)


def test_split_conformal_chronological_split_uses_first_half() -> None:
    """``shuffle=False`` calibrates on the leading ``calibration_frac``
    of the array and tests on the trailing remainder. Asserts equality
    with manual fit/evaluate on the same slices."""
    rng = np.random.default_rng(15)
    n = 400
    probs = rng.uniform(0.0, 1.0, n)
    outcomes = (rng.uniform(0.0, 1.0, n) < probs).astype(float)
    summary = split_conformal_evaluation(
        probs, outcomes, alpha=0.1, calibration_frac=0.5, shuffle=False
    )
    cal = ConformalCalibrator(min_calibration=DEFAULT_MIN_CALIBRATION).fit(
        probs[:200], outcomes[:200]
    )
    expected = cal.evaluate(probs[200:], outcomes[200:], alpha=0.1)
    assert summary == expected


def test_split_conformal_calibration_frac_validation() -> None:
    rng = np.random.default_rng(14)
    n = 200
    probs = rng.uniform(0.0, 1.0, n)
    outcomes = (rng.uniform(0.0, 1.0, n) < probs).astype(float)
    with pytest.raises(ValueError, match="calibration_frac"):
        split_conformal_evaluation(probs, outcomes, calibration_frac=0.0)
    with pytest.raises(ValueError, match="calibration_frac"):
        split_conformal_evaluation(probs, outcomes, calibration_frac=1.0)


# --------------------------- defaults ---------------------------


def test_default_alpha_value() -> None:
    """Pin the default to the Phase 5 §5 #3 10 % bar — changing this is
    a semantic change to manifest output."""
    assert DEFAULT_ALPHA == 0.1


def test_default_min_calibration_value() -> None:
    assert DEFAULT_MIN_CALIBRATION == 50
