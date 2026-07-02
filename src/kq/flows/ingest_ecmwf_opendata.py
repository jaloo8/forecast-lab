"""ECMWF Open Data ingest -- Phase 2 (one cycle per tick, lead-1 daily Tmax).

Pulls the most recent published ECMWF IFS HRES cycle's ``fc.grib2`` at
the step whose ``mx2t24`` (max 2-metre temperature in the PREVIOUS 24
hours, valid-time-anchored) window covers the next full UTC calendar
day, and extracts that field at each station's nearest grid point. One
file per cycle (~130 MB), one variable per file -- no client-side
multi-step aggregation.

**mx2t24 date attribution (2026-07-01 audit, Tier 2 high — the
off-by-one):** ``mx2t24`` at step S is the max over ``[init+S-24h,
init+S]`` — the 24 hours *ending* at the valid time, not starting
there. From a 00z init on day D, step=48h is valid at D+2 00:00 UTC
and covers ``[D+1 00z, D+2 00z]`` — calendar day **D+1**, i.e.
"tomorrow", NOT ``(init + 48h).date()`` = D+2. The old code stored the
valid-time date, shifting every row one day late. Generally, with
``step = 48h - init_hour`` the window is day-aligned for every cycle
(00z→48h, 06z→42h, 12z→36h, 18z→30h; all ≤ the 90h short-cutoff
ceiling) and the covered day is always ``init.date() + 1``.

The day covered is the *UTC* calendar day. Kalshi settles on LST days;
this lane remains UTC-aligned pending the model-improvement work
(SESSION-2026-07-01 next-lever #3) — documented, not hidden.

Why not pull every step file (3h, 6h, ..., 48h) and aggregate
client-side: each step file is ~130 MB at 0.25 deg resolution; 16
steps x 4 cycles/day = ~8 GB/day. Untenable on a home cron. The
``mx2t24`` accumulation field is the WMO-standard pre-aggregated
answer.

**Tagged as ``model='ecmwf_opendata'`` in weather_forecast** so the
existing backtest engine can consume it as a parallel lane to the
Open-Meteo ``model='ecmwf'`` rows. Brier-vs-NDFD on the ecmwf_opendata
lane vs the ecmwf lane is the A/B that justifies (or refutes) the
direct-feed operational-resilience win.

**Cycle publication (the "picks unpublished cycles" fix):** IFS open
data is released at the END of the real-time dissemination schedule,
NOT 1-2h after init as this module previously claimed. Per ECMWF's
dissemination schedule the 00z HRES window runs ~05:45-07:34 UTC, so
open data lands ~7.5-8h after init (same offset for the other
cycles). The old 2.5h buffer therefore selected a not-yet-published
cycle on essentially every tick and burned the single 404 fallback as
a matter of routine. The buffer is now 8.5h
(``DEFAULT_PUBLISH_BUFFER_HOURS``), and the 404 fallback genuinely
walks back up to ``max_lookback_cycles`` (default 4 = 24h of cycles)
prior cycles -- the loop that previously read ``for ...: return`` and
never iterated. Operators get a structured
``ecmwf_opendata.fallback_to_prior_cycle`` log event per miss.

Since IFS Cycle 50r1 (May 2026) the 06z/18z short-cutoff runs are
published under ``oper`` (previously ``scda``) with steps to 90h, so
all four daily cycles are usable by this flow.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import structlog

from kq.clients._http import default_client
from kq.clients.ecmwf_opendata import (
    CYCLE_HOURS,
    OpenDataFile,
    StationCoord,
    fetch_grib2_bytes,
    kelvin_to_fahrenheit,
)
from kq.clients.openmeteo._types import EnsembleForecast
from kq.clients.stations import STATIONS, Station
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.storage.duckdb_store import connect
from kq.storage.repositories.forecasts import insert_forecasts

log = structlog.get_logger(__name__)

# Tag for ECMWF Open Data rows in `weather_forecast.model`. Distinct
# from `'ecmwf'` (Open-Meteo's ifs025 lane) so the two can be A/B'd
# without conflicting on the (as_of, model, member, station,
# valid_date) PK.
MODEL_TAG: str = "ecmwf_opendata"

# Forecast step that gives us tomorrow's (UTC) calendar-day max under a
# 00z init: ``mx2t24`` at step=48h accumulates over [init+24h, init+48h]
# = the next UTC calendar day. For later cycles the day-aligned step is
# ``LEAD_1_STEP_HOURS - cycle.hour`` (see ``step_hours_for_cycle``).
LEAD_1_STEP_HOURS: int = 48

# WMO short name for "Maximum 2 metre temperature in last 24 hours"
# (paramId 121). Same filter pattern as ``2t`` extraction in PR 1.
SHORT_NAME_MX2T24: str = "mx2t24"

# How long after init the step files become downloadable. IFS open data
# is released at the END of the real-time dissemination schedule (00z
# HRES window ~05:45-07:34 UTC => ~7.5-8h after init); 8.5h adds margin.
# The previous 2.5h figure was the paid real-time latency, not open
# data's -- it made the flow ask for unpublished cycles nearly every tick.
DEFAULT_PUBLISH_BUFFER_HOURS: float = 8.5


def step_hours_for_cycle(cycle: datetime) -> int:
    """Day-aligned ``mx2t24`` step for a cycle: ``48 - init_hour``.

    The mx2t24 window ``[init+step-24h, init+step]`` then always ends at
    the second UTC midnight after the init date -- i.e. it covers exactly
    the UTC calendar day ``cycle.date() + 1`` for every published cycle
    (00z→48h, 06z→42h, 12z→36h, 18z→30h). All four are 3-hourly steps
    within the 90h short-cutoff ceiling.
    """
    if cycle.hour not in CYCLE_HOURS:
        raise ValueError(f"cycle hour {cycle.hour} not in published cycles {CYCLE_HOURS}")
    return LEAD_1_STEP_HOURS - cycle.hour


def valid_date_for_cycle(cycle: datetime) -> date:
    """UTC calendar day covered by the day-aligned mx2t24 window: init date + 1.

    NOT the valid-time date ``(cycle + step).date()`` -- mx2t24 is a
    *trailing* 24h max, so the valid-time date is one day AFTER the day
    the field describes (the 2026-07-01 off-by-one).
    """
    if cycle.hour not in CYCLE_HOURS:
        raise ValueError(f"cycle hour {cycle.hour} not in published cycles {CYCLE_HOURS}")
    return (cycle + timedelta(hours=step_hours_for_cycle(cycle) - 24)).date()


def _stations_to_coords(stations: tuple[Station, ...] = STATIONS) -> tuple[StationCoord, ...]:
    """Project ``Station`` (full record) to ``StationCoord`` (lat/lon
    needed for nearest-grid-point sampling)."""
    return tuple(
        StationCoord(icao=s.icao, latitude=s.latitude, longitude=s.longitude) for s in stations
    )


def latest_published_cycle(
    *,
    now: datetime,
    publish_buffer_hours: float = DEFAULT_PUBLISH_BUFFER_HOURS,
) -> datetime:
    """Return the most recent ECMWF cycle (00/06/12/18 UTC) whose open-data
    files have plausibly published by ``now``.

    IFS open data lands ~7.5-8h after init (end of the real-time
    dissemination schedule); the default 8.5h buffer adds margin. This is
    only the *plausibility* pick — actual 404s (late dissemination, an
    outage) are handled by :func:`fetch_and_upsert`'s real lookback loop.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if publish_buffer_hours < 0:
        raise ValueError(f"publish_buffer_hours must be >= 0, got {publish_buffer_hours}")
    candidate = now.astimezone(UTC) - timedelta(hours=publish_buffer_hours)
    # Round down to the most recent published cycle hour.
    candidate_hour = max(h for h in CYCLE_HOURS if h <= candidate.hour)
    return candidate.replace(hour=candidate_hour, minute=0, second=0, microsecond=0)


