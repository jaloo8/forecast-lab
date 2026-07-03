"""Historical weather backfill: TRUE lead-1 daily highs/lows for training.

2026-06-11 audit root cause #8 (fixed in PR-F): the old backfill pulled the
Open-Meteo *Historical Forecast* archive — which serves the freshest archived
run for each past day (~lead-0) — and backdated ``as_of`` to fake lead-1.
Every manifest built on that data was void. This flow now pulls the
Previous Runs API's ``temperature_2m_previous_day1`` (genuinely "predicted
24 hours before valid time"), aggregated over each station's LST day, with
``as_of`` set to the honest availability instant. See
``kq.clients.openmeteo._parsers`` for the full semantics.

Phase A (2026-07-02): the backfill is multi-model. Each verified Previous
Runs model becomes its own lane (``gfs_prevday1``, ``ecmwf_prevday1``,
``icon_prevday1``, ``gem_prevday1``, ``meteofrance_prevday1``,
``jma_prevday1`` — see ``PREV_DAY1_MODELS``), same LST-day aggregation and
honest ``as_of`` for every lane. ``kq.features.weather`` pools the lanes
into a cross-model consensus (mean + spread) so training/backtest see a
multi-model input comparable to the GEFS+ECMWF ensembles live ingest
provides — the 2026-07-01 audit's caveat (b).

Rate-limit etiquette: one request per (station, model, ~90-day chunk) with a
short pause between requests; ``request_json`` adds exponential backoff on
429/5xx. A full 2024-11 → today backfill is ~8 chunks x 6 stations x 6
models ≈ 288 requests.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Final

import structlog

from kq.clients.openmeteo import PREV_DAY1_MODELS, EnsembleForecast, OpenMeteoClient
from kq.clients.stations import STATIONS
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.storage.duckdb_store import connect
from kq.storage.repositories.forecasts import insert_forecasts

log = structlog.get_logger(__name__)

# ~90 days of hourly data per request keeps individual responses small and
# polite on the free tier while still finishing a 20-month window in <10
# requests per station per model.
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
    model_ids: Sequence[str] | None = None,
) -> int:
    """Backfill true lead-1 forecasts for every station x model lane.

    ``model_ids`` are Previous Runs API model ids (keys of
    ``PREV_DAY1_MODELS``); default is every verified lane. Returns rows
    written. Idempotent within the existing weather_forecast PK — ``as_of``
    derives deterministically from ``valid_date`` (not fetch time), so
    re-running the same window overwrites in place rather than duplicating.
    """
    if end_date < start_date:
        raise ValueError(f"end_date {end_date} precedes start_date {start_date}")
    ids: tuple[str, ...] = tuple(model_ids) if model_ids else tuple(PREV_DAY1_MODELS)
    unknown = [m for m in ids if m not in PREV_DAY1_MODELS]
    if unknown:
        raise ValueError(
            f"unknown previous-runs model ids {unknown!r}; verified: {sorted(PREV_DAY1_MODELS)}"
        )

    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)

    rows: list[EnsembleForecast] = []
    async with OpenMeteoClient() as client:
        for station in STATIONS:
            for model_id in ids:
                lane_rows: list[EnsembleForecast] = []
                failed = False
                for chunk_start, chunk_end in _chunks(start_date, end_date):
                    try:
                        chunk_rows = await client.fetch_previous_day1(
                            station,
                            start_date=chunk_start,
                            end_date=chunk_end,
                            model_id=model_id,
                        )
                    except Exception:
                        log.exception(
                            "openmeteo.backfill_failed",
                            station=station.icao,
                            model_id=model_id,
                            chunk_start=chunk_start.isoformat(),
                            chunk_end=chunk_end.isoformat(),
                        )
                        failed = True
                        break
                    lane_rows.extend(chunk_rows)
                    await asyncio.sleep(INTER_REQUEST_PAUSE_S)
                if failed:
                    # A partially-covered lane is worse than none: a lane
                    # whose window is silently truncated would enter the
                    # cross-model pool for only a seasonal subset of days.
                    # Drop the whole (station, model) lane and let the
                    # operator re-run (idempotent PK makes that safe).
                    # Other lanes for the station are unaffected — the
                    # feature pool tolerates per-day membership counts.
                    continue
                log.info(
                    "openmeteo.backfilled",
                    station=station.icao,
                    model_id=model_id,
                    rows=len(lane_rows),
                    start=start_date.isoformat(),
                    end=end_date.isoformat(),
                )
                rows.extend(lane_rows)

    con = connect(path)
    try:
        n = insert_forecasts(con, rows)
    finally:
        con.close()
    log.info(
        "weather.backfill_done",
        inserted=n,
        models=list(ids),
        start=start_date.isoformat(),
        end=end_date.isoformat(),
        db=str(path),
    )
    return n


def main(*, start: str, end: str, model_ids: Sequence[str] | None = None) -> None:
    """`python -m kq backfill-weather --start YYYY-MM-DD --end YYYY-MM-DD` entrypoint."""
    start_d = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    total = asyncio.run(backfill(start_date=start_d, end_date=end_d, model_ids=model_ids))
    lanes = ", ".join(model_ids) if model_ids else "all verified models"
    print(f"backfilled {total} true-lead-1 forecast rows ({start} to {end}; {lanes})")


if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--model-id", action="append", default=None)
    args = parser.parse_args()
    main(start=args.start, end=args.end, model_ids=args.model_id)
