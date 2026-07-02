"""Tests for the historical weather backfill flow (true lead-1, PR-F)."""

from __future__ import annotations

import asyncio
import itertools
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from kq.clients.openmeteo import PREV_DAY1_MODEL_NAME, parse_previous_runs_payload
from kq.clients.stations import STATIONS_BY_ICAO
from kq.flows.backfill_weather import _chunks, backfill
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.forecasts import insert_forecasts

FIXTURE = Path(__file__).parent / "fixtures" / "openmeteo_previous_runs_klax.json"


def test_backfill_rejects_reversed_date_range(tmp_path: Path) -> None:
    async def _run() -> None:
        with pytest.raises(ValueError, match="precedes"):
            await backfill(
                start_date=date(2025, 6, 10),
                end_date=date(2025, 6, 1),
                db_path=tmp_path / "b.duckdb",
            )

    asyncio.run(_run())


def test_chunks_cover_range_without_overlap() -> None:
    chunks = _chunks(date(2024, 11, 1), date(2025, 6, 30), days=90)
    # Contiguous, non-overlapping, inclusive cover of the window.
    assert chunks[0][0] == date(2024, 11, 1)
    assert chunks[-1][1] == date(2025, 6, 30)
    for (_, prev_end), (next_start, _) in itertools.pairwise(chunks):
        assert next_start == prev_end + timedelta(days=1)
    assert all((end - start).days + 1 <= 90 for start, end in chunks)


def test_chunks_single_day() -> None:
    assert _chunks(date(2025, 1, 1), date(2025, 1, 1)) == [(date(2025, 1, 1), date(2025, 1, 1))]


def test_prevday1_rows_coexist_with_ensemble_in_pk(tmp_path: Path) -> None:
    """The model='gfs_prevday1' tag keeps the PK distinct from ensemble rows
    with the same (member, station, valid_date)."""
    db_path = tmp_path / "hist.duckdb"
    bootstrap(db_path)

    rows = parse_previous_runs_payload(
        json.loads(FIXTURE.read_text(encoding="utf-8")),
        station=STATIONS_BY_ICAO["KLAX"],
    )

    con = connect(db_path)
    try:
        n_hist = insert_forecasts(con, rows)

        # Hand-insert an ensemble row with the SAME member=0, station=KLAX,
        # valid_date=2024-11-01 but model='gefs' — must coexist, not collide.
        as_of = rows[0].as_of
        con.execute(
            """
            INSERT INTO weather_forecast
            (as_of, run_time, model, member, station, valid_date,
             forecast_high_f, forecast_low_f)
            VALUES (?, ?, 'gefs', 0, 'KLAX', '2024-11-01', 67.5, 47.0)
            """,
            (as_of, as_of),
        )

        counts = con.execute(
            """
            SELECT model, COUNT(*) FROM weather_forecast
            GROUP BY model ORDER BY model
            """
        ).fetchall()
    finally:
        con.close()

    assert n_hist == 3
    assert counts == [("gefs", 1), (PREV_DAY1_MODEL_NAME, 3)]


def test_backfill_is_idempotent_because_as_of_is_deterministic(tmp_path: Path) -> None:
    """as_of derives from valid_date (the honest prediction instant), not
    fetch time — so re-inserting the same window overwrites in place."""
    db_path = tmp_path / "idem.duckdb"
    bootstrap(db_path)
    rows = parse_previous_runs_payload(
        json.loads(FIXTURE.read_text(encoding="utf-8")),
        station=STATIONS_BY_ICAO["KLAX"],
    )
    con = connect(db_path)
    try:
        insert_forecasts(con, rows)
        insert_forecasts(con, rows)  # second run must not duplicate
        (n,) = con.execute("SELECT COUNT(*) FROM weather_forecast").fetchone()  # type: ignore[misc]
    finally:
        con.close()
    assert n == 3