def _extract_mx2t24_per_station(
    record_bytes: bytes,
    *,
    stations: tuple[StationCoord, ...],
) -> dict[str, float]:
    """Extract ``mx2t24`` at each station's nearest grid point.

    Mirrors ``ecmwf_opendata.extract_station_tmax`` but with
    ``shortName='mx2t24'`` instead of ``'2t'``. Could share more code
    via a parameter, but the v1 split keeps the Phase 1 primitive
    untouched and the Phase 2 ingest semantically explicit about what
    field it's after.
    """
    import contextlib  # noqa: PLC0415 -- lazy: only used in cleanup
    import os  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    import xarray as xr  # noqa: PLC0415 -- lazy: cfgrib loads eccodes lib

    with tempfile.NamedTemporaryFile(suffix=".grib2", delete=False) as f:
        f.write(record_bytes)
        path = f.name
    try:
        ds = xr.open_dataset(
            path,
            engine="cfgrib",
            backend_kwargs={"filter_by_keys": {"shortName": SHORT_NAME_MX2T24}},
        )
        var_name = next(iter(ds.data_vars))
        out: dict[str, float] = {}
        for st in stations:
            value = ds[var_name].sel(
                latitude=st.latitude,
                longitude=st.longitude_e,
                method="nearest",
            )
            out[st.icao] = float(value)
        return out
    finally:
        if os.path.exists(path):
            os.unlink(path)
        parent = os.path.dirname(path)
        for sibling in os.listdir(parent):
            if sibling.startswith(os.path.basename(path) + "."):
                with contextlib.suppress(OSError):
                    os.unlink(os.path.join(parent, sibling))


