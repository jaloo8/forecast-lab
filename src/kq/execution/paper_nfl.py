"""NFL paper-trading signal evaluator.

Same edge thesis as NBA (CLAUDE.md §1, MULTI-SPORT-NFL-PGA-DESIGN.md §2):
the vig-stripped Pinnacle moneyline IS the fair probability; compare it to
the Kalshi quote and trade the gap. One deliberate difference from the NBA
evaluator: **no model fallback.** NBA falls back to Elo when Pinnacle is
off-board; the design doc pins "No Elo for v1" for NFL because Pinnacle
quotes next-season NFL lines months early — the anchor never goes missing
the way NBA's does. When the anchor IS unusable (missing side, bad odds,
out-of-band booksum) this evaluator emits NO signal, with a structured
skip reason. A no-model lane must never trade without its anchor.

Pure function; no DB I/O. Sizing / Kelly / fee math delegates to the
sport-agnostic :func:`kq.execution.paper.evaluate_market`, and the devig
is the SAME function the NBA evaluator uses
(:func:`kq.execution.paper_nba.pinnacle_fair_home_or_none`) — one devig
definition across the sports lane.
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
from kq.execution.paper_nba import pinnacle_fair_home_or_none

# Signal-table model name for NFL paper trades. There is deliberately no
# fallback model name — NFL v1 has no fallback model.
DEFAULT_NFL_MODEL_NAME: Final = "nfl_pinnacle_anchored_v1"


@dataclass(frozen=True, slots=True)
class NflQuotePair:
    """The Kalshi quote pair for one NFL-game team-wins YES contract.

    Field naming mirrors the Kalshi book-snap row. Both sides nullable —
    a one-sided book is a real state we handle gracefully.
    """

    ticker: str
    yes_bid: float | None
    yes_ask: float | None
    # Displayed top-of-book sizes; None = unknown (uncapped sizing).
    yes_bid_size: float | None = None
    yes_ask_size: float | None = None


@dataclass(frozen=True, slots=True)
class NflSignalInputs:
    """All the inputs needed to evaluate one NFL paper-trading signal."""

    home_team_abbr: str
    away_team_abbr: str

    pinnacle_home_decimal_odds: float | None
    pinnacle_away_decimal_odds: float | None
    """Both sides of the Pinnacle moneyline. Both must be non-None (and
    usable) for a signal to exist at all — there is no fallback model."""

    kalshi_quote: NflQuotePair
    """The Kalshi YES contract for one side of this game."""

    bankroll_usd: float
    as_of: datetime

    yes_is_home: bool = True
    """Which side of the matchup pays YES on ``kalshi_quote.ticker``.
    Kalshi lists one market per side; the flow sets this from the parsed
    ticker's ``yes_is_home``."""


@dataclass(frozen=True, slots=True)
class NflSignalDecision:
    """Pure-function output. Either a sized intent or a structured
    no-signal record explaining why."""

    intent: PaperTradeIntent | None
    model_prob_home: float | None
    """The devigged Pinnacle home probability, or None when the anchor
    was unusable (which always means no signal)."""

    source: str
    """'pinnacle' when a fair value was formed; 'none' otherwise."""

    skip_reason: str | None = None


def evaluate_nfl_signal(
    inputs: NflSignalInputs,
    *,
    min_edge_pct: float = DEFAULT_MIN_EDGE_PCT,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    max_stake_usd: float = DEFAULT_MAX_STAKE_USD,
) -> NflSignalDecision:
    """Devig the Pinnacle anchor + delegate to ``evaluate_market`` for sizing.

    Returns ``NflSignalDecision``. With no usable anchor the decision is
    a hard no-signal (``source='none'``) — never a model guess.
    """
    fair_home = pinnacle_fair_home_or_none(
        inputs.pinnacle_home_decimal_odds, inputs.pinnacle_away_decimal_odds
    )
    if fair_home is None:
        return NflSignalDecision(
            intent=None,
            model_prob_home=None,
            source="none",
            skip_reason="no usable Pinnacle anchor (missing/invalid quote); NFL v1 has no fallback",
        )

    model_prob_yes = fair_home if inputs.yes_is_home else (1.0 - fair_home)
    intent = evaluate_market(
        model_prob_yes=model_prob_yes,
        yes_bid=inputs.kalshi_quote.yes_bid,
        yes_ask=inputs.kalshi_quote.yes_ask,
        yes_bid_size=inputs.kalshi_quote.yes_bid_size,
        yes_ask_size=inputs.kalshi_quote.yes_ask_size,
        bankroll_usd=inputs.bankroll_usd,
        as_of=inputs.as_of,
        ticker=inputs.kalshi_quote.ticker,
        model_name=DEFAULT_NFL_MODEL_NAME,
        min_edge_pct=min_edge_pct,
        kelly_fraction=kelly_fraction,
        max_stake_usd=max_stake_usd,
    )
    if intent is None:
        return NflSignalDecision(
            intent=None,
            model_prob_home=fair_home,
            source="pinnacle",
            skip_reason="evaluate_market returned None (no edge / unusable quote / zero stake)",
        )
    return NflSignalDecision(
        intent=intent,
        model_prob_home=fair_home,
        source="pinnacle",
        skip_reason=None,
    )


__all__ = [
    "DEFAULT_NFL_MODEL_NAME",
    "NflQuotePair",
    "NflSignalDecision",
    "NflSignalInputs",
    "evaluate_nfl_signal",
]
