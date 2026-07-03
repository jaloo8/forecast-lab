"""Build/refresh the NFL game-id crosswalk.

Reads:
- ``nfl_odds`` for current Odds API games + their ids.
- ``nfl_game`` for schedule rows + team abbrs + US/Eastern dates.

Runs the deterministic matcher in :mod:`kq.models.nfl_crosswalk` and
upserts results into ``nfl_game_crosswalk``. Idempotent on PK
(odds_api_game_id) — re-running is a free no-op modulo ``matched_at``.

Because both NFL tables key on The Odds API's event id the pairs are
usually identity mappings; the flow still matches on the
(home_abbr, away_abbr, game_date) 3-tuple — never on the id — so the
bridge stays correct even if the ``/odds`` and ``/scores`` endpoints ever
disagree, and so the paper flow's Kalshi-ticker joins have one canonical
lookup shape shared with the NBA lane.

Designed for a daily cron tick after the schedule + odds ingests:

    45 10 * * *    kq build-nfl-crosswalk
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import structlog

from kq.clients.the_odds_api import SPORT_NFL, OddsApiGame
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.models.nfl_crosswalk import NflGameRow, match_nfl_games
from kq.storage.duckdb_store import connect
from kq.storage.repositories.nfl_crosswalk import upsert_nfl_crosswalk

log = structlog.get_logger(__name__)

# Default lookback window. NFL weeks cluster on Sunday; 8 days covers a
# full week-cycle of late-arriving odds + late result updates without
# re-touching stale rows.
DEFAULT_LOOKBACK_DAYS: int = 8


def fetch_recent_nfl_odds_games(
    con: duckdb.DuckDBPyConnection, *, since: datetime
) -> list[OddsApiGame]:
    """Reconstruct the ``OddsApiGame`` shape from the latest ``nfl_odds``
    snapshot per game so the matcher reuses the same pure-function
    pipeline the ingest tests exercise. Bookmakers can be empty — the
    matcher only needs (id, home, away, commence_time)."""
    rows = con.execute(
        """
        SELECT
            o.odds_api_game_id, o.home_team, o.away_team, o.commence_time
        FROM nfl_odds o
        JOIN (
            SELECT odds_api_game_id, MAX(fetched_at) AS max_fetched
            FROM nfl_odds
            WHERE commence_time >= ?
            GROUP BY odds_api_game_id
        ) latest USING (odds_api_game_id)
        WHERE o.commence_time >= ?
          AND o.fetched_at = latest.max_fetched
        """,
        [since.replace(tzinfo=None), since.replace(tzinfo=None)],
    ).fetchall()

    by_game_id: dict[str, OddsApiGame] = {}
    for game_id, home, away, commence in rows:
        if game_id in by_game_id:
            continue
        commence_aware = commence.replace(tzinfo=UTC) if commence.tzinfo is None else commence
        by_game_id[str(game_id)] = OddsApiGame(
            game_id=str(game_id),
            sport_key=SPORT_NFL,
            commence_time=commence_aware,
            home_team=str(home),
            away_team=str(away),
            bookmakers=(),
        )
    return list(by_game_id.values())


def fetch_recent_nfl_game_rows(con: duckdb.DuckDBPyConnection, *, since: date) -> list[NflGameRow]:
    """Pull ``nfl_game`` rows on or after ``since`` re-shaped as
    ``NflGameRow`` so the matcher consumes them directly."""
    rows = con.execute(
        """
        SELECT game_id, season, game_date, commence_time, home_team, home_team_abbr,
               away_team, away_team_abbr, home_score, away_score, completed, home_won
        FROM nfl_game
        WHERE game_date >= ?
        ORDER BY game_date, game_id
        """,
        [since],
    ).fetchall()
    return [
        NflGameRow(
            game_id=str(r[0]),
            season=int(r[1]),
            game_date=r[2],
            commence_time=r[3],
            home_team=str(r[4]),
            home_team_abbr=str(r[5]),
            away_team=str(r[6]),
            away_team_abbr=str(r[7]),
            home_score=None if r[8] is None else int(r[8]),
            away_score=None if r[9] is None else int(r[9]),
            completed=bool(r[10]),
            home_won=None if r[11] is None else bool(r[11]),
        )
        for r in rows
    ]


def main(*, lookback_days: int = DEFAULT_LOOKBACK_DAYS, db_path: Path | None = None) -> int:
    """``python -m kq build-nfl-crosswalk`` entrypoint.

    Returns the count of crosswalk pairs upserted (0 when there are no
    new alignments, which is normal in the off-season).
    """
    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)
    now = datetime.now(tz=UTC)
    since_date = now.date() - timedelta(days=lookback_days)
    since_dt = datetime.combine(since_date, datetime.min.time(), tzinfo=UTC)

    con = connect(path)
    try:
        odds_games = fetch_recent_nfl_odds_games(con, since=since_dt)
        nfl_rows = fetch_recent_nfl_game_rows(con, since=since_date)
        pairs = match_nfl_games(odds_games, nfl_rows)
        n = upsert_nfl_crosswalk(con, pairs)
    finally:
        con.close()

    log.info(
        "nfl_crosswalk.build_done",
        n_odds_games=len(odds_games),
        n_nfl_rows=len(nfl_rows),
        n_matched=len(pairs),
        n_upserted=n,
        since=since_date.isoformat(),
        db=str(path),
    )
    print(
        f"crosswalk: matched {len(pairs)}/{len(odds_games)} odds games "
        f"to nfl schedule (lookback {lookback_days}d) -> {path}"
    )
    return n


__all__ = [
    "DEFAULT_LOOKBACK_DAYS",
    "fetch_recent_nfl_game_rows",
    "fetch_recent_nfl_odds_games",
    "main",
]
