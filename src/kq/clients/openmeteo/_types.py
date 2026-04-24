"""Domain types for Open-Meteo ensemble forecasts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class EnsembleForecast:
    """One row per (station, model, member, valid_date).

    `as_of` is stamped at fetch time; `run_time` is the most recent model
    cycle inferred from the payload (or rounded to 6h when absent).
    """

    as_of: datetime
    run_time: datetime
    model: str  # 'gefs' | 'ecmwf'
    member: int  # 0-based
    station: str  # ICAO, e.g. 'KLAX'
    valid_date: date
    forecast_high_f: float | None
    forecast_low_f: float | None
