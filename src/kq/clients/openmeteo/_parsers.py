"""Parsers: Open-Meteo JSON -> typed EnsembleForecast rows."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from typing import Any, Final

from kq.clients.openmeteo._types import EnsembleForecast

MODEL_ID_MAP: Final[dict[str, str]] = {
    "gfs_seamless": "gefs",
    "ecmwf_ifs025": "ecmwf",
}

# Sentinel model name used to tag deterministic historical forecasts in the
# shared weather_forecast table. Distinguishable from the live ensemble 'gefs'
# so downstream queries can filter `WHERE model='gefs'` vs historical.
HIST_MODEL_NAME: Final = "gfs_hist"
HIST_MEMBER: Final = 0

_MEMBER_RE: Final = re.compile(r"^temperature_2m_(?P<kind>max|min)_member(?P<n>\d+)$")


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


def _gather_members(daily: dict[str, Any], *, kind: str) -> dict[int, list[Any]]:
    """Collect `temperature_2m_<kind>_member<NN>` series into {member_idx: values}."""
    out: dict[int, list[Any]] = {}
    for key, values in daily.items():
        match = _MEMBER_RE.match(key)
        if not match or match.group("kind") != kind:
            continue
        out[int(match.group("n"))] = list(values)
    # Non-member control series (`temperature_2m_max`) promoted to member 0
    # when no explicit member 00 is present.
    control_key = f"temperature_2m_{kind}"
    if control_key in daily and 0 not in out:
        out[0] = list(daily[control_key])
    return out


def _coerce_run_time(payload: dict[str, Any], *, fallback: datetime) -> datetime:
    """Round `fallback` down to the most recent 6h cycle (00/06/12/18 UTC).

    Open-Meteo doesn't always expose the exact cycle time. The 6h
    granularity matches GEFS/ECMWF cycle cadence and is enough for PIT
    bookkeeping in v1.
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


def _parse_historical_payload(
    payload: dict[str, Any],
    *,
    as_of: datetime,
    station_icao: str,
) -> list[EnsembleForecast]:
    """Flatten Open-Meteo's Historical Forecast response to EnsembleForecast rows.

    Historical endpoint returns a single deterministic series (no member index).
    Stored with model=HIST_MODEL_NAME ('gfs_hist') + member=0 so the shared
    weather_forecast PK stays unique vs live ensemble rows.
    """
    daily = payload.get("daily") or {}
    times = daily.get("time") or []
    if not times:
        return []
    valid_dates: list[date] = [date.fromisoformat(t) for t in times]

    maxes = list(daily.get("temperature_2m_max") or [None] * len(valid_dates))
    mins = list(daily.get("temperature_2m_min") or [None] * len(valid_dates))

    run_time = _coerce_run_time(payload, fallback=as_of)

    rows: list[EnsembleForecast] = []
    for vd, hi, lo in zip(valid_dates, maxes, mins, strict=False):
        rows.append(
            EnsembleForecast(
                as_of=as_of,
                run_time=run_time,
                model=HIST_MODEL_NAME,
                member=HIST_MEMBER,
                station=station_icao,
                valid_date=vd,
                forecast_high_f=_as_float(hi),
                forecast_low_f=_as_float(lo),
            )
        )
    return rows
