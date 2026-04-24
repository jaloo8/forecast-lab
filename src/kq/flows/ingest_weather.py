"""One-shot weather ingest: pull Open-Meteo ensembles for every station, write DuckDB.

Safe to run on any cadence (cron, Prefect, manual). Every row is idempotent on
(as_of, model, member, station, valid_date).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from kq.clients.openmeteo import EnsembleForecast, OpenMeteoClient
from kq.clients.stations import STATIONS
from kq.config import get_settings
from kq.storage.duckdb_store import connect
from kq.storage.repositories.forecasts import insert_forecasts

log = structlog.get_logger(__name__)


async def ingest_once(*, db_path: Path | None = None) -> int:
    """Pull one round of ensemble forecasts for every station, write to DuckDB.

    Returns total rows inserted. Idempotent within the same as_of cycle.
    """
    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)
    rows: list[EnsembleForecast] = []
    async with OpenMeteoClient() as client:
        for station in STATIONS:
            try:
                station_rows = await client.fetch_ensemble(station)
            except Exception:
                log.exception("openmeteo.fetch_failed", station=station.icao)
                continue
            log.info(
                "openmeteo.fetched",
                station=station.icao,
                rows=len(station_rows),
            )
            rows.extend(station_rows)

    con = connect(path)
    try:
        n = insert_forecasts(con, rows)
    finally:
        con.close()
    log.info("weather.ingest_done", inserted=n, db=str(path))
    return n


def main() -> None:
    """`python -m kq.flows.ingest_weather` entrypoint."""
    total = asyncio.run(ingest_once())
    print(f"inserted {total} forecast rows")


def _db_path_from_settings(url: str) -> Path:
    prefix = "duckdb:///"
    if not url.startswith(prefix):
        raise ValueError(f"Only duckdb:// URLs supported in v1, got {url!r}")
    return Path(url.removeprefix(prefix))


if __name__ == "__main__":
    main()
