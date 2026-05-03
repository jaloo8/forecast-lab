"""Tests for the NBA paper-trading signal evaluator.

Coverage:
- Pinnacle-quoted path: vig-stripped Pinnacle becomes the model prob.
- Pinnacle-unavailable fallback: Elo with adjustments takes over.
- Both-sides-unusable Pinnacle (one None or invalid odds) falls back
  cleanly without raising.
- Source tag + model_name distinguish the two paths so downstream
  telemetry can split them.
- evaluate_market delegation: Kalshi unusable / inside-spread / no-edge
  cases all surface as decision.intent == None with a skip_reason.
- Sizing (bankroll, Kelly fraction, max stake) honored on the
  underlying call.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kq.execution.paper_nba import (
    DEFAULT_NBA_MODEL_NAME,
    NBA_FALLBACK_MODEL_NAME,
    NbaQuotePair,
    NbaSignalInputs,
    evaluate_nba_signal,
)
from kq.models.nba_elo import GameContext, NbaEloRatings


def _inputs(
    *,
    home_team: str = "LAL",
    away_team: str = "BOS",
    elo: NbaEloRatings | None = None,
    pinnacle_home: float | None = 1.91,
    pinnacle_away: float | None = 1.91,
    kalshi_yes_bid: float | None = 0.39,
    kalshi_yes_ask: float | None = 0.40,
    bankroll: float = 1000.0,
    elo_context: GameContext | None = None,
) -> NbaSignalInputs:
    return NbaSignalInputs(
        home_team_abbr=home_team,
        away_team_abbr=away_team,
        elo=elo or NbaEloRatings(),
        pinnacle_home_decimal_odds=pinnacle_home,
        pinnacle_away_decimal_odds=pinnacle_away,
        kalshi_quote=NbaQuotePair(
            ticker="KXNBAGAME-26MAY04LALBOS-LAL",
            yes_bid=kalshi_yes_bid,
            yes_ask=kalshi_yes_ask,
        ),
        bankroll_usd=bankroll,
        as_of=datetime(2026, 5, 4, 22, 0, tzinfo=UTC),
        elo_context=elo_context,
    )


# --------------------------- pinnacle path ---------------------------


def test_pinnacle_quoted_uses_vig_stripped_fair_as_model_prob() -> None:
    """1.91/1.91 Pinnacle -> fair_home == 0.5. Kalshi yes_ask 0.40
    means Kalshi implied 0.40 < 0.5 -> we'd buy YES with 10 ppts edge."""
    decision = evaluate_nba_signal(_inputs())
    assert decision.source == "pinnacle"
    assert decision.model_prob_home == pytest.approx(0.5, abs=1e-3)
    assert decision.intent is not None
    assert decision.intent.model_name == DEFAULT_NBA_MODEL_NAME
    assert decision.intent.side == "BUY_YES"
    assert decision.intent.limit_price == pytest.approx(0.40)


def test_pinnacle_one_sided_falls_back_to_elo() -> None:
    """Only one Pinnacle leg quoted -> can't vig-strip -> Elo fallback."""
    decision = evaluate_nba_signal(_inputs(pinnacle_home=None, pinnacle_away=1.91))
    assert decision.source == "elo"
    assert decision.model_prob_home is not None
    # At Elo parity with home-court bonus, ~0.64.
    assert decision.model_prob_home == pytest.approx(0.64, abs=1e-2)


def test_pinnacle_invalid_odds_falls_back_to_elo() -> None:
    """Decimal odds <= 1.0 means an invalid quote -> fall back."""
    decision = evaluate_nba_signal(_inputs(pinnacle_home=0.95, pinnacle_away=1.91))
    assert decision.source == "elo"


def test_pinnacle_out_of_band_booksum_falls_back_to_elo() -> None:
    """Booksum below MIN_BOOKSUM (3.0/3.0 -> sum 0.667) refuses devig."""
    decision = evaluate_nba_signal(_inputs(pinnacle_home=3.0, pinnacle_away=3.0))
    assert decision.source == "elo"


# --------------------------- elo fallback path ---------------------------


def test_elo_fallback_uses_predict_win_prob_with_context() -> None:
    """B2B context drops the home prob; the fallback honors it."""
    elo = NbaEloRatings(ratings={"LAL": 1500.0, "BOS": 1500.0})
    baseline = evaluate_nba_signal(_inputs(elo=elo, pinnacle_home=None))
    b2b = evaluate_nba_signal(
        _inputs(
            elo=elo,
            pinnacle_home=None,
            elo_context=GameContext(home_back_to_back=True),
        )
    )
    assert baseline.source == "elo"
    assert b2b.source == "elo"
    assert b2b.model_prob_home is not None and baseline.model_prob_home is not None
    assert b2b.model_prob_home < baseline.model_prob_home


