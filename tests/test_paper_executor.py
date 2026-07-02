"""Tests for the paper-trading executor's pure-logic core.

Schema-touching tests live in `test_paper_trade_repository.py`. These tests
exercise `evaluate_market` + `settlement_pnl` + the deterministic id helpers
in isolation, with no DB dependencies.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kq.execution.paper import (
    PaperExecutor,
    PaperTradeIntent,
    evaluate_market,
    make_signal_id,
    make_trade_id,
    settlement_pnl,
)

AS_OF = datetime(2026, 4, 28, 18, 0, tzinfo=UTC)
DEFAULT_KW = {
    "as_of": AS_OF,
    "ticker": "KXHIGHLAX-26APR30-T75",
    "model_name": "test_model",
}

# --------------------------------------------------- evaluate_market: BUY_YES


def test_buy_yes_when_model_above_ask() -> None:
    """Big edge: model 0.70, market 0.50/0.55. Should BUY_YES at 0.55."""
    intent = evaluate_market(
        model_prob_yes=0.70,
        yes_bid=0.50,
        yes_ask=0.55,
        bankroll_usd=1_000.0,
        **DEFAULT_KW,
    )
    assert intent is not None
    assert intent.side == "BUY_YES"
    assert intent.limit_price == pytest.approx(0.55)
    assert intent.qty >= 1
    # Edge = 0.70 - 0.55 = 0.15 = 1500 bps
    assert intent.edge_bps == 1500
    assert intent.fee_usd > 0


def test_buy_no_when_model_below_bid() -> None:
    """Big edge on the NO side: model 0.20, market 0.50/0.55. BUY_NO at 1-0.50=0.50."""
    intent = evaluate_market(
        model_prob_yes=0.20,
        yes_bid=0.50,
        yes_ask=0.55,
        bankroll_usd=1_000.0,
        **DEFAULT_KW,
    )
    assert intent is not None
    assert intent.side == "BUY_NO"
    assert intent.limit_price == pytest.approx(0.50)  # 1 - 0.50 yes_bid
    assert intent.qty >= 1
    # Edge: prob_at_fill (1-0.20=0.80) - fill_price (0.50) = 0.30 = 3000 bps
    assert intent.edge_bps == 3000


# ---------------------------------------------------- evaluate_market: skips


def test_no_trade_inside_spread() -> None:
    """Model 0.52 sits between bid 0.50 and ask 0.55 → no trade."""
    intent = evaluate_market(
        model_prob_yes=0.52,
        yes_bid=0.50,
        yes_ask=0.55,
        bankroll_usd=1_000.0,
        **DEFAULT_KW,
    )
    assert intent is None


def test_no_trade_when_edge_under_min_pct() -> None:
    """Model 0.56 vs ask 0.55 → 1pp edge, below default 4% threshold → skip."""
    intent = evaluate_market(
        model_prob_yes=0.56,
        yes_bid=0.50,
        yes_ask=0.55,
        bankroll_usd=1_000.0,
        **DEFAULT_KW,
    )
    assert intent is None


def test_no_trade_when_quote_missing() -> None:
    """Either side None → market untradable → no intent."""
    assert (
        evaluate_market(
            model_prob_yes=0.70, yes_bid=None, yes_ask=0.55, bankroll_usd=1_000.0, **DEFAULT_KW
        )
        is None
    )
    assert (
        evaluate_market(
            model_prob_yes=0.70, yes_bid=0.50, yes_ask=None, bankroll_usd=1_000.0, **DEFAULT_KW
        )
        is None
    )


def test_no_trade_on_crossed_book() -> None:
    """bid > ask (data error) → no trade, no exception."""
    intent = evaluate_market(
        model_prob_yes=0.70,
        yes_bid=0.60,
        yes_ask=0.55,  # crossed
        bankroll_usd=1_000.0,
        **DEFAULT_KW,
    )
    assert intent is None


def test_no_trade_on_out_of_range_quote() -> None:
    """Prices outside (0, 1) → defensive skip rather than ValueError."""
    intent = evaluate_market(
        model_prob_yes=0.70,
        yes_bid=0.0,
        yes_ask=0.55,
        bankroll_usd=1_000.0,
        **DEFAULT_KW,
    )
    assert intent is None


def test_no_trade_when_bankroll_zero() -> None:
    """Zero bankroll → Kelly stake is zero → no contracts → no trade."""
    intent = evaluate_market(
        model_prob_yes=0.70,
        yes_bid=0.50,
        yes_ask=0.55,
        bankroll_usd=0.0,
        **DEFAULT_KW,
    )
    assert intent is None


def test_invalid_model_prob_raises() -> None:
    """Model returning 0 or 1 is a logic bug; raise rather than swallow."""
    with pytest.raises(ValueError, match="model_prob_yes"):
        evaluate_market(
            model_prob_yes=0.0,
            yes_bid=0.50,
            yes_ask=0.55,
            bankroll_usd=1_000.0,
            **DEFAULT_KW,
        )
    with pytest.raises(ValueError, match="model_prob_yes"):
        evaluate_market(
            model_prob_yes=1.0,
            yes_bid=0.50,
            yes_ask=0.55,
            bankroll_usd=1_000.0,
            **DEFAULT_KW,
        )


def test_max_stake_cap_applied() -> None:
    """Even with huge bankroll, cap binds — qty stays bounded."""
    intent = evaluate_market(
        model_prob_yes=0.95,
        yes_bid=0.10,
        yes_ask=0.15,
        bankroll_usd=10_000_000.0,
        max_stake_usd=20.0,
        **DEFAULT_KW,
    )
    assert intent is not None
    assert intent.qty * intent.limit_price <= 20.0 + 1e-6


# ---------------------------------------- hard-cap clamps (audit / PR-G)
# All sizing flows through kq.execution.kelly.fractional_kelly_stake, where
# the CLAUDE.md §5 #7 caps (0.15x Kelly, $200/position) are enforced clamps.
# These pin that evaluate_market — the boundary every paper/NBA flow calls —
# inherits them.


def test_oversized_kelly_fraction_sizes_identically_to_015() -> None:
    """kelly_fraction=0.5 must produce the SAME intent as 0.15 (clamped)."""
    kw = dict(
        model_prob_yes=0.70,
        yes_bid=0.50,
        yes_ask=0.55,
        bankroll_usd=1_000.0,
        **DEFAULT_KW,
    )
    at_cap = evaluate_market(kelly_fraction=0.15, **kw)
    oversized = evaluate_market(kelly_fraction=0.5, **kw)
    assert at_cap is not None and oversized is not None
    assert oversized == at_cap


def test_stake_never_exceeds_position_cap() -> None:
    """A huge max_stake_usd cannot lift the $200 per-position hard cap."""
    intent = evaluate_market(
        model_prob_yes=0.95,
        yes_bid=0.10,
        yes_ask=0.15,
        bankroll_usd=100_000_000.0,
        max_stake_usd=100_000.0,
        **DEFAULT_KW,
    )
    assert intent is not None
    assert intent.stake_usd <= 200.0 + 1e-6


# ------------------------------------------------ deterministic ID helpers


def test_signal_id_is_stable_across_same_day() -> None:
    """Two calls with different times on the same UTC day produce the same id."""
    morning = datetime(2026, 4, 28, 6, 30, tzinfo=UTC)
    evening = datetime(2026, 4, 28, 21, 45, tzinfo=UTC)
    a = make_signal_id(model_name="m", ticker="t", as_of=morning)
    b = make_signal_id(model_name="m", ticker="t", as_of=evening)
    assert a == b


def test_signal_id_changes_with_day() -> None:
    a = make_signal_id(model_name="m", ticker="t", as_of=datetime(2026, 4, 28, tzinfo=UTC))
    b = make_signal_id(model_name="m", ticker="t", as_of=datetime(2026, 4, 29, tzinfo=UTC))
    assert a != b


def test_signal_id_changes_with_ticker_and_model() -> None:
    base = datetime(2026, 4, 28, tzinfo=UTC)
    base_id = make_signal_id(model_name="m1", ticker="t1", as_of=base)
    assert base_id != make_signal_id(model_name="m2", ticker="t1", as_of=base)
    assert base_id != make_signal_id(model_name="m1", ticker="t2", as_of=base)


def test_trade_id_derived_from_signal() -> None:
    sig = make_signal_id(model_name="m", ticker="t", as_of=AS_OF)
    trade_id = make_trade_id(sig)
    assert trade_id.startswith("paper-")
    # Contains the same hash suffix as the signal id
    assert sig.split("-", 1)[1] == trade_id.split("-", 1)[1]


# ---------------------------------------------------------- settlement_pnl


def test_settlement_buy_yes_wins() -> None:
    """BUY_YES at 0.55, qty 10, fee 0.20, outcome YES → 10*(1-0.55) - 0.20 = 4.30."""
    pnl = settlement_pnl(side="BUY_YES", fill_price=0.55, qty=10, fee_usd=0.20, outcome_yes=True)
    assert pnl == pytest.approx(4.30)


def test_settlement_buy_yes_loses() -> None:
    """BUY_YES at 0.55, qty 10, fee 0.20, outcome NO → -10*0.55 - 0.20 = -5.70."""
    pnl = settlement_pnl(side="BUY_YES", fill_price=0.55, qty=10, fee_usd=0.20, outcome_yes=False)
    assert pnl == pytest.approx(-5.70)


def test_settlement_buy_no_wins() -> None:
    """BUY_NO at 0.50 (paid), qty 10, fee 0.20, outcome NO → 10*(1-0.50) - 0.20 = 4.80."""
    pnl = settlement_pnl(side="BUY_NO", fill_price=0.50, qty=10, fee_usd=0.20, outcome_yes=False)
    assert pnl == pytest.approx(4.80)


def test_settlement_buy_no_loses() -> None:
    """BUY_NO at 0.50 (paid), qty 10, fee 0.20, outcome YES → -10*0.50 - 0.20 = -5.20."""
    pnl = settlement_pnl(side="BUY_NO", fill_price=0.50, qty=10, fee_usd=0.20, outcome_yes=True)
    assert pnl == pytest.approx(-5.20)


def test_settlement_zero_qty_zero_pnl_minus_fee() -> None:
    """qty=0 is a degenerate case but must not raise — pnl is just -fee."""
    pnl = settlement_pnl(side="BUY_YES", fill_price=0.55, qty=0, fee_usd=0.20, outcome_yes=True)
    assert pnl == pytest.approx(-0.20)


# ----------------------------------------------------------- PaperExecutor


def test_executor_evaluate_delegates_to_module_function() -> None:
    """Sanity: PaperExecutor.evaluate produces same result as `evaluate_market`."""
    ex = PaperExecutor(bankroll_usd=500.0, model_name="exec_test")
    intent = ex.evaluate(
        model_prob_yes=0.70,
        yes_bid=0.50,
        yes_ask=0.55,
        ticker="KXHIGHLAX-26APR30-T75",
        as_of=AS_OF,
    )
    assert intent is not None
    assert intent.side == "BUY_YES"
    assert intent.model_name == "exec_test"


def test_intent_stake_usd_helper() -> None:
    """`stake_usd` property returns price * qty (capital at risk excl. fees)."""
    intent = PaperTradeIntent(
        signal_id="sig-x",
        as_of=AS_OF,
        ticker="KXHIGHLAX-26APR30-T75",
        side="BUY_YES",
        limit_price=0.50,
        qty=20,
        fee_usd=0.40,
        model_prob_yes=0.7,
        market_yes_bid=0.45,
        market_yes_ask=0.50,
        edge_bps=2000,
        model_name="t",
    )
    assert intent.stake_usd == pytest.approx(10.0)
