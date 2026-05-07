"""Combinatorial Purged Cross-Validation (CPCV).

Per López de Prado, "Advances in Financial Machine Learning" (2018) ch.7:
rolling-origin splits like the ones in :mod:`kq.models.cv` have a known
correctness issue when training labels overlap in time -- the same
observation can land in both train and test under sliding-window CV
because forecast horizons span multiple days. CPCV addresses this by:

1. **Combinatorial test sets.** Instead of one test window slid forward,
   we partition the timeline into ``N`` non-overlapping groups and
   evaluate every k-of-N test combination separately, keeping the
   remaining groups as training. The total number of folds is C(N, k).
2. **Purging.** Drop training samples whose labels overlap (in time)
   with any test sample's label window. Without this, a same-week
   training label leaks into the test fold.
3. **Embargo.** Drop training samples for ``embargo`` days AFTER the
   test set ends, on top of purging. Hedges against serial correlation
   that purging alone misses (e.g. multi-day weather patterns).

For our weather backtest, the rolling-origin in cv.py is fine -- our
labels (daily Tmax) don't overlap. But for NBA models that use
multi-game features (rolling team form over the last 10 games),
labels DO overlap and CPCV is the right CV. Same for any future
LightGBM-style model that uses lagged predictors.

This module is intentionally framework-agnostic: it returns
``(train_idx, test_idx)`` arrays just like ``rolling_origin_splits``,
so callers can swap CVs without changing the rest of the backtest
pipeline.

Reference:
- López de Prado, "Advances in Financial Machine Learning" (2018),
  ch. 7. The seminal CPCV write-up; defines purging + embargo.
- Hewamalage, Bergmeir, Bandara (2023, IJF) -- benchmarks CPCV vs
  rolling-origin and finds CPCV materially less optimistic when
  label overlap is non-trivial.
"""

from __future__ import annotations

from collections.abc import Iterator
from itertools import combinations

import numpy as np


def _split_into_groups(n_samples: int, n_groups: int) -> list[np.ndarray]:
    """Partition ``range(n_samples)`` into ``n_groups`` near-equal,
    contiguous, ordered groups."""
    if n_samples <= 0:
        return []
    if n_groups <= 0:
        raise ValueError(f"n_groups must be positive, got {n_groups}")
    if n_groups > n_samples:
        raise ValueError(f"n_groups ({n_groups}) > n_samples ({n_samples})")
    edges = np.linspace(0, n_samples, n_groups + 1, dtype=int)
    return [np.arange(edges[i], edges[i + 1]) for i in range(n_groups)]


def cpcv_splits(
    n_samples: int,
    *,
    n_groups: int = 6,
    n_test_groups: int = 2,
    label_horizon: int = 1,
    embargo: int = 0,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield ``(train_idx, test_idx)`` arrays for every CPCV fold.

    Number of folds = ``C(n_groups, n_test_groups)``. Default 6-choose-2
    = 15 folds, a common starting point.

    Purging: ``label_horizon`` is the size of the training-label
    window in samples. A training sample at position ``i`` is purged
    if any of indices ``[i, i + label_horizon)`` overlaps with a test
    sample's index range. For daily-Tmax weather (1-day horizon),
    set 1; for a 5-day rolling team-form feature, set 5.

    Embargo: ``embargo`` extra samples after each test group are
    dropped from training (one-sided -- only forward embargo, since
    leakage is forward in time). Defaults to 0; set higher when
    serial correlation is suspected (e.g. multi-day weather patterns
    or multi-game team momentum).

    Returns the index arrays in the same shape as
    :func:`kq.models.cv.rolling_origin_splits` so callers can swap
    one for the other behind a config flag.
    """
    if n_test_groups < 1 or n_test_groups >= n_groups:
        raise ValueError(
            f"n_test_groups must be in [1, n_groups - 1], got {n_test_groups} "
            f"with n_groups={n_groups}"
        )
    if label_horizon < 1:
        raise ValueError(f"label_horizon must be >= 1, got {label_horizon}")
    if embargo < 0:
        raise ValueError(f"embargo must be >= 0, got {embargo}")

    groups = _split_into_groups(n_samples, n_groups)
    if not groups:
        return

    for test_combo in combinations(range(n_groups), n_test_groups):
        # Build the test mask + the union of its index range.
        test_mask = np.zeros(n_samples, dtype=bool)
        for g_idx in test_combo:
            test_mask[groups[g_idx]] = True

        # Purge: training samples whose label window overlaps a test
        # sample. For each test-mask position p, mark
        # [max(0, p - label_horizon + 1), p + 1] as purgeable.
        purge_mask = test_mask.copy()
        for offset in range(1, label_horizon):
            shifted = np.zeros_like(purge_mask)
            shifted[:-offset] = test_mask[offset:]
            purge_mask |= shifted

        # Embargo: drop ``embargo`` samples AFTER each test group.
        if embargo > 0:
            for g_idx in test_combo:
                end = groups[g_idx][-1] + 1
                stop = min(n_samples, end + embargo)
                purge_mask[end:stop] = True

        train_mask = ~test_mask & ~purge_mask
        train_idx = np.flatnonzero(train_mask)
        test_idx = np.flatnonzero(test_mask)
        if train_idx.size == 0 or test_idx.size == 0:
            continue
        yield train_idx, test_idx


def cpcv_n_folds(*, n_groups: int = 6, n_test_groups: int = 2) -> int:
    """Pure helper: how many folds does ``cpcv_splits`` yield?"""
    if n_test_groups < 1 or n_test_groups >= n_groups:
        raise ValueError(
            f"n_test_groups must be in [1, n_groups - 1], got {n_test_groups} "
            f"with n_groups={n_groups}"
        )
    # C(n, k)
    from math import comb  # noqa: PLC0415 -- inlined for one-call helper

    return comb(n_groups, n_test_groups)


__all__ = [
    "cpcv_n_folds",
    "cpcv_splits",
]
