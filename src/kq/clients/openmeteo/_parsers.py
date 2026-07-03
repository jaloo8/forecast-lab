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

**run_time honesty (2026-07-01 audit, Tier 2):** Open-Meteo's JSON exposes
no model-cycle init time on either API (the keys the old ``_coerce_run_time``
probed — ``last_model_run_initialisation_time``, and ``generationtime_utc``
read as a datetime — do not exist / are a server-processing duration in ms).
The old fallback fabricated a plausible-looking cycle by flooring fetch time
to the 6h grid; that fabrication is deleted. ``run_time`` is now:

- live ensemble path: ``as_of`` (the fetch instant) — an honest *upper
  bound* on when the underlying cycle ran, transparently equal to ``as_of``
  so it can never be mistaken for independent cycle information. (NULL
  would be cleaner, but ``weather_forecast.run_time`` is ``NOT NULL``;
  relaxing that schema is a separate migration.)
- previous-runs path: ``as_of``, which by the API's own definition IS the
  prediction instant — each ``previous_day1`` sample "was predicted 24
  hours before valid time", and ``as_of`` = (last contributing sample's
  valid time) - 24h. The producing cycle's init is ≤ this instant.

No lead computation derives from ``run_time`` anywhere (leads come from
``as_of``; see ``kq.features.weather``).
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any, Final

from kq.clients.openmeteo._types import EnsembleForecast
from kq.clients.stations import Station

MODEL_ID_MAP: Final[dict[str, str]] = {
    "gfs_seamless": "gefs",
    "ecmwf_ifs025": "ecmwf",
}

# True lead-1 lanes from the Previous Runs API (hourly
# `temperature_2m_previous_day1`, LST-day aggregated). One lane per model,
# named `<family>_prevday1`. Every lane was verified live 2026-07-02 at all
# 6 stations: variable served, values plausible, archive reaches 2024-11-01
# and earlier (ecmwf ~2024-03; icon/gem/meteofrance <=2024-02; jma <=2021-06;
# gfs ~2021-03 per docs), and `previous_day1` genuinely differs from the
# day-0 series (the lead-honesty signal). Probed-but-excluded: ukmo_seamless
# (archive starts ~fall 2024 — no pre-window coverage margin) and
# ncep_nbm_conus (IS the Phase 5 benchmark; pooling it as an input would
# blur the gate — a true-lead-1 NBM *benchmark* is a separate lever).
PREV_DAY1_SUFFIX: Final = "_prevday1"
PREV_DAY1_MODELS: Final[dict[str, str]] = {
    "gfs_seamless": "gfs_prevday1",
    "ecmwf_ifs025": "ecmwf_prevday1",
    "icon_seamless": "icon_prevday1",
    "gem_seamless": "gem_prevday1",
    "meteofrance_seamless": "meteofrance_prevday1",
    "jma_seamless": "jma_prevday1",
}

# Default lane (the original PR-F single-model path). Deliberately NOT the
# old 'gfs_hist' sentinel: 'gfs_hist' rows were lead-0 data with a
# backdated as_of (2026-06-11 audit root cause #8) and must never blend
# into training sets again. On any DB that still carries them, delete with:
#   DELETE FROM weather_forecast WHERE model = 'gfs_hist'
PREV_DAY1_MODEL_NAME: Final = PREV_DAY1_MODELS["gfs_seamless"]
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

    ``run_time`` is ``as_of``: the payload carries no model-cycle init
    time, so the fetch instant is stored as an honest upper bound rather
    than a fabricated 6h-floored pseudo-cycle (see module docstring).
    """
    daily = payload.get("daily") or {}
    times = daily.get("time") or []
    if not times:
        return []
    valid_dates: list[date] = [date.fromisoformat(t) for t in times]

    max_by_member = _gather_members(daily, kind="max")
    min_by_member = _gather_members(daily, kind="min")
    members = sorted(set(max_by_member) | set(min_by_member))

    run_time = as_of
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
    model: str = PREV_DAY1_MODEL_NAME,
) -> list[EnsembleForecast]:
    """Aggregate hourly ``temperature_2m_previous_day1`` to LST-day rows.

    ``model`` is the lane the rows are tagged with (a ``PREV_DAY1_MODELS``
    value, e.g. ``'ecmwf_prevday1'``); default is the original GFS lane.
    The lead/as_of semantics are identical across lanes — the API applies
    the same 24h ``previous_day1`` offset to every model.

    Expects a Previous Runs API response requested with the station's
    fixed-offset LST timezone (``Etc/GMT+N``), so ``hourly.time`` strings
    are already local-standard wall clock. One row per LST calendar day:

    - ``forecast_high_f`` / ``forecast_low_f``: max/min of the day's
      non-null hourly samples; NULL when fewer than ``MIN_HOURLY_SAMPLES``
      samples are present (partial days can understate extremes).
    - ``as_of``: :func:`previous_day1_as_of` — the honest availability
      instant, never a backdate.
    - ``run_time``: ``as_of``. By the API's definition of ``previous_day1``
      ("the value that was predicted 24 hours before valid time"), the
      newest contributing prediction instant is exactly (last sample's
      valid time) - 24h = ``as_of``; the producing cycle's init is ≤ that
      instant and is not exposed by the API. Bookkeeping only (no lead
      computation derives from it).
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
                run_time=as_of,
                model=model,
                member=PREV_DAY1_MEMBER,
                station=station.icao,
                valid_date=day,
                forecast_high_f=max(samples) if enough else None,
                forecast_low_f=min(samples) if enough else None,
            )
        )
    return rows
