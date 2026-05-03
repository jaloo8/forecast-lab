"""NBA paper-trading signal evaluator.

Per CLAUDE.md §1: NBA edge comes from "Pinnacle-anchored fair-value
arbitrage on Kalshi NBA markets" -- we treat the vig-stripped Pinnacle
quote as our fair probability, then compare against Kalshi's quote.
The 538-style Elo model is a fallback for when Pinnacle isn't
available (off-board, late scratch, mid-game suspension).

This module is the pure-function evaluator: given an NBA game's
inputs (Elo state, Pinnacle quote, Kalshi quote, bankroll), it
produces a :class:`PaperTradeIntent` ready for the existing paper-
trade repository to persist. No DB I/O; the flow that wraps this is
a separate concern.

Signal shape:
- Pick model probability:
    - If Pinnacle is quoted: ``model_prob_home = pinnacle_fair_home``
      (vig-stripped via :mod:`kq.models.vig_strip`).
    - Else: ``model_prob_home = elo_prob_home`` (Elo prediction with
      home-court / B2B / altitude / travel adjustments).
- Compare to Kalshi: ``edge = model_prob_home - kalshi_implied``
  where ``kalshi_implied`` is the YES-side ask if betting home or
  the NO-side ask (= 1 - YES_bid) if betting away.
- Reuse :func:`kq.execution.paper.evaluate_market` for sizing /
  Kelly / fee math so paper-NBA and paper-weather agree on every
  decision the existing infrastructure makes.

Why a thin wrapper rather than a parallel rewrite: the post-fee
Kelly + min-edge gate is sport-agnostic. The NBA-specific bits are
(a) which probability to plug in, (b) the model_name we tag signals
with for downstream filtering. Everything else delegates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from kq.execution.paper import (
    DEFAULT_KELLY_FRACTION,
    DEFAULT_MAX_STAKE_USD,
    DEFAULT_MIN_EDGE_PCT,
    PaperTradeIntent,
    evaluate_market,
)
from kq.models.nba_elo import GameContext, NbaEloRatings, predict_win_prob
from kq.models.vig_strip import (
    MoneylineQuote,
    TwoWayMarket,
    devig_proportional,
)

# Default model name used in the signal table for NBA paper trades.
# Lets downstream queries filter by model when comparing weather vs
# NBA paper-trade history.
DEFAULT_NBA_MODEL_NAME: Final = "nba_pinnacle_anchored_v1"
NBA_FALLBACK_MODEL_NAME: Final = "nba_elo_fallback_v1"


@dataclass(frozen=True, slots=True)
class NbaQuotePair:
    """The Kalshi quote pair for one NBA-game home-team-wins YES contract.

    Field naming mirrors the Kalshi book-snap row's ``yes_bid`` /
    ``yes_ask``. Both sides nullable -- a one-sided book is a possible
    real-world state we want to handle gracefully.
    """

    ticker: str
    yes_bid: float | None
    yes_ask: float | None


@dataclass(frozen=True, slots=True)
class NbaSignalInputs:
    """All the inputs needed to evaluate one NBA paper-trading signal."""

    home_team_abbr: str
    away_team_abbr: str
    elo: NbaEloRatings
    """Live Elo state. Used as fallback when Pinnacle isn't quoted."""

    pinnacle_home_decimal_odds: float | None
    pinnacle_away_decimal_odds: float | None
    """Both sides of the Pinnacle moneyline. Both must be non-None for
    the vig-strip to apply; otherwise we fall back to Elo."""

    kalshi_quote: NbaQuotePair
    """Kalshi YES contract on home-team wins."""

    bankroll_usd: float
    as_of: datetime
    elo_context: GameContext | None = None


@dataclass(frozen=True, slots=True)
class NbaSignalDecision:
    """Pure-function output. Either a sized intent or a structured
    no-signal record explaining why."""

    intent: PaperTradeIntent | None
    model_prob_home: float | None
    """The probability we used for the comparison. None when neither
    Pinnacle nor Elo could produce a usable number (very rare)."""

    source: str
    """Tag for the model_prob_home value: 'pinnacle' | 'elo' | 'none'."""

    skip_reason: str | None = None
    """When ``intent is None``, a short reason string suitable for
    structured logging / dashboard display."""


def _pinnacle_fair_home_or_none(
    home_decimal_odds: float | None, away_decimal_odds: float | None
) -> float | None:
    """Vig-strip the Pinnacle quote; return None on any unusable
    input (missing side, decimal_odds <= 1.0, out-of-band booksum)."""
    if home_decimal_odds is None or away_decimal_odds is None:
        return None
    try:
        market = TwoWayMarket(
            home=MoneylineQuote(decimal_odds=home_decimal_odds),
            away=MoneylineQuote(decimal_odds=away_decimal_odds),
        )
        fair = devig_proportional(market)
    except ValueError:
        return None
    return fair.home


def evaluate_nba_signal(
    inputs: NbaSignalInputs,
    *,
    min_edge_pct: float = DEFAULT_MIN_EDGE_PCT,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    max_stake_usd: float = DEFAULT_MAX_STAKE_USD,
) -> NbaSignalDecision:
    """Compute the home-side model probability + delegate to
    ``evaluate_market`` for sizing.

    Returns ``NbaSignalDecision``. When we can't form a model prob
    OR the edge / sizing rejects the trade, the decision carries
    ``intent=None`` plus a ``skip_reason`` for telemetry.
    """
    pinnacle_p = _pinnacle_fair_home_or_none(
        inputs.pinnacle_home_decimal_odds, inputs.pinnacle_away_decimal_odds
    )
    if pinnacle_p is not None:
        model_prob = pinnacle_p
        source = "pinnacle"
        model_name = DEFAULT_NBA_MODEL_NAME
    else:
        # Fallback: use Elo with adjustments.
        model_prob = predict_win_prob(
            home_rating=inputs.elo.get(inputs.home_team_abbr),
            away_rating=inputs.elo.get(inputs.away_team_abbr),
            home_team_abbr=inputs.home_team_abbr,
            ctx=inputs.elo_context,
        )
        source = "elo"
        model_name = NBA_FALLBACK_MODEL_NAME

    intent = evaluate_market(
        model_prob_yes=model_prob,
        yes_bid=inputs.kalshi_quote.yes_bid,
        yes_ask=inputs.kalshi_quote.yes_ask,
        bankroll_usd=inputs.bankroll_usd,
        as_of=inputs.as_of,
        ticker=inputs.kalshi_quote.ticker,
        model_name=model_name,
        min_edge_pct=min_edge_pct,
        kelly_fraction=kelly_fraction,
        max_stake_usd=max_stake_usd,
    )
    if intent is None:
        return NbaSignalDecision(
            intent=None,
            model_prob_home=model_prob,
            source=source,
            skip_reason="evaluate_market returned None (no edge / unusable quote / zero stake)",
        )
    return NbaSignalDecision(
        intent=intent,
        model_prob_home=model_prob,
        source=source,
        skip_reason=None,
    )


__all__ = [
    "DEFAULT_NBA_MODEL_NAME",
    "NBA_FALLBACK_MODEL_NAME",
    "NbaQuotePair",
    "NbaSignalDecision",
    "NbaSignalInputs",
    "evaluate_nba_signal",
]
