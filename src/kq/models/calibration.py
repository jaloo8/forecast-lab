"""Calibration primitives: Brier score, reliability diagram bins, and the
n-aware aggregate-quality summary used to evaluate the Phase 5 readiness
criterion (CLAUDE.md §5 #3)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

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
    # Distinct settlement DAYS behind `n` — the independent unit of evidence.
    #
    # PSEUDO-REPLICATION (audit 2026-08-07): the ~7 bracket outcomes for one
    # (station, day) are a deterministic step function of ONE realized daily
    # high — perfectly comonotone, zero additional information. Treating them
    # as 7 independent Bernoulli draws inflated every `n` in every manifest
    # ~7x, which is the same class of error as the step_size=1 window overlap
    # the 2026-06-11 audit caught across folds — this one lived inside the
    # fold. None when the caller didn't supply dates (legacy call sites).
    n_days: int | None = None


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

    gating_unit: str = "rows"
    """What `min_n` counted: ``"days"`` when the bins carried distinct-day
    counts (the independent unit — ~7 brackets per day settle off ONE
    temperature), ``"rows"`` for legacy call sites without dates. A manifest
    gated on rows overstates its evidence ~7x; the field makes that visible
    instead of silent."""


def _distinct_days(dates: Sequence[date] | None, idx: np.ndarray) -> int | None:
    """Distinct dates among the selected rows; None when dates weren't given."""
    if dates is None:
        return None
    return len({dates[int(i)] for i in idx})


def reliability_bins(
    probs: np.ndarray,
    outcomes: np.ndarray,
    *,
    n_bins: int = 10,
    dates: Sequence[date] | None = None,
) -> list[ReliabilityBin]:
    """Bucket predictions into `n_bins` equal-width buckets on [0, 1].

    ``dates`` — the settlement day of each prediction, aligned with ``probs``.
    When supplied, each bin also carries ``n_days``, the count of DISTINCT
    days it draws on. That is the honest sample size: the ~7 brackets of one
    (station, day) settle off a single realized temperature, so a bin fed by
    700 rows from 100 days holds 100 independent observations, not 700.
    """
    probs = np.asarray(probs, dtype=float)
    outcomes = np.asarray(outcomes, dtype=float)
    if dates is not None and len(dates) != probs.size:
        raise ValueError(f"dates length {len(dates)} != probs length {probs.size}")
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins: list[ReliabilityBin] = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (probs >= lo) & (probs < hi if i < n_bins - 1 else probs <= hi)
        n = int(mask.sum())
        if n == 0:
            bins.append(
                ReliabilityBin(
                    lo, hi, 0, float("nan"), float("nan"), n_days=0 if dates is not None else None
                )
            )
        else:
            bins.append(
                ReliabilityBin(
                    lower=float(lo),
                    upper=float(hi),
                    n=n,
                    mean_predicted=float(probs[mask].mean()),
                    mean_observed=float(outcomes[mask].mean()),
                    n_days=_distinct_days(dates, np.nonzero(mask)[0]),
                )
            )
    return bins


def reliability_bins_quantile(
    probs: np.ndarray,
    outcomes: np.ndarray,
    *,
    n_bins: int = 10,
    dates: Sequence[date] | None = None,
) -> list[ReliabilityBin]:
    """Bucket predictions into `n_bins` **equal-`n` quantile** buckets — the
    Hosmer-Lemeshow goodness-of-fit binning scheme.

    Why this exists alongside `reliability_bins`: the equal-width buckets
    on [0, 1] are easy to read but distribute samples poorly when the
    forecaster is sharp (most mass at extremes 0-0.1 and 0.9-1.0). The
    middle bins end up with n=10-100 where binomial noise dominates the
    empirical observed-frequency. Equal-`n` quantile binning evens the
    statistical power across all 10 bins by adapting the bin edges to the
    prediction distribution.

    Reference: Hosmer, D. W. & Lemeshow, S. (1980). "Goodness-of-fit
    tests for the multiple logistic regression model." Wiley.

    Returns the same `ReliabilityBin` shape as `reliability_bins`, so the
    `summarize_reliability` aggregator works on either binning. The
    `lower` / `upper` fields here are the **quantile-derived bin edges**,
    which can fall anywhere in [0, 1].
    """
    probs = np.asarray(probs, dtype=float)
    outcomes = np.asarray(outcomes, dtype=float)
    if probs.shape != outcomes.shape:
        raise ValueError(f"shape mismatch: probs {probs.shape} vs outcomes {outcomes.shape}")
    if dates is not None and len(dates) != probs.size:
        raise ValueError(f"dates length {len(dates)} != probs length {probs.size}")
    if n_bins <= 0:
        raise ValueError(f"n_bins must be positive, got {n_bins}")
    if probs.size == 0:
        # Degenerate input — return zero-bin layout matching reliability_bins'
        # shape so downstream summary code doesn't need a special case.
        return [ReliabilityBin(0.0, 1.0, 0, float("nan"), float("nan"))] * n_bins

    # `np.argsort` followed by even-split gives equal-n buckets up to one
    # extra row in the last bin if probs.size is not divisible by n_bins.
    # `np.array_split` handles the uneven case automatically.
    order = np.argsort(probs, kind="stable")
    chunks = np.array_split(order, n_bins)

    bins: list[ReliabilityBin] = []
    for chunk in chunks:
        if chunk.size == 0:
            # Possible when probs.size < n_bins; emit an empty bucket so
            # the caller still gets `n_bins` entries back.
            bins.append(ReliabilityBin(0.0, 1.0, 0, float("nan"), float("nan")))
            continue
        bin_probs = probs[chunk]
        bin_outcomes = outcomes[chunk]
        bins.append(
            ReliabilityBin(
                # Use the actual min/max of the chunk as the bin edges; the
                # caller may want to display them but they're not mathematically
                # used by `summarize_reliability` (which only reads n,
                # mean_predicted, mean_observed).
                lower=float(bin_probs.min()),
                upper=float(bin_probs.max()),
                n=int(chunk.size),
                mean_predicted=float(bin_probs.mean()),
                mean_observed=float(bin_outcomes.mean()),
                n_days=_distinct_days(dates, chunk),
            )
        )
    return bins


