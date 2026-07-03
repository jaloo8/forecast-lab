"""NFL trade-level CLV evaluator — the price-based Phase 5 #5 metric,
computed on EXECUTED paper trades.

The NBA evaluator (:mod:`kq.backtest.nba_clv`) replays a MODEL (Elo)
against Pinnacle because NBA has one. NFL v1 has no model — the devigged
Pinnacle anchor IS the signal — so replaying "our probability" against the
entry quote would tautologically produce zero picks. The honest NFL CLV is
therefore the strategy panel's corrected trade-level definition
(STRATEGY-PANEL-2026-06-11, Seat 2 P0-B), measured on the Kalshi contracts
we actually held:

    CLV_t = p_close(side held) - p_entry(side held)

where

* ``p_entry`` = fee-adjusted fill price in probability units on the Kalshi
  contract actually held: ``(fill_price * qty + fees) / qty``;
* ``p_close`` = proportional-devig Pinnacle probability of the held side
  from the LAST snapshot fetched STRICTLY BEFORE kickoff, and no staler
  than ``max_close_staleness`` before it — older closes exclude the trade
  (counted ``n_excluded_stale_close``), never silently anchor.

No realized outcome appears anywhere in the formula; it is computable at
kickoff, before settlement. The devig is the SAME function the NBA lane
uses (:func:`kq.backtest.nba_clv.devig_home_prob`) — the metric math is
shared, never forked.

Aggregates: ``mean_clv`` (gate bar: >= +0.01), ``close_beat_rate`` (share
of trades with CLV > 0; Seat 2 target > 55%), and a week-clustered
standard error — ~13-16 NFL games settle per Sunday with shared shocks, so
per-trade independence would overstate precision. Clusters are NFL game
weeks (Thu-Mon), formed by shifting game dates back two days so a Monday
night game clusters with the preceding Sunday slate.

Read-only and pure: no DB I/O here. The flow wrapper
(:mod:`kq.flows.run_nfl_clv_backtest`) does the fetching and writes
``models/backtest_nfl_clv_manifest.json``.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Final

from kq.backtest.nba_clv import PinnacleQuote, devig_home_prob
from kq.clients.kalshi._ticker_parser_nfl import parse_nfl_market_ticker

EVAL_BOOKMAKER: Final = "pinnacle"
EVAL_MARKET: Final = "h2h"

# Seat 2's staleness bar: a "close" more than 30 minutes older than kickoff
# is not a closing line; the trade is excluded from the CLV aggregate.
DEFAULT_MAX_CLOSE_STALENESS: Final = timedelta(minutes=30)


@dataclass(frozen=True, slots=True)
class NflTradeForClv:
    """The slice of a paper_trade row the evaluator needs."""

    trade_id: str
    ticker: str
    side: str  # 'BUY_YES' | 'BUY_NO'
    fill_price: float
    qty: int
    fee_usd: float


@dataclass(frozen=True, slots=True)
class NflCloseQuote:
    """The last STRICTLY-pre-kickoff Pinnacle snapshot for one game."""

    odds_api_game_id: str
    home_decimal_odds: float
    away_decimal_odds: float
    fetched_at: datetime  # naive UTC
    commence_time: datetime  # naive UTC


@dataclass(frozen=True, slots=True)
class NflTradeClvEvaluation:
    """Per-trade evaluator output."""

    trade_id: str
    ticker: str
    game_date: date
    held_team_abbr: str  # the team whose win pays our position
    entry_prob: float  # fee-adjusted fill price, probability units
    close_fair_prob: float  # devigged Pinnacle prob of the held side at close
    clv: float  # close_fair_prob - entry_prob; outcome-free


@dataclass(frozen=True, slots=True)
class BacktestNflClvSummary:
    """Aggregated trade-level CLV result."""

    n_trades: int  # NFL paper trades considered
    n_evaluated: int  # trades with a valid pre-kickoff close
    n_excluded_no_crosswalk: int
    n_excluded_no_close: int
    n_excluded_stale_close: int
    n_excluded_bad_quote: int
    mean_clv: float | None
    """Phase 5 #5-style gate metric: mean over evaluated trades of
    (devigged pre-kickoff Pinnacle close of the held side) minus
    (fee-adjusted Kalshi fill price). Bar: >= +0.01 (1pp)."""

    close_beat_rate: float | None
    """Share of evaluated trades with CLV > 0. Seat 2 target: > 55%."""

    mean_clv_se_week_clustered: float | None
    """Standard error of mean_clv treating each NFL game week (Thu-Mon)
    as one cluster — between-cluster estimator, honest about the ~13-16
    shared-shock games each Sunday. None with < 2 clusters."""

    n_week_clusters: int
    evaluations: list[NflTradeClvEvaluation] = field(default_factory=list)


def nfl_week_cluster_key(game_date: date) -> tuple[int, int]:
    """Cluster id for week-clustered errors: the ISO (year, week) of the
    game date shifted BACK two days, so Thu..Mon(+Tue) of one NFL game
    week share a cluster and the next Thursday starts a new one."""
    shifted = game_date - timedelta(days=2)
    iso = shifted.isocalendar()
    return (iso[0], iso[1])


def _held_side_close_prob(
    trade: NflTradeForClv,
    *,
    yes_is_home: bool,
    close: NflCloseQuote,
) -> float:
    """Devigged closing probability of the side the trade actually holds.

    BUY_YES holds the ticker's YES team; BUY_NO holds the opponent.
    Raises ValueError on an unusable quote (delegated to the shared
    devig; callers count the exclusion).
    """
    close_home = devig_home_prob(
        PinnacleQuote(
            odds_api_game_id=close.odds_api_game_id,
            home_decimal_odds=close.home_decimal_odds,
            away_decimal_odds=close.away_decimal_odds,
        )
    )
    yes_prob = close_home if yes_is_home else 1.0 - close_home
    return yes_prob if trade.side == "BUY_YES" else 1.0 - yes_prob


def evaluate_nfl_trades(
    trades: Iterable[NflTradeForClv],
    *,
    close_by_game: Mapping[str, NflCloseQuote],
    odds_id_by_matchup: Mapping[tuple[date, str, str], str],
    max_close_staleness: timedelta = DEFAULT_MAX_CLOSE_STALENESS,
) -> BacktestNflClvSummary:
    """Score every NFL paper trade with a valid pre-kickoff close.

    ``close_by_game`` carries the LAST strictly-pre-kickoff Pinnacle
    snapshot per Odds API game id (the flow's SQL enforces
    ``fetched_at < commence_time``); ``odds_id_by_matchup`` is the
    crosswalk lookup ``(game_date, home_abbr, away_abbr) -> odds id``.
    Trades whose ticker doesn't parse as NFL are ignored entirely (they
    belong to other verticals). Every exclusion is counted, never silent.
    """
    evaluations: list[NflTradeClvEvaluation] = []
    n_trades = 0
    n_no_crosswalk = 0
    n_no_close = 0
    n_stale = 0
    n_bad_quote = 0

    for trade in trades:
        ref = parse_nfl_market_ticker(trade.ticker)
        if ref is None:
            continue  # not an NFL contract; not counted at all
        n_trades += 1
        odds_id = odds_id_by_matchup.get((ref.game_date, ref.home_team_abbr, ref.away_team_abbr))
        if odds_id is None:
            n_no_crosswalk += 1
            continue
        close = close_by_game.get(odds_id)
        if close is None:
            n_no_close += 1
            continue
        if close.commence_time - close.fetched_at > max_close_staleness:
            n_stale += 1
            continue
        try:
            close_prob = _held_side_close_prob(trade, yes_is_home=ref.yes_is_home, close=close)
        except ValueError:
            n_bad_quote += 1
            continue
        entry_prob = (
            (trade.fill_price * trade.qty + trade.fee_usd) / trade.qty
            if trade.qty > 0
            else trade.fill_price
        )
        held_team = (
            ref.yes_team_abbr
            if trade.side == "BUY_YES"
            else (
                ref.away_team_abbr
                if ref.yes_team_abbr == ref.home_team_abbr
                else ref.home_team_abbr
            )
        )
        evaluations.append(
            NflTradeClvEvaluation(
                trade_id=trade.trade_id,
                ticker=trade.ticker,
                game_date=ref.game_date,
                held_team_abbr=held_team,
                entry_prob=entry_prob,
                close_fair_prob=close_prob,
                clv=close_prob - entry_prob,
            )
        )

    return _aggregate(
        evaluations,
        n_trades=n_trades,
        n_no_crosswalk=n_no_crosswalk,
        n_no_close=n_no_close,
        n_stale=n_stale,
        n_bad_quote=n_bad_quote,
    )


def _aggregate(
    evaluations: Sequence[NflTradeClvEvaluation],
    *,
    n_trades: int,
    n_no_crosswalk: int,
    n_no_close: int,
    n_stale: int,
    n_bad_quote: int,
) -> BacktestNflClvSummary:
    n = len(evaluations)
    if n == 0:
        return BacktestNflClvSummary(
            n_trades=n_trades,
            n_evaluated=0,
            n_excluded_no_crosswalk=n_no_crosswalk,
            n_excluded_no_close=n_no_close,
            n_excluded_stale_close=n_stale,
            n_excluded_bad_quote=n_bad_quote,
            mean_clv=None,
            close_beat_rate=None,
            mean_clv_se_week_clustered=None,
            n_week_clusters=0,
            evaluations=[],
        )
    clvs = [e.clv for e in evaluations]
    mean_clv = sum(clvs) / n
    beat = sum(1 for c in clvs if c > 0) / n

    clusters: dict[tuple[int, int], list[float]] = {}
    for e in evaluations:
        clusters.setdefault(nfl_week_cluster_key(e.game_date), []).append(e.clv)
    cluster_means = [sum(v) / len(v) for v in clusters.values()]
    k = len(cluster_means)
    se: float | None = None
    if k >= 2:
        grand = sum(cluster_means) / k
        var = sum((m - grand) ** 2 for m in cluster_means) / (k - 1)
        se = math.sqrt(var / k)

    return BacktestNflClvSummary(
        n_trades=n_trades,
        n_evaluated=n,
        n_excluded_no_crosswalk=n_no_crosswalk,
        n_excluded_no_close=n_no_close,
        n_excluded_stale_close=n_stale,
        n_excluded_bad_quote=n_bad_quote,
        mean_clv=mean_clv,
        close_beat_rate=beat,
        mean_clv_se_week_clustered=se,
        n_week_clusters=k,
        evaluations=list(evaluations),
    )


__all__ = [
    "DEFAULT_MAX_CLOSE_STALENESS",
    "EVAL_BOOKMAKER",
    "EVAL_MARKET",
    "BacktestNflClvSummary",
    "NflCloseQuote",
    "NflTradeClvEvaluation",
    "NflTradeForClv",
    "evaluate_nfl_trades",
    "nfl_week_cluster_key",
]
