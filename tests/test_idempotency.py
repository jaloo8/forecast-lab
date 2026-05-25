"""Idempotency regression guards for the ingest repositories.

The cron soak re-runs every ingest constantly (weather every 6 h, METAR every
15 min, NDFD every 6 h, ...), so each repository write MUST be idempotent:
re-inserting the SAME rows must NOT grow the table, and re-inserting with a
changed value at the same PK must REPLACE in place. Every repo uses
``INSERT OR REPLACE`` today; these tests pin that invariant so a future change
to a plain ``INSERT`` -- which would silently duplicate data on every cron tick
and corrupt the model's training set -- fails CI.

Scoped to the weather lane (forecasts / METAR / observed) — the highest-
frequency writers in the live soak. The NBA/Kalshi upserts are exercised by
their own repo tests; the matrix (docs/TESTING.md) tracks the full coverage.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

from kq.clients.acis import DailyClimateObservation
from kq.clients.metar import MetarObservation
from kq.clients.openmeteo import EnsembleForecast
from kq.storage.duckdb_store import bootstrap
from kq.storage.repositories.forecasts import insert_forecasts
from kq.storage.repositories.metar import insert_metar
from kq.storage.repositories.observed import insert_observed


def _con(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    db = tmp_path / "idem.duckdb"
    bootstrap(db)
    return duckdb.connect(str(db))


def _count(con: duckdb.DuckDBPyConnection, table: str) -> int:
    return int(con.execute(f"SELECT count(*) FROM {table}").fetchone()[0])


def _forecasts() -> list[EnsembleForecast]:
    aso = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    return [
        EnsembleForecast(
            as_of=aso,
            run_time=aso,
            model="gfs_seamless",
            member=m,
            station="KLAX",
            valid_date=date(2025, 1, 2),
            forecast_high_f=75.0 + m,
            forecast_low_f=55.0,
        )
        for m in range(3)
    ]


def test_insert_forecasts_idempotent(tmp_path: Path) -> None:
    con = _con(tmp_path)
    rows = _forecasts()
    insert_forecasts(con, rows)
    assert _count(con, "weather_forecast") == 3
    insert_forecasts(con, rows)  # same rows again
    assert _count(con, "weather_forecast") == 3


def test_forecasts_replace_updates_in_place(tmp_path: Path) -> None:
    con = _con(tmp_path)
    insert_forecasts(con, _forecasts())
    aso = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    updated = [
        EnsembleForecast(
            as_of=aso,
            run_time=aso,
            model="gfs_seamless",
            member=0,
            station="KLAX",
            valid_date=date(2025, 1, 2),
            forecast_high_f=99.0,  # changed, same PK
            forecast_low_f=55.0,
        )
    ]
    insert_forecasts(con, updated)
    assert _count(con, "weather_forecast") == 3  # replaced, not appended
    val = con.execute(
        "SELECT forecast_high_f FROM weather_forecast WHERE member = 0 AND station = 'KLAX'"
    ).fetchone()[0]
    assert val == 99.0


def test_insert_metar_idempotent(tmp_path: Path) -> None:
    con = _con(tmp_path)
    t = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
    rows = [
        MetarObservation(
            obs_time=t, station=s, temp_f=70.0, dewpoint_f=50.0, wind_kt=5.0, pressure_mb=1013.0
        )
        for s in ("KLAX", "KJFK")
    ]
    insert_metar(con, rows)
    assert _count(con, "metar_obs") == 2
    insert_metar(con, rows)
    assert _count(con, "metar_obs") == 2


def test_insert_observed_idempotent(tmp_path: Path) -> None:
    con = _con(tmp_path)
    rows = [
        DailyClimateObservation(
            station="KLAX",
            valid_date=date(2025, 1, 2),
            high_f=78.0,
            low_f=54.0,
            source="acis",
            fetched_at=datetime(2025, 1, 3, 0, 0, tzinfo=UTC),
        )
    ]
    insert_observed(con, rows)
    assert _count(con, "weather_observed") == 1
    insert_observed(con, rows)
    assert _count(con, "weather_observed") == 1