def test_elo_fallback_signal_carries_fallback_model_name() -> None:
    """Tag emitted on the intent so dashboard / telemetry can split
    pinnacle-anchored signals from Elo-fallback signals."""
    decision = evaluate_nba_signal(_inputs(pinnacle_home=None, pinnacle_away=None))
    assert decision.source == "elo"
    if decision.intent is not None:
        assert decision.intent.model_name == NBA_FALLBACK_MODEL_NAME


# --------------------------- kalshi-side rejection ---------------------------


def test_unusable_kalshi_quote_returns_none_intent() -> None:
    """Both Kalshi sides None -> evaluate_market refuses. We surface
    that as decision.intent == None with a skip_reason."""
    decision = evaluate_nba_signal(_inputs(kalshi_yes_bid=None, kalshi_yes_ask=None))
    assert decision.intent is None
    assert decision.skip_reason is not None
    # Model prob is still computed -- the failure is on the market side.
    assert decision.model_prob_home is not None


def test_kalshi_inside_spread_returns_none_intent() -> None:
    """Pinnacle fair = 0.5; Kalshi quotes 0.48/0.52 -> our prob is
    inside the spread -> evaluate_market returns None."""
    decision = evaluate_nba_signal(_inputs(kalshi_yes_bid=0.48, kalshi_yes_ask=0.52))
    assert decision.intent is None
    assert decision.skip_reason is not None
    assert decision.source == "pinnacle"
    assert decision.model_prob_home == pytest.approx(0.5, abs=1e-3)


def test_no_edge_after_min_edge_threshold_returns_none() -> None:
    """Tiny edge below the min_edge_pct gate -> None."""
    decision = evaluate_nba_signal(
        _inputs(kalshi_yes_bid=0.49, kalshi_yes_ask=0.495),
        min_edge_pct=10.0,  # tighten so the small edge doesn't clear
    )
    assert decision.intent is None
    assert decision.skip_reason is not None


def test_buy_no_path_when_pinnacle_picks_away() -> None:
    """Pinnacle 1.30/4.0 -> fair_home ~0.75. Kalshi 0.85/0.86 -> our
    prob (0.75) < bid (0.85) -> BUY_NO at (1 - 0.85) = 0.15."""
    decision = evaluate_nba_signal(
        _inputs(
            pinnacle_home=1.30,
            pinnacle_away=4.0,
            kalshi_yes_bid=0.85,
            kalshi_yes_ask=0.86,
        )
    )
    assert decision.intent is not None
    assert decision.intent.side == "BUY_NO"
    assert decision.intent.limit_price == pytest.approx(0.15, abs=1e-3)


# --------------------------- sizing / bankroll ---------------------------


def test_kelly_fraction_honored_in_underlying_call() -> None:
    """Two evaluations with different kelly_fraction values -> the
    larger fraction sizes a (weakly) larger qty."""
    cheap_kelly = evaluate_nba_signal(_inputs(), kelly_fraction=0.05)
    rich_kelly = evaluate_nba_signal(_inputs(), kelly_fraction=0.25)
    assert cheap_kelly.intent is not None and rich_kelly.intent is not None
    assert rich_kelly.intent.qty >= cheap_kelly.intent.qty


def test_max_stake_caps_qty() -> None:
    """A small max_stake_usd caps qty regardless of Kelly's preference."""
    big_max = evaluate_nba_signal(_inputs(), max_stake_usd=1000.0)
    small_max = evaluate_nba_signal(_inputs(), max_stake_usd=5.0)
    assert big_max.intent is not None and small_max.intent is not None
    assert big_max.intent.qty >= small_max.intent.qty


def test_zero_bankroll_returns_no_signal() -> None:
    """Empty bankroll -> Kelly stake collapses to 0 -> no intent."""
    decision = evaluate_nba_signal(_inputs(bankroll=0.0))
    assert decision.intent is None


# --------------------------- type sanity ---------------------------


def test_decision_is_frozen() -> None:
    decision = evaluate_nba_signal(_inputs())
    with pytest.raises(AttributeError):
        decision.source = "mutated"  # type: ignore[misc]


def test_pinnacle_pickem_with_kalshi_at_parity_no_signal() -> None:
    """Pinnacle 1.91/1.91 -> fair 0.5. Kalshi 0.50/0.50 -> our prob
    is inside the spread (== bid == ask) -> no signal."""
    decision = evaluate_nba_signal(_inputs(kalshi_yes_bid=0.50, kalshi_yes_ask=0.50))
    assert decision.intent is None
