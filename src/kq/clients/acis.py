"""NWS ACIS (Applied Climate Information System) daily-climate client.

Source of truth for "what was actually observed" — specifically the same daily
high / low values that appear on the NWS Daily Climate Report, which is
Kalshi's settlement source for weather markets. Using ACIS for training data
means our ground truth matches the market's resolution truth.

Endpoint: https://data.rcc-acis.org/StnData
Free, no auth, hosted by the NOAA Regional Climate Centers. Station lookup
accepts ICAO codes (e.g. `sid=KLAX`); `elems=maxt,mint` returns daily max
and min temperatures in Fahrenheit. Missing days are marked 'M'.

Docs: https://www.rcc-acis.org/docs_webservices.html
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Final

import httpx

from kq.clients._http import default_client, request_json
from kq.clients.stations import STATIONS_BY_ICAO

BASE_URL: Final = "https://data.rcc-acis.org/StnData"


@dataclass(frozen=True, slots=True)
class DailyClimateObservation:
    station: str  # ICAO
    valid_date: date
    high_f: float | None
    low_f: float | None
    source: str
    fetched_at: datetime


class AcisClient:
    """Async ACIS daily-climate client."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> AcisClient:
        if self._client is None:
            self._client = default_client()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_daily(
        self,
        station: str,
        *,
        start_date: date,
        end_date: date,
    ) -> list[DailyClimateObservation]:
        """Pull observed daily max/min temperatures for a station over a date range."""
        if station not in STATIONS_BY_ICAO:
            raise ValueError(f"unknown station {station!r}")
        if end_date < start_date:
            raise ValueError(f"end_date {end_date} precedes start_date {start_date}")
        if self._client is None:
            raise RuntimeError("use `async with AcisClient()` or pass a client")

        fetched_at = datetime.now(tz=UTC)
        params: dict[str, Any] = {
            "sid": station,
            "sdate": start_date.isoformat(),
            "edate": end_date.isoformat(),
            "elems": "maxt,mint",
        }
        payload = await request_json(self._client, BASE_URL, params=params)
        return _parse_payload(payload, station_icao=station, fetched_at=fetched_at)


def _parse_payload(
    payload: Any,
    *,
    station_icao: str,
    fetched_at: datetime,
    source: str = "nws_acis",
) -> list[DailyClimateObservation]:
    """Flatten ACIS `data` list (`[[date, maxt, mint], ...]`) to typed rows."""
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    out: list[DailyClimateObservation] = []
    for entry in data:
        if not isinstance(entry, list | tuple) or len(entry) < 3:
            continue
        date_str, max_raw, min_raw = entry[0], entry[1], entry[2]
        if not isinstance(date_str, str):
            continue
        try:
            valid_date = date.fromisoformat(date_str)
        except ValueError:
            continue
        out.append(
            DailyClimateObservation(
                station=station_icao,
                valid_date=valid_date,
                high_f=_parse_acis_value(max_raw),
                low_f=_parse_acis_value(min_raw),
                source=source,
                fetched_at=fetched_at,
            )
        )
    return out


def _parse_acis_value(raw: Any) -> float | None:
    """ACIS returns values as strings (e.g. '76'). Missing days are 'M'.

    Also defensively handle already-numeric values (some endpoints return
    floats on certain queries).
    """
    if raw is None or raw in {"M", ""}:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None
