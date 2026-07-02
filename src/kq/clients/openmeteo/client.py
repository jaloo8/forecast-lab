"""OpenMeteoClient: async ensemble + previous-runs forecast client.

Docs: https://open-meteo.com/en/docs/ensemble-api and
https://open-meteo.com/en/docs/previous-runs-api

All daily aggregation is over the station's Local Standard Time day —
see the module docstring in ``kq.clients.openmeteo._parsers`` for the
LST rationale (2026-06-11 audit) and the honest lead-1 ``as_of`` rules.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Final

import httpx

from kq.clients._http import default_client, request_json
from kq.clients.openmeteo._parsers import (
    MODEL_ID_MAP,
    _parse_payload,
    parse_previous_runs_payload,
)
from kq.clients.openmeteo._types import EnsembleForecast
from kq.clients.stations import STATIONS_BY_ICAO, Station, lst_timezone_name

BASE_URL: Final = "https://ensemble-api.open-meteo.com/v1/ensemble"
PREVIOUS_RUNS_BASE_URL: Final = "https://previous-runs-api.open-meteo.com/v1/forecast"

# The Previous Runs API is hourly-only for `_previous_dayN` variables
# (daily previous-day variables do not exist — probed live 2026-07-01).
PREV_DAY1_HOURLY_VAR: Final = "temperature_2m_previous_day1"
# Explicit model for reproducibility; GFS previous-run 2m temperature is
# archived back to March 2021 per the Open-Meteo docs.
PREV_DAY1_MODEL_ID: Final = "gfs_seamless"


class OpenMeteoClient:
    """Async Open-Meteo ensemble client."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> OpenMeteoClient:
        if self._client is None:
            self._client = default_client()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_ensemble(
        self,
        station: str | Station,
        *,
        models: tuple[str, ...] = ("gfs_seamless", "ecmwf_ifs025"),
        forecast_days: int = 7,
    ) -> list[EnsembleForecast]:
        """Pull the current ensemble for one station across requested models.

        ``as_of`` is the fetch instant (honest: the freshest current run is
        what we hold at fetch time). Daily max/min are aggregated by the
        server over the station's fixed-offset LST day (``Etc/GMT+N``), so
        ``valid_date`` is the Kalshi settlement day, not a UTC day.
        """
        station_obj = _coerce_station(station)
        if self._client is None:
            raise RuntimeError("use `async with OpenMeteoClient()` or pass a client")

        as_of = datetime.now(tz=UTC)
        rows: list[EnsembleForecast] = []
        for model_id in models:
            if model_id not in MODEL_ID_MAP:
                raise ValueError(f"unsupported model {model_id!r}")
            params: dict[str, Any] = {
                "latitude": station_obj.latitude,
                "longitude": station_obj.longitude,
                "daily": "temperature_2m_max,temperature_2m_min",
                "models": model_id,
                "temperature_unit": "fahrenheit",
                "timezone": lst_timezone_name(station_obj),
                "forecast_days": forecast_days,
            }
            payload = await request_json(self._client, BASE_URL, params=params)
            rows.extend(
                _parse_payload(
                    payload,
                    as_of=as_of,
                    model_id=model_id,
                    station_icao=station_obj.icao,
                )
            )
        return rows

    async def fetch_previous_day1(
        self,
        station: str | Station,
        *,
        start_date: date,
        end_date: date,
    ) -> list[EnsembleForecast]:
        """Pull TRUE lead-1 daily high/low for past LST days (one row per day).

        Replaces the deleted ``fetch_historical_deterministic`` (2026-06-11
        audit root cause #8): the Historical Forecast archive serves the
        freshest archived run (~lead-0) and the old parser backdated
        ``as_of`` to fake lead-1. This method instead queries the Previous
        Runs API's hourly ``temperature_2m_previous_day1`` — "the value that
        was predicted 24 hours before valid time" — and aggregates max/min
        over each LST calendar day client-side. ``as_of`` is stamped with
        the honest availability instant (23:00 LST of ``valid_date - 1``);
        see ``_parsers.previous_day1_as_of``.

        Rows are tagged ``model='gfs_prevday1'``, ``member=0``.
        Docs: https://open-meteo.com/en/docs/previous-runs-api
        """
        station_obj = _coerce_station(station)
        if self._client is None:
            raise RuntimeError("use `async with OpenMeteoClient()` or pass a client")
        if end_date < start_date:
            raise ValueError(f"end_date {end_date} precedes start_date {start_date}")

        params: dict[str, Any] = {
            "latitude": station_obj.latitude,
            "longitude": station_obj.longitude,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "hourly": PREV_DAY1_HOURLY_VAR,
            "models": PREV_DAY1_MODEL_ID,
            "temperature_unit": "fahrenheit",
            "timezone": lst_timezone_name(station_obj),
        }
        payload = await request_json(self._client, PREVIOUS_RUNS_BASE_URL, params=params)
        return parse_previous_runs_payload(payload, station=station_obj)


def _coerce_station(station: str | Station) -> Station:
    if isinstance(station, Station):
        return station
    try:
        return STATIONS_BY_ICAO[station]
    except KeyError as exc:
        raise ValueError(f"unknown station {station!r}") from exc
