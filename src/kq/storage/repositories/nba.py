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

    Idempotent on `game_id` (the schema PK). A re-run with the same
    input is a no-op modulo the `fetched_at` field updating to the new
    pull time. This is intentional — when scores arrive (e.g. game
    finished), the row's home_score / away_score / home_won transition
    from NULL to populated.

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
        INSERT OR REPLACE INTO nba_game
        (game_id, season, season_type, game_date, home_team_id, home_team_abbr,
         away_team_id, away_team_abbr, home_score, away_score, home_won, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
