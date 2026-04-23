"""Minimal DuckDB connection factory, schema bootstrap, and typed inserts."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    from kq.clients.kalshi import Market, OrderBookSnapshot
    from kq.clients.metar import MetarObservation
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


def insert_metar(
    con: duckdb.DuckDBPyConnection,
    rows: Iterable[MetarObservation],
) -> int:
    """Insert METAR observations, returning the count inserted.

    Idempotent on the (obs_time, station) PK.
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


def upsert_kalshi_markets(
    con: duckdb.DuckDBPyConnection,
    rows: Iterable[Market],
) -> int:
    """Upsert Kalshi market metadata. PK is `ticker`."""
    batch: list[Sequence[object]] = [
        (
            m.ticker,
            m.event_ticker,
            _kalshi_category(m),
            m.rules_primary,
            m.open_time,
            m.close_time,
            m.rules_primary,
        )
        for m in rows
    ]
    if not batch:
        return 0
    con.executemany(
        """
        INSERT OR REPLACE INTO kalshi_market
        (ticker, event_ticker, category, settlement_src, opens_at, closes_at, rules_text)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        batch,
    )
    return len(batch)


def insert_kalshi_books(
    con: duckdb.DuckDBPyConnection,
    rows: Iterable[OrderBookSnapshot],
) -> int:
    """Append one row per orderbook snapshot. PK is (snap_time, ticker)."""
    batch: list[Sequence[object]] = [
        (
            s.snap_time,
            s.ticker,
            s.yes_bid,
            s.yes_ask,
            s.yes_bid_size,
            s.yes_ask_size,
            None,  # volume_24h — not exposed on snapshot endpoint; left null for v1
            None,  # open_interest — same
        )
        for s in rows
    ]
    if not batch:
        return 0
    con.executemany(
        """
        INSERT OR REPLACE INTO kalshi_book_snap
        (snap_time, ticker, yes_bid, yes_ask, yes_bid_size, yes_ask_size,
         volume_24h, open_interest)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        batch,
    )
    return len(batch)


def _kalshi_category(market: Market) -> str | None:
    # Placeholder; Kalshi's own `category` field is authoritative when present.
    return market.category
