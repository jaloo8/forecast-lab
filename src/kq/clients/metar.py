"""METAR airport observations client.

Phase 1 deliverable. Source: aviationweather.gov. Polled every 5–10 min during
trading hours. Used for same-day Bayesian nowcast updates on remaining-day high.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MetarObservation:
    obs_time: datetime
    station: str  # ICAO code, e.g. "KLAX"
    temp_f: float | None
    dewpoint_f: float | None
    wind_kt: float | None
    pressure_mb: float | None


class MetarClient:
    """Thin wrapper over aviationweather.gov. Not implemented until Phase 1."""

    async def fetch_latest(self, stations: tuple[str, ...]) -> list[MetarObservation]:
        """Fetch the latest METAR for each station. Raises on network failure."""
        _ = stations
        raise NotImplementedError("Phase 1 task")
