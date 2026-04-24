"""Per-domain DuckDB write helpers. One module per table group."""

from __future__ import annotations

from kq.storage.repositories.forecasts import insert_forecasts
from kq.storage.repositories.kalshi import insert_kalshi_books, upsert_kalshi_markets
from kq.storage.repositories.metar import insert_metar
from kq.storage.repositories.observed import insert_observed

__all__ = [
    "insert_forecasts",
    "insert_kalshi_books",
    "insert_metar",
    "insert_observed",
    "upsert_kalshi_markets",
]
