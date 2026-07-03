"""NFL trade-level CLV flow.

Reads executed NFL paper trades + pre-kickoff Pinnacle closes + the
crosswalk from DuckDB, scores each trade through the pure evaluator in
:mod:`kq.backtest.nfl_clv`, and writes a JSON manifest.

This is the NFL sibling of :mod:`kq.flows.run_nba_clv_backtest`, with the
model-replay machinery removed: NFL v1 has no model, so CLV is measured on
the trades the paper flow actually booked (Seat 2 P0-B definition — fill
price in, devigged pre-kickoff close out, no realized outcome anywhere).

**Pre-kickoff anchor discipline.** Every closing quote is the LAST
Pinnacle h2h row fetched STRICTLY BEFORE kickoff (``fetched_at <
commence_time``); rows at/after kickoff embed the score and never anchor.
A close more than 30 minutes older than kickoff is excluded and counted
(``n_excluded_stale_close``) — bump the pre-kickoff odds cadence if that
counter grows.

**No-data safe.** Off-season / pre-key state exits cleanly with a
manifest reporting ``n_trades=0``. Cron entries can be active year-round.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb
import structlog

from kq.backtest.nfl_clv import (
    EVAL_BOOKMAKER,
    EVAL_MARKET,
    BacktestNflClvSummary,
    NflCloseQuote,
    NflTradeForClv,
    evaluate_nfl_trades,
)
from kq.config import REPO_ROOT, get_settings
from kq.flows.ingest_weather import _db_path_from_settings

log = structlog.get_logger(__name__)

MODELS_DIR: Path = REPO_ROOT / "models"
MANIFEST_PATH: Path = MODELS_DIR / "backtest_nfl_clv_manifest.json"


def fetch_nfl_paper_trades(con: duckdb.DuckDBPyConnection) -> list[NflTradeForClv]:
    """Every filled NFL-lane paper trade (settled or not — CLV is
    computable at kickoff, before settlement). The KXNFLGAME ticker prefix
    is the vertical filter; the evaluator re-parses each ticker anyway."""
    rows = con.execute(
        """
        SELECT trade_id, ticker, side, fill_price, qty, fee_usd
        FROM paper_trade
        WHERE ticker LIKE 'KXNFLGAME-%'
          AND fill_price IS NOT NULL
        ORDER BY submitted_at, trade_id
        """,
    ).fetchall()
    return [
        NflTradeForClv(
            trade_id=str(r[0]),
            ticker=str(r[1]),
            side=str(r[2]),
            fill_price=float(r[3]),
            qty=int(r[4]),
            fee_usd=float(r[5]),
        )
        for r in rows
    ]


def fetch_prekickoff_closes(
    con: duckdb.DuckDBPyConnection,
) -> dict[str, NflCloseQuote]:
    """Last STRICTLY-pre-kickoff Pinnacle snapshot per Odds API game id.

    The ``fetched_at < commence_time`` filter is the in-play leakage guard
    (2026-06-11 audit #10 class) — same discipline as the NBA CLV flow's
    quote fetch, applied to ``nfl_odds``.
    """
    rows = con.execute(
        """
        SELECT
            odds_api_game_id,
            arg_max(home_decimal_odds, fetched_at) AS close_home,
            arg_max(away_decimal_odds, fetched_at) AS close_away,
            MAX(fetched_at) AS close_fetched_at,
            arg_max(commence_time, fetched_at) AS commence_time
        FROM nfl_odds
        WHERE bookmaker_key = ?
          AND market_key = ?
          AND fetched_at < commence_time
          AND home_decimal_odds IS NOT NULL
          AND away_decimal_odds IS NOT NULL
        GROUP BY odds_api_game_id
        """,
        [EVAL_BOOKMAKER, EVAL_MARKET],
    ).fetchall()
    out: dict[str, NflCloseQuote] = {}
    for r in rows:
        game_id = str(r[0])
        out[game_id] = NflCloseQuote(
            odds_api_game_id=game_id,
            home_decimal_odds=float(r[1]),
            away_decimal_odds=float(r[2]),
            fetched_at=r[3],
            commence_time=r[4],
        )
    return out


def fetch_matchup_index(con: duckdb.DuckDBPyConnection) -> dict[tuple[date, str, str], str]:
    """Crosswalk lookup: (game_date, home_abbr, away_abbr) -> odds id."""
    rows = con.execute(
        """
        SELECT game_date, home_team_abbr, away_team_abbr, odds_api_game_id
        FROM nfl_game_crosswalk
        """,
    ).fetchall()
    return {(r[0], str(r[1]), str(r[2])): str(r[3]) for r in rows}


def write_manifest(
    summary: BacktestNflClvSummary,
    *,
    out_path: Path = MANIFEST_PATH,
) -> Path:
    """Serialize the trade-level CLV summary as JSON."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "evaluation": "nfl_trade_level_clv",
        "n_trades": summary.n_trades,
        "n_evaluated": summary.n_evaluated,
        "n_excluded_no_crosswalk": summary.n_excluded_no_crosswalk,
        "n_excluded_no_close": summary.n_excluded_no_close,
        "n_excluded_stale_close": summary.n_excluded_stale_close,
        "n_excluded_bad_quote": summary.n_excluded_bad_quote,
        "mean_clv": summary.mean_clv,
        "close_beat_rate": summary.close_beat_rate,
        "mean_clv_se_week_clustered": summary.mean_clv_se_week_clustered,
        "n_week_clusters": summary.n_week_clusters,
        "honest_caveats": [
            "Trade-level CLV on executed NFL paper trades: (devigged "
            "pre-kickoff Pinnacle close of the held side) - (fee-adjusted "
            "Kalshi fill price). Outcome-free by construction (Seat 2 P0-B).",
            "Closing anchor = LAST Pinnacle h2h row fetched STRICTLY BEFORE "
            "kickoff; rows at/after kickoff never anchor. Closes staler than "
            "30 min are EXCLUDED and counted, never silently used.",
            "Same proportional devig as the NBA lane at every point "
            "(kq.backtest.nba_clv.devig_home_prob) — metric math is shared.",
            "Errors are week-clustered (Thu-Mon game weeks): ~13-16 games "
            "share each Sunday's shocks, so per-trade CIs would overstate "
            "precision. Expect ~110-135 trades/season — a valid late-window "
            "verdict in 4-7 weeks, never a tight one within one season.",
            "Phase 5 #5-style bar: mean_clv >= +0.01 with the clustered CI "
            "lower bound > 0 before widening entry windows (W2-first plan).",
        ],
    }
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
    return out_path


