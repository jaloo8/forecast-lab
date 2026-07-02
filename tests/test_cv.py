"""Tests for rolling-origin time-series cross-validation."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from kq.models.cv import rolling_origin_splits, sort_by_valid_date


def test_basic_split_shapes() -> None:
    # Default step_size = test_window_size (non-overlapping test windows,
    # 2026-06-11 audit root cause #9): train_end goes 60, 70, 80, 90 → 4 folds.
    # Default embargo=1 (2026-07-01 audit): each fold's training set drops
    # its trailing sample, so the first fold trains on 59 rows.
    splits = list(rolling_origin_splits(n_samples=100, initial_train_size=60, test_window_size=10))
    assert len(splits) == 4
    for train_idx, test_idx in splits:
        assert len(train_idx) >= 59
        assert len(test_idx) == 10
        # Train always strictly precedes test
        assert train_idx.max() < test_idx.min()


def test_default_step_yields_non_overlapping_test_windows() -> None:
    """2026-06-11 audit root cause #9: the old default (step_size=1) put every
    sample in up to `test_window_size` overlapping test windows, replicating
    each evaluation ~14x in every manifest statistic. The default must make
    each index appear in AT MOST ONE test window."""
    seen: set[int] = set()
    for _, test_idx in rolling_origin_splits(
        n_samples=200, initial_train_size=60, test_window_size=14
    ):
        overlap = seen & set(test_idx.tolist())
        assert overlap == set()
        seen.update(test_idx.tolist())
    assert len(seen) > 0


def test_explicit_step_size_one_still_overlaps() -> None:
    """Diagnostic escape hatch: an explicit step_size=1 keeps the old
    sliding-by-one behavior (callers own the double-counting)."""
    splits = list(
        rolling_origin_splits(
            n_samples=100, initial_train_size=60, test_window_size=10, step_size=1
        )
    )
    # train_end goes 60, 61, ..., 90 inclusive = 31 folds.
    assert len(splits) == 31


def test_step_size_changes_fold_count() -> None:
    splits = list(
        rolling_origin_splits(
            n_samples=100, initial_train_size=60, test_window_size=10, step_size=5
        )
    )
    # train_end goes 60, 65, 70, ..., last where train_end + 10 <= 100 → train_end <= 90
    # That's 60, 65, 70, 75, 80, 85, 90 → 7 folds
    assert len(splits) == 7


def test_returns_nothing_when_too_small() -> None:
    splits = list(rolling_origin_splits(n_samples=10, initial_train_size=60, test_window_size=10))
    assert splits == []


def test_invalid_args_raise() -> None:
    with pytest.raises(ValueError, match="positive"):
        list(rolling_origin_splits(n_samples=100, initial_train_size=0, test_window_size=10))
    with pytest.raises(ValueError, match="positive"):
        list(rolling_origin_splits(n_samples=100, initial_train_size=10, test_window_size=0))


def test_train_window_grows_each_fold() -> None:
    """Rolling-origin: train always grows; test is fixed-size sliding."""
    splits = list(rolling_origin_splits(n_samples=50, initial_train_size=20, test_window_size=5))
    train_sizes = [len(t) for t, _ in splits]
    assert train_sizes == sorted(train_sizes)
    assert train_sizes[0] == 19  # 20 minus the default 1-sample embargo
    assert train_sizes[-1] >= 19


def test_no_overlap_between_train_and_test() -> None:
    for train_idx, test_idx in rolling_origin_splits(
        n_samples=80, initial_train_size=30, test_window_size=10
    ):
        assert set(train_idx).isdisjoint(set(test_idx))


# --------------------------------------------------------- embargo (2026-07-01)


def test_default_embargo_leaves_one_sample_gap() -> None:
    """As_of-aware embargo (2026-07-01 audit): the sample immediately before
    each test window is dropped from training — its label (lead-1 settlement)
    is not yet settled at the test window's signal time. With embargo=1 the
    index gap between train end and test start must be exactly 2 (one
    embargoed index in between). Fails on the old adjacent-fold behavior."""
    splits = list(rolling_origin_splits(n_samples=100, initial_train_size=60, test_window_size=10))
    assert splits
    for train_idx, test_idx in splits:
        assert int(test_idx.min()) - int(train_idx.max()) == 2
        # The embargoed index belongs to NEITHER set.
        embargoed = int(train_idx.max()) + 1
        assert embargoed not in set(train_idx.tolist())
        assert embargoed not in set(test_idx.tolist())


def test_embargo_does_not_move_test_windows() -> None:
    """The embargo shrinks training sets only; the evaluated test days must be
    identical with and without it, so fold counts and n_evaluated stay
    comparable across embargo settings."""
    with_embargo = list(
        rolling_origin_splits(n_samples=100, initial_train_size=60, test_window_size=10, embargo=1)
    )
    without = list(
        rolling_origin_splits(n_samples=100, initial_train_size=60, test_window_size=10, embargo=0)
    )
    assert len(with_embargo) == len(without)
    for (_, test_a), (_, test_b) in zip(with_embargo, without, strict=True):
        assert test_a.tolist() == test_b.tolist()


def test_embargo_zero_restores_adjacency() -> None:
    splits = list(
        rolling_origin_splits(n_samples=100, initial_train_size=60, test_window_size=10, embargo=0)
    )
    for train_idx, test_idx in splits:
        assert int(test_idx.min()) - int(train_idx.max()) == 1


def test_embargo_matches_longer_label_horizon() -> None:
    """embargo=lead_days: a lead-3 backtest must embargo 3 trailing samples."""
    splits = list(
        rolling_origin_splits(n_samples=100, initial_train_size=60, test_window_size=10, embargo=3)
    )
    for train_idx, test_idx in splits:
        assert int(test_idx.min()) - int(train_idx.max()) == 4


def test_embargo_validation() -> None:
    with pytest.raises(ValueError, match="embargo"):
        list(
            rolling_origin_splits(
                n_samples=100, initial_train_size=60, test_window_size=10, embargo=-1
            )
        )
    with pytest.raises(ValueError, match="embargo"):
        list(
            rolling_origin_splits(
                n_samples=100, initial_train_size=10, test_window_size=10, embargo=10
            )
        )


def test_sort_by_valid_date_orders_chronologically() -> None:
    df = pl.DataFrame(
        {
            "valid_date": [date(2025, 1, 3), date(2025, 1, 1), date(2025, 1, 2)],
            "value": [3, 1, 2],
        }
    )
    sorted_df = sort_by_valid_date(df)
    assert sorted_df["value"].to_list() == [1, 2, 3]


def test_sort_by_valid_date_requires_column() -> None:
    df = pl.DataFrame({"x": [1, 2, 3]})
    with pytest.raises(ValueError, match="valid_date"):
        sort_by_valid_date(df)
