"""NBA backtest CLV evaluator (Phase 3).

Given:
- a set of finished games with known scores (``nba_game``),
- a snapshot of the latest pre-tipoff Pinnacle quote per game (``nba_odds``),
- a crosswalk mapping odds-API game ids to NBA game ids (``nba_game_crosswalk``),
- a fitted Elo state (running rating dict by team abbr),

this module produces a per-game evaluation:

- our_prob_home: Elo home-team win probability (with adjustments).
- pinnacle_prob_home: vig-stripped Pinnacle home-team win probability.
- edge: ``our_prob_home - pinnacle_prob_home`` -- positive means we
  rate the home team higher than Pinnacle does.
- realized: 1 if home won, 0 if away won.
- correct_side: True iff the side our edge picked won.

And aggregates:
- Brier score for our model AND for Pinnacle's vig-stripped fair.
- CLV-vs-Pinnacle: mean edge across all games we evaluated. Positive
  means we systematically disagreed with Pinnacle in directions
  consistent with the realized outcomes (the Phase 5 #5 bar).
- n_evaluated: count of games successfully joined + scored.
- n_skipped: count of games dropped for missing odds, missing
  crosswalk, or missing scores -- documented for honesty.

The evaluator is **read-only** -- it doesn't update the Elo state
(that's a separate training pass) and doesn't write to DuckDB. The
output is a JSON-safe dict ready to land in
``models/backtest_nba_clv_manifest.json`` once the flow lands in a
follow-up PR.

Two structural simplifications worth flagging:

1. **Pinnacle-only.** The evaluator picks the Pinnacle quote from the
   nba_odds rows; if Pinnacle didn't quote the game (rare on NBA),
   the game is skipped. We don't fall back to BetMGM / DraftKings
   in v1 -- mixing books muddies the CLV measurement.
2. **Single snapshot per game.** The evaluator joins to the LATEST
   pre-tipoff snapshot per (game_id, bookmaker_key, market_key).
   Line movement during a game's market window is not measured.
   Backtest CLV against the closing line is a follow-up; the v1
   number measures CLV against the latest available snapshot, which
   is a slightly inferior anchor but sufficient to clear the Phase 5
   #5 ≥+1% bar.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Final

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
    """Latest pre-tipoff Pinnacle h2h quote for one game.

    Attached to a game by ``odds_api_game_id`` via the crosswalk.
    Decimal odds are guaranteed > 1.0 by ``MoneylineQuote``'s
    constructor; if either side is None the caller should drop the
    game before passing it in.
    """

    odds_api_game_id: str
    home_decimal_odds: float
    away_decimal_odds: float


@dataclass(frozen=True, slots=True)
class GameEvaluation:
    """Per-game evaluator output."""

    nba_game_id: str
    home_team_abbr: str
    away_team_abbr: str
    our_prob_home: float
    pinnacle_prob_home: float
    edge: float  # our_prob_home - pinnacle_prob_home
    realized_home_won: bool
    correct_side: bool  # True iff edge sign matched realized outcome


@dataclass(frozen=True, slots=True)
class BacktestNbaClvSummary:
    """Aggregated CLV-vs-Pinnacle backtest result."""

    n_evaluated: int
    n_skipped_no_odds: int
    n_skipped_no_crosswalk: int
    n_skipped_no_pinnacle: int
    brier_model: float | None
    brier_pinnacle: float | None
    mean_clv_vs_pinnacle: float | None
    """Mean(our_prob_home - pinnacle_prob_home) over evaluated games.
    Positive -> we systematically rated home teams higher than
    Pinnacle did -- but the *useful* CLV is the side-correct version
    (see ``mean_signed_clv``)."""

    mean_signed_clv: float | None
    """Mean(edge_in_picked_direction) -- absolute edge in the side
    we'd actually trade. This is the closest single-number summary
    of "did our disagreements with Pinnacle predict outcomes?". The
    Phase 5 #5 bar is ≥ +0.01 (1pp)."""

    win_rate_when_picked: float | None
    """Fraction of evaluated games where the side our edge picked
    won. >0.5 with positive mean_signed_clv is the green-light combo."""

    evaluations: list[GameEvaluation] = field(default_factory=list)


