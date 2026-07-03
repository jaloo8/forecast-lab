"""Daily index OHLC repository (Phase C index-brackets lane)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

import duckdb
import polars as pl

from kq.storage._tz import to_naive_utc

if TYPE_CHECKING:
    from kq.clients.yahoo_chart import IndexDailyBar


def insert_index_daily(
    con: duckdb.DuckDBPyConnection,
    rows: Iterable[IndexDailyBar],
) -> int:
    """Insert daily index OHLC rows; returns count processed.

    Idempotent on (symbol, valid_date). ``fetched_at`` is updated on replace
    so we know when the last vendor pull happened. Timestamps normalized to
    naive UTC before bind (see ``kq.storage._tz``).

    Guarded upsert (house rule, same posture as ``weather_observed``): this
    table is backtest/settlement-adjacent truth. A degraded vendor payload
    re-serving NULL for a session we already stored must never wipe the
    stored value; a real incoming value still updates the stored one,
    because late index corrections are the point of the trailing re-fetch.
    """
    batch: list[Sequence[object]] = [
        (
            r.symbol,
            r.valid_date,
            r.open,
            r.high,
            r.low,
            r.close,
            r.source,
            to_naive_utc(r.fetched_at),
        )
        for r in rows
    ]
    if not batch:
        return 0
    con.executemany(
        """
        INSERT INTO index_daily
        (symbol, valid_date, open, high, low, close, source, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (symbol, valid_date) DO UPDATE SET
            open       = COALESCE(EXCLUDED.open, index_daily.open),
            high       = COALESCE(EXCLUDED.high, index_daily.high),
            low        = COALESCE(EXCLUDED.low, index_daily.low),
            close      = COALESCE(EXCLUDED.close, index_daily.close),
            source     = EXCLUDED.source,
            fetched_at = EXCLUDED.fetched_at
        """,
        batch,
    )
    return len(batch)


def load_daily_closes(con: duckdb.DuckDBPyConnection, symbol: str) -> pl.DataFrame:
    """Chronological daily closes for one symbol.

    Schema: ``valid_date`` (pl.Date), ``close`` (pl.Float64). Rows with a
    NULL close (vendor gap not yet healed) are excluded — HAR-RV needs an
    unbroken close-to-close return chain, and a silent NULL would poison it.
    """
    rows = con.execute(
        """
        SELECT valid_date, close
        FROM index_daily
        WHERE symbol = ? AND close IS NOT NULL
        ORDER BY valid_date
        """,
        [symbol],
    ).fetchall()
    return pl.DataFrame(
        {
            "valid_date": [r[0] for r in rows],
            "close": [float(r[1]) for r in rows],
        },
        schema={"valid_date": pl.Date, "close": pl.Float64},
    )
