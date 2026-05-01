"""Tests for the per-(station, month) climatology + lead-time blend."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest
from scipy import stats

from kq.models.climatology import (
    DEFAULT_TAU_DAYS,
    PROB_CLIP_HIGH,
    PROB_CLIP_LOW,
    SIGMA_FLOOR_F,
    StationClimatology,
    blend_probability,
)

# --------------------------- StationClimatology.fit ---------------------------


def test_fit_one_station_groups_by_month() -> None:
    """Per-month Gaussians built from training rows, each with mean + sigma."""
    rng = np.random.default_rng(0)
    rows = []
    # 30 January days at mean 50, std 5
    for day in range(1, 31):
        rows.append((date(2025, 1, day), 50.0 + rng.normal(0, 5)))
    # 30 July days at mean 90, std 4
    for day in range(1, 31):
        rows.append((date(2025, 7, day), 90.0 + rng.normal(0, 4)))

    clim = StationClimatology(min_samples_per_month=10).fit_one_station("KAUS", rows)

    jan = clim.by_station_month[("KAUS", 1)]
    jul = clim.by_station_month[("KAUS", 7)]
    assert 45.0 < jan[0] < 55.0  # mean
    assert 3.0 < jan[1] < 7.0  # sigma
    assert 87.0 < jul[0] < 93.0
    # Station-overall fit also present.
    assert "KAUS" in clim.by_station


def test_fit_skips_sparse_months() -> None:
    """Months with fewer than min_samples are dropped from per-month dict."""
    rows = [(date(2025, 3, d), 60.0) for d in range(1, 8)]  # 7 samples in March
    clim = StationClimatology(min_samples_per_month=10).fit_one_station("KAUS", rows)
    assert ("KAUS", 3) not in clim.by_station_month
    # Station-overall fit still present (uses all rows; min_samples is 2 there).
    assert "KAUS" in clim.by_station


def test_fit_drops_nan_observations() -> None:
    """NaN observations are filtered before counting + fit."""
    rows: list[tuple[date, float]] = [
        (date(2025, 1, d), 50.0 if d != 5 else float("nan")) for d in range(1, 25)
    ]
    clim = StationClimatology(min_samples_per_month=5).fit_one_station("KAUS", rows)
    jan = clim.by_station_month[("KAUS", 1)]
    # All non-NaN values are 50 → mean ≈ 50, sigma at floor.
    assert jan[0] == pytest.approx(50.0)
    assert jan[1] == pytest.approx(SIGMA_FLOOR_F)


def test_fit_sigma_floor_applied() -> None:
    """Constant observations produce sigma at the SIGMA_FLOOR_F floor."""
    rows = [(date(2025, 1, d), 50.0) for d in range(1, 31)]
    clim = StationClimatology(min_samples_per_month=10).fit_one_station("KAUS", rows)
    _mu, sigma = clim.by_station_month[("KAUS", 1)]
    assert sigma == pytest.approx(SIGMA_FLOOR_F)


# --------------------------- predict_proba ---------------------------


def test_predict_proba_uses_per_month_fit() -> None:
    """If month-specific fit exists, use it (not the station-overall fallback)."""
    clim = StationClimatology()
    clim.by_station_month[("KAUS", 7)] = (90.0, 4.0)
    clim.by_station[("KAUS")] = (75.0, 10.0)  # different fallback
    p_july = clim.predict_proba("KAUS", date(2025, 7, 15), threshold=88.0)
    raw = float(stats.norm.sf(88.0, loc=90.0, scale=4.0))
    expected = float(np.clip(raw, PROB_CLIP_LOW, PROB_CLIP_HIGH))
    assert p_july == pytest.approx(expected)


def test_predict_proba_falls_back_to_station_when_month_missing() -> None:
    clim = StationClimatology()
    clim.by_station["KAUS"] = (75.0, 10.0)
    # No per-month fit exists for July.
    p = clim.predict_proba("KAUS", date(2025, 7, 15), threshold=80.0)
    raw = float(stats.norm.sf(80.0, loc=75.0, scale=10.0))
    expected = float(np.clip(raw, PROB_CLIP_LOW, PROB_CLIP_HIGH))
    assert p == pytest.approx(expected)


def test_predict_proba_returns_none_when_unfit() -> None:
    clim = StationClimatology()
    assert clim.predict_proba("KAUS", date(2025, 7, 15), threshold=80.0) is None


def test_predict_proba_clipped_to_bounds() -> None:
    clim = StationClimatology()
    clim.by_station_month[("KAUS", 7)] = (90.0, 4.0)
    # Threshold way below mean → P → 1, clipped to 0.99.
    assert clim.predict_proba("KAUS", date(2025, 7, 1), 50.0) == pytest.approx(PROB_CLIP_HIGH)
    # Threshold way above mean → P → 0, clipped to 0.01.
    assert clim.predict_proba("KAUS", date(2025, 7, 1), 200.0) == pytest.approx(PROB_CLIP_LOW)


# --------------------------- blend_probability ---------------------------


def test_blend_at_lead_zero_is_pure_model() -> None:
    """w = exp(0) = 1 → 100% model weight, 0% climatology."""
    blended = blend_probability(0.6, 0.3, lead_days=0, tau_days=4.0)
    assert blended == pytest.approx(0.6)


def test_blend_at_long_lead_dominates_climatology() -> None:
    """At lead=20, tau=4 → model weight ~ exp(-5) ~ 0.007; climatology dominates."""
    blended = blend_probability(0.99, 0.3, lead_days=20, tau_days=4.0)
    # Should be close to climatology (0.3) since model weight is tiny.
    assert abs(blended - 0.3) < 0.01


def test_blend_default_tau_at_lead_one() -> None:
    """At lead=1, tau=4 → model weight = exp(-0.25) ≈ 0.7788."""
    w_expected = math.exp(-0.25)
    blended = blend_probability(0.7, 0.4, lead_days=1, tau_days=DEFAULT_TAU_DAYS)
    expected = w_expected * 0.7 + (1.0 - w_expected) * 0.4
    assert blended == pytest.approx(expected)


def test_blend_clipped_to_bounds() -> None:
    """Even if both inputs are at bounds, blend stays in [0.01, 0.99]."""
    blended_low = blend_probability(0.01, 0.01, lead_days=1, tau_days=4.0)
    blended_high = blend_probability(0.99, 0.99, lead_days=1, tau_days=4.0)
    assert blended_low == pytest.approx(PROB_CLIP_LOW)
    assert blended_high == pytest.approx(PROB_CLIP_HIGH)


def test_blend_validates_inputs() -> None:
    with pytest.raises(ValueError, match="tau_days"):
        blend_probability(0.5, 0.5, lead_days=1, tau_days=0.0)
    with pytest.raises(ValueError, match="lead_days"):
        blend_probability(0.5, 0.5, lead_days=-1, tau_days=4.0)


# --------------------------- end-to-end ---------------------------


def test_climatology_blend_pulls_overconfident_wing_toward_truth() -> None:
    """Synthetic check: model says wing is impossible (P=0.01) but it actually fires;
    climatology with realistic tail width pulls the blend toward truth.
    """
    # Climatology: KMIA July, mean 90F, std 4F. P(Tmax > 95F) ≈ 0.106
    clim = StationClimatology()
    clim.by_station_month[("KMIA", 7)] = (90.0, 4.0)

    model_prob = 0.01  # pathologically over-confident "no"
    clim_prob = clim.predict_proba("KMIA", date(2025, 7, 15), 95.0)
    assert clim_prob is not None
    assert 0.05 < clim_prob < 0.20  # ~0.106 expected

    blended = blend_probability(model_prob, clim_prob, lead_days=1, tau_days=4.0)
    # At lead=1, model weight 0.78. Blend pulled toward climatology's 0.10
    # by ~22% — meaningful damping of the over-confident "no".
    assert blended > 0.02  # noticeably above pure model
    assert blended < clim_prob  # but not all the way to climatology
