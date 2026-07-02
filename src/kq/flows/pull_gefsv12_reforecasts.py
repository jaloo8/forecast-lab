"""GEFSv12 reforecast ingest (Phase 2 of #6).

Pulls per-(station, cycle, member) lead-day-1 Tmax forecasts from the
``s3://noaa-gefs-retrospective`` archive and stores them in the existing
``weather_forecast`` table tagged ``model='gefsv12_reforecast'``,
``member=0..4`` (c00=0, p01..p04 = 1..4).

Lead-day-1 aggregation: each 10-day Days:1-10 GRIB2 file contains ~80
records at 3-hour TMAX windows. For lead-day-1 (next calendar day's max
from a 00z cycle), we take the **max across records covering hours
24-48** — i.e., 7 overlapping 3-hour windows. One forecast_high_f row
per (cycle, member, station, valid_date).

Usage::

    # Smoke test (~30 files, ~5 min):
    kq pull-gefsv12-reforecasts --start-year 2019 --end-year 2019 --members c00 --max-days 30

    # Full c00-only 20-year pull (~7.3k files, ~30-60 min):
    kq pull-gefsv12-reforecasts --start-year 2000 --end-year 2019 --members c00

    # Full archive (5 members, ~36k files, ~hours):
    kq pull-gefsv12-reforecasts

The ingest is idempotent on the ``weather_forecast`` PK
``(as_of, model, member, station, valid_date)`` — re-running with the
same scope overwrites in place rather than duplicating.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import structlog

from kq.clients.gefs_reforecast import (
    DEFAULT_DAYS_RANGE,
    DEFAULT_MEMBERS,
    TMAX_VARIABLE,
    ReforecastPullIncompleteError,
    StationCoord,
    StationRecord,
    fetch_records_for_files,
    iter_reforecast_files,
    kelvin_to_fahrenheit,
)
from kq.clients.stations import STATIONS
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.storage.duckdb_store import connect

log = structlog.get_logger(__name__)

REFORECAST_MODEL_TAG = "gefsv12_reforecast"
MEMBER_INDEX_BY_NAME: dict[str, int] = {
    "c00": 0,
    "p01": 1,
    "p02": 2,
    "p03": 3,
    "p04": 4,
}

# Lead-day-1 record selection. From a 00z cycle, the 24-48 hour window
# covers tomorrow's calendar day (UTC). Records 9-16 in the standard
# GEFSv12 TMAX file are the seven 3-hour windows: 24-27, 27-30, ..., 45-48.
# We take the max across them per (station, cycle, member).
DAY1_RECORD_NOS: tuple[int, ...] = (9, 10, 11, 12, 13, 14, 15, 16)


@dataclass(frozen=True, slots=True)
class IngestRow:
    """One row to insert into weather_forecast."""

    as_of: datetime
    run_time: datetime
    member: int  # 0..4
    station: str
    valid_date: datetime  # midnight of the day being forecast
    forecast_high_f: float


def _parse_cycle_to_datetime(cycle: str) -> datetime:
    """``YYYYMMDDHH`` -> ``datetime`` (naive UTC, matching weather_forecast convention)."""
    return datetime.strptime(cycle, "%Y%m%d%H")


def _stations_to_coords() -> list[StationCoord]:
    """Build StationCoord list from kq.clients.stations.STATIONS.

    Converts negative (Western-hemisphere) longitude to GEFS's 0-360 convention.
    """
    return [
        StationCoord(
            icao=s.icao,
            latitude=s.latitude,
            longitude_e=(s.longitude + 360.0) % 360.0,
        )
        for s in STATIONS
    ]


def _aggregate_day1_max(records: list[StationRecord]) -> dict[tuple[str, str, str], float]:
    """Group by (cycle, member, station), take max(tmax_kelvin) across records.

    Returns ``{(cycle, member, icao): max_tmax_kelvin}``.
    """
    by_key: dict[tuple[str, str, str], float] = {}
    for r in records:
        key = (r.cycle, r.member, r.icao)
        prev = by_key.get(key, float("-inf"))
        if r.tmax_kelvin > prev:
            by_key[key] = r.tmax_kelvin
    return by_key


def _build_ingest_rows(
    aggregated: dict[tuple[str, str, str], float],
) -> list[IngestRow]:
    """Convert aggregated max-Tmax dict to IngestRow with valid_date = cycle + 1 day."""
    rows: list[IngestRow] = []
    for (cycle, member_name, icao), tmax_k in aggregated.items():
        cycle_dt = _parse_cycle_to_datetime(cycle)
        valid_date = cycle_dt + timedelta(days=1)
        member_idx = MEMBER_INDEX_BY_NAME.get(member_name)
        if member_idx is None:
            log.warning("ingest.unknown_member", member=member_name)
            continue
        rows.append(
            IngestRow(
                as_of=cycle_dt,
                run_time=cycle_dt,
                member=member_idx,
                station=icao,
                valid_date=valid_date,
                forecast_high_f=kelvin_to_fahrenheit(tmax_k),
            )
        )
    return rows


def _insert_ingest_rows(con: object, rows: list[IngestRow]) -> int:
    """Insert into weather_forecast with model='gefsv12_reforecast'.

    Idempotent on ``(as_of, model, member, station, valid_date)``.
    Uses the existing connect()'s DuckDB connection.
    """
    if not rows:
        return 0
    batch = [
        (
            r.as_of,
            r.run_time,
            REFORECAST_MODEL_TAG,
            r.member,
            r.station,
            r.valid_date.date(),
            r.forecast_high_f,
            None,  # forecast_low_f — not in our extraction yet
        )
        for r in rows
    ]
    con.executemany(  # type: ignore[attr-defined]
        """
        INSERT OR REPLACE INTO weather_forecast
        (as_of, run_time, model, member, station, valid_date, forecast_high_f, forecast_low_f)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        batch,
    )
    return len(batch)


