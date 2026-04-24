"""Historical weather backfill: pull deterministic daily highs/lows for training.

Phase 2 deliverable. Feeds the bias-correction model training set.

The Open-Meteo Historical Forecast API returns one deterministic series per
station, so this is dramatically cheaper than a full ensemble backfill. For
the proper 31-member GEFS reforecast (Pass 1 §1b), see the deferred TODO in
docs/research/PASS-1-FEASIBILITY.md.
"""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import structlog

from kq.clients.openmeteo import EnsembleForecast, OpenMeteoClient
from kq.clients.stations import STATIONS
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.storage.duckdb_store import connect
from kq.storage.repositories.forecasts import insert_forecasts

log = structlog.get_logger(__name__)


async def backfill(
    *,
    start_date: date,
    end_date: date,
    db_path: Path | None = None,
) -> int:
    """Backfill historical deterministic forecasts for every station. Returns rows written.

    Idempotent within the existing weather_forecast PK — re-running with the
    same dates overwrites in place rather than duplicating.
    """
    if end_date < start_date:
        raise ValueError(f"end_date {end_date} precedes start_date {start_date}")

    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)

    rows: list[EnsembleForecast] = []
    async with OpenMeteoClient() as client:
        for station in STATIONS:
            try:
                station_rows = await client.fetch_historical_deterministic(
                    station,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception:
                log.exception("openmeteo.backfill_failed", station=station.icao)
                continue
            log.info(
                "openmeteo.backfilled",
                station=station.icao,
                rows=len(station_rows),
                start=start_date.isoformat(),
                end=end_date.isoformat(),
            )
            rows.extend(station_rows)

    con = connect(path)
    try:
        n = insert_forecasts(con, rows)
    finally:
        con.close()
    log.info(
        "weather.backfill_done",
        inserted=n,
        start=start_date.isoformat(),
        end=end_date.isoformat(),
        db=str(path),
    )
    return n


def main(*, start: str, end: str) -> None:
    """`python -m kq backfill-weather --start YYYY-MM-DD --end YYYY-MM-DD` entrypoint."""
    start_d = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    total = asyncio.run(backfill(start_date=start_d, end_date=end_d))
    print(f"backfilled {total} historical forecast rows ({start} to {end})")


if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()
    main(start=args.start, end=args.end)
