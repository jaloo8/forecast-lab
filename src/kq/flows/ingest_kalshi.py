"""One-shot Kalshi ingest: snapshot orderbooks for a set of event tickers.

Default behavior — production weather mode:
    For each Kalshi weather station (KXHIGHLAX, KXHIGHNY, ...), list active
    markets and snapshot every orderbook into DuckDB.

Override behavior — `event_tickers=[...]`:
    Skip the station-derived defaults and snapshot orderbooks for whichever
    event tickers the caller passes. Used for verification against demo
    (which currently has NBA / MLB / tennis but no weather), or for one-off
    snapshots of a single market the user cares about.

Refuses to run when Kalshi credentials aren't configured — see README + SETUP.md.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

import structlog

from kq.clients.kalshi import KalshiClient, KalshiCredentialsError, Market, OrderBookSnapshot
from kq.clients.stations import STATIONS
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.kalshi import insert_kalshi_books, upsert_kalshi_markets

log = structlog.get_logger(__name__)


async def ingest_once(
    *,
    db_path: Path | None = None,
    event_tickers: Sequence[str] | None = None,
) -> tuple[int, int]:
    """Snapshot Kalshi markets. Returns (markets_upserted, book_rows_inserted).

    By default, iterates over the 6 weather stations from `kq.clients.stations`.
    When `event_tickers` is supplied, that list is used instead.
    """
    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)

    # Default path: query each weather station's Kalshi SERIES ticker (returns
    # all current markets across its open dated events). The `event_tickers`
    # override instead passes explicit dated EVENT tickers (e.g. NBA verify).
    if event_tickers:
        targets: list[tuple[str, bool]] = [(t, False) for t in event_tickers]
        station_lookup: dict[str, str] = {}
    else:
        targets = [(s.kalshi_series_ticker, True) for s in STATIONS]
        station_lookup = {s.kalshi_series_ticker: s.icao for s in STATIONS}

    markets: list[Market] = []
    books: list[OrderBookSnapshot] = []

    try:
        async with KalshiClient.from_settings(settings) as client:
            for ticker, is_series in targets:
                label = station_lookup.get(ticker, ticker)
                try:
                    if is_series:
                        event_markets = await client.list_markets(series_ticker=ticker)
                    else:
                        event_markets = await client.list_markets(event_ticker=ticker)
                except Exception:
                    log.exception("kalshi.list_markets_failed", ticker=ticker)
                    continue
                markets.extend(event_markets)
                for m in event_markets:
                    try:
                        book = await client.get_orderbook(m.ticker)
                    except Exception:
                        log.exception("kalshi.orderbook_failed", ticker=m.ticker)
                        continue
                    books.append(book)
                log.info(
                    "kalshi.event_snapshotted",
                    ticker=ticker,
                    label=label,
                    markets=len(event_markets),
                )
    except KalshiCredentialsError as exc:
        log.error("kalshi.credentials_missing", detail=str(exc))
        raise

    # bootstrap() is idempotent and carries the column migrations -- without
    # this, a pre-migration DB silently rounds fractional sizes (4985.18 ->
    # 4985) on insert into the old INTEGER columns (2026-06-11 audit, PR-A).
    bootstrap(path)
    con = connect(path)
    try:
        n_markets = upsert_kalshi_markets(con, markets)
        n_books = insert_kalshi_books(con, books)
    finally:
        con.close()
    log.info(
        "kalshi.ingest_done",
        markets=n_markets,
        book_rows=n_books,
        db=str(path),
    )
    return n_markets, n_books


def main(event_tickers: Sequence[str] | None = None) -> None:
    """`python -m kq.flows.ingest_kalshi` entrypoint."""
    n_markets, n_books = asyncio.run(ingest_once(event_tickers=event_tickers))
    print(f"upserted {n_markets} markets, inserted {n_books} orderbook snapshots")


if __name__ == "__main__":
    main()
