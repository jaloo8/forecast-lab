"""Historical NDFD/NBM backfill: pull deterministic Tmax for past valid_dates.

Feeds PR 2's backtest CLV / Brier-vs-NDFD comparison. Open-Meteo's NBM history
reaches back to ~2024-11-01; pre-Nov-2024 dates return null and are silently
dropped by the parser. See ``docs/research/NDFD-BENCHMARK-SOURCE.md``.
"""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import structlog

from kq.clients.ndfd import NbmDeterministicForecast, NdfdClient
from kq.clients.stations import STATIONS
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.storage.duckdb_store import connect
from kq.storage.repositories.ndfd import insert_ndfd_forecasts

log = structlog.get_logger(__name__)


async def backfill(
    *,
    start_date: date,
    end_date: date,
    db_path: Path | None = None,
) -> int:
    """Backfill historical NBM-deterministic Tmax for every station.

    Returns total rows written. Idempotent on the ndfd_forecast PK.
    Per-station failures log and continue so a single upstream blip
    doesn't lose the whole window.
    """
    if end_date < start_date:
        raise ValueError(f"end_date {end_date} precedes start_date {start_date}")

    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)

    rows: list[NbmDeterministicForecast] = []
    async with NdfdClient() as client:
        for station in STATIONS:
            try:
                station_rows = await client.fetch_historical(
                    station,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception:
                log.exception("ndfd.backfill_failed", station=station.icao)
                continue
            log.info(
                "ndfd.backfilled",
                station=station.icao,
                rows=len(station_rows),
                start=start_date.isoformat(),
                end=end_date.isoformat(),
            )
            rows.extend(station_rows)

    con = connect(path)
    try:
        n = insert_ndfd_forecasts(con, rows)
    finally:
        con.close()
    log.info(
        "ndfd.backfill_done",
        inserted=n,
        start=start_date.isoformat(),
        end=end_date.isoformat(),
        db=str(path),
    )
    return n


def main(*, start: str, end: str) -> None:
    """`python -m kq backfill-ndfd --start YYYY-MM-DD --end YYYY-MM-DD` entrypoint."""
    start_d = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    total = asyncio.run(backfill(start_date=start_d, end_date=end_d))
    print(f"backfilled {total} NDFD/NBM rows ({start} to {end})")


if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()
    main(start=args.start, end=args.end)
