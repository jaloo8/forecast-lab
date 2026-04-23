"""Open-Meteo ensemble forecast client.

Pulls multi-member ensemble forecasts for daily high/low temperature at the
6 Kalshi weather stations. Free, non-commercial, no auth, ~10k calls/day
rate limit.

Ensemble members are exposed as separate keys:
    daily.temperature_2m_max_member01, _member02, ..., _memberNN

We normalize every row to:
    (as_of, run_time, model, member, station, valid_date, high_f, low_f)

Model IDs mapped:
    gfs_seamless  -> 'gefs'  (31 members, 0-30)
    ecmwf_ifs025  -> 'ecmwf' (51 members, 0-50)

Docs: https://open-meteo.com/en/docs/ensemble-api
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Final

import httpx

from kq.clients._http import default_client, request_json
from kq.clients.stations import STATIONS_BY_ICAO, Station

BASE_URL: Final = "https://ensemble-api.open-meteo.com/v1/ensemble"

MODEL_ID_MAP: Final[dict[str, str]] = {
    "gfs_seamless": "gefs",
    "ecmwf_ifs025": "ecmwf",
}

_MEMBER_RE: Final = re.compile(r"^temperature_2m_(?P<kind>max|min)_member(?P<n>\d+)$")


@dataclass(frozen=True, slots=True)
class EnsembleForecast:
    """One row per (station, model, member, valid_date)."""

    as_of: datetime
    run_time: datetime
    model: str  # 'gefs' | 'ecmwf'
    member: int  # 0-based index
    station: str  # ICAO
    valid_date: date
    forecast_high_f: float | None
    forecast_low_f: float | None


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


def _parse_payload(
    payload: dict[str, Any],
    *,
    as_of: datetime,
    model_id: str,
    station_icao: str,
) -> list[EnsembleForecast]:
    """Flatten Open-Meteo's keyed-by-member daily response to typed rows."""
    daily = payload.get("daily") or {}
    times = daily.get("time") or []
    if not times:
        return []
    valid_dates: list[date] = [date.fromisoformat(t) for t in times]

    max_by_member = _gather_members(daily, kind="max")
    min_by_member = _gather_members(daily, kind="min")
    # A member present in `max` might be missing in `min` (and vice versa).
    members = sorted(set(max_by_member) | set(min_by_member))

    run_time = _coerce_run_time(payload, fallback=as_of)
    model = MODEL_ID_MAP[model_id]

    rows: list[EnsembleForecast] = []
    for member in members:
        maxes = max_by_member.get(member, [None] * len(valid_dates))
        mins = min_by_member.get(member, [None] * len(valid_dates))
        for vd, hi, lo in zip(valid_dates, maxes, mins, strict=False):
            rows.append(
                EnsembleForecast(
                    as_of=as_of,
                    run_time=run_time,
                    model=model,
                    member=member,
                    station=station_icao,
                    valid_date=vd,
                    forecast_high_f=_as_float(hi),
                    forecast_low_f=_as_float(lo),
                )
            )
    return rows


def _gather_members(
    daily: dict[str, Any],
    *,
    kind: str,
) -> dict[int, list[Any]]:
    """Collect `temperature_2m_<kind>_member<NN>` series into {member_idx: values}."""
    out: dict[int, list[Any]] = {}
    for key, values in daily.items():
        match = _MEMBER_RE.match(key)
        if not match or match.group("kind") != kind:
            continue
        out[int(match.group("n"))] = list(values)
    # Some models also emit a non-member "temperature_2m_max" / "_min" — the
    # "control" run. Treat it as member 0 when no explicit member 00 exists.
    control_key = f"temperature_2m_{kind}"
    if control_key in daily and 0 not in out:
        out[0] = list(daily[control_key])
    return out


def _coerce_run_time(payload: dict[str, Any], *, fallback: datetime) -> datetime:
    """Open-Meteo doesn't always expose the cycle time; approximate when absent.

    When absent, round `fallback` down to the most recent 6-hourly cycle
    (00/06/12/18 UTC). That's the right granularity for Phase 1 — we'll
    revisit if we ever need cycle-exact PIT features.
    """
    raw = payload.get("generationtime_utc") or payload.get("last_model_run_initialisation_time")
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    fb = fallback.astimezone(UTC)
    cycle_hour = (fb.hour // 6) * 6
    return (fb - timedelta(hours=fb.hour - cycle_hour)).replace(minute=0, second=0, microsecond=0)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
