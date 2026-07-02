"""NBA backtest CLV flow.

Reads finished games + Pinnacle odds + crosswalk from DuckDB, replays
each season's games through the Elo model with sequential rating
updates, evaluates per-game price-based CLV vs the devigged pre-tipoff
Pinnacle close, and writes a JSON manifest.

This is the cron-runnable wrapper around the pure evaluator in
:mod:`kq.backtest.nba_clv`. The evaluator is read-only and stateless;
this flow does the I/O + the Elo state evolution.

**Elo training discipline.** We rebuild Elo state by replaying games
in chronological order, pulling per-game ratings BEFORE the game
into the evaluator (so the prediction is honestly out-of-sample at
the per-game level), then folding the realized outcome into the
state for the next game. This is the right shape: trained on the
past, predicting the present, never on the future.

**Pre-tipoff anchor discipline (2026-06-11 audit, root cause #10).**
The odds cron ticks hourly straight through games, so ``nba_odds``
carries in-play snapshots that embed the realized outcome. Every quote
this flow feeds the evaluator is fetched STRICTLY BEFORE tipoff
(``fetched_at < commence_time``, the same tipoff column PR-D's
pre-tipoff trade guard reads). Games whose only Pinnacle rows are
in-play are EXCLUDED from evaluation and counted in the manifest
(``n_excluded_no_pretipoff_close``) -- never silently dropped.

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
import structlog

from kq.backtest.nba_clv import (
    EVAL_BOOKMAKER,
    EVAL_MARKET,
    BacktestNbaClvSummary,
    FinishedGame,
    GameEvaluation,
    GameQuotes,
    PinnacleQuote,
    aggregate_evaluations,
    evaluate_games,
)
from kq.config import REPO_ROOT, get_settings
from kq.flows.ingest_weather import _db_path_from_settings
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


def fetch_pretipoff_pinnacle_quotes(
    con: duckdb.DuckDBPyConnection,
) -> tuple[dict[str, GameQuotes], set[str]]:
    """Entry + closing Pinnacle h2h snapshots per Odds API game id,
    restricted to rows fetched STRICTLY BEFORE tipoff.

    Entry = earliest pre-tipoff snapshot; close = latest pre-tipoff
    snapshot (``fetched_at < commence_time``, per-row). The strict
    filter is the 2026-06-11 audit fix: the old ``MAX(fetched_at)``
    anchor let in-play quotes -- which embed the realized outcome --
    leak into the closing line.

    Returns ``(quotes, inplay_only_ids)`` where ``inplay_only_ids`` is
    the set of game ids that have Pinnacle h2h rows but NONE usable
    before tipoff; the evaluator counts those games in
    ``n_excluded_no_pretipoff_close`` instead of the no-odds skip.
    """
    rows = con.execute(
        """
        SELECT
            odds_api_game_id,
            arg_min(home_decimal_odds, fetched_at) AS entry_home,
            arg_min(away_decimal_odds, fetched_at) AS entry_away,
            arg_max(home_decimal_odds, fetched_at) AS close_home,
            arg_max(away_decimal_odds, fetched_at) AS close_away
        FROM nba_odds
        WHERE bookmaker_key = ?
          AND market_key = ?
          AND fetched_at < commence_time
          AND home_decimal_odds IS NOT NULL
          AND away_decimal_odds IS NOT NULL
        GROUP BY odds_api_game_id
        """,
        [EVAL_BOOKMAKER, EVAL_MARKET],
    ).fetchall()
    quotes: dict[str, GameQuotes] = {}
    for r in rows:
        odds_api_id = str(r[0])
        quotes[odds_api_id] = GameQuotes(
            odds_api_game_id=odds_api_id,
            entry=PinnacleQuote(
                odds_api_game_id=odds_api_id,
                home_decimal_odds=float(r[1]),
                away_decimal_odds=float(r[2]),
            ),
            close=PinnacleQuote(
                odds_api_game_id=odds_api_id,
                home_decimal_odds=float(r[3]),
                away_decimal_odds=float(r[4]),
            ),
        )

    inplay_rows = con.execute(
        """
        SELECT odds_api_game_id
        FROM nba_odds
        WHERE bookmaker_key = ?
          AND market_key = ?
        GROUP BY odds_api_game_id
        HAVING SUM(
            CASE WHEN fetched_at < commence_time
                  AND home_decimal_odds IS NOT NULL
                  AND away_decimal_odds IS NOT NULL
            THEN 1 ELSE 0 END
        ) = 0
        """,
        [EVAL_BOOKMAKER, EVAL_MARKET],
    ).fetchall()
    inplay_only_ids = {str(r[0]) for r in inplay_rows}
    return quotes, inplay_only_ids


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
    quotes: dict[str, GameQuotes],
    crosswalk: list[CrosswalkPair],
    contexts: dict[str, GameContext] | None = None,
    inplay_only_odds_ids: set[str] | None = None,
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
    # Per-game predictions must use the BEFORE-game state, so we run
    # the evaluator once per game with a frozen one-game input and
    # collect the per-game records. This is O(N^2) but N is ~1230
    # regular-season games; fast enough for backtest.
    aggregated_evaluations: list[GameEvaluation] = []
    skipped_no_crosswalk = 0
    skipped_no_odds = 0
    skipped_no_pinnacle = 0
    excluded_no_pretipoff_close = 0
    contexts_local = contexts or {}
    inplay_only = inplay_only_odds_ids or set()
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
            inplay_only_odds_ids=inplay_only,
        )
        if single_summary.n_evaluated == 1:
            aggregated_evaluations.extend(single_summary.evaluations)
        skipped_no_crosswalk += single_summary.n_skipped_no_crosswalk
        skipped_no_odds += single_summary.n_skipped_no_odds
        skipped_no_pinnacle += single_summary.n_skipped_no_pinnacle
        excluded_no_pretipoff_close += single_summary.n_excluded_no_pretipoff_close
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

    # Re-aggregate from the per-game evaluations we collected above,
    # using the SAME public aggregator as the evaluator -- one metric
    # definition, one place. We can't re-run `evaluate_games` because
    # Elo has already moved past every game; the per-game predictions
    # in `aggregated_evaluations` are the correct snapshot.
    summary = aggregate_evaluations(
        aggregated_evaluations,
        skipped_no_odds=skipped_no_odds,
        skipped_no_crosswalk=skipped_no_crosswalk,
        skipped_no_pinnacle=skipped_no_pinnacle,
        excluded_no_pretipoff_close=excluded_no_pretipoff_close,
    )
    return summary, elo


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
        "n_picked": summary.n_picked,
        "n_skipped_no_odds": summary.n_skipped_no_odds,
        "n_skipped_no_crosswalk": summary.n_skipped_no_crosswalk,
        "n_skipped_no_pinnacle": summary.n_skipped_no_pinnacle,
        "n_excluded_no_pretipoff_close": summary.n_excluded_no_pretipoff_close,
        "brier_model": summary.brier_model,
        "brier_pinnacle": summary.brier_pinnacle,
        "mean_clv": summary.mean_clv,
        "mean_edge_vs_close": summary.mean_edge_vs_close,
        "win_rate_when_picked": summary.win_rate_when_picked,
        "honest_caveats": [
            "Pinnacle-only evaluation; games not quoted by Pinnacle are skipped.",
            "CLV = (devigged pre-tipoff closing prob of the bought side) - "
            "(vig-INCLUSIVE entry price paid). Outcome-free by construction; "
            "replaces the outcome-conditioned mean_signed_clv retired by the "
            "2026-06-11 audit (root cause #10).",
            "Closing anchor = LATEST Pinnacle h2h row fetched STRICTLY BEFORE "
            "tipoff; entry = earliest pre-tipoff row. In-play rows never anchor.",
            "Games with Pinnacle rows but none pre-tipoff are EXCLUDED and "
            "counted in n_excluded_no_pretipoff_close -- never silently.",
            "Skip-path counters are reported separately so n_evaluated stays honest.",
            "win_rate_when_picked is descriptive only (favorite-leaning models "
            "exceed 0.5 without skill); it gates nothing.",
            "Phase 5 #5 bar: mean_clv >= +0.01 over a full season.",
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
        quotes, inplay_only_ids = fetch_pretipoff_pinnacle_quotes(con)
        crosswalk = fetch_crosswalk_rows(con)
    finally:
        con.close()

    summary, final_elo = replay_and_evaluate(
        games_with_dates=games_with_dates,
        quotes=quotes,
        crosswalk=crosswalk,
        inplay_only_odds_ids=inplay_only_ids,
    )
    out_path = write_manifest(summary, final_elo, out_path=manifest_path or MANIFEST_PATH)

    log.info(
        "nba_clv_backtest.done",
        n_evaluated=summary.n_evaluated,
        n_picked=summary.n_picked,
        n_skipped_no_odds=summary.n_skipped_no_odds,
        n_skipped_no_crosswalk=summary.n_skipped_no_crosswalk,
        n_skipped_no_pinnacle=summary.n_skipped_no_pinnacle,
        n_excluded_no_pretipoff_close=summary.n_excluded_no_pretipoff_close,
        mean_clv=summary.mean_clv,
        mean_edge_vs_close=summary.mean_edge_vs_close,
        win_rate=summary.win_rate_when_picked,
        manifest=str(out_path),
    )
    print(
        f"nba_clv_backtest: evaluated {summary.n_evaluated} games "
        f"(skipped {summary.n_skipped_no_crosswalk} no-crosswalk, "
        f"{summary.n_skipped_no_odds} no-odds, "
        f"{summary.n_skipped_no_pinnacle} no-pinnacle; "
        f"excluded {summary.n_excluded_no_pretipoff_close} with no pre-tipoff close); "
        f"mean_clv={summary.mean_clv} "
        f"-> {out_path}"
    )
    return summary.n_evaluated


__all__ = [
    "MANIFEST_PATH",
    "fetch_crosswalk_rows",
    "fetch_finished_games",
    "fetch_finished_games_with_dates",
    "fetch_pretipoff_pinnacle_quotes",
    "main",
    "replay_and_evaluate",
    "write_manifest",
]
