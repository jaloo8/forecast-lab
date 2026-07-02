"""Historical weather backfill: TRUE lead-1 daily highs/lows for training.

2026-06-11 audit root cause #8 (fixed in PR-F): the old backfill pulled the
Open-Meteo *Historical Forecast* archive — which serves the freshest archived
run for each past day (~lead-0) — and backdated ``as_of`` to fake lead-1.
Every manifest built on that data was void. This flow now pulls the
Previous Runs API's ``temperature_2m_previous_day1`` (genuinely "predicted
24 hours before valid time"), aggregated over each station's LST day, with
``as_of`` set to the honest availability instant. See
``kq.clients.openmeteo._parsers`` for the full semantics.

Rate-limit etiquette: one request per (station, ~90-day chunk) with a short
pause between requests; ``request_json`` adds exponential backoff on 429/5xx.
A full 2024-11 → today backfill is ~8 chunks x 6 stations ≈ 48 requests.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path
from typing import Final

import structlog

from kq.clients.openmeteo import EnsembleForecast, OpenMeteoClient
from kq.clients.stations import STATIONS
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.storage.duckdb_store import connect
from kq.storage.repositories.forecasts import insert_forecasts

log = structlog.get_logger(__name__)

# ~90 days of hourly data per request keeps individual responses small and
# polite on the free tier while still finishing a 20-month window in <10
# requests per station.
CHUNK_DAYS: Final = 90
# Pause between consecutive requests (seconds). Deliberate under-throttle;
# the shared HTTP helper's backoff handles any 429 that still slips through.
INTER_REQUEST_PAUSE_S: Final = 0.4


def _chunks(start: date, end: date, *, days: int = CHUNK_DAYS) -> list[tuple[date, date]]:
    """Split [start, end] into inclusive chunks of at most ``days`` days."""
    out: list[tuple[date, date]] = []
    cur = start
    while cur <= end:
        stop = min(cur + timedelta(days=days - 1), end)
        out.append((cur, stop))
        cur = stop + timedelta(days=1)
    return out


async def backfill(
    *,
    start_date: date,
    end_date: date,
    db_path: Path | None = None,
) -> int:
    """Backfill true lead-1 forecasts for every station. Returns rows written.

    Idempotent within the existing weather_forecast PK — ``as_of`` derives
    deterministically from ``valid_date`` (not fetch time), so re-running
    the same window overwrites in place rather than duplicating.
    """
    if end_date < start_date:
        raise ValueError(f"end_date {end_date} precedes start_date {start_date}")

    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)

    rows: list[EnsembleForecast] = []
    async with OpenMeteoClient() as client:
        for station in STATIONS:
            station_rows: list[EnsembleForecast] = []
            failed = False
            for chunk_start, chunk_end in _chunks(start_date, end_date):
                try:
                    chunk_rows = await client.fetch_previous_day1(
                        station,
                        start_date=chunk_start,
                        end_date=chunk_end,
                    )
                except Exception:
                    log.exception(
                        "openmeteo.backfill_failed",
                        station=station.icao,
                        chunk_start=chunk_start.isoformat(),
                        chunk_end=chunk_end.isoformat(),
                    )
                    failed = True
                    break
                station_rows.extend(chunk_rows)
                await asyncio.sleep(INTER_REQUEST_PAUSE_S)
            if failed:
                # Partial-station data is worse than none for training: a
                # station whose window is silently truncated would train on
                # a seasonal subset. Drop the whole station and let the
                # operator re-run (idempotent PK makes that safe).
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
    print(f"backfilled {total} true-lead-1 forecast rows ({start} to {end})")


if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()
    main(start=args.start, end=args.end)
