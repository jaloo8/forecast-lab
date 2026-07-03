"""NFL odds repository -- insert/upsert + read helpers for ``nfl_odds``.

Identical semantics to :mod:`kq.storage.repositories.nba_odds` — one row
per (odds_api_game_id, bookmaker_key, market_key, fetched_at), a
time-series of line movement. All mechanics live in the shared
:mod:`kq.storage.repositories.odds_common`; this module just pins the
``nfl_odds`` table.
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


def upsert_nfl_odds_rows(con: duckdb.DuckDBPyConnection, rows: Iterable[OddsRow]) -> int:
    """Upsert flattened odds rows into ``nfl_odds``. Returns the count touched.

    Idempotent on the (odds_api_game_id, bookmaker_key, market_key,
    fetched_at) PK — re-runs with the same input are no-ops; a different
    fetched_at appends to the line-movement time-series.
    """
    return upsert_odds_rows_into(con, rows, table="nfl_odds")


def fetch_latest_nfl_odds(
    con: duckdb.DuckDBPyConnection,
    *,
    bookmaker_key: str | None = None,
    on_or_after: date | None = None,
) -> list[dict[str, object]]:
    """Return the latest ``nfl_odds`` snapshot per (game, book, market).

    Optional filters narrow to a single bookmaker (``pinnacle`` is the
    fair-value anchor) and to games kicking off on or after a date.
    """
    return fetch_latest_odds_from(
        con, table="nfl_odds", bookmaker_key=bookmaker_key, on_or_after=on_or_after
    )


__all__ = [
    "OddsRow",
    "fetch_latest_nfl_odds",
    "odds_rows_from_games",
    "upsert_nfl_odds_rows",
]