def evaluate_games(
    *,
    games: Iterable[FinishedGame],
    quotes_by_odds_id: dict[str, PinnacleQuote],
    crosswalk: Iterable[CrosswalkPair],
    elo: NbaEloRatings,
    contexts: dict[str, GameContext] | None = None,
) -> BacktestNbaClvSummary:
    """Run the evaluator. Returns the JSON-safe summary.

    ``crosswalk`` provides the (odds_api_game_id, nba_game_id) join
    keys; ``quotes_by_odds_id`` is the latest pre-tipoff Pinnacle
    quote per Odds API game id (caller pre-aggregates from nba_odds).
    ``contexts`` optionally overrides per-game B2B / travel; missing
    keys default to ``GameContext()`` (no adjustments beyond
    home-court / altitude).
    """
    nba_to_odds: dict[str, str] = {p.nba_game_id: p.odds_api_game_id for p in crosswalk}
    contexts_local = contexts or {}

    evaluations: list[GameEvaluation] = []
    skipped_no_crosswalk = 0
    skipped_no_odds = 0
    skipped_no_pinnacle = 0
    games_list = list(games)

    for game in games_list:
        odds_api_id = nba_to_odds.get(game.nba_game_id)
        if odds_api_id is None:
            skipped_no_crosswalk += 1
            continue
        quote = quotes_by_odds_id.get(odds_api_id)
        if quote is None:
            skipped_no_odds += 1
            continue
        try:
            market = TwoWayMarket(
                home=MoneylineQuote(decimal_odds=quote.home_decimal_odds),
                away=MoneylineQuote(decimal_odds=quote.away_decimal_odds),
            )
        except ValueError:
            # Unusable quote (decimal_odds <= 1.0). Skip rather than
            # propagate -- this is bad data, not a real fair value.
            skipped_no_pinnacle += 1
            continue
        try:
            fair = devig_proportional(market)
        except ValueError:
            # Out-of-band booksum (stale quote, etc.). Skip.
            skipped_no_pinnacle += 1
            continue

        ctx = contexts_local.get(game.nba_game_id, GameContext())
        our_p = predict_win_prob(
            home_rating=elo.get(game.home_team_abbr),
            away_rating=elo.get(game.away_team_abbr),
            home_team_abbr=game.home_team_abbr,
            ctx=ctx,
        )
        edge = our_p - fair.home
        realized_home_won = game.home_score > game.away_score
        # The "correct side" semantic: edge > 0 means we'd buy the
        # home side; that side won iff home_score > away_score. Edge
        # < 0 means we'd buy the away side. Edge == 0 is no trade,
        # which the evaluator records as not-correct (don't reward
        # ties in the win-rate aggregate).
        if edge > 0:
            correct_side = realized_home_won
        elif edge < 0:
            correct_side = not realized_home_won
        else:
            correct_side = False
        evaluations.append(
            GameEvaluation(
                nba_game_id=game.nba_game_id,
                home_team_abbr=game.home_team_abbr,
                away_team_abbr=game.away_team_abbr,
                our_prob_home=our_p,
                pinnacle_prob_home=fair.home,
                edge=edge,
                realized_home_won=realized_home_won,
                correct_side=correct_side,
            )
        )

    return _aggregate(
        evaluations,
        skipped_no_odds=skipped_no_odds,
        skipped_no_crosswalk=skipped_no_crosswalk,
        skipped_no_pinnacle=skipped_no_pinnacle,
    )


def _aggregate(
    evaluations: Sequence[GameEvaluation],
    *,
    skipped_no_odds: int,
    skipped_no_crosswalk: int,
    skipped_no_pinnacle: int,
) -> BacktestNbaClvSummary:
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
    import numpy as np  # noqa: PLC0415 -- lazy import to keep cold-import surface small

    our_probs = np.array([e.our_prob_home for e in evaluations])
    pinnacle_probs = np.array([e.pinnacle_prob_home for e in evaluations])
    realized = np.array([1.0 if e.realized_home_won else 0.0 for e in evaluations])

    brier_model = brier_score(np.clip(our_probs, 0.01, 0.99), realized)
    brier_pinnacle = brier_score(np.clip(pinnacle_probs, 0.01, 0.99), realized)
    mean_clv = float((our_probs - pinnacle_probs).mean())

    # Signed CLV: edge in the side we'd actually pick. For each game,
    # the magnitude of the edge in the picked direction is
    # |edge| * sign(picked_correctly). A correct-direction game adds
    # |edge| to the sum; a wrong-direction game subtracts it. The
    # mean is the load-bearing Phase 5 #5 metric.
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


__all__ = [
    "EVAL_BOOKMAKER",
    "EVAL_MARKET",
    "BacktestNbaClvSummary",
    "FinishedGame",
    "GameEvaluation",
    "PinnacleQuote",
    "evaluate_games",
]
