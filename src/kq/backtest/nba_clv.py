"""NBA backtest CLV evaluator (Phase 3, honest-metrics rev per the 2026-06-11 audit).

Given:
- a set of finished games with known scores (``nba_game``),
- entry + closing PRE-TIPOFF Pinnacle quotes per game (``nba_odds``),
- a crosswalk mapping odds-API game ids to NBA game ids (``nba_game_crosswalk``),
- a fitted Elo state (running rating dict by team abbr),

this module produces a per-game evaluation and a price-based CLV aggregate.

**The metric (Phase 5 #5).** For each game we pick a side against the
devigged ENTRY quote, pay that side's vig-inclusive entry price, and
measure against the devigged closing line:

- ``side``      = home if ``our_prob_home > entry_fair_home`` else away
  (equal -> no trade, no CLV contribution).
- ``entry_price`` = ``1 / entry_decimal_odds(side)`` -- the raw,
  vig-INCLUSIVE implied probability, i.e. the price actually paid.
- ``close_fair_prob_side`` = proportional-devig fair probability of
  ``side`` from the LATEST quote fetched STRICTLY BEFORE tipoff.
- ``clv`` = ``close_fair_prob_side - entry_price``.
- ``mean_clv`` = mean of ``clv`` over picked games -- the Phase 5 #5
  gate metric (bar: >= +0.01).

This is outcome-free by construction: the realized winner never enters
the formula. The 2026-06-11 audit (root cause #10) retired the old
``mean_signed_clv`` -- ``mean(+|edge| if picked side won else -|edge|)``
-- whose expectation is ``|edge| * (2p - 1)``: positive for any
zero-skill model that leans toward favorites. It was not CLV.

Also reported:
- Brier score for our model AND for Pinnacle's devigged close, on the
  same realized outcomes (this pair, not CLV, is the skill comparison).
- ``mean_edge_vs_close``: unconditional ``mean(our_prob_home -
  close_fair_prob_home)`` -- a disagreement diagnostic, not a skill claim.
- ``win_rate_when_picked``: fraction of PICKED sides that won.
  Descriptive only; a favorite-leaning zero-skill model exceeds 0.5 here,
  so it must never gate anything.
- skip/exclusion counters, documented for honesty. Games whose only
  Pinnacle rows are in-play (nothing fetched before tipoff) are EXCLUDED
  from evaluation and counted in ``n_excluded_no_pretipoff_close`` --
  in-play quotes embed the realized outcome and must never anchor.

The evaluator is **read-only** -- it doesn't update the Elo state
(that's a separate training pass) and doesn't write to DuckDB. The
output is a JSON-safe dict ready to land in
``models/backtest_nba_clv_manifest.json``.

Structural simplification worth flagging: **Pinnacle-only.** If
Pinnacle didn't quote the game (rare on NBA), the game is skipped. We
don't fall back to BetMGM / DraftKings -- mixing books muddies the CLV
measurement.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from typing import Final, Literal

from kq.models.calibration import brier_score
from kq.models.nba_crosswalk import CrosswalkPair
from kq.models.nba_elo import GameContext, NbaEloRatings, predict_win_prob
from kq.models.vig_strip import (
    MoneylineQuote,
    TwoWayMarket,
    devig_proportional,
)

# Pinnacle is the canonical fair-value anchor; we evaluate exclusively
# against it for v1. See docs/research/PASS-1-EXTENSION-EMOS-EXECUTION.md
# for why.
EVAL_BOOKMAKER: Final = "pinnacle"
EVAL_MARKET: Final = "h2h"

Side = Literal["home", "away"]


@dataclass(frozen=True, slots=True)
class FinishedGame:
    """One settled game with the inputs the evaluator needs.

    All fields are required -- we don't evaluate games whose scores
    haven't landed (caller filters out unsettled rows before passing
    to the evaluator).
    """

    nba_game_id: str
    home_team_abbr: str
    away_team_abbr: str
    home_score: int
    away_score: int


@dataclass(frozen=True, slots=True)
class PinnacleQuote:
    """One Pinnacle h2h snapshot (pair of decimal odds) for one game.

    If either side is None the caller should drop the row before
    passing it in; odds validity (> 1.0) is enforced downstream by
    ``MoneylineQuote``.
    """

    odds_api_game_id: str
    home_decimal_odds: float
    away_decimal_odds: float


@dataclass(frozen=True, slots=True)
class GameQuotes:
    """Entry + closing pre-tipoff Pinnacle snapshots for one game.

    ``entry`` is the EARLIEST snapshot fetched before tipoff (the quote
    a trade would have been placed against); ``close`` is the LATEST
    snapshot fetched STRICTLY BEFORE tipoff (the closing anchor). With
    a single pre-tipoff snapshot the two are the same row. In-play
    snapshots must never appear here -- the flow's fetch enforces
    ``fetched_at < commence_time``.
    """

    odds_api_game_id: str
    entry: PinnacleQuote
    close: PinnacleQuote


@dataclass(frozen=True, slots=True)
class GameEvaluation:
    """Per-game evaluator output."""

    nba_game_id: str
    home_team_abbr: str
    away_team_abbr: str
    our_prob_home: float
    entry_fair_prob_home: float  # devigged entry quote (side-pick anchor)
    close_fair_prob_home: float  # devigged pre-tipoff close (Brier + edge anchor)
    edge: float  # our_prob_home - entry_fair_prob_home
    side: Side | None  # None when edge == 0 (no trade)
    entry_price: float | None  # vig-INCLUSIVE implied prob paid for `side` at entry
    close_fair_prob_side: float | None  # devigged close prob of `side`
    clv: float | None  # close_fair_prob_side - entry_price; outcome-free
    realized_home_won: bool
    correct_side: bool  # descriptive only; True iff the picked side won


@dataclass(frozen=True, slots=True)
class BacktestNbaClvSummary:
    """Aggregated price-based CLV-vs-Pinnacle backtest result."""

    n_evaluated: int
    n_picked: int  # games where a side was actually picked (edge != 0)
    n_skipped_no_odds: int
    n_skipped_no_crosswalk: int
    n_skipped_no_pinnacle: int
    n_excluded_no_pretipoff_close: int
    """Games with Pinnacle rows but NONE fetched strictly before tipoff.
    Excluded from evaluation entirely (an in-play quote embeds the
    realized outcome and must never anchor CLV) -- counted, never silent."""

    brier_model: float | None
    brier_pinnacle: float | None
    mean_clv: float | None
    """Phase 5 #5 gate metric: mean over picked games of
    (devigged pre-tipoff closing prob of the bought side) minus
    (vig-inclusive entry price paid for it). Outcome-free by
    construction. Bar: >= +0.01 (1pp)."""

    mean_edge_vs_close: float | None
    """Unconditional mean(our_prob_home - close_fair_prob_home).
    Disagreement diagnostic only -- says nothing about skill."""

    win_rate_when_picked: float | None
    """Fraction of PICKED sides that won. Descriptive; biased above 0.5
    for any favorite-leaning model, so never a gate."""

    evaluations: list[GameEvaluation] = field(default_factory=list)


def _devig_home_prob(quote: PinnacleQuote) -> float:
    """Proportional-devig fair home probability of one snapshot.

    Raises ValueError on unusable odds (<= 1.0) or out-of-band booksum;
    callers convert that into the no-pinnacle skip path.
    """
    market = TwoWayMarket(
        home=MoneylineQuote(decimal_odds=quote.home_decimal_odds),
        away=MoneylineQuote(decimal_odds=quote.away_decimal_odds),
    )
    return devig_proportional(market).home


def _evaluate_one(
    game: FinishedGame,
    quotes: GameQuotes,
    *,
    elo: NbaEloRatings,
    ctx: GameContext,
) -> GameEvaluation:
    """Score one game. Raises ValueError when either snapshot is
    unusable (bad decimal odds / out-of-band booksum)."""
    entry_fair_home = _devig_home_prob(quotes.entry)
    close_fair_home = _devig_home_prob(quotes.close)

    our_p = predict_win_prob(
        home_rating=elo.get(game.home_team_abbr),
        away_rating=elo.get(game.away_team_abbr),
        home_team_abbr=game.home_team_abbr,
        ctx=ctx,
    )
    edge = our_p - entry_fair_home
    side: Side | None
    entry_price: float | None
    close_fair_prob_side: float | None
    clv: float | None
    if edge > 0:
        side = "home"
        entry_price = 1.0 / quotes.entry.home_decimal_odds
        close_fair_prob_side = close_fair_home
        clv = close_fair_prob_side - entry_price
    elif edge < 0:
        side = "away"
        entry_price = 1.0 / quotes.entry.away_decimal_odds
        close_fair_prob_side = 1.0 - close_fair_home
        clv = close_fair_prob_side - entry_price
    else:
        side = None
        entry_price = None
        close_fair_prob_side = None
        clv = None

    realized_home_won = game.home_score > game.away_score
    if side == "home":
        correct_side = realized_home_won
    elif side == "away":
        correct_side = not realized_home_won
    else:
        correct_side = False
    return GameEvaluation(
        nba_game_id=game.nba_game_id,
        home_team_abbr=game.home_team_abbr,
        away_team_abbr=game.away_team_abbr,
        our_prob_home=our_p,
        entry_fair_prob_home=entry_fair_home,
        close_fair_prob_home=close_fair_home,
        edge=edge,
        side=side,
        entry_price=entry_price,
        close_fair_prob_side=close_fair_prob_side,
        clv=clv,
        realized_home_won=realized_home_won,
        correct_side=correct_side,
    )


def evaluate_games(
    *,
    games: Iterable[FinishedGame],
    quotes_by_odds_id: dict[str, GameQuotes],
    crosswalk: Iterable[CrosswalkPair],
    elo: NbaEloRatings,
    contexts: dict[str, GameContext] | None = None,
    inplay_only_odds_ids: AbstractSet[str] = frozenset(),
) -> BacktestNbaClvSummary:
    """Run the evaluator. Returns the JSON-safe summary.

    ``crosswalk`` provides the (odds_api_game_id, nba_game_id) join
    keys; ``quotes_by_odds_id`` carries the entry + closing PRE-TIPOFF
    Pinnacle snapshots per Odds API game id (caller pre-aggregates from
    nba_odds with a strict ``fetched_at < commence_time`` filter).
    ``inplay_only_odds_ids`` names games that have Pinnacle rows but no
    pre-tipoff snapshot -- they land in
    ``n_excluded_no_pretipoff_close`` rather than the generic no-odds
    skip. ``contexts`` optionally overrides per-game B2B / travel;
    missing keys default to ``GameContext()`` (no adjustments beyond
    home-court / altitude).
    """
    nba_to_odds: dict[str, str] = {p.nba_game_id: p.odds_api_game_id for p in crosswalk}
    contexts_local = contexts or {}

    evaluations: list[GameEvaluation] = []
    skipped_no_crosswalk = 0
    skipped_no_odds = 0
    skipped_no_pinnacle = 0
    excluded_no_pretipoff_close = 0

    for game in games:
        odds_api_id = nba_to_odds.get(game.nba_game_id)
        if odds_api_id is None:
            skipped_no_crosswalk += 1
            continue
        quotes = quotes_by_odds_id.get(odds_api_id)
        if quotes is None:
            if odds_api_id in inplay_only_odds_ids:
                excluded_no_pretipoff_close += 1
            else:
                skipped_no_odds += 1
            continue
        try:
            evaluations.append(
                _evaluate_one(
                    game,
                    quotes,
                    elo=elo,
                    ctx=contexts_local.get(game.nba_game_id, GameContext()),
                )
            )
        except ValueError:
            # Unusable quote (decimal_odds <= 1.0) or out-of-band
            # booksum (stale quote, etc.) in either snapshot. Skip
            # rather than propagate -- this is bad data, not a real
            # fair value.
            skipped_no_pinnacle += 1
            continue

    return aggregate_evaluations(
        evaluations,
        skipped_no_odds=skipped_no_odds,
        skipped_no_crosswalk=skipped_no_crosswalk,
        skipped_no_pinnacle=skipped_no_pinnacle,
        excluded_no_pretipoff_close=excluded_no_pretipoff_close,
    )


def aggregate_evaluations(
    evaluations: Sequence[GameEvaluation],
    *,
    skipped_no_odds: int,
    skipped_no_crosswalk: int,
    skipped_no_pinnacle: int,
    excluded_no_pretipoff_close: int,
) -> BacktestNbaClvSummary:
    """Aggregate per-game evaluations into the summary.

    Public so the chronological-replay flow (which collects per-game
    evaluations across an evolving Elo state) reuses the exact same
    arithmetic as the one-shot evaluator -- one definition, one place.
    """
    n = len(evaluations)
    if n == 0:
        return BacktestNbaClvSummary(
            n_evaluated=0,
            n_picked=0,
            n_skipped_no_odds=skipped_no_odds,
            n_skipped_no_crosswalk=skipped_no_crosswalk,
            n_skipped_no_pinnacle=skipped_no_pinnacle,
            n_excluded_no_pretipoff_close=excluded_no_pretipoff_close,
            brier_model=None,
            brier_pinnacle=None,
            mean_clv=None,
            mean_edge_vs_close=None,
            win_rate_when_picked=None,
            evaluations=[],
        )
    import numpy as np  # noqa: PLC0415 -- lazy import to keep cold-import surface small

    our_probs = np.array([e.our_prob_home for e in evaluations])
    close_probs = np.array([e.close_fair_prob_home for e in evaluations])
    realized = np.array([1.0 if e.realized_home_won else 0.0 for e in evaluations])

    brier_model = brier_score(np.clip(our_probs, 0.01, 0.99), realized)
    brier_pinnacle = brier_score(np.clip(close_probs, 0.01, 0.99), realized)
    mean_edge_vs_close = float((our_probs - close_probs).mean())

    clvs = [e.clv for e in evaluations if e.side is not None and e.clv is not None]
    n_picked = len(clvs)
    mean_clv = float(np.mean(clvs)) if clvs else None
    n_correct = sum(1 for e in evaluations if e.side is not None and e.correct_side)
    win_rate = (n_correct / n_picked) if n_picked else None

    return BacktestNbaClvSummary(
        n_evaluated=n,
        n_picked=n_picked,
        n_skipped_no_odds=skipped_no_odds,
        n_skipped_no_crosswalk=skipped_no_crosswalk,
        n_skipped_no_pinnacle=skipped_no_pinnacle,
        n_excluded_no_pretipoff_close=excluded_no_pretipoff_close,
        brier_model=brier_model,
        brier_pinnacle=brier_pinnacle,
        mean_clv=mean_clv,
        mean_edge_vs_close=mean_edge_vs_close,
        win_rate_when_picked=win_rate,
        evaluations=list(evaluations),
    )


__all__ = [
    "EVAL_BOOKMAKER",
    "EVAL_MARKET",
    "BacktestNbaClvSummary",
    "FinishedGame",
    "GameEvaluation",
    "GameQuotes",
    "PinnacleQuote",
    "Side",
    "aggregate_evaluations",
    "evaluate_games",
]
