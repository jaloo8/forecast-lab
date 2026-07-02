"""Domain types for Open-Meteo ensemble forecasts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class EnsembleForecast:
    """One row per (station, model, member, valid_date).

    `as_of` is stamped at fetch time. `run_time` is honest bookkeeping, not
    an inferred cycle: Open-Meteo exposes no cycle init, so parsers store
    the prediction/availability instant (== `as_of`); direct-feed ingests
    (ECMWF Open Data, GEFSv12 reforecast) store the true cycle init. No
    lead computation derives from it — leads come from `as_of`.
    """

    as_of: datetime
    run_time: datetime
    model: str  # 'gefs' | 'ecmwf'
    member: int  # 0-based
    station: str  # ICAO, e.g. 'KLAX'
    valid_date: date
    forecast_high_f: float | None
    forecast_low_f: float | None
