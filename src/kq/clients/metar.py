"""METAR airport observations client.

Source: https://aviationweather.gov/api/data/metar (no auth, no rate card, polite
use only). One HTTP call fetches all requested stations via the `ids` parameter.

Temperatures in the upstream feed are Celsius; we normalize to Fahrenheit at
parse time so the rest of the system only handles one unit. Pressure is in
hPa/mb (same unit); we prefer `slp` (sea-level pressure) and fall back to
`altim` when `slp` is missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import httpx

from kq.clients._http import default_client, request_json

BASE_URL: Final = "https://aviationweather.gov/api/data/metar"


@dataclass(frozen=True, slots=True)
class MetarObservation:
    obs_time: datetime
    station: str  # ICAO, e.g. "KLAX"
    temp_f: float | None
    dewpoint_f: float | None
    wind_kt: float | None
    pressure_mb: float | None


class MetarClient:
    """Async METAR client over aviationweather.gov."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> MetarClient:
        if self._client is None:
            self._client = default_client()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_latest(
        self,
        stations: tuple[str, ...],
        *,
        hours: int = 1,
    ) -> list[MetarObservation]:
        """Fetch the most recent METARs for each station within the last `hours`."""
        if not stations:
            return []
        if self._client is None:
            raise RuntimeError("use `async with MetarClient()` or pass a client")
        params: dict[str, Any] = {
            "ids": ",".join(stations),
            "format": "json",
            "hours": hours,
        }
        payload = await request_json(self._client, BASE_URL, params=params)
        return _parse_payload(payload)


def _parse_payload(payload: Any) -> list[MetarObservation]:
    """The API returns a JSON array; defensive parsing for each row."""
    if not isinstance(payload, list):
        return []
    out: list[MetarObservation] = []
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        obs = _parse_one(raw)
        if obs is not None:
            out.append(obs)
    return out


def _parse_one(raw: dict[str, Any]) -> MetarObservation | None:
    station = raw.get("icaoId")
    obs_time_raw = raw.get("obsTime")
    if not isinstance(station, str) or not isinstance(obs_time_raw, int | float):
        return None
    obs_time = datetime.fromtimestamp(int(obs_time_raw), tz=UTC)
    return MetarObservation(
        obs_time=obs_time,
        station=station,
        temp_f=_c_to_f(_as_float(raw.get("temp"))),
        dewpoint_f=_c_to_f(_as_float(raw.get("dewp"))),
        wind_kt=_as_float(raw.get("wspd")),
        pressure_mb=_as_float(raw.get("slp")) or _as_float(raw.get("altim")),
    )


def _c_to_f(celsius: float | None) -> float | None:
    if celsius is None:
        return None
    return round(celsius * 9.0 / 5.0 + 32.0, 2)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
