"""NBA game repository — insert/upsert + read helpers for `nba_game`."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    from kq.clients.nba_schedule import NbaGameRow


def upsert_nba_games(
    con: duckdb.DuckDBPyConnection,
    rows: Iterable[NbaGameRow],
) -> int:
    """Upsert NBA games. Returns the count of input rows touched.

    Idempotent on `game_id` (the schema PK). When scores arrive (game
    reported final by the ingest), the row's home_score / away_score /
    home_won transition from NULL to populated.

    A recorded result is FROZEN: once ``home_won`` is non-NULL the ENTIRE
    row (scores, outcome, and the identifying/metadata columns — season,
    season_type, game_date, team ids/abbrs) is immutable; only
    ``fetched_at`` still moves, so we can see the row was re-touched.
    Settlement is irreversible downstream, so a degraded/partial refetch
    (scores or status missing from the payload) must not regress a final —
    the old blind ``INSERT OR REPLACE`` did exactly that, and PR-H's
    narrower freeze (scores + home_won only) still let a partial payload
    rewrite the metadata a final was recorded under (game_date, team
    abbrs), silently re-keying settlement's date-keyed lookup. While
    ``home_won`` is still NULL, non-NULL incoming values win and NULL
    incoming values keep whatever is already stored (reschedules keep
    flowing through; a degraded payload clobbers nothing).

    Timestamps are normalized to naive UTC before insert (DuckDB
    TIMESTAMP is naive — leaving tz-aware values would silently corrupt
    via local-clock conversion).
    """
    fetched_at = datetime.now(tz=UTC).replace(tzinfo=None)
    batch: list[Sequence[object]] = [
        (
            r.game_id,
            r.season,
            r.season_type,
            r.game_date,
            r.home_team_id,
            r.home_team_abbr,
            r.away_team_id,
            r.away_team_abbr,
            r.home_score,
            r.away_score,
            r.home_won,
            fetched_at,
        )
        for r in rows
    ]
    if not batch:
        return 0
    con.executemany(
        """
        INSERT INTO nba_game
        (game_id, season, season_type, game_date, home_team_id, home_team_abbr,
         away_team_id, away_team_abbr, home_score, away_score, home_won, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (game_id) DO UPDATE SET
            season         = CASE
                                 WHEN nba_game.home_won IS NOT NULL THEN nba_game.season
                                 ELSE COALESCE(EXCLUDED.season, nba_game.season)
                             END,
            season_type    = CASE
                                 WHEN nba_game.home_won IS NOT NULL THEN nba_game.season_type
                                 ELSE COALESCE(EXCLUDED.season_type, nba_game.season_type)
                             END,
            game_date      = CASE
                                 WHEN nba_game.home_won IS NOT NULL THEN nba_game.game_date
                                 ELSE COALESCE(EXCLUDED.game_date, nba_game.game_date)
                             END,
            home_team_id   = CASE
                                 WHEN nba_game.home_won IS NOT NULL THEN nba_game.home_team_id
                                 ELSE COALESCE(EXCLUDED.home_team_id, nba_game.home_team_id)
                             END,
            home_team_abbr = CASE
                                 WHEN nba_game.home_won IS NOT NULL THEN nba_game.home_team_abbr
                                 ELSE COALESCE(EXCLUDED.home_team_abbr, nba_game.home_team_abbr)
                             END,
            away_team_id   = CASE
                                 WHEN nba_game.home_won IS NOT NULL THEN nba_game.away_team_id
                                 ELSE COALESCE(EXCLUDED.away_team_id, nba_game.away_team_id)
                             END,
            away_team_abbr = CASE
                                 WHEN nba_game.home_won IS NOT NULL THEN nba_game.away_team_abbr
                                 ELSE COALESCE(EXCLUDED.away_team_abbr, nba_game.away_team_abbr)
                             END,
            home_score     = CASE
                                 WHEN nba_game.home_won IS NOT NULL THEN nba_game.home_score
                                 ELSE COALESCE(EXCLUDED.home_score, nba_game.home_score)
                             END,
            away_score     = CASE
                                 WHEN nba_game.home_won IS NOT NULL THEN nba_game.away_score
                                 ELSE COALESCE(EXCLUDED.away_score, nba_game.away_score)
                             END,
            home_won       = COALESCE(nba_game.home_won, EXCLUDED.home_won),
            fetched_at     = EXCLUDED.fetched_at
        """,
        batch,
    )
    return len(batch)


def fetch_nba_games(
    con: duckdb.DuckDBPyConnection,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    season_types: Sequence[str] | None = None,
) -> list[dict[str, object]]:
    """Read NBA games as a list of dicts. Tolerant of empty filter bounds.

    Returns one dict per row, JSON-safe (dates stay as `date`, scores as
    int|None, etc.). Used by tests + future analysis scripts; the
    backtest engine consumes the table directly via SQL when wired up.
    """
    where_clauses: list[str] = []
    params: list[object] = []
    if start_date is not None:
        where_clauses.append("game_date >= ?")
        params.append(start_date)
    if end_date is not None:
        where_clauses.append("game_date <= ?")
        params.append(end_date)
    if season_types:
        placeholders = ",".join("?" for _ in season_types)
        where_clauses.append(f"season_type IN ({placeholders})")
        params.extend(season_types)
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    rows = con.execute(
        f"""
        SELECT game_id, season, season_type, game_date, home_team_id, home_team_abbr,
               away_team_id, away_team_abbr, home_score, away_score, home_won, fetched_at
        FROM nba_game
        {where_sql}
        ORDER BY game_date, game_id
        """,
        params,
    ).fetchall()

    cols = (
        "game_id",
        "season",
        "season_type",
        "game_date",
        "home_team_id",
        "home_team_abbr",
        "away_team_id",
        "away_team_abbr",
        "home_score",
        "away_score",
        "home_won",
        "fetched_at",
    )
    return [dict(zip(cols, row, strict=False)) for row in rows]


__all__ = ["fetch_nba_games", "upsert_nba_games"]
