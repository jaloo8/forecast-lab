"""NBA odds repository -- insert/upsert + read helpers for ``nba_odds``.

One row per (odds_api_game_id, bookmaker_key, market_key, fetched_at).
A fresh fetch produces fresh rows even for the same game/book pair --
the table is a time-series of line movement, not a "current snapshot"
view. Queries that want "latest" pick the MAX(fetched_at) group per
(game, book, market).

The mechanics are sport-agnostic and live in
:mod:`kq.storage.repositories.odds_common` (shared with the NFL lane
since 2026-07-02); this module pins the ``nba_odds`` table and keeps the
import surface every existing NBA caller/test already uses. ``OddsRow``
and ``odds_rows_from_games`` are re-exported from the common module
unchanged.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

import duckdb

from kq.storage.repositories.odds_common import (
    OddsRow,
    fetch_latest_odds_from,
    odds_rows_from_games,
    upsert_odds_rows_into,
)


def upsert_odds_rows(con: duckdb.DuckDBPyConnection, rows: Iterable[OddsRow]) -> int:
    """Upsert flattened odds rows into ``nba_odds``. Returns the count touched.

    Idempotent on (odds_api_game_id, bookmaker_key, market_key,
    fetched_at) -- the schema PK. Re-running with the same input is a
    no-op; a different fetched_at produces a new row, preserving the
    line-movement time-series.
    """
    return upsert_odds_rows_into(con, rows, table="nba_odds")


def fetch_latest_odds(
    con: duckdb.DuckDBPyConnection,
    *,
    bookmaker_key: str | None = None,
    on_or_after: date | None = None,
) -> list[dict[str, object]]:
    """Return the latest ``nba_odds`` snapshot per (odds_api_game_id,
    bookmaker_key, market_key) -- the "current view" against the
    time-series.

    Optional filters narrow to a single bookmaker (typically ``pinnacle``
    for the fair-value anchor) and to games tipping on or after a
    given calendar date (e.g. today + future).
    """
    return fetch_latest_odds_from(
        con, table="nba_odds", bookmaker_key=bookmaker_key, on_or_after=on_or_after
    )


__all__ = [
    "OddsRow",
    "fetch_latest_odds",
    "odds_rows_from_games",
    "upsert_odds_rows",
]
