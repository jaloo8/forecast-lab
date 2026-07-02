"""Observed daily climate repository."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

import duckdb

from kq.storage._tz import to_naive_utc

if TYPE_CHECKING:
    from kq.clients.acis import DailyClimateObservation


def insert_observed(
    con: duckdb.DuckDBPyConnection,
    rows: Iterable[DailyClimateObservation],
) -> int:
    """Insert observed daily climate rows; returns count inserted.

    Idempotent on (station, valid_date). `fetched_at` is updated on replace
    so we know when the last truth-pull happened. Timestamps are normalized
    to naive UTC before bind (see `kq.storage._tz`).
    """
    batch: list[Sequence[object]] = [
        (r.station, r.valid_date, r.high_f, r.low_f, r.source, to_naive_utc(r.fetched_at))
        for r in rows
    ]
    if not batch:
        return 0
    con.executemany(
        """
        INSERT OR REPLACE INTO weather_observed
        (station, valid_date, high_f, low_f, source, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        batch,
    )
    return len(batch)
