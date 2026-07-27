"""Write fantasy NFL projections into the ledger (F1b).

One tick projects the target (season, week) under BOTH scoring formats
(std + ppr — owner decision, both first-class) and appends the rows to
``nfl_player_projection`` with a single ``as_of`` stamp. Re-running later
appends a fresh ``as_of`` revision — Tuesday's number and Sunday-morning's
number are both evidence; the ledger keeps each.

Game context comes from the EXISTING odds lane (never re-ingested):
upcoming opponents from ``nfl_game``, win probabilities from the latest
pre-kickoff Pinnacle ``h2h`` snapshot in ``nfl_odds``, devigged with the
shared :mod:`kq.models.vig_strip` primitives and mapped from odds-lane
team codes (JAC/LAR) to nflverse codes (JAX/LA). When the odds lane has
nothing (off-season, dead ODDS_API_KEY — currently 401 per ROADMAP), the
model degrades to neutral adjustments rather than blocking.

Pre-game enforcement is structural and PER PLAYER: anyone who already has
an actuals row for the target week is skipped, so a Sunday-morning re-run
can still project the late slate without ever "projecting" a settled
Thursday line.

**Recommended cron** (UTC, in-season): after the Tuesday stats ingest and
again Sunday morning::

    30 12 * * 2    kq project-fantasy-nfl
    0  13 * * 7    kq project-fantasy-nfl
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import structlog

from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.models.fantasy_nfl import (
    MODEL_VERSION,
    PlayerProjection,
    nflverse_abbr,
    project_week,
)
from kq.models.nfl_crosswalk import NFL_TEAM_NAME_TO_ABBR, nfl_season_start_year
from kq.models.vig_strip import MoneylineQuote, TwoWayMarket, devig_proportional
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.nfl_odds import fetch_latest_nfl_odds
from kq.storage.repositories.nfl_players import (
    ProjectionRow,
    fetch_player_games,
    insert_projections,
)

log = structlog.get_logger(__name__)


def _row_int(row: dict[str, object], key: str) -> int:
    v = row[key]
    if isinstance(v, int | float):
        return int(v)
    raise TypeError(f"{key!r} is not numeric: {v!r}")


# How far ahead nfl_game rows count as "the upcoming slate". A full NFL
# week spans Thu-Mon; 8 days covers it with margin without dragging in
# the week after next.
UPCOMING_WINDOW_DAYS: int = 8


def _upcoming_context(
    con: duckdb.DuckDBPyConnection, *, now: datetime
) -> tuple[dict[str, str], dict[str, float]]:
    """(opponents, win_probs) keyed by nflverse team code, from the odds
    lane's schedule + latest Pinnacle h2h. Both empty when the lane has
    nothing — the model treats missing keys as neutral."""
    rows = con.execute(
        """
        SELECT home_team_abbr, away_team_abbr
        FROM nfl_game
        WHERE NOT completed AND commence_time >= ? AND commence_time <= ?
        """,
        [now, now + timedelta(days=UPCOMING_WINDOW_DAYS)],
    ).fetchall()
    opponents: dict[str, str] = {}
    for home_abbr, away_abbr in rows:
        home, away = nflverse_abbr(str(home_abbr)), nflverse_abbr(str(away_abbr))
        opponents[home] = away
        opponents[away] = home

    win_probs: dict[str, float] = {}
    try:
        quotes = fetch_latest_nfl_odds(con, bookmaker_key="pinnacle", on_or_after=now.date())
    except duckdb.Error as exc:
        log.warning("fantasy_nfl.odds_read_failed", error=str(exc))
        quotes = []
    for q in quotes:
        home_name, away_name = str(q["home_team"]), str(q["away_team"])
        home_code = NFL_TEAM_NAME_TO_ABBR.get(home_name)
        away_code = NFL_TEAM_NAME_TO_ABBR.get(away_name)
        h_odds, a_odds = q["home_decimal_odds"], q["away_decimal_odds"]
        if home_code is None or away_code is None or h_odds is None or a_odds is None:
            continue
        try:
            fair = devig_proportional(
                TwoWayMarket(
                    home=MoneylineQuote(decimal_odds=float(h_odds)),  # type: ignore[arg-type]
                    away=MoneylineQuote(decimal_odds=float(a_odds)),  # type: ignore[arg-type]
                )
            )  # devig math shared with the CLV lanes -- audit #10 discipline
        except ValueError as exc:
            log.warning("fantasy_nfl.devig_rejected", home=home_name, error=str(exc))
            continue
        win_probs[nflverse_abbr(home_code)] = fair.home
        win_probs[nflverse_abbr(away_code)] = fair.away
    return opponents, win_probs


def _default_week(history: list[dict[str, object]], *, season: int) -> int:
    """Next unplayed week: 1 + the max stored week of the target season
    (week 1 when the season has no rows yet — prior-season fallback)."""
    weeks = [_row_int(r, "week") for r in history if _row_int(r, "season") == season]
    return (max(weeks) + 1) if weeks else 1


def _to_ledger_rows(
    projections: list[PlayerProjection], *, as_of: datetime, model_version: str
) -> list[ProjectionRow]:
    return [
        ProjectionRow(
            player_id=p.player_id,
            player_name=p.player_name,
            season=p.season,
            week=p.week,
            scoring_format=p.scoring,
            projected_points=p.projected_points,
            floor_points=p.floor_points,
            ceiling_points=p.ceiling_points,
            as_of=as_of,
            model_version=model_version,
        )
        for p in projections
    ]


def run(
    *,
    db_path: Path,
    season: int | None = None,
    week: int | None = None,
    now: datetime | None = None,
) -> int:
    """Project (season, week) under both formats and append to the ledger.
    Returns ledger rows written (players x 2 formats)."""
    stamp = now or datetime.now(tz=UTC)
    bootstrap(db_path)
    con = connect(db_path)
    try:
        history = fetch_player_games(con)
        target_season = season or nfl_season_start_year(stamp.date())
        target_week = week or _default_week(history, season=target_season)
        opponents, win_probs = _upcoming_context(
            con, now=stamp.astimezone(UTC).replace(tzinfo=None)
        )

        already_played = {
            str(r["player_id"])
            for r in history
            if _row_int(r, "season") == target_season and _row_int(r, "week") == target_week
        }
        rows: list[ProjectionRow] = []
        n_skipped = 0
        for scoring in ("std", "ppr"):
            projections = project_week(
                history,
                season=target_season,
                week=target_week,
                scoring=scoring,
                opponents=opponents,
                win_probs=win_probs,
            )
            kept = [p for p in projections if p.player_id not in already_played]
            n_skipped += len(projections) - len(kept)
            rows.extend(_to_ledger_rows(kept, as_of=stamp, model_version=MODEL_VERSION))

        n = insert_projections(con, rows)
    finally:
        con.close()

    log.info(
        "fantasy_nfl.projections_written",
        season=target_season,
        week=target_week,
        n_rows=n,
        n_skipped_already_played=n_skipped,
        n_opponent_pairs=len(opponents) // 2,
        n_win_probs=len(win_probs) // 2,
        model_version=MODEL_VERSION,
        db=str(db_path),
    )
    print(
        f"wrote {n} projection rows (season {target_season} week {target_week}, "
        f"std+ppr, {MODEL_VERSION}) -> {db_path}"
    )
    if not opponents:
        print("note: no upcoming games in nfl_game — opponent/game-script adjustments neutral")
    return n


def main(
    *,
    season: int | None = None,
    week: int | None = None,
    db_path: Path | None = None,
) -> int:
    """``python -m kq project-fantasy-nfl`` entrypoint."""
    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)
    return run(db_path=path, season=season, week=week)


__all__ = ["UPCOMING_WINDOW_DAYS", "main", "run"]
