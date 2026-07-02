"""Weather ensemble forecast repository."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

import duckdb

from kq.storage._tz import to_naive_utc

if TYPE_CHECKING:
    from kq.clients.openmeteo import EnsembleForecast


def insert_forecasts(
    con: duckdb.DuckDBPyConnection,
    rows: Iterable[EnsembleForecast],
) -> int:
    """Insert ensemble forecast rows; returns the count inserted.

    `INSERT OR REPLACE` keeps re-running the same ingest idempotent for
    the (as_of, model, member, station, valid_date) PK. Timestamps are
    normalized to naive UTC before bind (see `kq.storage._tz`).
    """
    batch: list[Sequence[object]] = [
        (
            to_naive_utc(r.as_of),
            to_naive_utc(r.run_time),
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
