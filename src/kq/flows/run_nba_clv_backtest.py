"""NBA backtest CLV flow.

Reads finished games + Pinnacle odds + crosswalk from DuckDB, replays
each season's games through the Elo model with sequential rating
updates, evaluates per-game CLV vs Pinnacle, and writes a JSON
manifest.

This is the cron-runnable wrapper around the pure evaluator in
:mod:`kq.backtest.nba_clv`. The evaluator is read-only and stateless;
this flow does the I/O + the Elo state evolution.

**Elo training discipline.** We rebuild Elo state by replaying games
in chronological order, pulling per-game ratings BEFORE the game
into the evaluator (so the prediction is honestly out-of-sample at
the per-game level), then folding the realized outcome into the
state for the next game. This is the right shape: trained on the
past, predicting the present, never on the future.

**Pinnacle-only.** Same v1 simplification as the evaluator -- if a
game has no Pinnacle quote in nba_odds, we skip rather than fall
back to BetMGM/DraftKings.

**No-data safe.** When there are no finished games or no Pinnacle
quotes (the off-season + pre-GOAT-plan-signoff state), the flow
exits cleanly with a manifest reporting `n_evaluated=0` and the
skip-path counters. Cron entries can be active without producing
errors.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import structlog

from kq.backtest.nba_clv import (
    EVAL_BOOKMAKER,
    EVAL_MARKET,
    BacktestNbaClvSummary,
    FinishedGame,
    PinnacleQuote,
    evaluate_games,
)
from kq.config import REPO_ROOT, get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.models.calibration import brier_score
from kq.models.nba_crosswalk import CrosswalkPair
from kq.models.nba_elo import (
    GameContext,
    NbaEloRatings,
    season_start_year,
    update_after_game,
)

log = structlog.get_logger(__name__)

MODELS_DIR: Path = REPO_ROOT / "models"
MANIFEST_PATH: Path = MODELS_DIR / "backtest_nba_clv_manifest.json"


def fetch_finished_games(
    con: duckdb.DuckDBPyConnection,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[FinishedGame]:
    """Pull settled NBA games (home_score IS NOT NULL) in the window.

    The score-not-null filter is the truth gate -- we only evaluate
    games whose outcomes have landed. Pre-tipoff or in-progress games
    silently drop out.
    """
    where_clauses = ["home_score IS NOT NULL", "away_score IS NOT NULL"]
    params: list[object] = []
    if start_date is not None:
        where_clauses.append("game_date >= ?")
        params.append(start_date)
    if end_date is not None:
        where_clauses.append("game_date <= ?")
        params.append(end_date)
    where_sql = "WHERE " + " AND ".join(where_clauses)
    rows = con.execute(
        f"""
        SELECT game_id, home_team_abbr, away_team_abbr, home_score, away_score,
               game_date
        FROM nba_game
        {where_sql}
        ORDER BY game_date, game_id
        """,
        params,
    ).fetchall()
    return [
        FinishedGame(
            nba_game_id=str(r[0]),
            home_team_abbr=str(r[1]),
            away_team_abbr=str(r[2]),
            home_score=int(r[3]),
            away_score=int(r[4]),
        )
        for r in rows
    ]


def fetch_finished_games_with_dates(
    con: duckdb.DuckDBPyConnection,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[tuple[FinishedGame, date]]:
    """Same as :func:`fetch_finished_games` but also returns each game's
    date -- needed by the chronological replay loop."""
    where_clauses = ["home_score IS NOT NULL", "away_score IS NOT NULL"]
    params: list[object] = []
    if start_date is not None:
        where_clauses.append("game_date >= ?")
        params.append(start_date)
    if end_date is not None:
        where_clauses.append("game_date <= ?")
        params.append(end_date)
    where_sql = "WHERE " + " AND ".join(where_clauses)
    rows = con.execute(
        f"""
        SELECT game_id, home_team_abbr, away_team_abbr, home_score, away_score,
               game_date
        FROM nba_game
        {where_sql}
        ORDER BY game_date, game_id
        """,
        params,
    ).fetchall()
    return [
        (
            FinishedGame(
                nba_game_id=str(r[0]),
                home_team_abbr=str(r[1]),
                away_team_abbr=str(r[2]),
                home_score=int(r[3]),
                away_score=int(r[4]),
            ),
            r[5],
        )
        for r in rows
    ]


def fetch_latest_pinnacle_quotes(
    con: duckdb.DuckDBPyConnection,
) -> dict[str, PinnacleQuote]:
    """Latest pre-tipoff Pinnacle h2h quote per Odds API game id."""
    rows = con.execute(
        """
        SELECT
            o.odds_api_game_id, o.home_decimal_odds, o.away_decimal_odds
        FROM nba_odds o
        JOIN (
            SELECT odds_api_game_id, MAX(fetched_at) AS max_fetched
            FROM nba_odds
            WHERE bookmaker_key = ? AND market_key = ?
            GROUP BY odds_api_game_id
        ) latest USING (odds_api_game_id)
        WHERE o.bookmaker_key = ?
          AND o.market_key = ?
          AND o.fetched_at = latest.max_fetched
        """,
        [EVAL_BOOKMAKER, EVAL_MARKET, EVAL_BOOKMAKER, EVAL_MARKET],
    ).fetchall()
    quotes: dict[str, PinnacleQuote] = {}
    for r in rows:
        odds_api_id = str(r[0])
        home = r[1]
        away = r[2]
        if home is None or away is None:
            continue
        quotes[odds_api_id] = PinnacleQuote(
            odds_api_game_id=odds_api_id,
            home_decimal_odds=float(home),
            away_decimal_odds=float(away),
        )
    return quotes


def fetch_crosswalk_rows(
    con: duckdb.DuckDBPyConnection,
) -> list[CrosswalkPair]:
    """Hydrate ``nba_game_crosswalk`` rows as ``CrosswalkPair``."""
    rows = con.execute(
        """
        SELECT odds_api_game_id, nba_game_id, home_team_abbr, away_team_abbr,
               game_date
        FROM nba_game_crosswalk
        """,
    ).fetchall()
    return [
        CrosswalkPair(
            odds_api_game_id=str(r[0]),
            nba_game_id=str(r[1]),
            home_team_abbr=str(r[2]),
            away_team_abbr=str(r[3]),
            game_date=r[4],
        )
        for r in rows
    ]


def replay_and_evaluate(
    *,
    games_with_dates: list[tuple[FinishedGame, date]],
    quotes: dict[str, PinnacleQuote],
    crosswalk: list[CrosswalkPair],
    contexts: dict[str, GameContext] | None = None,
) -> tuple[BacktestNbaClvSummary, NbaEloRatings]:
    """Walk the games chronologically, predict each one with the Elo
    state BEFORE the game, then update the state with the realized
    outcome. Ratings regress 1/4 toward the baseline at every season
    boundary (detected from game dates via ``season_start_year``).

    Returns the aggregated CLV summary plus the final Elo state (for
    later inspection / debugging). The state's per-team ratings are
    JSON-safe (plain floats) so the manifest can include them.
    """
    elo = NbaEloRatings()
    # Pre-walk to fill the evaluator: we evaluate ALL games together
    # at the end using the BEFORE-state per game. For v1 we bake the
    # per-game prediction into `evaluate_games` by running it once
    # per game with a frozen one-game input. This is O(N^2) but N is
    # ~1230 regular-season games; fast enough for backtest.
    aggregated_evaluations = []
    skipped_no_crosswalk = 0
    skipped_no_odds = 0
    skipped_no_pinnacle = 0
    contexts_local = contexts or {}
    prev_season: int | None = None

    for game, gd in games_with_dates:
        # 538-style between-seasons regression to the mean. Without it a
        # multi-season replay carries last June's ratings straight into
        # October (2026-06-11 audit: regress_to_baseline was dead code).
        season = season_start_year(gd)
        if prev_season is not None and season != prev_season:
            elo.regress_to_baseline()
        prev_season = season
        single_summary = evaluate_games(
            games=[game],
            quotes_by_odds_id=quotes,
            crosswalk=crosswalk,
            elo=elo,  # state BEFORE this game
            contexts=contexts_local,
        )
        if single_summary.n_evaluated == 1:
            aggregated_evaluations.extend(single_summary.evaluations)
        skipped_no_crosswalk += single_summary.n_skipped_no_crosswalk
        skipped_no_odds += single_summary.n_skipped_no_odds
        skipped_no_pinnacle += single_summary.n_skipped_no_pinnacle
        # Always update Elo with the realized outcome -- including for
        # games we couldn't evaluate (no odds / no crosswalk). The state
        # tracks team strength regardless of whether we had a quote.
        update_after_game(
            elo,
            home_team_abbr=game.home_team_abbr,
            away_team_abbr=game.away_team_abbr,
            home_score=game.home_score,
            away_score=game.away_score,
            ctx=contexts_local.get(game.nba_game_id, GameContext()),
        )

    # Re-aggregate from the per-game evaluations we collected above.
    # We can't re-run `evaluate_games` because Elo has already moved
    # past every game; the per-game predictions in
    # `aggregated_evaluations` are the correct snapshot.
    summary = _aggregate_from_evaluations(
        aggregated_evaluations,
        skipped_no_odds=skipped_no_odds,
        skipped_no_crosswalk=skipped_no_crosswalk,
        skipped_no_pinnacle=skipped_no_pinnacle,
    )
    return summary, elo


def _aggregate_from_evaluations(
    evaluations: list[Any],
    *,
    skipped_no_odds: int,
    skipped_no_crosswalk: int,
    skipped_no_pinnacle: int,
) -> BacktestNbaClvSummary:
    """Mirror the aggregator in `kq.backtest.nba_clv._aggregate` but
    work on already-collected per-game evaluations. Inlining keeps
    the chronological replay's loop transparent."""
    n = len(evaluations)
    if n == 0:
        return BacktestNbaClvSummary(
            n_evaluated=0,
            n_skipped_no_odds=skipped_no_odds,
            n_skipped_no_crosswalk=skipped_no_crosswalk,
            n_skipped_no_pinnacle=skipped_no_pinnacle,
            brier_model=None,
            brier_pinnacle=None,
            mean_clv_vs_pinnacle=None,
            mean_signed_clv=None,
            win_rate_when_picked=None,
            evaluations=[],
        )

    our_probs = np.array([e.our_prob_home for e in evaluations])
    pinnacle_probs = np.array([e.pinnacle_prob_home for e in evaluations])
    realized = np.array([1.0 if e.realized_home_won else 0.0 for e in evaluations])

    brier_model = brier_score(np.clip(our_probs, 0.01, 0.99), realized)
    brier_pinnacle = brier_score(np.clip(pinnacle_probs, 0.01, 0.99), realized)
    mean_clv = float((our_probs - pinnacle_probs).mean())

    signed_edges = np.array(
        [(abs(e.edge) if e.correct_side else -abs(e.edge)) for e in evaluations]
    )
    mean_signed_clv = float(signed_edges.mean())
    win_rate = float(sum(1 for e in evaluations if e.correct_side) / n)

    return BacktestNbaClvSummary(
        n_evaluated=n,
        n_skipped_no_odds=skipped_no_odds,
        n_skipped_no_crosswalk=skipped_no_crosswalk,
        n_skipped_no_pinnacle=skipped_no_pinnacle,
        brier_model=brier_model,
        brier_pinnacle=brier_pinnacle,
        mean_clv_vs_pinnacle=mean_clv,
        mean_signed_clv=mean_signed_clv,
        win_rate_when_picked=win_rate,
        evaluations=list(evaluations),
    )


