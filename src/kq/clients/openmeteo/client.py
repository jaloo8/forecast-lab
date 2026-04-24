"""OpenMeteoClient: async ensemble forecast client.

Docs: https://open-meteo.com/en/docs/ensemble-api
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

import httpx

from kq.clients._http import default_client, request_json
from kq.clients.openmeteo._parsers import MODEL_ID_MAP, _parse_payload
from kq.clients.openmeteo._types import EnsembleForecast
from kq.clients.stations import STATIONS_BY_ICAO, Station

BASE_URL: Final = "https://ensemble-api.open-meteo.com/v1/ensemble"


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
        """Pull the current ensemble for one station across requested models."""
        if isinstance(station, str):
            try:
                station = STATIONS_BY_ICAO[station]
            except KeyError as exc:
                raise ValueError(f"unknown station {station!r}") from exc
        if self._client is None:
            raise RuntimeError("use `async with OpenMeteoClient()` or pass a client")

        as_of = datetime.now(tz=UTC)
        rows: list[EnsembleForecast] = []
        for model_id in models:
            if model_id not in MODEL_ID_MAP:
                raise ValueError(f"unsupported model {model_id!r}")
            params: dict[str, Any] = {
                "latitude": station.latitude,
                "longitude": station.longitude,
                "daily": "temperature_2m_max,temperature_2m_min",
                "models": model_id,
                "temperature_unit": "fahrenheit",
                "timezone": "UTC",
                "forecast_days": forecast_days,
            }
            payload = await request_json(self._client, BASE_URL, params=params)
            rows.extend(
                _parse_payload(
                    payload,
                    as_of=as_of,
                    model_id=model_id,
                    station_icao=station.icao,
                )
            )
        return rows
