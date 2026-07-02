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

    Guarded upsert: this table is settlement truth. ACIS re-serving 'M'
    (missing -> parsed as NULL) for a day whose value we already ingested
    must never wipe the stored value — the blind ``INSERT OR REPLACE`` this
    replaces did exactly that. NULL never overwrites a non-NULL ``high_f`` /
    ``low_f``; a real incoming value still updates the stored one, because
    late corrections are the whole point of the trailing re-fetch window.
    """
    batch: list[Sequence[object]] = [
        (r.station, r.valid_date, r.high_f, r.low_f, r.source, to_naive_utc(r.fetched_at))
        for r in rows
    ]
    if not batch:
        return 0
    con.executemany(
        """
        INSERT INTO weather_observed
        (station, valid_date, high_f, low_f, source, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (station, valid_date) DO UPDATE SET
            high_f     = COALESCE(EXCLUDED.high_f, weather_observed.high_f),
            low_f      = COALESCE(EXCLUDED.low_f, weather_observed.low_f),
            source     = EXCLUDED.source,
            fetched_at = EXCLUDED.fetched_at
        """,
        batch,
    )
    return len(batch)
