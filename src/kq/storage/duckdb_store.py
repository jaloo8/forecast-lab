"""Minimal DuckDB connection factory, schema bootstrap, and typed inserts."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    from kq.clients.openmeteo import EnsembleForecast

SCHEMA_PATH = Path(__file__).parent / "schemas.sql"


def connect(db_path: Path) -> duckdb.DuckDBPyConnection:
    """Open (or create) a DuckDB connection at `db_path`."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def bootstrap(db_path: Path) -> None:
    """Create all tables from schemas.sql if they don't exist. Idempotent."""
    con = connect(db_path)
    try:
        con.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    finally:
        con.close()


def insert_forecasts(
    con: duckdb.DuckDBPyConnection,
    rows: Iterable[EnsembleForecast],
) -> int:
    """Insert ensemble forecast rows, returning the count inserted.

    Uses `INSERT OR REPLACE` so re-running an ingest within the same `as_of`
    cycle is idempotent for the (as_of, model, member, station, valid_date) PK.
    """
    batch: list[Sequence[object]] = [
        (
            r.as_of,
            r.run_time,
            r.model,
            r.member,
            r.station,
            r.valid_date,
            r.forecast_high_f,
            r.forecast_low_f,
        )
        for r in rows
    ]
    if not batch:
        return 0
    con.executemany(
        """
        INSERT OR REPLACE INTO weather_forecast
        (as_of, run_time, model, member, station, valid_date,
         forecast_high_f, forecast_low_f)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        batch,
    )
    return len(batch)
