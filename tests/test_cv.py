"""Tests for rolling-origin time-series cross-validation."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from kq.models.cv import rolling_origin_splits, sort_by_valid_date


def test_basic_split_shapes() -> None:
    splits = list(rolling_origin_splits(n_samples=100, initial_train_size=60, test_window_size=10))
    # train_end goes 60, 61, ..., last where train_end + 10 <= 100 → 60..90 inclusive = 31 folds
    assert len(splits) == 31
    for train_idx, test_idx in splits:
        assert len(train_idx) >= 60
        assert len(test_idx) == 10
        # Train always strictly precedes test
        assert train_idx.max() < test_idx.min()


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
    assert train_sizes[0] == 20
    assert train_sizes[-1] >= 20


def test_no_overlap_between_train_and_test() -> None:
    for train_idx, test_idx in rolling_origin_splits(
        n_samples=80, initial_train_size=30, test_window_size=10
    ):
        assert set(train_idx).isdisjoint(set(test_idx))


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
