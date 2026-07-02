"""Tests for the paper-trading executor's pure-logic core.

Schema-touching tests live in `test_paper_trade_repository.py`. These tests
exercise `evaluate_market` + `settlement_pnl` + the deterministic id helpers
in isolation, with no DB dependencies.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

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


def test_missing_side_blocks_only_trades_that_need_it() -> None:
    """A missing side is ABSENT, not a poisoned quote (2026-07-01 audit):
    BUY_YES needs only a real ask, BUY_NO needs only a real bid."""
    # No bid, real ask, model above ask → BUY_YES still trades.
    yes_intent = evaluate_market(
        model_prob_yes=0.70, yes_bid=None, yes_ask=0.55, bankroll_usd=1_000.0, **DEFAULT_KW
    )
    assert yes_intent is not None and yes_intent.side == "BUY_YES"
    # No ask, real bid, model below bid → BUY_NO still trades.
    no_intent = evaluate_market(
        model_prob_yes=0.20, yes_bid=0.50, yes_ask=None, bankroll_usd=1_000.0, **DEFAULT_KW
    )
    assert no_intent is not None and no_intent.side == "BUY_NO"
    # The trade that NEEDS the absent side is refused: model below the
    # (absent) bid with only an ask on the book → no BUY_NO possible.
    assert (
        evaluate_market(
            model_prob_yes=0.005, yes_bid=None, yes_ask=0.55, bankroll_usd=1_000.0, **DEFAULT_KW
        )
        is None
    )
    # Both sides absent → empty book → no trade.
    assert (
        evaluate_market(
            model_prob_yes=0.70, yes_bid=None, yes_ask=None, bankroll_usd=1_000.0, **DEFAULT_KW
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
    """Prices outside [0, 1] are data errors → defensive skip, not ValueError.
    (Exactly 0.0 bid / 1.0 ask are prod sentinels, tested separately.)"""
    for bad_bid in (-0.1, 1.5):
        assert (
            evaluate_market(
                model_prob_yes=0.70,
                yes_bid=bad_bid,
                yes_ask=0.55,
                bankroll_usd=1_000.0,
                **DEFAULT_KW,
            )
            is None
        )
    for bad_ask in (-0.5, 1.2):
        assert (
            evaluate_market(
                model_prob_yes=0.20,
                yes_bid=0.50,
                yes_ask=bad_ask,
                bankroll_usd=1_000.0,
                **DEFAULT_KW,
            )
            is None
        )


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


# -------------------- prod one-sided-book sentinels (2026-07-01 audit)
# Kalshi prod serves one-sided books with sentinel prices: bid "0.0000" =
# no resting bid, ask "1.0000" = no resting ask. Values below are quoted
# verbatim from the recorded prod fixture
# tests/fixtures/kalshi_prod_markets_weather.json (captured 2026-06-11).
# The old 0 < x < 1 guard rejected the whole market, making the EXECUTABLE
# side of every one-sided book untradable.


def test_prod_sentinel_no_bid_still_buys_yes() -> None:
    """KXHIGHLAX-26JUN11-T79: yes_bid "0.0000" (size 0.00), yes_ask "0.0100"
    (size 220971.25). The ask is real — a model above it must BUY_YES."""
    intent = evaluate_market(
        model_prob_yes=0.10,
        yes_bid=0.0,
        yes_ask=0.01,
        yes_bid_size=0.0,
        yes_ask_size=220971.25,
        bankroll_usd=1_000.0,
        as_of=AS_OF,
        ticker="KXHIGHLAX-26JUN11-T79",
        model_name="test_model",
    )
    assert intent is not None
    assert intent.side == "BUY_YES"
    assert intent.limit_price == pytest.approx(0.01)
    assert intent.qty >= 1
    # The absent bid is recorded in Kalshi's own sentinel encoding.
    assert intent.market_yes_bid == 0.0
    assert intent.market_yes_ask == pytest.approx(0.01)


def test_prod_sentinel_no_ask_still_buys_no() -> None:
    """KXHIGHLAX-26JUN11-B76.5: yes_bid "0.9900" (size 33149.46), yes_ask
    "1.0000" (size 0.00). The bid is real — a model below it must BUY_NO."""
    intent = evaluate_market(
        model_prob_yes=0.90,
        yes_bid=0.99,
        yes_ask=1.0,
        yes_bid_size=33149.46,
        yes_ask_size=0.0,
        bankroll_usd=1_000.0,
        as_of=AS_OF,
        ticker="KXHIGHLAX-26JUN11-B76.5",
        model_name="test_model",
    )
    assert intent is not None
    assert intent.side == "BUY_NO"
    assert intent.limit_price == pytest.approx(0.01)  # 1 - 0.99
    assert intent.market_yes_ask == 1.0


def test_sentinel_side_itself_cannot_be_traded() -> None:
    """A model that would need the sentinel (absent) side gets no trade:
    only-ask book + model below everything → BUY_NO impossible."""
    assert (
        evaluate_market(
            model_prob_yes=0.005,
            yes_bid=0.0,
            yes_ask=0.01,
            bankroll_usd=1_000.0,
            **DEFAULT_KW,
        )
        is None
    )


def test_double_sentinel_book_is_empty() -> None:
    """bid 0.0 AND ask 1.0 → both sides absent → nothing to trade."""
    assert (
        evaluate_market(
            model_prob_yes=0.50,
            yes_bid=0.0,
            yes_ask=1.0,
            bankroll_usd=1_000.0,
            **DEFAULT_KW,
        )
        is None
    )


# ------------------------- displayed-size caps (2026-07-01 audit)
# Paper fills previously ignored quoted size entirely — qty could exceed
# displayed liquidity by orders of magnitude. None = size unknown
# (legacy/demo payload) = uncapped legacy behavior, by contract.


def test_qty_capped_at_displayed_ask_size() -> None:
    """BUY_YES hits the ask → qty is capped at the displayed ask size."""
    intent = evaluate_market(
        model_prob_yes=0.70,
        yes_bid=0.50,
        yes_ask=0.55,
        yes_ask_size=7.9,
        bankroll_usd=1_000_000.0,
        **DEFAULT_KW,
    )
    assert intent is not None
    assert intent.qty == 7  # floor(7.9), NOT the ~90 Kelly would buy


def test_qty_capped_at_displayed_bid_size() -> None:
    """BUY_NO hits the bid → qty is capped at the displayed bid size."""
    intent = evaluate_market(
        model_prob_yes=0.20,
        yes_bid=0.50,
        yes_ask=0.55,
        yes_bid_size=5.2,
        bankroll_usd=1_000_000.0,
        **DEFAULT_KW,
    )
    assert intent is not None
    assert intent.side == "BUY_NO"
    assert intent.qty == 5


def test_size_none_means_uncapped_legacy_behavior() -> None:
    """No size on the payload → sizing is uncapped (documented legacy path)."""
    intent = evaluate_market(
        model_prob_yes=0.70,
        yes_bid=0.50,
        yes_ask=0.55,
        bankroll_usd=1_000_000.0,
        **DEFAULT_KW,
    )
    assert intent is not None
    assert intent.qty == 90  # floor($50 stake cap / 0.55) — no size cap


def test_displayed_size_below_one_contract_no_trade() -> None:
    """Prod really quotes fractional sizes < 1 (KXHIGHLAX-26JUN12-B78.5 ask
    size "0.60") — we trade whole contracts, so that is zero liquidity."""
    intent = evaluate_market(
        model_prob_yes=0.20,
        yes_bid=0.07,
        yes_ask=0.08,
        yes_ask_size=0.60,
        bankroll_usd=1_000.0,
        as_of=AS_OF,
        ticker="KXHIGHLAX-26JUN12-B78.5",
        model_name="test_model",
    )
    assert intent is None


@given(
    prob=st.floats(min_value=0.02, max_value=0.98),
    bid_size=st.floats(min_value=0.0, max_value=1e6, allow_nan=False),
    ask_size=st.floats(min_value=0.0, max_value=1e6, allow_nan=False),
)
def test_qty_never_exceeds_quoted_size(prob: float, bid_size: float, ask_size: float) -> None:
    """Property: whatever side the trade hits, qty <= that side's size."""
    intent = evaluate_market(
        model_prob_yes=prob,
        yes_bid=0.40,
        yes_ask=0.45,
        yes_bid_size=bid_size,
        yes_ask_size=ask_size,
        bankroll_usd=1_000_000_000.0,
        **DEFAULT_KW,
    )
    if intent is None:
        return
    size_hit = ask_size if intent.side == "BUY_YES" else bid_size
    assert intent.qty <= size_hit