def write_manifest(
    summary: BacktestNbaClvSummary,
    final_elo: NbaEloRatings,
    *,
    out_path: Path = MANIFEST_PATH,
) -> Path:
    """Serialize the backtest summary + final Elo state as JSON."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "evaluation": "chronological_replay",
        "n_evaluated": summary.n_evaluated,
        "n_skipped_no_odds": summary.n_skipped_no_odds,
        "n_skipped_no_crosswalk": summary.n_skipped_no_crosswalk,
        "n_skipped_no_pinnacle": summary.n_skipped_no_pinnacle,
        "brier_model": summary.brier_model,
        "brier_pinnacle": summary.brier_pinnacle,
        "mean_clv_vs_pinnacle": summary.mean_clv_vs_pinnacle,
        "mean_signed_clv": summary.mean_signed_clv,
        "win_rate_when_picked": summary.win_rate_when_picked,
        "honest_caveats": [
            "Pinnacle-only evaluation; games not quoted by Pinnacle are skipped.",
            "Latest pre-tipoff snapshot is the anchor (not closing line).",
            "Skip-path counters are reported separately so n_evaluated stays honest.",
            "Phase 5 #5 bar: mean_signed_clv >= +0.01 over a full season.",
        ],
        "final_elo_ratings": dict(sorted(final_elo.ratings.items())),
    }
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
    return out_path


def main(*, db_path: Path | None = None, manifest_path: Path | None = None) -> int:
    """``python -m kq backtest-nba-clv`` entrypoint.

    Returns ``n_evaluated`` (the count of games actually scored). 0 is
    a normal off-season / pre-GOAT-plan-signoff state.

    ``manifest_path`` overrides the default ``MANIFEST_PATH`` -- handy
    in tests where we want the JSON to land in a tmp dir rather than
    pollute the repo's ``models/`` directory.
    """
    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)
    con = duckdb.connect(str(path), read_only=True)
    try:
        games_with_dates = fetch_finished_games_with_dates(con)
        quotes = fetch_latest_pinnacle_quotes(con)
        crosswalk = fetch_crosswalk_rows(con)
    finally:
        con.close()

    summary, final_elo = replay_and_evaluate(
        games_with_dates=games_with_dates,
        quotes=quotes,
        crosswalk=crosswalk,
    )
    out_path = write_manifest(summary, final_elo, out_path=manifest_path or MANIFEST_PATH)

    log.info(
        "nba_clv_backtest.done",
        n_evaluated=summary.n_evaluated,
        n_skipped_no_odds=summary.n_skipped_no_odds,
        n_skipped_no_crosswalk=summary.n_skipped_no_crosswalk,
        n_skipped_no_pinnacle=summary.n_skipped_no_pinnacle,
        mean_signed_clv=summary.mean_signed_clv,
        win_rate=summary.win_rate_when_picked,
        manifest=str(out_path),
    )
    print(
        f"nba_clv_backtest: evaluated {summary.n_evaluated} games "
        f"(skipped {summary.n_skipped_no_crosswalk} no-crosswalk, "
        f"{summary.n_skipped_no_odds} no-odds, "
        f"{summary.n_skipped_no_pinnacle} no-pinnacle); "
        f"mean_signed_clv={summary.mean_signed_clv} "
        f"-> {out_path}"
    )
    return summary.n_evaluated


__all__ = [
    "MANIFEST_PATH",
    "fetch_crosswalk_rows",
    "fetch_finished_games",
    "fetch_finished_games_with_dates",
    "fetch_latest_pinnacle_quotes",
    "main",
    "replay_and_evaluate",
    "write_manifest",
]
