"""Shared two-way (h2h) odds persistence — the sport-agnostic core behind
``nba_odds`` and ``nfl_odds``.

Both sports store identical rows: one per (odds_api_game_id, bookmaker_key,
market_key, fetched_at) — a time-series of line movement, never a mutable
"current snapshot" view. Queries that want "latest" pick the
MAX(fetched_at) group per (game, book, market).

The table name is the ONLY thing that differs, so the SQL here is
parameterized by an allowlisted table identifier (never caller-supplied
free text — DuckDB can't bind identifiers, so the allowlist is the
injection guard). The sport-named modules (`nba_odds`, `nfl_odds`) are thin
delegating wrappers that pin the table; existing NBA callers keep their
exact import surface.

``OddsRow`` / ``odds_rows_from_games`` were born in ``nba_odds`` but never
contained anything NBA-specific; they moved here when the NFL lane landed
(2026-07-02) and are re-exported from ``nba_odds`` for backward
compatibility.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Final, Literal

import duckdb

if TYPE_CHECKING:
    from kq.clients.the_odds_api import OddsApiGame

OddsTable = Literal["nba_odds", "nfl_odds"]

_ALLOWED_TABLES: Final[frozenset[str]] = frozenset(("nba_odds", "nfl_odds"))


def _checked_table(table: OddsTable) -> str:
    """The allowlist IS the SQL-identifier injection guard — enforce it at
    runtime too, since Literal only protects statically-typed callers."""
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"unknown odds table {table!r}; allowed: {sorted(_ALLOWED_TABLES)}")
    return table


@dataclass(frozen=True, slots=True)
class OddsRow:
    """Flat-row view of one (game, book, market) snapshot.

    Decimal odds are nullable: when the book quotes only one side of
    the moneyline, the other column carries None. This is rare but
    happens in pre-market windows and around late scratches.
    """

    odds_api_game_id: str
    bookmaker_key: str
    market_key: str
    home_team: str
    away_team: str
    commence_time: datetime  # naive UTC
    home_decimal_odds: float | None
    away_decimal_odds: float | None
    book_last_update: datetime  # naive UTC
    fetched_at: datetime  # naive UTC


def odds_rows_from_games(
    games: Iterable[OddsApiGame], *, fetched_at: datetime | None = None
) -> list[OddsRow]:
    """Flatten ``OddsApiGame`` tree into ``OddsRow``s ready for upsert.

    Walks each game's bookmakers x markets, picks the home/away
    decimal-odds outcomes by matching ``OddsApiOutcome.team_name``
    against the game's ``home_team`` / ``away_team``. Any market with
    neither side matching is skipped (defensive against future market
    keys we don't handle yet, e.g. spreads/totals).

    All ``datetime`` fields land as naive UTC -- DuckDB ``TIMESTAMP``
    is timezone-naive, and silently localizes tz-aware values on
    insert.
    """
    when = (fetched_at or datetime.now(tz=UTC)).astimezone(UTC).replace(tzinfo=None)
    out: list[OddsRow] = []
    for game in games:
        commence = game.commence_time.astimezone(UTC).replace(tzinfo=None)
        for book in game.bookmakers:
            book_when = book.last_update.astimezone(UTC).replace(tzinfo=None)
            for market in book.markets:
                home_quote: float | None = None
                away_quote: float | None = None
                for outcome in market.outcomes:
                    if outcome.team_name == game.home_team:
                        home_quote = outcome.decimal_odds
                    elif outcome.team_name == game.away_team:
                        away_quote = outcome.decimal_odds
                # Skip markets that didn't match either side -- spreads,
                # totals, and any future market keys we don't model
                # yet. The bookkeeping is by-design lossy in v1 (h2h
                # only) and rather than store mystery rows we drop them.
                if home_quote is None and away_quote is None:
                    continue
                out.append(
                    OddsRow(
                        odds_api_game_id=game.game_id,
                        bookmaker_key=book.key,
                        market_key=market.key,
                        home_team=game.home_team,
                        away_team=game.away_team,
                        commence_time=commence,
                        home_decimal_odds=home_quote,
                        away_decimal_odds=away_quote,
                        book_last_update=book_when,
                        fetched_at=when,
                    )
                )
    return out


def upsert_odds_rows_into(
    con: duckdb.DuckDBPyConnection,
    rows: Iterable[OddsRow],
    *,
    table: OddsTable,
) -> int:
    """Upsert flattened odds rows into ``table``. Returns the count touched.

    Idempotent on the (odds_api_game_id, bookmaker_key, market_key,
    fetched_at) PK. Re-running with the same input is a no-op; a
    different fetched_at produces a new row, preserving the
    line-movement time-series.
    """
    table_sql = _checked_table(table)
    batch: list[Sequence[object]] = [
        (
            r.odds_api_game_id,
            r.bookmaker_key,
            r.market_key,
            r.home_team,
            r.away_team,
            r.commence_time,
            r.home_decimal_odds,
            r.away_decimal_odds,
            r.book_last_update,
            r.fetched_at,
        )
        for r in rows
    ]
    if not batch:
        return 0
    con.executemany(
        f"""
        INSERT OR REPLACE INTO {table_sql}
        (odds_api_game_id, bookmaker_key, market_key, home_team, away_team,
         commence_time, home_decimal_odds, away_decimal_odds,
         book_last_update, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        batch,
    )
    return len(batch)


def fetch_latest_odds_from(
    con: duckdb.DuckDBPyConnection,
    *,
    table: OddsTable,
    bookmaker_key: str | None = None,
    on_or_after: date | None = None,
) -> list[dict[str, object]]:
    """Return the latest snapshot per (odds_api_game_id, bookmaker_key,
    market_key) in ``table`` -- the "current view" against the time-series.

    Optional filters narrow to a single bookmaker (typically ``pinnacle``
    for the fair-value anchor) and to games starting on or after a
    given calendar date (e.g. today + future).
    """
    table_sql = _checked_table(table)
    where_clauses: list[str] = []
    params: list[object] = []
    if bookmaker_key is not None:
        where_clauses.append("bookmaker_key = ?")
        params.append(bookmaker_key)
    if on_or_after is not None:
        where_clauses.append("commence_time >= ?")
        params.append(datetime.combine(on_or_after, datetime.min.time()))
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    rows = con.execute(
        f"""
        SELECT
            o.odds_api_game_id, o.bookmaker_key, o.market_key,
            o.home_team, o.away_team, o.commence_time,
            o.home_decimal_odds, o.away_decimal_odds,
            o.book_last_update, o.fetched_at
        FROM {table_sql} o
        JOIN (
            SELECT odds_api_game_id, bookmaker_key, market_key,
                   MAX(fetched_at) AS max_fetched
            FROM {table_sql}
            {where_sql}
            GROUP BY odds_api_game_id, bookmaker_key, market_key
        ) latest USING (odds_api_game_id, bookmaker_key, market_key)
        WHERE o.fetched_at = latest.max_fetched
        ORDER BY o.commence_time, o.odds_api_game_id, o.bookmaker_key
        """,
        params,
    ).fetchall()

    cols = (
        "odds_api_game_id",
        "bookmaker_key",
        "market_key",
        "home_team",
        "away_team",
        "commence_time",
        "home_decimal_odds",
        "away_decimal_odds",
        "book_last_update",
        "fetched_at",
    )
    return [dict(zip(cols, row, strict=False)) for row in rows]


__all__ = [
    "OddsRow",
    "OddsTable",
    "fetch_latest_odds_from",
    "odds_rows_from_games",
    "upsert_odds_rows_into",
]