def main(*, db_path: Path | None = None, manifest_path: Path | None = None) -> int:
    """``python -m kq backtest-nfl-clv`` entrypoint.

    Returns ``n_evaluated`` (trades actually scored). 0 is a normal
    off-season / no-trades-yet state.
    """
    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)
    con = duckdb.connect(str(path), read_only=True)
    try:
        trades = fetch_nfl_paper_trades(con)
        closes = fetch_prekickoff_closes(con)
        matchup_index = fetch_matchup_index(con)
    finally:
        con.close()

    summary = evaluate_nfl_trades(
        trades,
        close_by_game=closes,
        odds_id_by_matchup=matchup_index,
    )
    out_path = write_manifest(summary, out_path=manifest_path or MANIFEST_PATH)

    log.info(
        "nfl_clv_backtest.done",
        n_trades=summary.n_trades,
        n_evaluated=summary.n_evaluated,
        n_excluded_no_crosswalk=summary.n_excluded_no_crosswalk,
        n_excluded_no_close=summary.n_excluded_no_close,
        n_excluded_stale_close=summary.n_excluded_stale_close,
        n_excluded_bad_quote=summary.n_excluded_bad_quote,
        mean_clv=summary.mean_clv,
        close_beat_rate=summary.close_beat_rate,
        manifest=str(out_path),
    )
    print(
        f"nfl_clv_backtest: evaluated {summary.n_evaluated}/{summary.n_trades} trades "
        f"(excluded {summary.n_excluded_no_crosswalk} no-crosswalk, "
        f"{summary.n_excluded_no_close} no-close, "
        f"{summary.n_excluded_stale_close} stale-close, "
        f"{summary.n_excluded_bad_quote} bad-quote); "
        f"mean_clv={summary.mean_clv} "
        f"-> {out_path}"
    )
    return summary.n_evaluated


__all__ = [
    "MANIFEST_PATH",
    "fetch_matchup_index",
    "fetch_nfl_paper_trades",
    "fetch_prekickoff_closes",
    "main",
    "write_manifest",
]
