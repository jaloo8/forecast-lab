"""NBA injury repository -- upsert + lookup for ``nba_injury``.

PK on ``(player_id, as_of)`` so re-importing a CSV with the same
report timestamp is idempotent. Different ``as_of`` values per player
land as additional rows -- the table is a time-series of injury
status, not a "current snapshot".

Queries that want "what's the status now" pick MAX(as_of) per
player_id via :func:`fetch_latest_per_player`.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    from kq.clients.nba_injuries import InjuryRow


def upsert_injuries(con: duckdb.DuckDBPyConnection, rows: Iterable[InjuryRow]) -> int:
    """Upsert injury rows. Returns the count touched.

    PK ``(player_id, as_of)``; ``fetched_at`` is set at call time so
    re-runs update only that field on conflicting rows.
    """
    fetched_at = datetime.now(tz=UTC).replace(tzinfo=None)
    batch: list[Sequence[object]] = []
    for r in rows:
        as_of_naive = (
            r.as_of.astimezone(UTC).replace(tzinfo=None) if r.as_of.tzinfo is not None else r.as_of
        )
        batch.append(
            (
                r.player_id,
                r.player_name,
                r.team_abbr,
                r.status,
                r.reason,
                as_of_naive,
                fetched_at,
            )
        )
    if not batch:
        return 0
    con.executemany(
        """
        INSERT OR REPLACE INTO nba_injury
        (player_id, player_name, team_abbr, status, reason, as_of, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        batch,
    )
    return len(batch)


def fetch_latest_per_player(
    con: duckdb.DuckDBPyConnection,
    *,
    team_abbr: str | None = None,
    on_or_after: date | None = None,
) -> list[dict[str, object]]:
    """Return the latest status row per ``player_id``, optionally
    filtered to one team and to reports issued on or after a given
    calendar date.

    The ``on_or_after`` filter is the typical T-30min-before-tipoff
    cutoff: only consider reports issued today or later. Defaults to
    no date filter -- callers decide the cutoff.
    """
    where_clauses: list[str] = []
    params: list[object] = []
    if team_abbr is not None:
        where_clauses.append("team_abbr = ?")
        params.append(team_abbr)
    if on_or_after is not None:
        where_clauses.append("as_of >= ?")
        params.append(datetime.combine(on_or_after, datetime.min.time()))
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    rows = con.execute(
        f"""
        SELECT
            i.player_id, i.player_name, i.team_abbr, i.status, i.reason,
            i.as_of, i.fetched_at
        FROM nba_injury i
        JOIN (
            SELECT player_id, MAX(as_of) AS max_as_of
            FROM nba_injury
            {where_sql}
            GROUP BY player_id
        ) latest USING (player_id)
        WHERE i.as_of = latest.max_as_of
        ORDER BY i.team_abbr, i.player_name
        """,
        params,
    ).fetchall()

    cols = (
        "player_id",
        "player_name",
        "team_abbr",
        "status",
        "reason",
        "as_of",
        "fetched_at",
    )
    return [dict(zip(cols, row, strict=False)) for row in rows]


def fetch_for_team(con: duckdb.DuckDBPyConnection, team_abbr: str) -> list[dict[str, object]]:
    """Convenience: latest status per player for one team."""
    return fetch_latest_per_player(con, team_abbr=team_abbr)


__all__ = [
    "fetch_for_team",
    "fetch_latest_per_player",
    "upsert_injuries",
]
