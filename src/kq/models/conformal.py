"""Split-conformal calibration for binary probability predictions.

Conformal prediction (Vovk, Shafer; Romano et al.; Niemi 2024 -- NCAA
basketball application) supplies **distribution-free finite-sample
coverage guarantees** for predictions on exchangeable data. For our
binary task (Kalshi over/under at a given threshold), the prediction set
is a subset of {0, 1} with the property that, with probability >= 1 -
alpha over the calibration draw, the true outcome lies in the set.

Why we layer this on NGR + isotonic:

- NGR gives a calibrated *parametric* density on temperature.
- Isotonic gives empirical aggregate calibration on the binary projection.
- Conformal gives *finite-sample* coverage on individual predictions --
  and a defensible "don't trade" signal whenever the prediction set is
  the full {0, 1} (the model isn't confident enough at level alpha to
  pick a side).

The non-conformity score is ``1 - p_y`` (probability mass assigned to
the true class). The conformal threshold q is the
``ceil((n+1)*(1-alpha))/n``-th empirical quantile of calibration scores
-- the standard finite-sample correction. A new prediction p contains
class c iff ``1 - p_c <= q``.

This module is intentionally lightweight (no ``mapie`` dependency) so it
composes cleanly with the existing ``IsotonicCalibrator`` and the
backtest manifest. Coverage is reported into ``conformal_summary`` via
``ConformalSummary`` once the calibrator is wired into the engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Self

import numpy as np

# Conformal scores live in [0, 1]; we keep the minimum calibration size
# small (any positive integer is technically valid) but flag when n is
# below the level at which the finite-sample correction collapses to the
# trivial bound. With n=10 calibration points and alpha=0.1, the correction
# rounds q to the maximum score -- so the set is effectively always {0, 1}.
DEFAULT_MIN_CALIBRATION: Final = 50

# Standard miscoverage level for trading. alpha=0.1 -> 90 % coverage target.
# Keeps the language consistent with Phase 5 §5 #3's 10 pp bar.
DEFAULT_ALPHA: Final = 0.1


@dataclass(frozen=True, slots=True)
class ConformalSummary:
    """Backtest-manifest-friendly coverage summary."""

    n_calibration: int
    n_test: int
    alpha: float
    """Nominal miscoverage target. Coverage goal = 1 - alpha."""

    threshold: float
    """The conformal score cut-off q -- also the size of the symmetric
    "indecision band" around p = 0.5: any prediction with p in
    ``[1 - q, q]`` returns the full set {0, 1}."""

    empirical_coverage: float
    """Fraction of test points where the true outcome lay in the
    prediction set. Should be >= 1 - alpha (modulo finite-sample noise)."""

    avg_set_size: float
    """Mean prediction-set cardinality in {0, 1, 2}. Lower is sharper;
    bounded below by the coverage requirement."""

    pct_singleton: float
    """Fraction with a singleton set -- confident predictions we'd act on."""

    pct_full: float
    """Fraction with the full set {0, 1} -- model abstains, do not trade."""

    pct_empty: float
    """Fraction with the empty set -- model is wrong AND confident.
    Should be small (~ alpha) when the underlying model is well-calibrated;
    a large value flags either miscalibration or non-exchangeable data
    (e.g. distribution shift between calibration and test windows)."""


