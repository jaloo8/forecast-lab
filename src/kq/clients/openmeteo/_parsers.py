"""Parsers: Open-Meteo JSON -> typed EnsembleForecast rows.

**Day definition (2026-06-11 audit, UTC-vs-LST finding, fixed in PR-F):**
Kalshi weather contracts settle on the station's Local **Standard** Time
calendar day (see ``kq.utils.kalshi_dates``). Every daily aggregate produced
by this package is therefore computed over LST days, not UTC days:

- The live ensemble path requests Open-Meteo's ``daily`` aggregation with a
  fixed-offset ``Etc/GMT+N`` timezone (no DST — exactly LST), so the server
  aggregates over the correct 24h window.
- The historical previous-runs path pulls *hourly* values in the station's
  fixed LST offset and takes max/min per LST calendar day here.

Residual approximation, documented honestly: the daily max is the max of 24
*hourly* samples; a sub-hourly temperature spike between samples is invisible.
This affects model and settlement-truth symmetry only marginally (settlement
truth comes from NWS climate reports via ACIS, not from these forecasts).

**Lead-1 honesty (2026-06-11 audit root cause #8, fixed in PR-F):**
The old historical path served the *freshest archived run* (effectively
lead-0) and then BACKDATED ``as_of`` to midnight of ``valid_date - 1`` to
fake ``lead_days = 1``. That hack is deleted. The replacement pulls the
Previous Runs API's ``temperature_2m_previous_day1`` — per Open-Meteo docs,
"the value that was predicted 24 hours before valid time" — and stamps
``as_of`` with the *latest prediction instant that contributed to the
aggregate*: the last hourly sample of the LST day (23:00 LST) minus 24h,
i.e. 23:00 LST on ``valid_date - 1``. No stored ``as_of`` ever precedes the
actual availability of the data it stamps.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Final

from kq.clients.openmeteo._types import EnsembleForecast
from kq.clients.stations import Station

MODEL_ID_MAP: Final[dict[str, str]] = {
    "gfs_seamless": "gefs",
    "ecmwf_ifs025": "ecmwf",
}

# Sentinel model name for true lead-1 rows from the Previous Runs API
# (hourly `temperature_2m_previous_day1`, LST-day aggregated). Deliberately
# NOT the old 'gfs_hist' sentinel: 'gfs_hist' rows were lead-0 data with a
# backdated as_of (2026-06-11 audit root cause #8) and must never blend
# into training sets again. On any DB that still carries them, delete with:
#   DELETE FROM weather_forecast WHERE model = 'gfs_hist'
PREV_DAY1_MODEL_NAME: Final = "gfs_prevday1"
PREV_DAY1_MEMBER: Final = 0

# The Previous Runs API's documented offset for `_previous_day1` variables:
# each hourly value "was predicted 24 hours before valid time".
PREV_DAY1_LEAD_HOURS: Final = 24

# Minimum non-null hourly samples required to trust an LST-day max/min.
# Below this the aggregate could materially understate the true extreme,
# so the value is stored as NULL (training joins drop it).
MIN_HOURLY_SAMPLES: Final = 18

_MEMBER_RE: Final = re.compile(r"^temperature_2m_(?P<kind>max|min)_member(?P<n>\d+)$")


def _parse_payload(
    payload: dict[str, Any],
    *,
    as_of: datetime,
    model_id: str,
    station_icao: str,
) -> list[EnsembleForecast]:
    """Flatten Open-Meteo's keyed-by-member daily response to typed rows.

    ``valid_date`` is the LST calendar day when the request used the
    station's fixed-offset timezone (the client does; see module docstring).
    """
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
    fb = fallback.astimezone(UTC) if fallback.tzinfo is not None else fallback
    cycle_hour = (fb.hour // 6) * 6
    return (fb - timedelta(hours=fb.hour - cycle_hour)).replace(minute=0, second=0, microsecond=0)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def previous_day1_as_of(valid_date: date, station: Station) -> datetime:
    """Honest ``as_of`` for a previous-day-1 LST-day aggregate (naive UTC).

    The last hourly sample of the LST day is 23:00 LST; per the Previous
    Runs API definition it was predicted ``PREV_DAY1_LEAD_HOURS`` before
    that instant — 23:00 LST on ``valid_date - 1``. Every earlier sample
    of the day was predicted even earlier, so this is the moment the full
    aggregate became available. Stored UTC-naive per CLAUDE.md §6 (DuckDB
    TIMESTAMP localizes tz-aware datetimes on insert).

    Note the derived lead: ``as_of`` falls on the *local* day before
    ``valid_date`` at every station (23:00 LST), which is what "lead 1"
    means for LST-settled contracts. ``kq.features.weather`` computes
    ``lead_days`` from the station-local date of ``as_of`` for exactly
    this reason.
    """
    last_sample_local = datetime.combine(valid_date, time(23, 0))
    last_sample_utc = last_sample_local - timedelta(hours=station.lst_offset_hours)
    return last_sample_utc - timedelta(hours=PREV_DAY1_LEAD_HOURS)


def parse_previous_runs_payload(
    payload: dict[str, Any],
    *,
    station: Station,
) -> list[EnsembleForecast]:
    """Aggregate hourly ``temperature_2m_previous_day1`` to LST-day rows.

    Expects a Previous Runs API response requested with the station's
    fixed-offset LST timezone (``Etc/GMT+N``), so ``hourly.time`` strings
    are already local-standard wall clock. One row per LST calendar day:

    - ``forecast_high_f`` / ``forecast_low_f``: max/min of the day's
      non-null hourly samples; NULL when fewer than ``MIN_HOURLY_SAMPLES``
      samples are present (partial days can understate extremes).
    - ``as_of``: :func:`previous_day1_as_of` — the honest availability
      instant, never a backdate.
    - ``run_time``: ``as_of`` floored to the previous 00/06/12/18Z cycle.
      Upper bound of the newest contributing model cycle; bookkeeping only
      (no lead computation derives from it).
    """
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    values = hourly.get("temperature_2m_previous_day1") or []
    if not times:
        return []

    by_day: dict[date, list[float]] = {}
    counts: dict[date, int] = {}
    for raw_ts, raw_val in zip(times, values, strict=False):
        try:
            day = date.fromisoformat(str(raw_ts)[:10])
        except ValueError:
            continue
        counts[day] = counts.get(day, 0) + 1
        val = _as_float(raw_val)
        if val is not None:
            by_day.setdefault(day, []).append(val)

    rows: list[EnsembleForecast] = []
    for day in sorted(counts):
        samples = by_day.get(day, [])
        enough = len(samples) >= MIN_HOURLY_SAMPLES
        as_of = previous_day1_as_of(day, station)
        rows.append(
            EnsembleForecast(
                as_of=as_of,
                run_time=_coerce_run_time(payload, fallback=as_of),
                model=PREV_DAY1_MODEL_NAME,
                member=PREV_DAY1_MEMBER,
                station=station.icao,
                valid_date=day,
                forecast_high_f=max(samples) if enough else None,
                forecast_low_f=min(samples) if enough else None,
            )
        )
    return rows
