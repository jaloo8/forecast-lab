"""Backfill daily index OHLC (HAR-RV training ground-truth).

Phase C deliverable. Pulls daily S&P 500 (SPX) and Nasdaq-100 (NDX) closes
via the Yahoo chart endpoint for a date range — the close-to-close return
substrate the HAR-RV benchmark fits on. Kalshi's KXINX / KXNASDAQ100 range
brackets settle on these indices' official end-of-day prints, so our truth
matches the market's resolution truth (vendor caveats: see
``kq.clients.yahoo_chart``).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import structlog

from kq.clients.yahoo_chart import INDEX_SYMBOLS, IndexDailyBar, YahooChartClient
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.storage.duckdb_store import connect
from kq.storage.repositories.index_daily import insert_index_daily

log = structlog.get_logger(__name__)

DEFAULT_YEARS = 2


async def backfill(
    *,
    start_date: date,
    end_date: date,
    db_path: Path | None = None,
) -> int:
    """Backfill daily OHLC for every index symbol. Returns rows written."""
    if end_date < start_date:
        raise ValueError(f"end_date {end_date} precedes start_date {start_date}")

    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)

    rows: list[IndexDailyBar] = []
    async with YahooChartClient() as client:
        for symbol in INDEX_SYMBOLS:
            try:
                bars = await client.fetch_daily(symbol, start_date=start_date, end_date=end_date)
            except Exception:
                log.exception("index.backfill_failed", symbol=symbol)
                continue
            log.info(
                "index.backfilled",
                symbol=symbol,
                rows=len(bars),
                start=start_date.isoformat(),
                end=end_date.isoformat(),
            )
            rows.extend(bars)

    con = connect(path)
    try:
        n = insert_index_daily(con, rows)
    finally:
        con.close()
    log.info(
        "index.backfill_done",
        inserted=n,
        start=start_date.isoformat(),
        end=end_date.isoformat(),
        db=str(path),
    )
    return n


def main(*, start: str | None = None, end: str | None = None, years: int = DEFAULT_YEARS) -> None:
    """`python -m kq backfill-index` entrypoint.

    With no explicit dates, pulls the trailing ``years`` (default 2) so the
    HAR-RV backtest has enough history for rolling-origin CV.
    """
    if years < 1:
        raise ValueError(f"years must be >= 1, got {years}")
    end_d = date.fromisoformat(end) if end else datetime.now(tz=UTC).date()
    start_d = date.fromisoformat(start) if start else end_d - timedelta(days=365 * years)
    total = asyncio.run(backfill(start_date=start_d, end_date=end_d))
    print(f"backfilled {total} index daily rows ({start_d} to {end_d})")


if __name__ == "__main__":  # pragma: no cover
    main()
