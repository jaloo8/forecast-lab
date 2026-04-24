"""Tests for the historical weather backfill flow."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from kq.clients.openmeteo import HIST_MODEL_NAME, _parse_historical_payload
from kq.flows.backfill_weather import backfill
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.forecasts import insert_forecasts

FIXTURE = Path(__file__).parent / "fixtures" / "openmeteo_historical_klax.json"


def test_backfill_rejects_reversed_date_range(tmp_path: Path) -> None:
    async def _run() -> None:
        with pytest.raises(ValueError, match="precedes"):
            await backfill(
                start_date=date(2025, 6, 10),
                end_date=date(2025, 6, 1),
                db_path=tmp_path / "b.duckdb",
            )

    asyncio.run(_run())


def test_historical_rows_coexist_with_ensemble_in_pk(tmp_path: Path) -> None:
    """The historical model='gfs_hist' tag keeps PK distinct from ensemble rows
    with the same (as_of, member, station, valid_date)."""
    db_path = tmp_path / "hist.duckdb"
    bootstrap(db_path)

    as_of = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)

    # Historical deterministic rows
    hist_rows = _parse_historical_payload(
        json.loads(FIXTURE.read_text(encoding="utf-8")),
        as_of=as_of,
        station_icao="KLAX",
    )

    con = connect(db_path)
    try:
        n_hist = insert_forecasts(con, hist_rows)

        # Hand-insert a matching ensemble row with the SAME as_of, member=0,
        # station=KLAX, valid_date=2025-06-01 but model='gefs' — must coexist
        # with the historical row, not collide.
        con.execute(
            """
            INSERT INTO weather_forecast
            (as_of, run_time, model, member, station, valid_date,
             forecast_high_f, forecast_low_f)
            VALUES (?, ?, 'gefs', 0, 'KLAX', '2025-06-01', 77.5, 61.0)
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
    # 3 historical rows + 1 ensemble row, no PK collision.
    assert counts == [("gefs", 1), (HIST_MODEL_NAME, 3)]
