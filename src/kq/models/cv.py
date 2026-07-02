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

DEFAULT_EMBARGO: int = 1  # v1 label horizon: lead-1 settlement day


def rolling_origin_splits(
    n_samples: int,
    *,
    initial_train_size: int,
    test_window_size: int,
    step_size: int | None = None,
    embargo: int = DEFAULT_EMBARGO,
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

    ``embargo`` (2026-07-01 audit, Tier 2) is the as_of-aware gap between
    the end of train and the start of test: the last ``embargo`` samples
    before each test window are dropped from that fold's training set.
    Rationale: at lead ``L`` the signal for test day ``T`` is generated on
    day ``T - L``, but the LABEL for day ``T - 1`` (and, generally, days
    ``T - L`` .. ``T - 1``) is not settled at that signal time — training
    on it is look-ahead. Default is 1, the v1 lead-1 label horizon;
    callers backtesting a longer lead must pass ``embargo=lead_days``.
    ``embargo=0`` disables the guard (diagnostics only). Test-window
    positions are unchanged by the embargo — only training sets shrink —
    so fold counts and evaluated days stay comparable across settings.

    Indices are treated as consecutive periods (daily rows in v1); gaps in
    the underlying calendar make the embargo conservative-or-exact, never
    leaky, as long as rows are chronologically sorted.
    """
    if step_size is None:
        step_size = test_window_size
    if n_samples < initial_train_size + test_window_size:
        return
    if initial_train_size <= 0 or test_window_size <= 0 or step_size <= 0:
        raise ValueError("initial_train_size, test_window_size, step_size must be positive")
    if embargo < 0:
        raise ValueError(f"embargo must be >= 0, got {embargo}")
    if embargo >= initial_train_size:
        raise ValueError(
            f"embargo ({embargo}) must be smaller than initial_train_size "
            f"({initial_train_size}); no training samples would remain"
        )

    train_end = initial_train_size
    while train_end + test_window_size <= n_samples:
        train_idx = np.arange(0, train_end - embargo)
        test_idx = np.arange(train_end, train_end + test_window_size)
        yield train_idx, test_idx
        train_end += step_size


def sort_by_valid_date(df: pl.DataFrame) -> pl.DataFrame:
    """Defensive sort so split indices map to chronological order."""
    if "valid_date" not in df.columns:
        raise ValueError("DataFrame must have a 'valid_date' column")
    return df.sort("valid_date")
