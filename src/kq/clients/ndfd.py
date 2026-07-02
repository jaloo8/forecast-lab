"""NDFD/NBM benchmark client (deterministic Tmax via Open-Meteo).

Pulls NWS-blended deterministic Tmax forecasts via Open-Meteo's
``ncep_nbm_conus`` model. NBM is the operational backbone of the National
Digital Forecast Database (NDFD); pulling it via Open-Meteo gives us JSON
access without a GRIB2/eccodes system dependency.

The probabilistic NBM ``qmd`` quantiles (P10..P90) are deferred to a later
upgrade — see ``docs/research/NDFD-BENCHMARK-SOURCE.md`` for the source
decision and the upgrade path. The schema reserves columns for that upgrade
so the dataclass and downstream queries don't have to migrate later.

Live snapshots are pulled from ``api.open-meteo.com`` (today + ``forecast_days``);
historical backfill comes from ``historical-forecast-api.open-meteo.com``.
Two parsers, one dataclass: live rows have ``lead_days = valid_date - today``;
historical rows have ``lead_days = 1`` and ``as_of`` backdated to
``midnight UTC of (valid_date - 1)`` so the PIT join with our backtest
training set falls out naturally.

Timestamps are stored UTC-naive; DuckDB's ``TIMESTAMP`` silently localizes
tz-aware values on insert (per existing CLAUDE.md §6 pattern in
``openmeteo._parsers``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Final

import httpx

from kq.clients._http import default_client, request_json
from kq.clients.stations import STATIONS_BY_ICAO, Station

LIVE_BASE_URL: Final = "https://api.open-meteo.com/v1/forecast"
HISTORICAL_BASE_URL: Final = "https://historical-forecast-api.open-meteo.com/v1/forecast"
NBM_MODEL_ID: Final = "ncep_nbm_conus"
DETERMINISTIC_SOURCE: Final = "nbm_deterministic_openmeteo"

# IANA tz names for our 6 station LSTs. Open-Meteo's `daily` aggregation uses
# calendar-day boundaries in the named zone — exactly what Kalshi LST
# settlement does — so this hard-coded map is the right anchor and avoids a
# new dateutil/zoneinfo dependency surface.
_LST_TZ_BY_OFFSET: Final[dict[int, str]] = {
    -5: "America/New_York",  # EST (KNYC, KMIA)
    -6: "America/Chicago",  # CST (KMDW, KAUS)
    -7: "America/Denver",  # MST (KDEN)
    -8: "America/Los_Angeles",  # PST (KLAX)
}


@dataclass(frozen=True, slots=True)
class NbmDeterministicForecast:
    """One (station, valid_date) NBM deterministic Tmax row.

    Probabilistic columns (p10..p90) are NULL until the qmd/cfgrib upgrade.
    """

    as_of: datetime
    station: str
    valid_date: date
    lead_days: int
    forecast_max_f: float
    source: str = DETERMINISTIC_SOURCE
    p10_max_f: float | None = None
    p25_max_f: float | None = None
    p50_max_f: float | None = None
    p75_max_f: float | None = None
    p90_max_f: float | None = None


class NdfdClient:
    """Async NBM deterministic Tmax client (NDFD-equivalent benchmark)."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> NdfdClient:
        if self._client is None:
            self._client = default_client()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_forecast(
        self,
        station: str | Station,
        *,
        forecast_days: int = 7,
    ) -> list[NbmDeterministicForecast]:
        """Live NBM forecast for the station, from today to today+forecast_days.

        Each row's ``lead_days`` is computed from (valid_date - as_of.date()),
        so a single call returns lead 0 (today's remainder), 1 (tomorrow),
        through ``forecast_days``.
        """
        station_obj = _coerce_station(station)
        if self._client is None:
            raise RuntimeError("use `async with NdfdClient()` or pass a client")
        as_of = datetime.now(tz=UTC)
        params = self._build_params(
            station_obj,
            extras={"forecast_days": forecast_days},
        )
        payload = await request_json(self._client, LIVE_BASE_URL, params=params)
        return _parse_live_payload(payload, as_of=as_of, station_icao=station_obj.icao)

    async def fetch_historical(
        self,
        station: str | Station,
        *,
        start_date: date,
        end_date: date,
    ) -> list[NbmDeterministicForecast]:
        """Historical NBM Tmax for valid dates in [start_date, end_date].

        Each row is treated as the canonical lead-1 forecast for that day:
        ``as_of`` is backdated to midnight UTC of (valid_date - 1) so
        ``lead_days = 1`` falls out of the math, matching how
        ``openmeteo._parsers._parse_historical_payload`` anchors lead time.
        """
        station_obj = _coerce_station(station)
        if self._client is None:
            raise RuntimeError("use `async with NdfdClient()` or pass a client")
        if end_date < start_date:
            raise ValueError(f"end_date {end_date} precedes start_date {start_date}")
        params = self._build_params(
            station_obj,
            extras={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )
        payload = await request_json(self._client, HISTORICAL_BASE_URL, params=params)
        return _parse_historical_payload(payload, station_icao=station_obj.icao)

    @staticmethod
    def _build_params(station: Station, *, extras: dict[str, Any]) -> dict[str, Any]:
        tz = _LST_TZ_BY_OFFSET.get(station.lst_offset_hours, "UTC")
        params: dict[str, Any] = {
            "latitude": station.latitude,
            "longitude": station.longitude,
            "daily": "temperature_2m_max",
            "models": NBM_MODEL_ID,
            "temperature_unit": "fahrenheit",
            "timezone": tz,
        }
        params.update(extras)
        return params


def _coerce_station(station: str | Station) -> Station:
    if isinstance(station, Station):
        return station
    try:
        return STATIONS_BY_ICAO[station]
    except KeyError as exc:
        raise ValueError(f"unknown station {station!r}") from exc


def _parse_live_payload(
    payload: Any,
    *,
    as_of: datetime,
    station_icao: str,
) -> list[NbmDeterministicForecast]:
    """Live endpoint: lead_days = valid_date - as_of.date(); past dates dropped."""
    pairs = _extract_daily_pairs(payload)
    today_utc = as_of.astimezone(UTC).date()
    as_of_naive = _to_naive_utc(as_of)
    out: list[NbmDeterministicForecast] = []
    for valid_date, forecast_max in pairs:
        lead = (valid_date - today_utc).days
        if lead < 0:
            continue
        out.append(
            NbmDeterministicForecast(
                as_of=as_of_naive,
                station=station_icao,
                valid_date=valid_date,
                lead_days=lead,
                forecast_max_f=forecast_max,
            )
        )
    return out


def _parse_historical_payload(
    payload: Any,
    *,
    station_icao: str,
) -> list[NbmDeterministicForecast]:
    """Historical endpoint: every row is treated as lead-1; as_of backdated."""
    pairs = _extract_daily_pairs(payload)
    out: list[NbmDeterministicForecast] = []
    for valid_date, forecast_max in pairs:
        per_row_as_of = datetime.combine(valid_date - timedelta(days=1), time.min)
        out.append(
            NbmDeterministicForecast(
                as_of=per_row_as_of,
                station=station_icao,
                valid_date=valid_date,
                lead_days=1,
                forecast_max_f=forecast_max,
            )
        )
    return out


def _extract_daily_pairs(payload: Any) -> list[tuple[date, float]]:
    """Pull ``(valid_date, temperature_2m_max)`` pairs from an Open-Meteo response.

    Defensive parsing — silently drops malformed entries, returns empty list
    on any structural mismatch. Matches the metar/openmeteo parser style.
    """
    if not isinstance(payload, dict):
        return []
    daily = payload.get("daily")
    if not isinstance(daily, dict):
        return []
    times = daily.get("time")
    maxes = daily.get("temperature_2m_max")
    if not isinstance(times, list) or not isinstance(maxes, list):
        return []
    out: list[tuple[date, float]] = []
    for raw_date, raw_max in zip(times, maxes, strict=False):
        valid_date = _parse_iso_date(raw_date)
        forecast_max = _as_float(raw_max)
        if valid_date is None or forecast_max is None:
            continue
        out.append((valid_date, round(forecast_max, 2)))
    return out


def _parse_iso_date(raw: Any) -> date | None:
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_naive_utc(dt: datetime) -> datetime:
    """Strip tzinfo after converting to UTC. DuckDB stores naive UTC."""
    return dt.astimezone(UTC).replace(tzinfo=None)
