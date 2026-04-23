"""One-shot METAR ingest: pull the latest observations for every station."""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from kq.clients.metar import MetarClient
from kq.clients.stations import STATIONS
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.storage.duckdb_store import connect, insert_metar

log = structlog.get_logger(__name__)


async def ingest_once(*, db_path: Path | None = None, hours: int = 1) -> int:
    """Pull the latest METAR for every station into DuckDB.

    Returns the number of rows written. Idempotent on (obs_time, station).
    """
    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)
    station_icaos = tuple(s.icao for s in STATIONS)

    async with MetarClient() as client:
        rows = await client.fetch_latest(station_icaos, hours=hours)

    log.info("metar.fetched", rows=len(rows), stations=len(station_icaos))
    con = connect(path)
    try:
        n = insert_metar(con, rows)
    finally:
        con.close()
    log.info("metar.ingest_done", inserted=n, db=str(path))
    return n


def main() -> None:
    """`python -m kq.flows.ingest_metar` entrypoint."""
    total = asyncio.run(ingest_once())
    print(f"inserted {total} METAR rows")


if __name__ == "__main__":
    main()
