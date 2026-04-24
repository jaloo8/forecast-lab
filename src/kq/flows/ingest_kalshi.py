"""One-shot Kalshi ingest: snapshot all weather-market orderbooks.

Runs the following per station:
    1. `GET /markets?event_ticker=KXHIGHLAX` (list all brackets)
    2. For each market ticker, `GET /markets/{ticker}/orderbook`
    3. Write one row per market into `kalshi_market` (upsert) and one row per
       market into `kalshi_book_snap` (append).

Refuses to run when credentials aren't configured — this is expected while
the user hasn't signed up for Kalshi demo yet. See README + SETUP.md.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from kq.clients.kalshi import KalshiClient, KalshiCredentialsError, Market, OrderBookSnapshot
from kq.clients.stations import STATIONS
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.storage.duckdb_store import connect
from kq.storage.repositories.kalshi import insert_kalshi_books, upsert_kalshi_markets

log = structlog.get_logger(__name__)


async def ingest_once(*, db_path: Path | None = None) -> tuple[int, int]:
    """Snapshot Kalshi weather markets. Returns (markets_upserted, book_rows_inserted)."""
    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)

    markets: list[Market] = []
    books: list[OrderBookSnapshot] = []

    try:
        async with KalshiClient.from_settings(settings) as client:
            for station in STATIONS:
                try:
                    station_markets = await client.list_markets(
                        event_ticker=station.kalshi_event_ticker,
                    )
                except Exception:
                    log.exception(
                        "kalshi.list_markets_failed",
                        event_ticker=station.kalshi_event_ticker,
                    )
                    continue
                markets.extend(station_markets)
                for m in station_markets:
                    try:
                        book = await client.get_orderbook(m.ticker)
                    except Exception:
                        log.exception("kalshi.orderbook_failed", ticker=m.ticker)
                        continue
                    books.append(book)
                log.info(
                    "kalshi.station_snapshotted",
                    station=station.icao,
                    markets=len(station_markets),
                )
    except KalshiCredentialsError as exc:
        log.error("kalshi.credentials_missing", detail=str(exc))
        raise

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


def main() -> None:
    """`python -m kq.flows.ingest_kalshi` entrypoint."""
    n_markets, n_books = asyncio.run(ingest_once())
    print(f"upserted {n_markets} markets, inserted {n_books} orderbook snapshots")


if __name__ == "__main__":
    main()
