"""NFL game repository — insert/upsert + read helpers for ``nfl_game``.

Mirrors :mod:`kq.storage.repositories.nba` (post-P1 finality-freeze rev)
with one structural difference: the freeze keys off ``completed``, not
``home_won`` — NFL games can end in a TIE, where ``completed=TRUE`` and
``home_won`` stays NULL forever. Keying finality off ``home_won`` (the NBA
convention) would leave a completed tie permanently mutable.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import duckdb

from kq.storage._tz import to_naive_utc

if TYPE_CHECKING:
    from kq.models.nfl_crosswalk import NflGameRow


def upsert_nfl_games(
    con: duckdb.DuckDBPyConnection,
    rows: Iterable[NflGameRow],
) -> int:
    """Upsert NFL games. Returns the count of input rows touched.

    Idempotent on ``game_id`` (the schema PK — The Odds API event id).

    A completed result is FROZEN: once ``completed`` is TRUE the ENTIRE row
    (scores, outcome, and the identifying columns — season, game_date,
    commence_time, team names/abbrs) is immutable; only ``fetched_at``
    still moves, so we can see the row was re-touched. Settlement is
    irreversible downstream, so a degraded/partial refetch must never
    regress a final (the NBA lane's PR-H lesson, inherited wholesale).

    While ``completed`` is still FALSE, non-NULL incoming values win and
    NULL incoming values keep whatever is already stored — reschedules keep
    flowing through (commence_time updates on a flexed game), and a
    degraded payload clobbers nothing.

    Timestamps are normalized to naive UTC before insert (DuckDB TIMESTAMP
    is naive; tz-aware values silently corrupt via local-clock conversion).
    """
    fetched_at = datetime.now(tz=UTC).replace(tzinfo=None)
    batch: list[Sequence[object]] = [
        (
            r.game_id,
            r.season,
            r.game_date,
            to_naive_utc(r.commence_time),
            r.home_team,
            r.home_team_abbr,
            r.away_team,
            r.away_team_abbr,
            r.home_score,
            r.away_score,
            r.completed,
            r.home_won,
            fetched_at,
        )
        for r in rows
    ]
    if not batch:
        return 0
    con.executemany(
        """
        INSERT INTO nfl_game
        (game_id, season, game_date, commence_time, home_team, home_team_abbr,
         away_team, away_team_abbr, home_score, away_score, completed, home_won,
         fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (game_id) DO UPDATE SET
            season         = CASE
                                 WHEN nfl_game.completed THEN nfl_game.season
                                 ELSE COALESCE(EXCLUDED.season, nfl_game.season)
                             END,
            game_date      = CASE
                                 WHEN nfl_game.completed THEN nfl_game.game_date
                                 ELSE COALESCE(EXCLUDED.game_date, nfl_game.game_date)
                             END,
            commence_time  = CASE
                                 WHEN nfl_game.completed THEN nfl_game.commence_time
                                 ELSE COALESCE(EXCLUDED.commence_time, nfl_game.commence_time)
                             END,
            home_team      = CASE
                                 WHEN nfl_game.completed THEN nfl_game.home_team
                                 ELSE COALESCE(EXCLUDED.home_team, nfl_game.home_team)
                             END,
            home_team_abbr = CASE
                                 WHEN nfl_game.completed THEN nfl_game.home_team_abbr
                                 ELSE COALESCE(EXCLUDED.home_team_abbr, nfl_game.home_team_abbr)
                             END,
            away_team      = CASE
                                 WHEN nfl_game.completed THEN nfl_game.away_team
                                 ELSE COALESCE(EXCLUDED.away_team, nfl_game.away_team)
                             END,
            away_team_abbr = CASE
                                 WHEN nfl_game.completed THEN nfl_game.away_team_abbr
                                 ELSE COALESCE(EXCLUDED.away_team_abbr, nfl_game.away_team_abbr)
                             END,
            home_score     = CASE
                                 WHEN nfl_game.completed THEN nfl_game.home_score
                                 ELSE COALESCE(EXCLUDED.home_score, nfl_game.home_score)
                             END,
            away_score     = CASE
                                 WHEN nfl_game.completed THEN nfl_game.away_score
                                 ELSE COALESCE(EXCLUDED.away_score, nfl_game.away_score)
                             END,
            completed      = nfl_game.completed OR COALESCE(EXCLUDED.completed, FALSE),
            home_won       = CASE
                                 WHEN nfl_game.completed THEN nfl_game.home_won
                                 ELSE COALESCE(EXCLUDED.home_won, nfl_game.home_won)
                             END,
            fetched_at     = EXCLUDED.fetched_at
        """,
        batch,
    )
    return len(batch)


def fetch_nfl_games(
    con: duckdb.DuckDBPyConnection,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict[str, object]]:
    """Read NFL games as a list of dicts. Tolerant of empty filter bounds."""
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
        SELECT game_id, season, game_date, commence_time, home_team, home_team_abbr,
               away_team, away_team_abbr, home_score, away_score, completed,
               home_won, fetched_at
        FROM nfl_game
        {where_sql}
        ORDER BY game_date, game_id
        """,
        params,
    ).fetchall()

    cols = (
        "game_id",
        "season",
        "game_date",
        "commence_time",
        "home_team",
        "home_team_abbr",
        "away_team",
        "away_team_abbr",
        "home_score",
        "away_score",
        "completed",
        "home_won",
        "fetched_at",
    )
    return [dict(zip(cols, row, strict=False)) for row in rows]


__all__ = ["fetch_nfl_games", "upsert_nfl_games"]
