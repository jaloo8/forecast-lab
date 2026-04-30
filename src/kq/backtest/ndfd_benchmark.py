"""NDFD/NBM benchmark utilities for the backtest engine.

Pure functions: per-fold residual-sigma fit, Gaussian-exceedance probability,
and the NDFD-row → {station: {valid_date: forecast_max_f}} loader. Kept
separate from ``engine.py`` so the math is testable in isolation and the
engine integration stays surgical.

The benchmark used here is **NBM-deterministic + per-fold-fitted Gaussian
sigma** — see ``docs/research/NDFD-BENCHMARK-SOURCE.md`` for the source
decision and the upgrade path to true probabilistic NBM ``qmd``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_t
from typing import Final

import duckdb
import numpy as np
from scipy.stats import norm

# Minimum (NBM, observed) pairs needed to fit a stable per-fold sigma. Below
# this, return None and skip NDFD comparison for that fold — better to mark
# the fold "no NDFD coverage" than emit a sigma fit on 3 data points.
DEFAULT_MIN_PAIRS: Final[int] = 10

# Floor matching engine.py's market_sigma_f handling — never collapse the
# distribution to a degenerate point mass even if residuals happen to align.
DEFAULT_SIGMA_FLOOR_F: Final[float] = 1.0

# Match engine.py's brier_score input clamp.
_PROB_CLIP: Final[tuple[float, float]] = (0.01, 0.99)


@dataclass(frozen=True, slots=True)
class NdfdLookup:
    """Per-station map of (valid_date → NBM forecast Tmax in °F).

    Built once per backtest run; consumed inside the per-fold loop.
    Stations missing from the lookup return an empty dict via
    ``for_station`` rather than raising.
    """

    by_station: dict[str, dict[date_t, float]] = field(default_factory=dict)

    def for_station(self, station: str) -> dict[date_t, float]:
        return self.by_station.get(station, {})


def fit_residual_sigma(
    nbm_forecasts: np.ndarray,
    observed_highs: np.ndarray,
    *,
    min_pairs: int = DEFAULT_MIN_PAIRS,
    sigma_floor: float = DEFAULT_SIGMA_FLOOR_F,
) -> float | None:
    """Fit Gaussian sigma from element-wise (NBM - observed) residuals.

    Returns ``None`` when fewer than ``min_pairs`` valid pairs exist after
    dropping NaN rows on either side. Sample std uses ``ddof=1``; the result
    is clamped to ``sigma_floor`` (default 1°F) to mirror the engine's own
    sigma floor on NGR's ``raw_residual_std``.
    """
    if nbm_forecasts.shape != observed_highs.shape:
        raise ValueError(
            f"shape mismatch: {nbm_forecasts.shape} vs {observed_highs.shape}"
        )
    valid = ~(np.isnan(nbm_forecasts) | np.isnan(observed_highs))
    if int(valid.sum()) < min_pairs:
        return None
    residuals = nbm_forecasts[valid] - observed_highs[valid]
    return max(float(np.std(residuals, ddof=1)), sigma_floor)


def gaussian_exceedance(mean: float, sigma: float, threshold: float) -> float:
    """``P(X > threshold)`` for ``X ~ N(mean, sigma^2)``, clipped to [0.01, 0.99].

    Same clip range as ``brier_score`` in ``kq.models.calibration`` so the
    benchmark probability lives in the same numeric regime as our model's.
    """
    if sigma <= 0:
        raise ValueError(f"sigma must be > 0, got {sigma}")
    z = (threshold - mean) / sigma
    p = 1.0 - float(norm.cdf(z))
    return float(np.clip(p, *_PROB_CLIP))


def load_ndfd_lookup(
    con: duckdb.DuckDBPyConnection,
    *,
    source: str = "nbm_deterministic_openmeteo",
    lead_days: int = 1,
) -> NdfdLookup:
    """Load NDFD forecast rows into a station-keyed lookup.

    Defaults to v1's deterministic source at lead-1 — the operational
    backtest join shape (lead-1 corresponds to "yesterday's day-ahead
    forecast for today's settlement"). When multiple ``as_of`` rows exist
    for the same (station, valid_date), the one with the largest ``as_of``
    wins — that's the freshest forecast we'd have had access to before the
    market closed.
    """
    sql = """
        SELECT station, valid_date, forecast_max_f, as_of
        FROM ndfd_forecast
        WHERE source = ? AND lead_days = ?
        ORDER BY station, valid_date, as_of
    """
    rows = con.execute(sql, [source, lead_days]).fetchall()
    by_station: dict[str, dict[date_t, float]] = {}
    for station, valid_date, forecast_max_f, _as_of in rows:
        if forecast_max_f is None:
            continue
        # Later as_of overwrites earlier (rows sorted ascending).
        by_station.setdefault(station, {})[valid_date] = float(forecast_max_f)
    return NdfdLookup(by_station=by_station)
