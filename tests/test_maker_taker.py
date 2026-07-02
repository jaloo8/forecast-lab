"""Tests for the maker/taker order-type policy."""

from __future__ import annotations

import pytest

from kq.execution.fees import fee_per_contract
from kq.execution.maker_taker import KALSHI_TICK_USD, MakerTakerPolicy

# --------------------------- decision tree ---------------------------


def test_decide_skip_when_below_min_edge() -> None:
    """Edge below skip threshold returns ``skip`` regardless of magnitude."""
    policy = MakerTakerPolicy(maker_min_edge_pct=2.0, skip_min_edge_pct=4.0)
    # 50¢ ask, ~1.75¢ taker fee. 1¢ pre-fee edge => -0.75¢ post-fee => clearly skip.
    assert policy.decide(edge_pre_fee=0.01, fill_price_taker=0.50) == "skip"


def test_decide_maker_threshold_is_absolute_not_stacked_on_skip() -> None:
    """Pass-1 rule (a): post maker when fair value is >= 2 ticks better than
    the marginal taker price AFTER fees — an ABSOLUTE post-fee threshold.

    Regression pin (2026-07-01 audit): `decide` used to require
    `maker_min + skip_min` (6 pp) before posting maker, contradicting both
    its own documented decision tree and the memo it cites. Post-fee edge of
    5 pp (>= 2 pp maker gate, >= 4 pp skip gate, < the old 6 pp compound
    gate) must post maker.
    """
    policy = MakerTakerPolicy(maker_min_edge_pct=2.0, skip_min_edge_pct=4.0)
    # taker fee at 0.5 = ceil(0.07 * 0.5 * 0.5 * 100) / 100 = 2¢
    # pre-fee 7¢ → post-fee 5 pp.
    assert policy.decide(edge_pre_fee=0.07, fill_price_taker=0.50) == "maker"


def test_decide_maker_with_large_edge() -> None:
    """Well above every gate: post maker (pre-fee 9¢ → post-fee 7 pp)."""
    policy = MakerTakerPolicy(maker_min_edge_pct=2.0, skip_min_edge_pct=4.0)
    assert policy.decide(edge_pre_fee=0.09, fill_price_taker=0.50) == "maker"


def test_decide_taker_band_exists_only_above_skip_gate() -> None:
    """`taker` is the band [skip_min, maker_min) — reachable only when the
    maker gate is configured ABOVE the skip gate. At the maker boundary
    itself the contract is >= → maker."""
    policy = MakerTakerPolicy(maker_min_edge_pct=6.0, skip_min_edge_pct=4.0)
    # post-fee 5 pp: trades, but below the 6 pp maker gate → taker.
    assert policy.decide(edge_pre_fee=0.07, fill_price_taker=0.50) == "taker"
    # post-fee exactly 6 pp: boundary is inclusive per the contract → maker.
    assert policy.decide(edge_pre_fee=0.08, fill_price_taker=0.50) == "maker"


def test_decide_handles_negative_edge_via_abs() -> None:
    """Edge sign doesn't matter for the decision; we use absolute value."""
    policy = MakerTakerPolicy(maker_min_edge_pct=2.0, skip_min_edge_pct=4.0)
    assert policy.decide(edge_pre_fee=-0.09, fill_price_taker=0.50) == "maker"
    assert policy.decide(edge_pre_fee=-0.01, fill_price_taker=0.50) == "skip"


def test_decide_at_wing_price_skip_threshold_lower_due_to_lower_fee() -> None:
    """At wing prices (e.g., 0.10), taker fee is smaller so the edge threshold
    is easier to clear in pre-fee terms.

    taker_fee(0.10) = ceil(0.07 * 0.10 * 0.90 * 100)/100 = 0.01
    Post-fee 3 pp (pre-fee 4¢) < 4 pp skip gate → skip.
    Post-fee 4 pp (pre-fee 5¢) clears skip AND the 2 pp maker gate → maker.
    """
    policy = MakerTakerPolicy(maker_min_edge_pct=2.0, skip_min_edge_pct=4.0)
    assert policy.decide(edge_pre_fee=0.04, fill_price_taker=0.10) == "skip"
    assert policy.decide(edge_pre_fee=0.05, fill_price_taker=0.10) == "maker"
    assert policy.decide(edge_pre_fee=0.07, fill_price_taker=0.10) == "maker"


def test_decide_thresholds_are_configurable() -> None:
    """A higher maker threshold pushes more trades into the taker bucket."""
    permissive = MakerTakerPolicy(maker_min_edge_pct=1.0, skip_min_edge_pct=4.0)
    strict = MakerTakerPolicy(maker_min_edge_pct=5.5, skip_min_edge_pct=4.0)
    # 7¢ pre-fee edge at 0.5 → 5 pp post-fee.
    assert permissive.decide(edge_pre_fee=0.07, fill_price_taker=0.50) == "maker"
    # 5 pp clears the skip gate but not the 5.5 pp maker gate → taker.
    assert strict.decide(edge_pre_fee=0.07, fill_price_taker=0.50) == "taker"


# --------------------------- maker fill price ---------------------------


def test_maker_fill_price_is_one_tick_inside() -> None:
    policy = MakerTakerPolicy()
    # BUY_YES would have crossed at ask=0.58. Maker posts at 0.57.
    assert policy.maker_fill_price(0.58, side="BUY_YES") == pytest.approx(0.57)
    # BUY_NO would have crossed at 1 - bid = 0.42. Maker posts at 0.41.
    assert policy.maker_fill_price(0.42, side="BUY_NO") == pytest.approx(0.41)


def test_maker_fill_price_floored_at_one_cent() -> None:
    """Maker can't go below 1¢ — sanity floor matching the engine prob clip."""
    policy = MakerTakerPolicy()
    assert policy.maker_fill_price(0.01, side="BUY_YES") == pytest.approx(0.01)
    assert policy.maker_fill_price(0.005, side="BUY_YES") == pytest.approx(0.01)


def test_maker_fill_price_uses_configured_tick_size() -> None:
    """Some venues use 0.5¢ ticks; confirm the policy honors the cfg."""
    policy = MakerTakerPolicy(tick_size_usd=0.005)
    assert policy.maker_fill_price(0.58, side="BUY_YES") == pytest.approx(0.575)


# --------------------------- fee implications ---------------------------


def test_maker_fee_is_no_higher_than_taker_at_all_prices() -> None:
    """The maker fee is never above taker — invariant we rely on.

    Note: at extreme prices both sides round up to the 1¢ Kalshi floor,
    so the invariant is ``<=`` not ``<``. This is the correct Feb 2026
    Kalshi behavior — a 1¢ minimum applies regardless of side.
    """
    for price in [0.05, 0.10, 0.30, 0.50, 0.70, 0.90, 0.95]:
        taker = fee_per_contract(price, side="taker")
        maker = fee_per_contract(price, side="maker")
        assert maker <= taker, (price, taker, maker)
    # Strict inequality holds in the middle of the price range (not floor-clipped).
    for price in [0.30, 0.50, 0.70]:
        taker = fee_per_contract(price, side="taker")
        maker = fee_per_contract(price, side="maker")
        assert maker < taker, (price, taker, maker)


def test_default_thresholds_match_pass1_memo() -> None:
    """Default ``maker_min_edge_pct=2`` matches the memo's '2 ticks' framing."""
    policy = MakerTakerPolicy()
    assert policy.maker_min_edge_pct == 2.0
    assert policy.tick_size_usd == KALSHI_TICK_USD