# ------------------------- fee-aware Kelly sizing (2026-07-01 audit)


def test_kelly_sizing_is_fee_aware() -> None:
    """The taker fee the edge gate subtracts also reduces the Kelly stake.
    model 0.70 vs ask 0.55, fee(0.55) = $0.02:
    f* = (0.70 - 0.55 - 0.02) / 0.45 = 0.2889 → stake $43.33 → qty 78.
    The old fee-free sizing gave stake $50 (capped) → qty 90."""
    intent = evaluate_market(
        model_prob_yes=0.70,
        yes_bid=0.50,
        yes_ask=0.55,
        bankroll_usd=1_000.0,
        **DEFAULT_KW,
    )
    assert intent is not None
    assert intent.qty == 78
    assert intent.stake_usd == pytest.approx(78 * 0.55)


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


def test_signal_id_keyed_on_model_and_ticker_only() -> None:
    """PR-H: the id is a pure function of (model, ticker) — a Kalshi ticker
    names exactly one contract with one settlement date, so re-evaluating
    the same market at ANY later time must be the same intent. The old
    as_of-UTC-DATE component re-booked NBA evening games after 00:00 UTC."""
    assert make_signal_id(model_name="m", ticker="t") == make_signal_id(model_name="m", ticker="t")


def test_signal_id_stable_across_utc_midnight() -> None:
    """The 6/6-panel scenario: the same NBA market evaluated by the 23:50
    and 00:10 UTC cron ticks must produce ONE signal id (hence one trade)."""
    ticker = "KXNBAGAME-26APR30BOSPHI-PHI"
    before = evaluate_market(
        model_prob_yes=0.70,
        yes_bid=0.50,
        yes_ask=0.55,
        bankroll_usd=1_000.0,
        as_of=datetime(2026, 4, 30, 23, 50, tzinfo=UTC),
        ticker=ticker,
        model_name="nba_pinnacle_anchored_v1",
    )
    after = evaluate_market(
        model_prob_yes=0.70,
        yes_bid=0.50,
        yes_ask=0.55,
        bankroll_usd=1_000.0,
        as_of=datetime(2026, 5, 1, 0, 10, tzinfo=UTC),
        ticker=ticker,
        model_name="nba_pinnacle_anchored_v1",
    )
    assert before is not None and after is not None
    assert before.signal_id == after.signal_id
    assert make_trade_id(before.signal_id) == make_trade_id(after.signal_id)


def test_signal_id_changes_with_ticker_and_model() -> None:
    base_id = make_signal_id(model_name="m1", ticker="t1")
    assert base_id != make_signal_id(model_name="m2", ticker="t1")
    assert base_id != make_signal_id(model_name="m1", ticker="t2")


def test_trade_id_derived_from_signal() -> None:
    sig = make_signal_id(model_name="m", ticker="t")
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
