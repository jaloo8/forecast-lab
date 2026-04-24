"""Backfill observed daily climate (training ground-truth).

Phase 2 deliverable. Pulls NWS Daily Climate Report values via ACIS for every
station over a date range. Kalshi weather markets settle on these exact
values, so our training truth matches the market's resolution truth.
"""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import structlog

from kq.clients.acis import AcisClient, DailyClimateObservation
from kq.clients.stations import STATIONS
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.storage.duckdb_store import connect
from kq.storage.repositories.observed import insert_observed

log = structlog.get_logger(__name__)


async def backfill(
    *,
    start_date: date,
    end_date: date,
    db_path: Path | None = None,
) -> int:
    """Backfill observed daily climate for every station. Returns rows written."""
    if end_date < start_date:
        raise ValueError(f"end_date {end_date} precedes start_date {start_date}")

    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)

    rows: list[DailyClimateObservation] = []
    async with AcisClient() as client:
        for station in STATIONS:
            try:
                station_rows = await client.fetch_daily(
                    station.icao,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception:
                log.exception("acis.backfill_failed", station=station.icao)
                continue
            log.info(
                "acis.backfilled",
                station=station.icao,
                rows=len(station_rows),
                start=start_date.isoformat(),
                end=end_date.isoformat(),
            )
            rows.extend(station_rows)

    con = connect(path)
    try:
        n = insert_observed(con, rows)
    finally:
        con.close()
    log.info(
        "observed.backfill_done",
        inserted=n,
        start=start_date.isoformat(),
        end=end_date.isoformat(),
        db=str(path),
    )
    return n


def main(*, start: str, end: str) -> None:
    """`python -m kq backfill-observed --start YYYY-MM-DD --end YYYY-MM-DD` entrypoint."""
    start_d = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    total = asyncio.run(backfill(start_date=start_d, end_date=end_d))
    print(f"backfilled {total} observed daily rows ({start} to {end})")


if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()
    main(start=args.start, end=args.end)
