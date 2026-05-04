"""Tests for Combinatorial Purged CV."""

from __future__ import annotations

import numpy as np
import pytest

from kq.models.cpcv import cpcv_n_folds, cpcv_splits

# --------------------------- fold count ---------------------------


def test_cpcv_n_folds_canonical() -> None:
    """C(6, 2) = 15 — the default per López de Prado ch. 7."""
    assert cpcv_n_folds(n_groups=6, n_test_groups=2) == 15


def test_cpcv_n_folds_other_combinations() -> None:
    assert cpcv_n_folds(n_groups=10, n_test_groups=3) == 120
    assert cpcv_n_folds(n_groups=4, n_test_groups=1) == 4


def test_cpcv_n_folds_validates_inputs() -> None:
    with pytest.raises(ValueError, match=r"n_test_groups"):
        cpcv_n_folds(n_groups=6, n_test_groups=0)
    with pytest.raises(ValueError, match=r"n_test_groups"):
        cpcv_n_folds(n_groups=6, n_test_groups=6)


# --------------------------- splits structure ---------------------------


def test_cpcv_yields_expected_number_of_folds() -> None:
    """100 samples, 6 groups, k=2 -> C(6,2) = 15 folds."""
    folds = list(cpcv_splits(100, n_groups=6, n_test_groups=2))
    assert len(folds) == 15


def test_train_and_test_disjoint_in_every_fold() -> None:
    """No sample should appear in both train_idx and test_idx."""
    for train_idx, test_idx in cpcv_splits(100, n_groups=6, n_test_groups=2):
        assert np.intersect1d(train_idx, test_idx).size == 0


def test_test_idx_size_proportional_to_n_test_groups() -> None:
    """6-of-2 splits give 2/6 of the data as test -> ~33 of 100."""
    sizes = [len(test_idx) for _, test_idx in cpcv_splits(120, n_groups=6, n_test_groups=2)]
    # Each fold is exactly 2 of the 6 contiguous groups => 40 (= 120 * 2/6).
    assert all(s == 40 for s in sizes)


def test_indices_are_within_n_samples() -> None:
    n = 100
    for train_idx, test_idx in cpcv_splits(n, n_groups=6, n_test_groups=2):
        assert train_idx.min() >= 0 and train_idx.max() < n
        assert test_idx.min() >= 0 and test_idx.max() < n


# --------------------------- purging ---------------------------


def test_purging_drops_overlapping_train_samples() -> None:
    """With label_horizon=5, training samples in the 4 positions
    BEFORE a test sample should be purged (their labels would
    overlap into test territory)."""
    n = 60
    label_horizon = 5
    folds = list(cpcv_splits(n, n_groups=6, n_test_groups=1, label_horizon=label_horizon))
    for train_idx, test_idx in folds:
        # Earliest test index in this fold.
        earliest_test = test_idx.min()
        # Any train_idx in [earliest_test - label_horizon + 1, earliest_test - 1]
        # would have a label that overlaps the test set -> must be purged.
        purge_zone_start = max(0, earliest_test - label_horizon + 1)
        purge_zone_end = earliest_test
        in_purge_zone = train_idx[(train_idx >= purge_zone_start) & (train_idx < purge_zone_end)]
        assert in_purge_zone.size == 0, (
            f"train_idx in purge zone for test starting at {earliest_test}: {in_purge_zone}"
        )


def test_purging_with_horizon_1_drops_nothing() -> None:
    """label_horizon=1 means each label is a single point -> no overlap
    purging needed (only the test mask itself is excluded)."""
    folds_h1 = list(cpcv_splits(60, n_groups=6, n_test_groups=2, label_horizon=1))
    folds_h5 = list(cpcv_splits(60, n_groups=6, n_test_groups=2, label_horizon=5))
    for (train_h1, test_h1), (train_h5, test_h5) in zip(folds_h1, folds_h5, strict=True):
        # h1 should yield at least as many train samples as h5 (less purging).
        assert len(train_h1) >= len(train_h5)
        assert np.array_equal(test_h1, test_h5)  # test sets are identical


# --------------------------- embargo ---------------------------


def test_embargo_drops_post_test_train_samples() -> None:
    """Embargo of 5 -> training samples in the 5 positions AFTER each
    test group's last index should be excluded from train_idx."""
    n = 60
    embargo = 5
    folds = list(cpcv_splits(n, n_groups=6, n_test_groups=1, embargo=embargo))
    for train_idx, test_idx in folds:
        last_test = test_idx.max()
        embargo_zone = np.arange(last_test + 1, min(n, last_test + 1 + embargo))
        in_embargo = train_idx[np.isin(train_idx, embargo_zone)]
        assert in_embargo.size == 0


def test_embargo_zero_is_identity() -> None:
    folds_no_embargo = list(cpcv_splits(60, n_groups=6, n_test_groups=2, embargo=0))
    folds_with_embargo = list(cpcv_splits(60, n_groups=6, n_test_groups=2, embargo=3))
    # Same number of folds either way.
    assert len(folds_no_embargo) == len(folds_with_embargo)
    # With embargo, train sets are at most as large as without.
    for (train_no, _), (train_em, _) in zip(folds_no_embargo, folds_with_embargo, strict=True):
        assert len(train_em) <= len(train_no)


# --------------------------- input validation ---------------------------


def test_n_groups_too_large_raises() -> None:
    with pytest.raises(ValueError, match=r"n_groups"):
        list(cpcv_splits(5, n_groups=10, n_test_groups=2))


def test_invalid_n_test_groups_raises() -> None:
    with pytest.raises(ValueError, match=r"n_test_groups"):
        list(cpcv_splits(60, n_groups=6, n_test_groups=0))
    with pytest.raises(ValueError, match=r"n_test_groups"):
        list(cpcv_splits(60, n_groups=6, n_test_groups=6))


def test_invalid_label_horizon_raises() -> None:
    with pytest.raises(ValueError, match=r"label_horizon"):
        list(cpcv_splits(60, n_groups=6, n_test_groups=2, label_horizon=0))


def test_invalid_embargo_raises() -> None:
    with pytest.raises(ValueError, match=r"embargo"):
        list(cpcv_splits(60, n_groups=6, n_test_groups=2, embargo=-1))


def test_n_samples_zero_yields_no_folds() -> None:
    assert list(cpcv_splits(0, n_groups=6, n_test_groups=2)) == []


# --------------------------- contiguity property ---------------------------


def test_groups_are_contiguous_blocks() -> None:
    """Each test fold's index set should consist of contiguous
    blocks (n_test_groups of them at most). This is a structural
    property -- ensures groups respect time order, never random
    samples."""
    for _, test_idx in cpcv_splits(120, n_groups=6, n_test_groups=2):
        # Count discontinuities -- there should be at most n_test_groups - 1.
        diffs = np.diff(test_idx)
        n_discontinuities = int((diffs > 1).sum())
        assert n_discontinuities <= 2 - 1  # n_test_groups - 1


def test_train_set_includes_samples_outside_test_and_purge_zones() -> None:
    """Sanity: training set isn't pathologically empty for typical inputs."""
    folds = list(cpcv_splits(120, n_groups=6, n_test_groups=2, label_horizon=2, embargo=2))
    for train_idx, _ in folds:
        # Default 6-choose-2 + tiny purge/embargo should leave plenty.
        assert train_idx.size > 60  # > half the data
