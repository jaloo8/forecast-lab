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


def test_decide_taker_at_skip_boundary() -> None:
    """Just-above the skip threshold: take the trade as a taker (not maker yet)."""
    policy = MakerTakerPolicy(maker_min_edge_pct=2.0, skip_min_edge_pct=4.0)
    # Pre-fee edge engineered so post-fee edge is just above 4 pp but well below 6 pp.
    # taker fee at 0.5 = ceil(0.07 * 0.5 * 0.5 * 100) / 100 = 2¢
    # post-fee edge needs to be >= 4 pp but < 6 pp.
    # → pre-fee edge in [4¢ + 2¢ = 6¢, 6¢ + 2¢ = 8¢) at price 0.5.
    assert policy.decide(edge_pre_fee=0.07, fill_price_taker=0.50) == "taker"


def test_decide_maker_when_edge_buffer_clears_two_ticks_above_skip() -> None:
    """When post-fee edge is >= skip + maker_min_edge_pct, post maker."""
    policy = MakerTakerPolicy(maker_min_edge_pct=2.0, skip_min_edge_pct=4.0)
    # Need post-fee edge >= 4 + 2 = 6 pp at price 0.5 (taker fee 2¢).
    # → pre-fee edge >= 6 + 2 = 8¢.
    assert policy.decide(edge_pre_fee=0.09, fill_price_taker=0.50) == "maker"


def test_decide_handles_negative_edge_via_abs() -> None:
    """Edge sign doesn't matter for the decision; we use absolute value."""
    policy = MakerTakerPolicy(maker_min_edge_pct=2.0, skip_min_edge_pct=4.0)
    assert policy.decide(edge_pre_fee=-0.09, fill_price_taker=0.50) == "maker"
    assert policy.decide(edge_pre_fee=-0.01, fill_price_taker=0.50) == "skip"


def test_decide_at_wing_price_skip_threshold_lower_due_to_lower_fee() -> None:
    """At wing prices (e.g., 0.10), taker fee is smaller so the edge threshold
    is easier to clear in pre-fee terms.

    taker_fee(0.10) = ceil(0.07 * 0.10 * 0.90 * 100)/100 = 0.01
    Post-fee 4 pp edge → pre-fee >= 5¢.
    Post-fee 6 pp edge → pre-fee >= 7¢ (maker).
    """
    policy = MakerTakerPolicy(maker_min_edge_pct=2.0, skip_min_edge_pct=4.0)
    assert policy.decide(edge_pre_fee=0.04, fill_price_taker=0.10) == "skip"
    assert policy.decide(edge_pre_fee=0.05, fill_price_taker=0.10) == "taker"
    # 6 ticks of edge buffer above the skip threshold: 4 + 2 = 6, post-fee = 7 - 1 = 6 → maker.
    assert policy.decide(edge_pre_fee=0.07, fill_price_taker=0.10) == "maker"


def test_decide_thresholds_are_configurable() -> None:
    """A higher maker threshold pushes more trades into the taker bucket."""
    permissive = MakerTakerPolicy(maker_min_edge_pct=1.0, skip_min_edge_pct=4.0)
    strict = MakerTakerPolicy(maker_min_edge_pct=5.0, skip_min_edge_pct=4.0)
    # 7¢ pre-fee edge at 0.5 → 5 pp post-fee.
    assert permissive.decide(edge_pre_fee=0.07, fill_price_taker=0.50) == "maker"
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


def test_maker_fee_is_strictly_lower_than_taker_at_all_prices() -> None:
    """The maker discount is always positive — invariant we rely on."""
    for price in [0.05, 0.10, 0.30, 0.50, 0.70, 0.90, 0.95]:
        taker = fee_per_contract(price, side="taker")
        maker = fee_per_contract(price, side="maker")
        assert maker < taker, (price, taker, maker)


def test_default_thresholds_match_pass1_memo() -> None:
    """Default ``maker_min_edge_pct=2`` matches the memo's '2 ticks' framing."""
    policy = MakerTakerPolicy()
    assert policy.maker_min_edge_pct == 2.0
    assert policy.tick_size_usd == KALSHI_TICK_USD