def _build_forecast_rows(
    *,
    station_kelvin: dict[str, float],
    cycle: datetime,
    valid_date: date,
    as_of: datetime,
) -> list[EnsembleForecast]:
    """Wrap per-station mx2t24 readings as ``EnsembleForecast`` rows
    ready for ``insert_forecasts``.

    HRES is deterministic, so ``member=0``. ``run_time`` is the cycle
    init; ``as_of`` is when WE pulled it.
    """
    rows: list[EnsembleForecast] = []
    cycle_naive = cycle.astimezone(UTC).replace(tzinfo=None)
    as_of_naive = as_of.astimezone(UTC).replace(tzinfo=None)
    for icao, kelvin in station_kelvin.items():
        rows.append(
            EnsembleForecast(
                as_of=as_of_naive,
                run_time=cycle_naive,
                model=MODEL_TAG,
                member=0,
                station=icao,
                valid_date=valid_date,
                forecast_high_f=kelvin_to_fahrenheit(kelvin),
                forecast_low_f=None,  # mx2t24 is daily MAX; no MIN counterpart in this pull
            )
        )
    return rows


async def fetch_and_upsert(
    *,
    db_path: Path,
    cycle: datetime,
    stations: tuple[StationCoord, ...] | None = None,
    http_client: httpx.AsyncClient | None = None,
    max_lookback_cycles: int = 4,
) -> int:
    """Pull the newest available cycle's day-aligned mx2t24 ``fc.grib2``,
    extract per station, upsert into weather_forecast. Returns row count.

    Starts at ``cycle`` and, on a 404 (not yet / never published), walks
    back one 6h cycle at a time through ``max_lookback_cycles`` candidates
    (default 4 = 24h of cycles) before giving up — the tolerance the module
    docstring always promised. Each candidate uses its own day-aligned step
    (``step_hours_for_cycle``) and stores under its own covered UTC day
    (``valid_date_for_cycle``): the first three candidates of a UTC day all
    target the same ``valid_date``, so a fallback usually just means a
    longer-lead forecast of the same day. Non-404 errors raise immediately.

    ``http_client`` is injectable so tests can pass a
    ``MockTransport``-backed client to avoid touching the live ECMWF
    dissemination server.
    """
    if max_lookback_cycles < 1:
        raise ValueError(f"max_lookback_cycles must be >= 1, got {max_lookback_cycles}")
    coords = stations or _stations_to_coords()
    as_of = datetime.now(tz=UTC)

    owns_client = http_client is None
    client = http_client or default_client()
    body: bytes | None = None
    used_cycle = cycle
    try:
        for attempt in range(max_lookback_cycles):
            candidate = cycle - timedelta(hours=6 * attempt)
            file = OpenDataFile(
                cycle=candidate,
                stream="oper",
                type="fc",
                step_hours=step_hours_for_cycle(candidate),
            )
            try:
                body = await fetch_grib2_bytes(client, file)
                used_cycle = candidate
                break
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 404:
                    raise
                log.warning(
                    "ecmwf_opendata.fallback_to_prior_cycle",
                    asked=candidate.isoformat(),
                    attempt=attempt + 1,
                    max_lookback_cycles=max_lookback_cycles,
                )
        if body is None:
            raise RuntimeError(
                f"no published ECMWF Open Data cycle within {max_lookback_cycles} "
                f"lookback cycles of {cycle.isoformat()} (all 404) — page the operator"
            )
    finally:
        if owns_client:
            await client.aclose()

    valid_date = valid_date_for_cycle(used_cycle)
    station_kelvin = _extract_mx2t24_per_station(body, stations=coords)
    rows = _build_forecast_rows(
        station_kelvin=station_kelvin,
        cycle=used_cycle,
        valid_date=valid_date,
        as_of=as_of,
    )
    con = connect(db_path)
    try:
        n = insert_forecasts(con, rows)
    finally:
        con.close()
    log.info(
        "ecmwf_opendata.ingest_done",
        cycle=used_cycle.isoformat(),
        step_hours=step_hours_for_cycle(used_cycle),
        valid_date=valid_date.isoformat(),
        n_stations=len(station_kelvin),
        n_rows=n,
        bytes_pulled=len(body),
        db=str(db_path),
    )
    return n


def main(*, db_path: Path | None = None, now: datetime | None = None) -> int:
    """``python -m kq ingest-ecmwf-opendata`` entrypoint."""
    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)
    when = now or datetime.now(tz=UTC)
    cycle = latest_published_cycle(now=when)
    n = asyncio.run(fetch_and_upsert(db_path=path, cycle=cycle))
    print(
        f"ecmwf_opendata: upserted {n} rows starting from cycle {cycle.isoformat()} "
        f"-> {path} (see ecmwf_opendata.ingest_done log for the cycle used)"
    )
    return n


__all__ = [
    "DEFAULT_PUBLISH_BUFFER_HOURS",
    "LEAD_1_STEP_HOURS",
    "MODEL_TAG",
    "SHORT_NAME_MX2T24",
    "fetch_and_upsert",
    "latest_published_cycle",
    "main",
    "step_hours_for_cycle",
    "valid_date_for_cycle",
]
