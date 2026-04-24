"""METAR observation repository."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    from kq.clients.metar import MetarObservation


def insert_metar(
    con: duckdb.DuckDBPyConnection,
    rows: Iterable[MetarObservation],
) -> int:
    """Insert METAR observations; returns the count inserted.

    Idempotent on (obs_time, station).
    """
    batch: list[Sequence[object]] = [
        (r.obs_time, r.station, r.temp_f, r.dewpoint_f, r.wind_kt, r.pressure_mb) for r in rows
    ]
    if not batch:
        return 0
    con.executemany(
        """
        INSERT OR REPLACE INTO metar_obs
        (obs_time, station, temp_f, dewpoint_f, wind_kt, pressure_mb)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        batch,
    )
    return len(batch)
