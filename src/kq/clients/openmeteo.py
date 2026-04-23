"""Open-Meteo ensemble forecast client.

Phase 1 deliverable. Free tier non-commercial; ~10k calls/day rate limit.
Returns GEFS (31 members) + ECMWF (51 members) + HRRR (US only, same-day).

Docs: https://open-meteo.com/en/docs/ensemble-api
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class EnsembleForecast:
    """Per-member forecast row for a single station x valid date x model run."""

    as_of: datetime
    run_time: datetime
    model: str
    member: int | None
    station: str
    valid_date: date
    forecast_high_f: float | None
    forecast_low_f: float | None


class OpenMeteoClient:
    """Thin async wrapper. Not implemented until Phase 1."""

    def __init__(self) -> None:
        pass

    async def fetch_ensemble(
        self,
        station: str,
        *,
        models: tuple[str, ...] = ("gefs_seamless", "ecmwf_ifs025"),
    ) -> list[EnsembleForecast]:
        """Pull the current ensemble for a station across requested models."""
        _ = station, models
        raise NotImplementedError("Phase 1 task")
