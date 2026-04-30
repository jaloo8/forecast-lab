"""Per-(station, month) Gaussian climatology + lead-time-weighted blend.

Per the [Pass 1 extension memo §5](../../docs/research/PASS-1-EXTENSION-EMOS-EXECUTION.md):

> "At lead 5-7d our parametric tails are too thin; blend toward climatology
> with weight = exp(-lead/τ), τ ≈ 4 days. Defends Phase 5 reliability gate
> at the wings."

The blend formula is:

    P_blended = w * P_model + (1 - w) * P_climatology
    w = exp(-lead_days / tau_days)

At ``lead_days = 1, tau = 4`` the weight on the model is ``exp(-0.25) ≈ 0.78``
(climatology gets 22%). At ``lead = 5, tau = 4`` model weight drops to
``exp(-1.25) ≈ 0.29``. This is the standard linear blend used in the
operational literature (Wessel, Ferro, Kwasniok 2024 *QJRMS*; Hamill-Whitaker
analog).

**Climatology fit.** One Gaussian ``N(mu, sigma^2)`` per ``(station, month)``,
fit from training-fold observed Tmax. Falls through to a station-level
Gaussian when the per-month bucket has fewer than ``min_samples_per_month``
training rows. PIT-correct: each fold re-fits on its own training portion.

**Why per-month, not per-day-of-year?** Our v1 backfill window is ~14 months,
giving roughly 1 sample per (station, day-of-year). Per-month aggregation
gives ~30 samples/bucket — enough to fit a stable Gaussian without
over-smoothing seasonality. A finer grid (per-week, ±15-day window) would
need a multi-year reforecast climatology archive — out of scope for v1.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date as date_t
from typing import Final

import numpy as np
from scipy import stats

PROB_CLIP_LOW: Final = 0.01
PROB_CLIP_HIGH: Final = 0.99
DEFAULT_MIN_SAMPLES_PER_MONTH: Final = 10
DEFAULT_TAU_DAYS: Final = 4.0
SIGMA_FLOOR_F: Final = 1.0


@dataclass
class StationClimatology:
    """Per-(station, month) Gaussian climatology fit from observed truth.

    Two-tier lookup: month-specific Gaussian first, station-overall Gaussian
    as fallback. Empty (unfit) state returns ``None`` from ``predict_proba``,
    letting callers skip the blend gracefully.
    """

    by_station_month: dict[tuple[str, int], tuple[float, float]] = field(default_factory=dict)
    by_station: dict[str, tuple[float, float]] = field(default_factory=dict)
    min_samples_per_month: int = DEFAULT_MIN_SAMPLES_PER_MONTH

    def fit_one_station(
        self,
        station: str,
        rows: Iterable[tuple[date_t, float]],
    ) -> StationClimatology:
        """Fit (station, month) Gaussians from ``(valid_date, observed_high)`` pairs.

        Also fits a station-overall Gaussian as a fallback for months with
        sparse coverage. Drops NaN observations defensively.
        """
        by_month: dict[int, list[float]] = defaultdict(list)
        all_values: list[float] = []
        for valid_date, observed_high in rows:
            if observed_high is None or math.isnan(observed_high):
                continue
            by_month[valid_date.month].append(float(observed_high))
            all_values.append(float(observed_high))
        for month, values in by_month.items():
            if len(values) >= self.min_samples_per_month:
                arr = np.asarray(values, dtype=float)
                mu = float(arr.mean())
                sigma = float(arr.std(ddof=1)) if arr.size > 1 else 0.0
                self.by_station_month[(station, month)] = (
                    mu,
                    max(sigma, SIGMA_FLOOR_F),
                )
        if len(all_values) >= 2:
            arr = np.asarray(all_values, dtype=float)
            self.by_station[station] = (
                float(arr.mean()),
                max(float(arr.std(ddof=1)), SIGMA_FLOOR_F),
            )
        return self

    def predict_proba(
        self,
        station: str,
        valid_date: date_t,
        threshold: float,
    ) -> float | None:
        """``P(Tmax > threshold)`` under the per-(station, month) Gaussian, or None.

        Falls back to the station-overall Gaussian when the per-month bucket
        is missing. Returns ``None`` only when neither fit exists — caller
        should skip the blend in that case.
        """
        params = self.by_station_month.get((station, valid_date.month))
        if params is None:
            params = self.by_station.get(station)
        if params is None:
            return None
        mu, sigma = params
        prob = float(stats.norm.sf(threshold, loc=mu, scale=sigma))
        return float(np.clip(prob, PROB_CLIP_LOW, PROB_CLIP_HIGH))


def blend_probability(
    model_prob: float,
    climatology_prob: float,
    *,
    lead_days: int,
    tau_days: float = DEFAULT_TAU_DAYS,
) -> float:
    """Linear blend ``w * model + (1-w) * climatology``, ``w = exp(-lead/tau)``.

    At ``lead_days = 1, tau = 4`` model gets weight 0.78. At ``lead = 5``
    weight drops to 0.29 — climatology dominates at long lead, defending
    against over-confident parametric tails.

    Returns the blended probability clipped to ``[0.01, 0.99]``.
    """
    if tau_days <= 0:
        raise ValueError(f"tau_days must be > 0, got {tau_days}")
    if lead_days < 0:
        raise ValueError(f"lead_days must be >= 0, got {lead_days}")
    w = math.exp(-lead_days / tau_days)
    blended = w * model_prob + (1.0 - w) * climatology_prob
    return float(np.clip(blended, PROB_CLIP_LOW, PROB_CLIP_HIGH))
