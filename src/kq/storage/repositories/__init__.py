"""Per-domain DuckDB write helpers. One module per table group."""

from __future__ import annotations

from kq.storage.repositories.forecasts import insert_forecasts
from kq.storage.repositories.kalshi import insert_kalshi_books, upsert_kalshi_markets
from kq.storage.repositories.metar import insert_metar
from kq.storage.repositories.observed import insert_observed
from kq.storage.repositories.paper_trades import (
    PaperTradeRow,
    fetch_unsettled_paper_trades,
    insert_paper_trade_with_signal,
    mark_paper_trade_settled,
    settle_due_paper_trades,
    settled_pnl_total,
)

__all__ = [
    "PaperTradeRow",
    "fetch_unsettled_paper_trades",
    "insert_forecasts",
    "insert_kalshi_books",
    "insert_metar",
    "insert_observed",
    "insert_paper_trade_with_signal",
    "mark_paper_trade_settled",
    "settle_due_paper_trades",
    "settled_pnl_total",
    "upsert_kalshi_markets",
]
