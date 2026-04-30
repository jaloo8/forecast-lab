"""NDFD/NBM benchmark utilities for the backtest engine.

Pure functions: per-fold residual ``(bias, sigma)`` fit, Gaussian-exceedance
probability, and the NDFD-row → ``{station: {valid_date: forecast_max_f}}``
loader. Kept separate from ``engine.py`` so the math is testable in
isolation and the engine integration stays surgical.

The benchmark used here is **NBM-deterministic with per-fold bias correction
+ Gaussian residual sigma** — see ``docs/research/NDFD-BENCHMARK-SOURCE.md``
for the source decision and the upgrade path to true probabilistic NBM ``qmd``.

**Bias term.** Empirically, Open-Meteo's NBM underforecasts CONUS Tmax by
0.9-3.6 °F (verified 2026-04-29 against 162 station-days/station of joint
NDFD + NWS-observed truth). Fitting only the residual sigma without
subtracting the mean residual handicaps NDFD: the predictive Gaussian
``N(nbm, sigma^2)`` is centered on the wrong mean. The correct calibrated
predictive distribution is ``N(nbm - bias, sigma^2)`` where
``bias = mean(nbm - obs)``. ``fit_residual_stats`` returns both; the engine
subtracts ``bias`` from ``nbm_mean`` before calling ``gaussian_exceedance``.
This is the conventional EMOS bias correction, not a novel adjustment.
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


def fit_residual_stats(
    nbm_forecasts: np.ndarray,
    observed_highs: np.ndarray,
    *,
    min_pairs: int = DEFAULT_MIN_PAIRS,
    sigma_floor: float = DEFAULT_SIGMA_FLOOR_F,
) -> tuple[float, float] | None:
    """Fit ``(bias, sigma)`` from element-wise ``(NBM - observed)`` residuals.

    Returns:
        ``(bias, sigma)`` where ``bias = mean(nbm - obs)`` is the systematic
        per-fold offset (positive when NBM overforecasts), and ``sigma`` is the
        sample std of residuals (``ddof=1``) clamped to ``sigma_floor``.
        Returns ``None`` when fewer than ``min_pairs`` valid pairs exist after
        NaN-filtering on either side.

    The engine consumes this by treating the calibrated NBM predictive as
    ``Tmax | nbm ~ N(nbm - bias, sigma^2)`` — i.e., subtract bias from the
    forecast mean before the Gaussian-exceedance call. This is the standard
    EMOS bias correction; without it the benchmark is structurally wrong on
    biased stations (KLAX bias ~ -3.6 °F = ~-1.6 sigma at v1's parameters).
    """
    if nbm_forecasts.shape != observed_highs.shape:
        raise ValueError(
            f"shape mismatch: {nbm_forecasts.shape} vs {observed_highs.shape}"
        )
    valid = ~(np.isnan(nbm_forecasts) | np.isnan(observed_highs))
    if int(valid.sum()) < min_pairs:
        return None
    residuals = nbm_forecasts[valid] - observed_highs[valid]
    bias = float(np.mean(residuals))
    sigma = max(float(np.std(residuals, ddof=1)), sigma_floor)
    return bias, sigma


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
