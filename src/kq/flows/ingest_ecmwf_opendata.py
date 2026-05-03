"""ECMWF Open Data ingest -- Phase 2 (one cycle per tick, lead-1 daily Tmax).

Pulls the most recent ECMWF IFS HRES cycle's ``fc.grib2`` at step=48h
and extracts the ``mx2t24`` (max 2-metre temperature in last 24 hours)
field at each station's nearest grid point. ``mx2t24`` at step=48h
spans the [step=24h, step=48h] window after a 00z init -- which is
exactly tomorrow's calendar-day maximum. One file per cycle (~130 MB),
one variable per file -- no client-side multi-step aggregation.

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

**Tolerant of cycle-publish race**: ECMWF publishes step files 1-2
hours after the init time, so a 00z + step=48h fetch at 01z UTC will
404. The flow falls back to the previous cycle (which is 6h older
data) and only fails on the second 404. Operators get a structured
``ecmwf_opendata.fallback_to_prior_cycle`` log event.
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

# Forecast step that gives us tomorrow's calendar-day max under a 00z
# init. ``mx2t24`` at step=48h accumulates over the [24h, 48h] window
# -- the next calendar day from the init time.
LEAD_1_STEP_HOURS: int = 48

# WMO short name for "Maximum 2 metre temperature in last 24 hours"
# (paramId 121). Same filter pattern as ``2t`` extraction in PR 1.
SHORT_NAME_MX2T24: str = "mx2t24"


def _stations_to_coords(stations: tuple[Station, ...] = STATIONS) -> tuple[StationCoord, ...]:
    """Project ``Station`` (full record) to ``StationCoord`` (lat/lon
    needed for nearest-grid-point sampling)."""
    return tuple(
        StationCoord(icao=s.icao, latitude=s.latitude, longitude=s.longitude) for s in stations
    )


def latest_published_cycle(*, now: datetime, max_lookback_cycles: int = 4) -> datetime:
    """Return the most recent ECMWF cycle (00/06/12/18 UTC) that has
    plausibly published its step=48h ``fc.grib2`` by ``now``.

    ECMWF publishes step files 1-2 hours after the init time. We use a
    2.5h buffer so a fetch at 02:30 UTC pulls the 00z init confidently.
    Earlier cycles than that fall back to the previous one.

    ``max_lookback_cycles`` caps the recursion at 4 (24h of cycles) --
    if no cycle in the last day is reachable, the operator should be
    paged separately.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    publish_buffer = timedelta(hours=2, minutes=30)
    candidate = now.astimezone(UTC) - publish_buffer
    # Round down to the most recent published cycle hour.
    candidate_hour = max(h for h in CYCLE_HOURS if h <= candidate.hour)
    cycle = candidate.replace(hour=candidate_hour, minute=0, second=0, microsecond=0)
    for _ in range(max_lookback_cycles):
        return cycle
    raise RuntimeError("no plausible cycle within max_lookback_cycles")


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
) -> int:
    """Pull one cycle's step=48h ``fc.grib2``, extract mx2t24 per
    station, upsert into weather_forecast. Returns row count touched.

    ``http_client`` is injectable so tests can pass a
    ``MockTransport``-backed client to avoid touching the live ECMWF
    dissemination server.
    """
    coords = stations or _stations_to_coords()
    file = OpenDataFile(cycle=cycle, stream="oper", type="fc", step_hours=LEAD_1_STEP_HOURS)
    valid_date = (cycle + timedelta(hours=LEAD_1_STEP_HOURS)).date()
    as_of = datetime.now(tz=UTC)

    owns_client = http_client is None
    client = http_client or default_client()
    try:
        try:
            body = await fetch_grib2_bytes(client, file)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                # Cycle not yet published. Fall back to the previous cycle.
                prior_cycle = cycle - timedelta(hours=6)
                log.warning(
                    "ecmwf_opendata.fallback_to_prior_cycle",
                    asked=cycle.isoformat(),
                    falling_back_to=prior_cycle.isoformat(),
                )
                file = OpenDataFile(
                    cycle=prior_cycle,
                    stream="oper",
                    type="fc",
                    step_hours=LEAD_1_STEP_HOURS,
                )
                valid_date = (prior_cycle + timedelta(hours=LEAD_1_STEP_HOURS)).date()
                body = await fetch_grib2_bytes(client, file)
            else:
                raise
    finally:
        if owns_client:
            await client.aclose()

    station_kelvin = _extract_mx2t24_per_station(body, stations=coords)
    rows = _build_forecast_rows(
        station_kelvin=station_kelvin,
        cycle=file.cycle,
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
        cycle=file.cycle.isoformat(),
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
    print(f"ecmwf_opendata: upserted {n} rows for cycle {cycle.isoformat()} -> {path}")
    return n


__all__ = [
    "LEAD_1_STEP_HOURS",
    "MODEL_TAG",
    "SHORT_NAME_MX2T24",
    "fetch_and_upsert",
    "latest_published_cycle",
    "main",
]
