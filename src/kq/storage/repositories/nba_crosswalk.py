"""NBA game-id crosswalk repository.

Persists ``CrosswalkPair`` rows from :mod:`kq.models.nba_crosswalk` into
the ``nba_game_crosswalk`` table. The matcher is the source of truth
for which (odds_api_game_id, nba_game_id) pairs exist; this layer is
just durable storage so downstream queries (NBA backtest, edge calc,
CLV measurement) can join via SQL instead of re-running the matcher
every tick.

Idempotent on the ``odds_api_game_id`` PK -- re-runs replace existing
rows in place, including denormalized columns (team abbrs, game_date)
that may have been corrected upstream in nba_game.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime

import duckdb

from kq.models.nba_crosswalk import CrosswalkPair


def upsert_crosswalk(con: duckdb.DuckDBPyConnection, pairs: Iterable[CrosswalkPair]) -> int:
    """Upsert crosswalk rows. Returns the count touched.

    Each pair lands once per ``odds_api_game_id`` -- the PK ensures one
    Odds API game maps to exactly one NBA game (the matcher's
    structural assumption per ``kq.models.nba_crosswalk`` docstring).
    """
    matched_at = datetime.now(tz=UTC).replace(tzinfo=None)
    batch: list[Sequence[object]] = [
        (
            p.odds_api_game_id,
            p.nba_game_id,
            p.home_team_abbr,
            p.away_team_abbr,
            p.game_date,
            matched_at,
        )
        for p in pairs
    ]
    if not batch:
        return 0
    con.executemany(
        """
        INSERT OR REPLACE INTO nba_game_crosswalk
        (odds_api_game_id, nba_game_id, home_team_abbr, away_team_abbr,
         game_date, matched_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        batch,
    )
    return len(batch)


def fetch_by_odds_api_id(
    con: duckdb.DuckDBPyConnection, odds_api_game_id: str
) -> dict[str, object] | None:
    """Look up the NBA game id (and denormalized fields) for one Odds
    API game. Returns None when no match exists -- callers decide
    whether the gap is a problem (e.g. pre-season game, all-star, or
    just a matcher run that hasn't happened yet)."""
    row = con.execute(
        """
        SELECT odds_api_game_id, nba_game_id, home_team_abbr, away_team_abbr,
               game_date, matched_at
        FROM nba_game_crosswalk
        WHERE odds_api_game_id = ?
        """,
        [odds_api_game_id],
    ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def fetch_by_nba_game_id(
    con: duckdb.DuckDBPyConnection, nba_game_id: str
) -> dict[str, object] | None:
    """Reverse lookup: NBA game id -> Odds API game id.

    Multiple Odds API entries can in principle point at the same NBA
    game (different cycles' parses, although the matcher's PK on
    odds_api_game_id makes this rare in practice); we return the first
    deterministic row by table order.
    """
    row = con.execute(
        """
        SELECT odds_api_game_id, nba_game_id, home_team_abbr, away_team_abbr,
               game_date, matched_at
        FROM nba_game_crosswalk
        WHERE nba_game_id = ?
        ORDER BY odds_api_game_id
        LIMIT 1
        """,
        [nba_game_id],
    ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def fetch_for_date_range(
    con: duckdb.DuckDBPyConnection,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict[str, object]]:
    """Return crosswalk rows for games in the inclusive date window.

    Either bound may be None for an open-ended fetch -- typical use is
    "all games on or after today" for live trading or "all games last
    season" for backtest CLV measurement.
    """
    where_clauses: list[str] = []
    params: list[object] = []
    if start_date is not None:
        where_clauses.append("game_date >= ?")
        params.append(start_date)
    if end_date is not None:
        where_clauses.append("game_date <= ?")
        params.append(end_date)
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    rows = con.execute(
        f"""
        SELECT odds_api_game_id, nba_game_id, home_team_abbr, away_team_abbr,
               game_date, matched_at
        FROM nba_game_crosswalk
        {where_sql}
        ORDER BY game_date, nba_game_id
        """,
        params,
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: Sequence[object]) -> dict[str, object]:
    cols = (
        "odds_api_game_id",
        "nba_game_id",
        "home_team_abbr",
        "away_team_abbr",
        "game_date",
        "matched_at",
    )
    return dict(zip(cols, row, strict=False))


__all__ = [
    "fetch_by_nba_game_id",
    "fetch_by_odds_api_id",
    "fetch_for_date_range",
    "upsert_crosswalk",
]
