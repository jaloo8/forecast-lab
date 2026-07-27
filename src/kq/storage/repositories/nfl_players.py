"""NFL player-lane repository — ``nfl_player_game`` + ``nfl_player_projection``.

``nfl_player_game`` is truth-like but correctable (nflverse republishes stat
corrections), so the upsert REPLACES in place with the weather_observed
guard: an incoming NULL never wipes a stored value — a tick where the snap
join degraded must not erase last week's good snap counts — while real
corrections keep flowing. No finality freeze on purpose.

``nfl_player_projection`` is an append-only point-in-time ledger (``as_of``
in the PK, odds-tables semantics): re-inserting the same rows is a no-op,
a new ``as_of`` appends. The F1b scoring flow reads it back against
actuals — projections are never edited after the fact.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

import duckdb

from kq.storage._tz import to_naive_utc

if TYPE_CHECKING:
    from kq.clients.nfl_players import PlayerGameRow

SCORING_FORMATS: Final[frozenset[str]] = frozenset({"std", "ppr"})

_PLAYER_GAME_COLUMNS: Final[tuple[str, ...]] = (
    "player_id",
    "player_name",
    "season",
    "week",
    "season_type",
    "team",
    "opponent",
    "position",
    "snaps",
    "snap_pct",
    "targets",
    "receptions",
    "carries",
    "passing_yards",
    "passing_tds",
    "rushing_yards",
    "rushing_tds",
    "receiving_yards",
    "receiving_tds",
    "fumbles_lost",
    "interceptions",
    "red_zone_touches",
    "fantasy_points_std",
    "fantasy_points_ppr",
    "as_of",
)


@dataclass(frozen=True, slots=True)
class ProjectionRow:
    """One point-in-time fantasy projection for one (player, week, format)."""

    player_id: str
    player_name: str | None
    season: int
    week: int
    scoring_format: str  # 'std' | 'ppr'
    projected_points: float
    floor_points: float | None
    ceiling_points: float | None
    as_of: datetime
    model_version: str


def upsert_player_games(
    con: duckdb.DuckDBPyConnection,
    rows: Iterable[PlayerGameRow],
    *,
    as_of: datetime | None = None,
) -> int:
    """Upsert player-week stat rows. Returns the count of input rows.

    Idempotent on (player_id, season, week, season_type). Data columns
    take the incoming value when non-NULL and keep the stored value
    otherwise; ``as_of`` always moves to the current stamp so we can see
    when the row was last touched.
    """
    stamp = to_naive_utc(as_of) if as_of is not None else datetime.now(tz=UTC).replace(tzinfo=None)
    batch: list[Sequence[object]] = [
        (
            r.player_id,
            r.player_name,
            r.season,
            r.week,
            r.season_type,
            r.team,
            r.opponent,
            r.position,
            r.snaps,
            r.snap_pct,
            r.targets,
            r.receptions,
            r.carries,
            r.passing_yards,
            r.passing_tds,
            r.rushing_yards,
            r.rushing_tds,
            r.receiving_yards,
            r.receiving_tds,
            r.fumbles_lost,
            r.interceptions,
            r.red_zone_touches,
            r.fantasy_points_std,
            r.fantasy_points_ppr,
            stamp,
        )
        for r in rows
    ]
    if not batch:
        return 0
    guarded = (
        "player_name",
        "team",
        "opponent",
        "position",
        "snaps",
        "snap_pct",
        "targets",
        "receptions",
        "carries",
        "passing_yards",
        "passing_tds",
        "rushing_yards",
        "rushing_tds",
        "receiving_yards",
        "receiving_tds",
        "fumbles_lost",
        "interceptions",
        "red_zone_touches",
        "fantasy_points_std",
        "fantasy_points_ppr",
    )
    set_sql = ",\n            ".join(
        f"{c} = COALESCE(EXCLUDED.{c}, nfl_player_game.{c})" for c in guarded
    )
    con.executemany(
        f"""
        INSERT INTO nfl_player_game ({", ".join(_PLAYER_GAME_COLUMNS)})
        VALUES ({", ".join("?" for _ in _PLAYER_GAME_COLUMNS)})
        ON CONFLICT (player_id, season, week, season_type) DO UPDATE SET
            {set_sql},
            as_of = EXCLUDED.as_of
        """,
        batch,
    )
    return len(batch)


def fetch_player_games(
    con: duckdb.DuckDBPyConnection,
    *,
    seasons: Sequence[int] | None = None,
    season_type: str | None = None,
    position: str | None = None,
) -> list[dict[str, object]]:
    """Read player-week rows as dicts, ordered for reproducible consumption."""
    where_clauses: list[str] = []
    params: list[object] = []
    if seasons:
        where_clauses.append(f"season IN ({', '.join('?' for _ in seasons)})")
        params.extend(int(s) for s in seasons)
    if season_type is not None:
        where_clauses.append("season_type = ?")
        params.append(season_type)
    if position is not None:
        where_clauses.append("position = ?")
        params.append(position)
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    rows = con.execute(
        f"""
        SELECT {", ".join(_PLAYER_GAME_COLUMNS)}
        FROM nfl_player_game
        {where_sql}
        ORDER BY season, week, team, player_id
        """,
        params,
    ).fetchall()
    return [dict(zip(_PLAYER_GAME_COLUMNS, row, strict=False)) for row in rows]


def insert_projections(
    con: duckdb.DuckDBPyConnection,
    rows: Iterable[ProjectionRow],
) -> int:
    """Insert projection rows; returns count. Idempotent on the full PK
    (player_id, season, week, scoring_format, model_version, as_of) — the
    ledger appends, never mutates. Unknown scoring formats are refused so a
    typo can't fork the ledger into a phantom third format.
    """
    batch: list[Sequence[object]] = []
    for r in rows:
        if r.scoring_format not in SCORING_FORMATS:
            raise ValueError(
                f"unknown scoring_format {r.scoring_format!r} (expected one of "
                f"{sorted(SCORING_FORMATS)})"
            )
        batch.append(
            (
                r.player_id,
                r.player_name,
                r.season,
                r.week,
                r.scoring_format,
                r.projected_points,
                r.floor_points,
                r.ceiling_points,
                to_naive_utc(r.as_of),
                r.model_version,
            )
        )
    if not batch:
        return 0
    con.executemany(
        """
        INSERT OR REPLACE INTO nfl_player_projection
        (player_id, player_name, season, week, scoring_format, projected_points,
         floor_points, ceiling_points, as_of, model_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        batch,
    )
    return len(batch)


