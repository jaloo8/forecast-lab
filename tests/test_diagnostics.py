"""Tests for the verdict-deepening diagnostics."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from kq.backtest.diagnostics import bracket_band, per_band_brier, per_month_metrics

# --------------------------- bracket_band ---------------------------


def test_bracket_band_seven_brackets() -> None:
    """7 brackets → center = {2,3,4}, wing = {0,1,5,6}."""
    assert [bracket_band(i, 7) for i in range(7)] == [
        "wing",
        "wing",
        "center",
        "center",
        "center",
        "wing",
        "wing",
    ]


def test_bracket_band_three_brackets_all_center() -> None:
    """With only 3 brackets, |i - 1| <= 1 for every i → center for all."""
    assert [bracket_band(i, 3) for i in range(3)] == ["center"] * 3


def test_bracket_band_five_brackets() -> None:
    """5 brackets → center = {1,2,3}, wing = {0,4}."""
    assert [bracket_band(i, 5) for i in range(5)] == [
        "wing",
        "center",
        "center",
        "center",
        "wing",
    ]


def test_bracket_band_validates_inputs() -> None:
    with pytest.raises(ValueError, match="n_brackets"):
        bracket_band(0, 0)
    with pytest.raises(ValueError, match="out of range"):
        bracket_band(7, 7)
    with pytest.raises(ValueError, match="out of range"):
        bracket_band(-1, 7)


# --------------------------- per_band_brier ---------------------------


def test_per_band_brier_separates_center_and_wings() -> None:
    """Construct a fixture where center bands have lower model Brier than wings.

    Center rows: model is correct (prob 0.99 when outcome 1, 0.01 when 0).
    Wing rows: model is wrong (flipped).
    NDFD always at 0.5 → Brier = 0.25 baseline everywhere.
    """
    n_brackets = 7
    # Two test days, all 7 brackets each → 14 rows total.
    bracket_idx = np.array([0, 1, 2, 3, 4, 5, 6, 0, 1, 2, 3, 4, 5, 6])
    # center positions are 2, 3, 4
    is_center = np.array([bracket_band(int(i), n_brackets) == "center" for i in bracket_idx])
    outcomes = np.array([1.0] * 14)
    model_probs = np.where(is_center, 0.99, 0.01)
    ndfd_probs = np.full(14, 0.5)

    out = per_band_brier(
        bracket_idx=bracket_idx,
        model_probs=model_probs,
        ndfd_probs=ndfd_probs,
        outcomes=outcomes,
        n_brackets=n_brackets,
    )

    # Center: model is right → tiny Brier; NDFD at 0.5 → 0.25.
    center = out["center"]
    wing = out["wing"]
    assert center["n_with_ndfd"] == 6  # 2 days * 3 center brackets
    assert wing["n_with_ndfd"] == 8  # 2 days * 4 wing brackets
    # Center: model wins big → huge positive improvement.
    assert center["brier_improvement_vs_ndfd_pct"] is not None
    assert center["brier_improvement_vs_ndfd_pct"] > 90.0
    # Wing: model loses big → very negative improvement.
    assert wing["brier_improvement_vs_ndfd_pct"] is not None
    assert wing["brier_improvement_vs_ndfd_pct"] < -200.0


def test_per_band_brier_filters_nan_ndfd_rows() -> None:
    """Rows with NaN NDFD probability are dropped before band stats."""
    n_brackets = 7
    bracket_idx = np.array([2, 3, 4, 0, 6])  # 3 center, 2 wing
    outcomes = np.array([1.0, 1.0, 1.0, 0.0, 0.0])
    model_probs = np.array([0.7, 0.6, 0.65, 0.4, 0.3])
    # Drop one center + one wing via NaN.
    ndfd_probs = np.array([0.5, np.nan, 0.5, np.nan, 0.4])

    out = per_band_brier(
        bracket_idx=bracket_idx,
        model_probs=model_probs,
        ndfd_probs=ndfd_probs,
        outcomes=outcomes,
        n_brackets=n_brackets,
    )
    assert out["center"]["n_with_ndfd"] == 2
    assert out["wing"]["n_with_ndfd"] == 1


def test_per_band_brier_handles_empty_band() -> None:
    """Bracket-only-in-center fixture → wing band reports None."""
    bracket_idx = np.array([2, 3, 4, 2, 3])  # all center
    out = per_band_brier(
        bracket_idx=bracket_idx,
        model_probs=np.array([0.5] * 5),
        ndfd_probs=np.array([0.5] * 5),
        outcomes=np.array([1.0] * 5),
        n_brackets=7,
    )
    assert out["wing"]["n_with_ndfd"] == 0
    assert out["wing"]["brier_model_subset"] is None
    assert out["center"]["n_with_ndfd"] == 5


def test_per_band_brier_shape_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="shape mismatch"):
        per_band_brier(
            bracket_idx=np.array([0, 1, 2]),
            model_probs=np.array([0.5, 0.5]),
            ndfd_probs=np.array([0.5, 0.5, 0.5]),
            outcomes=np.array([1.0, 0.0, 1.0]),
            n_brackets=7,
        )


# --------------------------- per_month_metrics ---------------------------


def test_per_month_metrics_groups_and_sorts() -> None:
    """Two months x two days each, all matched - 2 rows sorted by month."""
    valid_dates = [
        date(2025, 1, 5),
        date(2025, 1, 12),
        date(2025, 2, 3),
        date(2025, 2, 19),
    ]
    model_probs = np.array([0.6, 0.6, 0.4, 0.4])
    ndfd_probs = np.array([0.5, 0.5, 0.5, 0.5])
    outcomes = np.array([1.0, 1.0, 0.0, 0.0])

    rows = per_month_metrics(
        valid_dates=valid_dates,
        model_probs=model_probs,
        ndfd_probs=ndfd_probs,
        outcomes=outcomes,
    )
    assert [r["month"] for r in rows] == ["2025-01", "2025-02"]
    # Jan: model says 0.6 with outcome 1 → better than ndfd (0.5).
    # Feb: model says 0.4 with outcome 0 → also better than ndfd.
    for r in rows:
        assert r["n_with_ndfd"] == 2
        assert r["brier_improvement_vs_ndfd_pct"] is not None
        assert r["brier_improvement_vs_ndfd_pct"] > 0
    # Jan model_prob - ndfd_prob = +0.1 → CLV +10pp.
    assert rows[0]["mean_clv_pp"] == pytest.approx(10.0, abs=0.01)
    assert rows[1]["mean_clv_pp"] == pytest.approx(-10.0, abs=0.01)


def test_per_month_metrics_drops_nan_rows() -> None:
    """NDFD-missing rows are filtered before grouping."""
    valid_dates = [date(2025, 1, 5), date(2025, 1, 6), date(2025, 1, 7)]
    rows = per_month_metrics(
        valid_dates=valid_dates,
        model_probs=np.array([0.6, 0.6, 0.6]),
        ndfd_probs=np.array([0.5, np.nan, 0.5]),
        outcomes=np.array([1.0, 1.0, 0.0]),
    )
    assert len(rows) == 1
    assert rows[0]["n_with_ndfd"] == 2


def test_per_month_metrics_sorts_lexicographically_across_year_boundary() -> None:
    """Cross-year input must sort by month string lexicographically."""
    valid_dates = [
        # Deliberately out of order; ascending YYYY-MM string sort should
        # land 2024-11 before 2025-01 (i.e., not by Python date order
        # mistakes that would put Jan before Nov within a year).
        date(2025, 1, 5),
        date(2024, 12, 1),
        date(2024, 11, 15),
    ]
    rows = per_month_metrics(
        valid_dates=valid_dates,
        model_probs=np.array([0.6, 0.6, 0.6]),
        ndfd_probs=np.array([0.5, 0.5, 0.5]),
        outcomes=np.array([1.0, 1.0, 1.0]),
    )
    assert [r["month"] for r in rows] == ["2024-11", "2024-12", "2025-01"]


def test_per_month_metrics_no_coverage_returns_empty() -> None:
    rows = per_month_metrics(
        valid_dates=[date(2025, 1, 1)],
        model_probs=np.array([0.5]),
        ndfd_probs=np.array([np.nan]),
        outcomes=np.array([1.0]),
    )
    assert rows == []


def test_per_month_metrics_length_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="length mismatch"):
        per_month_metrics(
            valid_dates=[date(2025, 1, 1), date(2025, 1, 2)],
            model_probs=np.array([0.5]),
            ndfd_probs=np.array([0.5]),
            outcomes=np.array([1.0]),
        )
