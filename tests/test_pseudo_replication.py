"""Pseudo-replication: sample sizes must count DAYS, not comonotone brackets.

THE DEFECT (audit 2026-08-07). One (station, day) settles ~7 bracket contracts
off a SINGLE realized daily high — the 7 outcomes are a deterministic step
function of one number, perfectly dependent. Every ``n`` in every manifest
(``n_evaluated=3822`` = 546 days x 7 brackets), the ``min_n=100`` reliability
gate, and the Hosmer-Lemeshow statistic treated them as independent draws.
The 2026-06-11 audit fixed replication ACROSS folds (step_size); this one
lived INSIDE the fold.

Consequence: gates could qualify on ~14 days of real evidence while claiming
n=100, and HL rejected calibration ~7x too readily. These tests pin the fix:
day-aware bins, day-gated qualification, day-deflated HL — with legacy
callers (no dates) keeping the old behaviour explicitly labelled ``rows``.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from kq.models.calibration import (
    hosmer_lemeshow_chi_squared,
    reliability_bins,
    reliability_bins_quantile,
    summarize_reliability,
)


def _comonotone_day_data(
    n_days: int, brackets_per_day: int = 7, *, seed: int = 20260807
) -> tuple[np.ndarray, np.ndarray, list[date]]:
    """Synthetic bracket predictions with the REAL dependence structure.

    Each day draws one 'temperature'; all of that day's bracket outcomes are a
    step function of it — exactly how weather contracts settle.
    """
    rng = np.random.default_rng(seed)
    probs: list[float] = []
    outcomes: list[float] = []
    dates: list[date] = []
    start = date(2025, 1, 1)
    for d in range(n_days):
        temp = rng.normal(70.0, 3.0)
        for b in range(brackets_per_day):
            threshold = 64.0 + 2.0 * b  # 7 thresholds spanning the ladder
            probs.append(float(np.clip(rng.uniform(0.05, 0.95), 0.05, 0.95)))
            outcomes.append(1.0 if temp > threshold else 0.0)
            dates.append(start + timedelta(days=d))
    return np.array(probs), np.array(outcomes), dates


def test_bins_count_distinct_days_not_rows() -> None:
    probs, outcomes, dates = _comonotone_day_data(100)
    bins = reliability_bins(probs, outcomes, n_bins=10, dates=dates)

    total_rows = sum(b.n for b in bins)
    assert total_rows == 700
    for b in bins:
        assert b.n_days is not None
        # A bin can never claim more independent days than rows...
        assert b.n_days <= b.n
        # ...nor more days than exist.
        assert b.n_days <= 100


def test_gate_refuses_replicated_rows_that_previously_qualified() -> None:
    """The exact inflation: 700 rows from 100 days must gate on 100, not 700.

    With min_n=150: the old row-gating would let a 200-row bucket qualify
    even if it drew on only ~30 distinct days. Day-gating refuses it.
    """
    # Force everything into one bucket so the arithmetic is visible.
    n_days = 30
    probs = np.full(n_days * 7, 0.55)
    rng = np.random.default_rng(1)
    outcomes = np.repeat((rng.uniform(size=n_days) < 0.55).astype(float), 7)
    dates = [date(2025, 1, 1) + timedelta(days=d) for d in range(n_days) for _ in range(7)]

    bins = reliability_bins(probs, outcomes, n_bins=10, dates=dates)
    target = next(b for b in bins if b.n > 0)
    assert target.n == 210  # rows would sail past min_n=150...
    assert target.n_days == 30  # ...but only 30 independent observations exist

    summary = summarize_reliability(bins, min_n=150)
    assert summary.gating_unit == "days"
    assert summary.n_bins_qualifying == 0
    assert summary.passes_bar is False  # silence isn't success — unchanged rule


def test_genuinely_independent_days_still_qualify() -> None:
    """The fix must not refuse REAL evidence: 200 days in one bucket qualifies."""
    n_days = 200
    probs = np.full(n_days, 0.55)
    rng = np.random.default_rng(2)
    outcomes = (rng.uniform(size=n_days) < 0.55).astype(float)
    dates = [date(2025, 1, 1) + timedelta(days=d) for d in range(n_days)]

    bins = reliability_bins(probs, outcomes, n_bins=10, dates=dates)
    summary = summarize_reliability(bins, min_n=100)
    assert summary.gating_unit == "days"
    assert summary.n_bins_qualifying == 1


def test_legacy_callers_without_dates_keep_row_gating_and_say_so() -> None:
    """Additive change: no dates -> old behaviour, explicitly labelled."""
    probs, outcomes, _dates = _comonotone_day_data(100)
    bins = reliability_bins(probs, outcomes, n_bins=10)
    assert all(b.n_days is None for b in bins)

    summary = summarize_reliability(bins, min_n=100)
    assert summary.gating_unit == "rows"


def test_quantile_bins_carry_day_counts_too() -> None:
    probs, outcomes, dates = _comonotone_day_data(50)
    bins = reliability_bins_quantile(probs, outcomes, n_bins=10, dates=dates)
    for b in bins:
        if b.n > 0:
            assert b.n_days is not None
            assert 1 <= b.n_days <= 50


def test_hl_statistic_is_deflated_by_the_design_effect() -> None:
    """7x replication must deflate the statistic ~7x, not reject 7x too hard."""
    probs, outcomes, dates = _comonotone_day_data(150)
    n_days = len(set(dates))

    raw, dof_raw = hosmer_lemeshow_chi_squared(probs, outcomes, n_bins=10)
    corrected, dof_c = hosmer_lemeshow_chi_squared(probs, outcomes, n_bins=10, n_days=n_days)

    assert dof_raw == dof_c
    assert corrected == pytest.approx(raw * n_days / probs.size)
    assert corrected < raw


def test_hl_without_clusters_is_unchanged() -> None:
    probs, outcomes, _ = _comonotone_day_data(80)
    a = hosmer_lemeshow_chi_squared(probs, outcomes, n_bins=10)
    b = hosmer_lemeshow_chi_squared(probs, outcomes, n_bins=10, n_days=None)
    assert a == b


def test_mismatched_dates_length_is_refused() -> None:
    probs, outcomes, dates = _comonotone_day_data(10)
    with pytest.raises(ValueError, match="dates length"):
        reliability_bins(probs, outcomes, n_bins=10, dates=dates[:-1])
    with pytest.raises(ValueError, match="dates length"):
        reliability_bins_quantile(probs, outcomes, n_bins=10, dates=dates[:-1])
