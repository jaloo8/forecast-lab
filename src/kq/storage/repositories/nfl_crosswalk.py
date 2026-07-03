"""NFL game-id crosswalk repository.

Persists ``NflCrosswalkPair`` rows from :mod:`kq.models.nfl_crosswalk` into
the ``nfl_game_crosswalk`` table. Same contract as the NBA twin: the
matcher is the source of truth for which pairs exist; this layer is durable
storage so downstream joins run in SQL. Idempotent on the
``odds_api_game_id`` PK — re-runs replace rows in place, so a corrected
``nfl_game`` row eventually heals the bridge.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime

import duckdb

from kq.models.nfl_crosswalk import NflCrosswalkPair


def upsert_nfl_crosswalk(con: duckdb.DuckDBPyConnection, pairs: Iterable[NflCrosswalkPair]) -> int:
    """Upsert crosswalk rows. Returns the count touched."""
    matched_at = datetime.now(tz=UTC).replace(tzinfo=None)
    batch: list[Sequence[object]] = [
        (
            p.odds_api_game_id,
            p.nfl_game_id,
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
        INSERT OR REPLACE INTO nfl_game_crosswalk
        (odds_api_game_id, nfl_game_id, home_team_abbr, away_team_abbr,
         game_date, matched_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        batch,
    )
    return len(batch)


def fetch_nfl_crosswalk_for_date_range(
    con: duckdb.DuckDBPyConnection,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict[str, object]]:
    """Return crosswalk rows for games in the inclusive date window.

    Either bound may be None for an open-ended fetch.
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
        SELECT odds_api_game_id, nfl_game_id, home_team_abbr, away_team_abbr,
               game_date, matched_at
        FROM nfl_game_crosswalk
        {where_sql}
        ORDER BY game_date, nfl_game_id
        """,
        params,
    ).fetchall()
    cols = (
        "odds_api_game_id",
        "nfl_game_id",
        "home_team_abbr",
        "away_team_abbr",
        "game_date",
        "matched_at",
    )
    return [dict(zip(cols, row, strict=False)) for row in rows]


__all__ = ["fetch_nfl_crosswalk_for_date_range", "upsert_nfl_crosswalk"]