def fetch_projections(
    con: duckdb.DuckDBPyConnection,
    *,
    season: int | None = None,
    week: int | None = None,
    scoring_format: str | None = None,
    model_version: str | None = None,
) -> list[dict[str, object]]:
    """Read projection ledger rows as dicts (all ``as_of`` revisions; the
    F1b scorer picks the revision policy, not the storage layer)."""
    cols = (
        "player_id",
        "player_name",
        "season",
        "week",
        "scoring_format",
        "projected_points",
        "floor_points",
        "ceiling_points",
        "as_of",
        "model_version",
    )
    where_clauses: list[str] = []
    params: list[object] = []
    if season is not None:
        where_clauses.append("season = ?")
        params.append(season)
    if week is not None:
        where_clauses.append("week = ?")
        params.append(week)
    if scoring_format is not None:
        where_clauses.append("scoring_format = ?")
        params.append(scoring_format)
    if model_version is not None:
        where_clauses.append("model_version = ?")
        params.append(model_version)
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    rows = con.execute(
        f"""
        SELECT {", ".join(cols)}
        FROM nfl_player_projection
        {where_sql}
        ORDER BY season, week, scoring_format, player_id, as_of
        """,
        params,
    ).fetchall()
    return [dict(zip(cols, row, strict=False)) for row in rows]


__all__ = [
    "SCORING_FORMATS",
    "ProjectionRow",
    "fetch_player_games",
    "fetch_projections",
    "insert_projections",
    "upsert_player_games",
]