@dataclass
class ConformalCalibrator:
    """Split-conformal calibrator.

    Usage::

        cal = ConformalCalibrator().fit(cal_probs, cal_outcomes)
        in_one, in_zero = cal.predict_set(new_probs, alpha=0.1)
        summary = cal.evaluate(test_probs, test_outcomes, alpha=0.1)

    Pre-fit, ``predict_set`` raises. Use the ``is_fitted`` property to
    guard branching when wiring this into a pipeline that may not have
    enough calibration data yet.
    """

    min_calibration: int = DEFAULT_MIN_CALIBRATION
    _scores: np.ndarray | None = field(default=None, init=False, repr=False)

    @property
    def is_fitted(self) -> bool:
        return self._scores is not None

    @property
    def n_calibration(self) -> int:
        return 0 if self._scores is None else int(self._scores.size)

    def fit(self, probs: np.ndarray, outcomes: np.ndarray) -> Self:
        """Compute non-conformity scores ``s_i = 1 - p_{y_i}`` from a
        calibration set of (predicted-prob-of-class-1, observed-outcome)
        pairs. NaN rows on either side are dropped before counting
        ``min_calibration``.
        """
        probs = np.asarray(probs, dtype=float)
        outcomes = np.asarray(outcomes, dtype=float)
        if probs.shape != outcomes.shape:
            raise ValueError(f"shape mismatch: probs {probs.shape} vs outcomes {outcomes.shape}")
        valid = ~(np.isnan(probs) | np.isnan(outcomes))
        n_valid = int(valid.sum())
        if n_valid < self.min_calibration:
            raise ValueError(
                f"need at least {self.min_calibration} non-NaN calibration pairs, got {n_valid}"
            )
        p = probs[valid]
        y_float = outcomes[valid]
        if not np.all((y_float == 0.0) | (y_float == 1.0)):
            raise ValueError("outcomes must be binary {0, 1}")
        y = y_float.astype(int)
        # Score for class-1 outcome: 1 - p; for class-0 outcome: 1 - (1 - p) = p.
        scores = np.where(y == 1, 1.0 - p, p)
        # Sort once at fit time -- threshold lookups are then O(1).
        self._scores = np.sort(scores)
        return self

    def threshold(self, alpha: float = DEFAULT_ALPHA) -> float:
        """Return the conformal cut-off q at miscoverage level ``alpha``.

        Uses the standard finite-sample correction
        ``q = scores[ceil((n+1)*(1-alpha)) - 1]``. When the index would
        exceed n (small n or very low alpha), q saturates at 1.0 -- the
        prediction set is then {0, 1} for every input.
        """
        if self._scores is None:
            raise RuntimeError("call .fit before .threshold")
        if not 0.0 < alpha < 1.0:
            raise ValueError(f"alpha must be in (0, 1), got {alpha}")
        n = self._scores.size
        k = int(np.ceil((n + 1) * (1.0 - alpha)))
        if k > n:
            return 1.0
        return float(self._scores[k - 1])

    def predict_set(
        self, probs: np.ndarray, alpha: float = DEFAULT_ALPHA
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return (in_set_one, in_set_zero) boolean arrays.

        ``in_set_one[i]`` is True iff class 1 lies in the prediction set
        for ``probs[i]`` at miscoverage level ``alpha``; ``in_set_zero[i]``
        likewise for class 0. The set cardinality is the elementwise sum.
        """
        if self._scores is None:
            raise RuntimeError("call .fit before .predict_set")
        p = np.asarray(probs, dtype=float)
        q = self.threshold(alpha)
        in_one = (1.0 - p) <= q
        in_zero = p <= q
        return in_one, in_zero

    def evaluate(
        self,
        probs: np.ndarray,
        outcomes: np.ndarray,
        alpha: float = DEFAULT_ALPHA,
    ) -> ConformalSummary:
        """Empirical coverage check on a held-out test set."""
        if self._scores is None:
            raise RuntimeError("call .fit before .evaluate")
        p = np.asarray(probs, dtype=float)
        y = np.asarray(outcomes, dtype=float)
        if p.shape != y.shape:
            raise ValueError(f"shape mismatch: probs {p.shape} vs outcomes {y.shape}")
        if p.size == 0:
            raise ValueError("empty test set")
        valid = ~(np.isnan(p) | np.isnan(y))
        p = p[valid]
        y_valid = y[valid]
        if not np.all((y_valid == 0.0) | (y_valid == 1.0)):
            raise ValueError("outcomes must be binary {0, 1}")
        y_int = y_valid.astype(int)

        in_one, in_zero = self.predict_set(p, alpha)
        covered = np.where(y_int == 1, in_one, in_zero)
        size = in_one.astype(int) + in_zero.astype(int)
        empty = size == 0
        full = size == 2
        single = size == 1
        return ConformalSummary(
            n_calibration=self.n_calibration,
            n_test=int(p.size),
            alpha=alpha,
            threshold=self.threshold(alpha),
            empirical_coverage=float(covered.mean()),
            avg_set_size=float(size.mean()),
            pct_singleton=float(single.mean()),
            pct_full=float(full.mean()),
            pct_empty=float(empty.mean()),
        )


def split_conformal_evaluation(
    probs: np.ndarray,
    outcomes: np.ndarray,
    *,
    alpha: float = DEFAULT_ALPHA,
    calibration_frac: float = 0.5,
    shuffle: bool = True,
    rng: np.random.Generator | None = None,
    min_calibration: int = DEFAULT_MIN_CALIBRATION,
) -> ConformalSummary:
    """One-shot split-conformal evaluation on a (probs, outcomes) sample.

    Splits the input into a calibration half and a test half, fits a
    ``ConformalCalibrator`` on the former, and returns its
    :class:`ConformalSummary` on the latter. Useful for emitting a
    ``conformal_summary`` block in the backtest manifest without
    threading a separate calibration set through the engine.

    Parameters
    ----------
    probs, outcomes
        1-D arrays of predicted P(y=1) and observed outcomes in {0, 1}.
    alpha
        Nominal miscoverage. Default 0.1 -> 90 % coverage target.
    calibration_frac
        Fraction of the input used for calibration; the remainder is
        the test set. Default 0.5 follows Romano et al. (2019).
    shuffle
        When True (default), splits randomly using ``rng`` -- the
        iid-exchangeable interpretation. When False, uses chronological
        order (first ``calibration_frac`` of the array for calibration,
        the remainder for test) -- appropriate when the input is already
        time-ordered and a prequential read is wanted.
    rng
        Optional ``numpy.random.Generator`` for reproducible random
        splits. Ignored when ``shuffle=False``. Defaults to
        ``default_rng(42)``.
    min_calibration
        Floor on calibration-set size. Smaller floors yield wider
        intervals; the default of 50 matches the module-level
        ``DEFAULT_MIN_CALIBRATION``.
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    if p.shape != y.shape:
        raise ValueError(f"shape mismatch: probs {p.shape} vs outcomes {y.shape}")
    if not 0.0 < calibration_frac < 1.0:
        raise ValueError(f"calibration_frac must be in (0, 1), got {calibration_frac}")
    valid = ~(np.isnan(p) | np.isnan(y))
    p = p[valid]
    y = y[valid]
    n = int(p.size)
    n_cal_required = max(min_calibration, 2)
    if n < n_cal_required + 1:
        raise ValueError(
            f"need at least {n_cal_required + 1} non-NaN points for split-conformal, got {n}"
        )

    if shuffle:
        if rng is None:
            rng = np.random.default_rng(seed=42)
        indices = rng.permutation(n)
    else:
        indices = np.arange(n)
    n_cal = int(np.floor(n * calibration_frac))
    n_cal = max(n_cal_required, min(n_cal, n - 1))
    cal_idx = indices[:n_cal]
    test_idx = indices[n_cal:]
    cal = ConformalCalibrator(min_calibration=min_calibration).fit(p[cal_idx], y[cal_idx])
    return cal.evaluate(p[test_idx], y[test_idx], alpha=alpha)
