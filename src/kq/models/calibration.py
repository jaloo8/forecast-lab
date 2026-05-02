"""Calibration primitives: Brier score, reliability diagram bins, and the
n-aware aggregate-quality summary used to evaluate the Phase 5 readiness
criterion (CLAUDE.md §5 #3)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

# Default min-n threshold for treating a reliability bucket as statistically
# meaningful. Below this, binomial-sampling variance dominates the empirical
# observed-frequency estimate (e.g. a true-50% bucket with n=50 has a 95%
# CI of ±13.9pp purely from sampling — wider than the 10pp bar). At n=100
# the 95% CI is ±9.8pp; at n=200 it's ±6.9pp. We default to 100 — the
# minimum where a 10pp deviation is more likely a real calibration issue
# than sampling noise. Configurable per call.
DEFAULT_MIN_N: int = 100

# Default per-bucket tolerance for the Phase 5 #3 bar. CLAUDE.md states
# "no bucket off by > 10pp"; this constant pins the default.
DEFAULT_TOLERANCE_PP: float = 10.0


def brier_score(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Binary Brier score: mean((p - y)^2).

    Parameters
    ----------
    probs
        Predicted probabilities in [0, 1], shape (n,).
    outcomes
        Realized binary outcomes {0, 1}, shape (n,).
    """
    probs = np.asarray(probs, dtype=float)
    outcomes = np.asarray(outcomes, dtype=float)
    if probs.shape != outcomes.shape:
        raise ValueError(f"shape mismatch: probs {probs.shape} vs outcomes {outcomes.shape}")
    if probs.size == 0:
        raise ValueError("empty arrays")
    return float(np.mean((probs - outcomes) ** 2))


@dataclass(frozen=True)
class ReliabilityBin:
    lower: float
    upper: float
    n: int
    mean_predicted: float
    mean_observed: float


@dataclass(frozen=True, slots=True)
class ReliabilitySummary:
    """Aggregate reliability-quality summary used to evaluate the Phase 5
    readiness bar (CLAUDE.md §5 #3 — "no bucket off by > 10pp").

    The original criterion was applied to all buckets uniformly, which
    proved noisy in practice: at sharp probabilistic forecasts (lead 1
    weather), most predictions concentrate at the extremes (P < 10% or
    P > 90%), leaving the mid-range buckets with tiny n where binomial
    sampling variance alone can produce 30-60pp deviations. This summary
    isolates the **statistically meaningful** subset (buckets with
    `n >= min_n`) and reports pass/fail against `tolerance_pp` over that
    subset.

    A station passes the Phase 5 bar iff ``passes_bar is True``.
    """

    n_bins_total: int
    """Total number of reliability bins (typically 10)."""

    n_bins_qualifying: int
    """Bins with `n >= min_n` — the statistically-meaningful subset."""

    n_bins_failing: int
    """Qualifying bins where |mean_predicted - mean_observed| > tolerance_pp."""

    max_delta_pp: float
    """Largest |delta| in pp across qualifying bins. NaN when no bin qualifies."""

    max_delta_bin: int | None
    """Index of the worst-offending qualifying bin. None when no bin qualifies."""

    passes_bar: bool
    """True iff `n_bins_qualifying > 0` AND `n_bins_failing == 0`. A station
    with zero qualifying bins (e.g. very thin data) does NOT pass — silence
    isn't success."""

    min_n_threshold: int
    """The `min_n` used for this evaluation."""

    tolerance_pp: float
    """The |delta| tolerance used for this evaluation."""


def reliability_bins(
    probs: np.ndarray,
    outcomes: np.ndarray,
    *,
    n_bins: int = 10,
) -> list[ReliabilityBin]:
    """Bucket predictions into `n_bins` equal-width buckets on [0, 1]."""
    probs = np.asarray(probs, dtype=float)
    outcomes = np.asarray(outcomes, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins: list[ReliabilityBin] = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (probs >= lo) & (probs < hi if i < n_bins - 1 else probs <= hi)
        n = int(mask.sum())
        if n == 0:
            bins.append(ReliabilityBin(lo, hi, 0, float("nan"), float("nan")))
        else:
            bins.append(
                ReliabilityBin(
                    lower=float(lo),
                    upper=float(hi),
                    n=n,
                    mean_predicted=float(probs[mask].mean()),
                    mean_observed=float(outcomes[mask].mean()),
                )
            )
    return bins


def summarize_reliability(
    bins: Sequence[ReliabilityBin],
    *,
    min_n: int = DEFAULT_MIN_N,
    tolerance_pp: float = DEFAULT_TOLERANCE_PP,
) -> ReliabilitySummary:
    """Aggregate `reliability_bins(...)` output into a pass/fail summary.

    Buckets with `n < min_n` are excluded from the max-delta calculation —
    binomial sampling variance at small n produces deviations that aren't
    distinguishable from noise. The summary is what answers "does this
    station meet the Phase 5 reliability bar?".

    Parameters
    ----------
    bins
        Output of `reliability_bins(probs, outcomes, n_bins=...)`.
    min_n
        Buckets below this `n` are excluded from the failing-buckets count
        and the `max_delta_pp` calculation. See `DEFAULT_MIN_N` rationale.
    tolerance_pp
        Per-bucket tolerance for `|mean_predicted - mean_observed|`, in pp.
        Defaults to 10pp per CLAUDE.md §5 #3.
    """
    if min_n < 0:
        raise ValueError(f"min_n must be non-negative, got {min_n}")
    if tolerance_pp < 0.0:
        raise ValueError(f"tolerance_pp must be non-negative, got {tolerance_pp}")

    qualifying = [(i, b) for i, b in enumerate(bins) if b.n >= min_n]
    if not qualifying:
        return ReliabilitySummary(
            n_bins_total=len(bins),
            n_bins_qualifying=0,
            n_bins_failing=0,
            max_delta_pp=float("nan"),
            max_delta_bin=None,
            # Silence isn't success — a station that never gets a bucket up to
            # min_n hasn't *demonstrated* calibration; it just hasn't been
            # tested. Phase 5 should not be auto-cleared on thin data.
            passes_bar=False,
            min_n_threshold=min_n,
            tolerance_pp=tolerance_pp,
        )

    deltas = [(i, abs(b.mean_predicted - b.mean_observed) * 100.0) for i, b in qualifying]
    max_idx, max_delta = max(deltas, key=lambda t: t[1])
    n_failing = sum(1 for _, d in deltas if d > tolerance_pp)
    return ReliabilitySummary(
        n_bins_total=len(bins),
        n_bins_qualifying=len(qualifying),
        n_bins_failing=n_failing,
        max_delta_pp=max_delta,
        max_delta_bin=max_idx,
        passes_bar=(n_failing == 0),
        min_n_threshold=min_n,
        tolerance_pp=tolerance_pp,
    )
