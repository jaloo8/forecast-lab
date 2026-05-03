"""Build/refresh the NBA game-id crosswalk.

Reads:
- ``nba_odds`` for current Odds API games + their UUIDs.
- ``nba_game`` for NBA-API game ids + team abbrs + dates.

Runs the deterministic matcher in :mod:`kq.models.nba_crosswalk` and
upserts results into ``nba_game_crosswalk``. Idempotent on PK
(odds_api_game_id) so re-running is a free no-op modulo the
``matched_at`` timestamp updating.

Designed for a daily cron tick: after the nba_schedule + nba_odds
ingest flows have run, this flow refreshes the bridge so downstream
queries can join the two tables.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import structlog

from kq.clients.nba_schedule import NbaGameRow
from kq.clients.the_odds_api import OddsApiGame
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.models.nba_crosswalk import match_games
from kq.storage.duckdb_store import connect
from kq.storage.repositories.nba_crosswalk import upsert_crosswalk

log = structlog.get_logger(__name__)

# Default lookback window. Crosswalk only needs to refresh games we
# actually still trade against -- yesterday's tipoffs settle today, so
# a 7-day window catches any late-arriving odds + late game-result
# updates without hammering the DB on stale rows.
DEFAULT_LOOKBACK_DAYS: int = 7


def fetch_recent_odds_games(
    con: duckdb.DuckDBPyConnection, *, since: datetime
) -> list[OddsApiGame]:
    """Reconstruct the ``OddsApiGame`` shape from the latest snapshot
    per (game, book, market) so the matcher can reuse the same
    pure-function pipeline used by ingest tests.

    Returns the latest snapshot per game (any bookmaker, any market)
    for games whose ``commence_time >= since`` -- enough to cover the
    next tipoff window.
    """
    rows = con.execute(
        """
        SELECT
            o.odds_api_game_id,
            o.bookmaker_key, o.market_key,
            o.home_team, o.away_team, o.commence_time,
            o.home_decimal_odds, o.away_decimal_odds,
            o.book_last_update
        FROM nba_odds o
        JOIN (
            SELECT odds_api_game_id, MAX(fetched_at) AS max_fetched
            FROM nba_odds
            WHERE commence_time >= ?
            GROUP BY odds_api_game_id
        ) latest USING (odds_api_game_id)
        WHERE o.commence_time >= ?
          AND o.fetched_at = latest.max_fetched
        """,
        [since.replace(tzinfo=None), since.replace(tzinfo=None)],
    ).fetchall()

    # Re-shape into OddsApiGame trees keyed by game_id. We only need
    # the game-level fields (id, home, away, commence_time) for the
    # matcher; bookmakers can be empty.
    by_game_id: dict[str, OddsApiGame] = {}
    for row in rows:
        game_id, _book, _market, home, away, commence, _hi, _ai, _bu = row
        if game_id in by_game_id:
            continue
        # commence_time stored naive UTC -> reattach UTC for the matcher.
        commence_aware = commence.replace(tzinfo=UTC) if commence.tzinfo is None else commence
        by_game_id[game_id] = OddsApiGame(
            game_id=str(game_id),
            sport_key="basketball_nba",
            commence_time=commence_aware,
            home_team=str(home),
            away_team=str(away),
            bookmakers=(),
        )
    return list(by_game_id.values())


def fetch_recent_nba_game_rows(con: duckdb.DuckDBPyConnection, *, since: date) -> list[NbaGameRow]:
    """Pull nba_game rows on or after ``since`` and re-shape as
    ``NbaGameRow`` so the matcher can consume them directly."""
    rows = con.execute(
        """
        SELECT game_id, season, season_type, game_date,
               home_team_id, home_team_abbr, away_team_id, away_team_abbr,
               home_score, away_score, home_won
        FROM nba_game
        WHERE game_date >= ?
        ORDER BY game_date, game_id
        """,
        [since],
    ).fetchall()
    return [
        NbaGameRow(
            game_id=str(r[0]),
            season=str(r[1]),
            season_type=str(r[2]),
            game_date=r[3],
            home_team_id=int(r[4]),
            home_team_abbr=str(r[5]),
            away_team_id=int(r[6]),
            away_team_abbr=str(r[7]),
            home_score=None if r[8] is None else int(r[8]),
            away_score=None if r[9] is None else int(r[9]),
            home_won=None if r[10] is None else bool(r[10]),
        )
        for r in rows
    ]


def main(*, lookback_days: int = DEFAULT_LOOKBACK_DAYS, db_path: Path | None = None) -> int:
    """``python -m kq build-nba-crosswalk`` entrypoint.

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
        odds_games = fetch_recent_odds_games(con, since=since_dt)
        nba_rows = fetch_recent_nba_game_rows(con, since=since_date)
        pairs = match_games(odds_games, nba_rows)
        n = upsert_crosswalk(con, pairs)
    finally:
        con.close()

    log.info(
        "nba_crosswalk.build_done",
        n_odds_games=len(odds_games),
        n_nba_rows=len(nba_rows),
        n_matched=len(pairs),
        n_upserted=n,
        since=since_date.isoformat(),
        db=str(path),
    )
    print(
        f"crosswalk: matched {len(pairs)}/{len(odds_games)} odds games "
        f"to nba schedule (lookback {lookback_days}d) -> {path}"
    )
    return n


__all__ = [
    "DEFAULT_LOOKBACK_DAYS",
    "fetch_recent_nba_game_rows",
    "fetch_recent_odds_games",
    "main",
]