async def pull(
    *,
    start_year: int = 2000,
    end_year: int = 2019,
    members: tuple[str, ...] = DEFAULT_MEMBERS,
    max_days: int | None = None,
    max_concurrent: int = 5,
    db_path: Path | None = None,
) -> int:
    """Run the reforecast pull. Returns rows inserted.

    ``max_days`` truncates the iteration after that many cycles per member —
    handy for smoke tests. Use ``None`` for the full year range.

    Partial-success semantics (2026-07-01 audit, Tier 2 high): rows from
    every file that fetched cleanly are persisted FIRST, then, if any file
    failed, :class:`ReforecastPullIncompleteError` is raised so the CLI
    exits nonzero. A re-run with the same scope is idempotent on the
    ``weather_forecast`` PK and fills only the holes.
    """
    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)

    files = list(
        iter_reforecast_files(
            start_year=start_year,
            end_year=end_year,
            members=members,
            variables=(TMAX_VARIABLE,),
            days_ranges=(DEFAULT_DAYS_RANGE,),
        )
    )
    if max_days is not None:
        # Truncate per (member, variable) — keep the same days across members.
        files_per_member = max_days
        truncated: list = []  # type: ignore[type-arg]
        seen_per_member: dict[str, int] = {}
        for f in files:
            seen_per_member.setdefault(f.member, 0)
            if seen_per_member[f.member] >= files_per_member:
                continue
            seen_per_member[f.member] += 1
            truncated.append(f)
        files = truncated

    log.info(
        "gefsv12.pull_starting",
        n_files=len(files),
        members=members,
        max_concurrent=max_concurrent,
        start_year=start_year,
        end_year=end_year,
    )
    print(f"Pulling {len(files)} files at {max_concurrent} concurrent...")

    stations = _stations_to_coords()
    result = await fetch_records_for_files(
        files,
        stations=stations,
        target_record_nos=DAY1_RECORD_NOS,
        max_concurrent=max_concurrent,
    )
    log.info(
        "gefsv12.records_fetched",
        n_records=len(result.records),
        n_files=len(files),
        n_failed=result.n_failed,
    )

    aggregated = _aggregate_day1_max(result.records)
    rows = _build_ingest_rows(aggregated)

    con = connect(path)
    try:
        n = _insert_ingest_rows(con, rows)
    finally:
        con.close()

    log.info("gefsv12.pull_done", n_inserted=n, n_failed_files=result.n_failed, db=str(path))
    print(f"inserted {n} rows into weather_forecast (model='{REFORECAST_MODEL_TAG}')")
    if result.failures:
        # Each failure was already logged as gefs_reforecast.file_failed.
        log.error(
            "gefsv12.pull_incomplete",
            n_failed=result.n_failed,
            n_files=len(files),
            failed_urls=[f.file.grib2_url for f in result.failures[:20]],
        )
        print(
            f"WARNING: {result.n_failed}/{len(files)} files failed; the {n} rows above "
            "are a PARTIAL result. Re-run the same scope to fill the holes."
        )
        raise ReforecastPullIncompleteError(
            f"{result.n_failed} of {len(files)} reforecast files failed to fetch; "
            f"{n} rows from successful files were persisted (idempotent re-run fills holes)"
        )
    return n


def main(
    *,
    start_year: int = 2000,
    end_year: int = 2019,
    members: tuple[str, ...] = DEFAULT_MEMBERS,
    max_days: int | None = None,
    max_concurrent: int = 5,
) -> None:
    """`python -m kq pull-gefsv12-reforecasts` entrypoint."""
    asyncio.run(
        pull(
            start_year=start_year,
            end_year=end_year,
            members=members,
            max_days=max_days,
            max_concurrent=max_concurrent,
        )
    )


if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=2000)
    parser.add_argument("--end-year", type=int, default=2019)
    parser.add_argument(
        "--members",
        type=str,
        default=",".join(DEFAULT_MEMBERS),
        help="Comma-separated list, e.g., 'c00' or 'c00,p01'",
    )
    parser.add_argument("--max-days", type=int, default=None)
    parser.add_argument("--max-concurrent", type=int, default=5)
    args = parser.parse_args()
    main(
        start_year=args.start_year,
        end_year=args.end_year,
        members=tuple(args.members.split(",")),
        max_days=args.max_days,
        max_concurrent=args.max_concurrent,
    )
