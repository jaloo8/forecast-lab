"""Rolling-origin time-series cross-validation.

Per CLAUDE.md §5 Phase 2 + the user's greenlit answer to validation question:
no random shuffles. Each fold trains strictly on the past and tests on the
next chronological window. Train always grows; test is a fixed-size sliding
window.

Iteration:

    | train      | test |
    | train          | test |
    | train              | test |
    ...

We use index-based splits so the caller can use any time-sortable column
(date, datetime, monotonically-increasing id) for ordering.
"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import polars as pl


def rolling_origin_splits(
    n_samples: int,
    *,
    initial_train_size: int,
    test_window_size: int,
    step_size: int | None = None,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield ``(train_idx, test_idx)`` arrays of position indices in [0, n_samples).

    Assumes the caller has already sorted samples chronologically. Each call
    returns increasing-train, fixed-test windows; train_idx always strictly
    precedes test_idx in position.

    ``step_size`` defaults to ``test_window_size`` so consecutive test
    windows are NON-overlapping: every sample lands in at most one test
    window. The old default (``step_size=1``) evaluated each sample in up
    to ``test_window_size`` overlapping windows, pseudo-replicating every
    manifest statistic ~14x — 2026-06-11 audit root cause #9. Passing an
    explicit ``step_size`` smaller than the window remains possible for
    diagnostics, but aggregate metrics computed over such splits will
    double-count samples.
    """
    if step_size is None:
        step_size = test_window_size
    if n_samples < initial_train_size + test_window_size:
        return
    if initial_train_size <= 0 or test_window_size <= 0 or step_size <= 0:
        raise ValueError("initial_train_size, test_window_size, step_size must be positive")

    train_end = initial_train_size
    while train_end + test_window_size <= n_samples:
        train_idx = np.arange(0, train_end)
        test_idx = np.arange(train_end, train_end + test_window_size)
        yield train_idx, test_idx
        train_end += step_size


def sort_by_valid_date(df: pl.DataFrame) -> pl.DataFrame:
    """Defensive sort so split indices map to chronological order."""
    if "valid_date" not in df.columns:
        raise ValueError("DataFrame must have a 'valid_date' column")
    return df.sort("valid_date")
