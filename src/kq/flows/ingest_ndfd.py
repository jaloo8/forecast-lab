"""One-shot NDFD/NBM ingest: pull deterministic Tmax for every station.

The benchmark for "do we have edge?" — see
``docs/research/NDFD-BENCHMARK-SOURCE.md``. Safe to run on any cadence;
each row is idempotent on (as_of, source, station, valid_date). v1 pulls
``forecast_days=7`` so a single cycle covers every operational lead time
we trade.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from kq.clients.ndfd import NbmDeterministicForecast, NdfdClient
from kq.clients.stations import STATIONS
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.storage.duckdb_store import connect
from kq.storage.repositories.ndfd import insert_ndfd_forecasts

log = structlog.get_logger(__name__)


async def ingest_once(
    *,
    db_path: Path | None = None,
    forecast_days: int = 7,
) -> int:
    """Pull live NBM-deterministic Tmax for every station, write to DuckDB.

    Returns total rows written. Idempotent within the as_of cycle. A single
    failed station logs and continues; the whole flow only raises on a
    catastrophic DB error.
    """
    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)
    rows: list[NbmDeterministicForecast] = []
    async with NdfdClient() as client:
        for station in STATIONS:
            try:
                station_rows = await client.fetch_forecast(
                    station,
                    forecast_days=forecast_days,
                )
            except Exception:
                log.exception("ndfd.fetch_failed", station=station.icao)
                continue
            log.info(
                "ndfd.fetched",
                station=station.icao,
                rows=len(station_rows),
            )
            rows.extend(station_rows)

    con = connect(path)
    try:
        n = insert_ndfd_forecasts(con, rows)
    finally:
        con.close()
    log.info("ndfd.ingest_done", inserted=n, db=str(path))
    return n


def main() -> None:
    """`python -m kq.flows.ingest_ndfd` entrypoint."""
    total = asyncio.run(ingest_once())
    print(f"inserted {total} NDFD/NBM rows")


if __name__ == "__main__":
    main()