def hosmer_lemeshow_chi_squared(
    probs: np.ndarray,
    outcomes: np.ndarray,
    *,
    n_bins: int = 10,
    n_days: int | None = None,
) -> tuple[float, int]:
    """Compute the Hosmer-Lemeshow chi-squared statistic on quantile bins.

    Returns `(statistic, dof)`. The null hypothesis is "the model is
    well-calibrated"; large statistic values reject calibration. With
    `n_bins=10` the dof is conventionally `n_bins - 2 = 8` (the minus-two
    is for the two parameters fit by the original logistic model;
    purists argue this is wrong for non-logistic models — we follow the
    convention since it's what most papers use).

    The statistic is:

        H = sum_g [ (O_g - E_g)^2 / (E_g * (1 - E_g/n_g)) ]

    where O_g is observed positives in bin g, E_g is expected positives
    (sum of probs), and n_g is bin size.

    Returns `(0.0, n_bins - 2)` on empty input. Caller can compute a
    p-value via `scipy.stats.chi2.sf(stat, dof)` if needed.

    ``n_days`` — the count of distinct settlement days behind ``probs``.
    When supplied, the statistic is deflated by the Kish design effect
    ``n_obs / n_days``: the ~7 brackets of a (station, day) settle off one
    temperature (perfectly dependent within the day), so the naive statistic
    treats each observation as carrying ~7x its true information and rejects
    calibration far too readily. Dividing by the average cluster size is the
    standard first-order effective-sample-size correction for fully dependent
    clusters — approximate, and stated as such, but the uncorrected statistic
    is not "exact", it is simply wrong by a factor of ~7.
    """
    bins = reliability_bins_quantile(probs, outcomes, n_bins=n_bins)
    stat = 0.0
    for b in bins:
        if b.n == 0:
            continue
        observed_positives = b.mean_observed * b.n
        expected_positives = b.mean_predicted * b.n
        # Variance term per HL paper. Guard against degenerate bins (all-0 or
        # all-1 predictions) where the variance term zeros out — those bins
        # contribute zero to the statistic by convention.
        if expected_positives <= 0.0 or expected_positives >= b.n:
            continue
        variance = expected_positives * (1.0 - expected_positives / b.n)
        if variance <= 0.0:
            continue
        stat += (observed_positives - expected_positives) ** 2 / variance
    dof = max(n_bins - 2, 1)

    n_obs = int(np.asarray(probs).size)
    if n_days is not None and n_days > 0 and n_obs > n_days:
        # Kish design-effect deflation for comonotone within-day clusters.
        stat *= n_days / n_obs
    return stat, dof


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

    # PSEUDO-REPLICATION FIX (audit 2026-08-07): when the bins know their
    # distinct-day counts, `min_n` gates on DAYS — the independent unit —
    # not rows. The ~7 brackets of one (station, day) are a deterministic
    # step function of one realized temperature; a bucket holding 700 such
    # rows from 10 days has 10 independent observations, and letting it
    # "qualify" at min_n=100 was certifying evidence that did not exist.
    # Bins without day counts (legacy callers) keep the old row gating, and
    # the summary says which unit it used so no manifest is ambiguous.
    have_days = all(b.n_days is not None for b in bins) and len(bins) > 0
    gating_unit = "days" if have_days else "rows"

    def _effective_n(b: ReliabilityBin) -> int:
        return b.n_days if (have_days and b.n_days is not None) else b.n

    qualifying = [(i, b) for i, b in enumerate(bins) if _effective_n(b) >= min_n]
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
            gating_unit=gating_unit,
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
        gating_unit=gating_unit,
    )
