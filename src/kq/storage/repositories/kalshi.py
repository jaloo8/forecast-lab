"""Kalshi market + order-book snapshot repositories."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    from kq.clients.kalshi import Market, OrderBookSnapshot


def upsert_kalshi_markets(
    con: duckdb.DuckDBPyConnection,
    rows: Iterable[Market],
) -> int:
    """Upsert Kalshi market metadata. PK is `ticker`."""
    batch: list[Sequence[object]] = [
        (
            m.ticker,
            m.event_ticker,
            m.category,
            m.rules_primary,
            m.open_time,
            m.close_time,
            m.rules_primary,
            m.strike_type,
            m.floor_strike,
            m.cap_strike,
        )
        for m in rows
    ]
    if not batch:
        return 0
    con.executemany(
        """
        INSERT OR REPLACE INTO kalshi_market
        (ticker, event_ticker, category, settlement_src, opens_at, closes_at, rules_text,
         strike_type, floor_strike, cap_strike)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            None,  # volume_24h not on snapshot endpoint in v1
            None,  # open_interest not on snapshot endpoint in v1
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
