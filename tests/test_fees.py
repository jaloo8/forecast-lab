"""Tests for the Kalshi fee model. Uses Hypothesis for property checks."""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from kq.execution.fees import (
    MAKER_COEFFICIENT,
    MAKER_DISCOUNT,
    TAKER_COEFFICIENT,
    fee_per_contract,
    total_fee,
)


def test_fee_at_50_cents_is_175_bps() -> None:
    """Kalshi fee peaks at 50c: ceil(0.07 * 0.25 * 100)/100 = 0.02. Per Pass 1 Section 1a."""
    assert fee_per_contract(0.50, side="taker") == pytest.approx(0.02)


def test_fee_at_extremes_is_cheap() -> None:
    """Fee at 10c or 90c should round down to ~1 cent per contract."""
    assert fee_per_contract(0.10, side="taker") == pytest.approx(0.01)
    assert fee_per_contract(0.90, side="taker") == pytest.approx(0.01)


def test_maker_is_cheaper_than_taker() -> None:
    for price in (0.10, 0.25, 0.50, 0.75, 0.90):
        assert fee_per_contract(price, side="maker") <= fee_per_contract(price, side="taker")


def test_rejects_out_of_range_prices() -> None:
    with pytest.raises(ValueError):
        fee_per_contract(0.0)
    with pytest.raises(ValueError):
        fee_per_contract(1.0)
    with pytest.raises(ValueError):
        fee_per_contract(-0.1)


@given(
    price=st.floats(min_value=0.01, max_value=0.99, exclude_min=False, exclude_max=False),
    qty=st.integers(min_value=0, max_value=10_000),
)
def test_total_fee_nonneg(price: float, qty: int) -> None:
    fee = total_fee(price, qty, side="taker")
    assert fee >= 0
    assert math.isfinite(fee)


def test_zero_qty_zero_fee() -> None:
    assert total_fee(0.50, 0) == 0.0


def test_total_fee_exact_for_nonzero_qty() -> None:
    """Pin total_fee to exact values for NONZERO qty.

    Guards the `round(fee*qty, 4)` precision. Mutation testing showed the
    suite never asserted a nonzero-qty fee, so a regression to `round(x)`
    (whole-dollar) would silently zero out every sub-dollar fee and
    understate trading costs. These pin the per-contract cent.
    """
    # Taker at 50c = 0.02/contract → 10 contracts = 0.20.
    assert total_fee(0.50, 10, side="taker") == pytest.approx(0.20)
    # A single contract keeps its cent (round-to-int would zero it).
    assert total_fee(0.50, 1, side="taker") == pytest.approx(0.02)


# ----------------------------- edge cases (PR #5) -----------------------------


def test_fee_at_transition_prices_rounds_up() -> None:
    """Kalshi fee formula: ceil(0.07 * C * (1-C) * 100) / 100 — always rounds up.

    Near C = 0.18 the fee transitions from 1c to 2c; mirror at C = 0.82.
    These rounding-ceiling tests catch implementation drift if someone swaps
    `math.ceil` for `round` or `floor` in a future refactor.
    """
    assert fee_per_contract(0.17, side="taker") == pytest.approx(0.01)
    assert fee_per_contract(0.18, side="taker") == pytest.approx(0.02)
    assert fee_per_contract(0.82, side="taker") == pytest.approx(0.02)
    assert fee_per_contract(0.83, side="taker") == pytest.approx(0.01)


def test_total_fee_rejects_negative_qty() -> None:
    with pytest.raises(ValueError, match="qty"):
        total_fee(0.50, -1)


# -------------------- Kalshi schedule provenance pin --------------------
# These tests assert the EXACT values from Kalshi's published Feb 2026
# schedule. If the schedule changes, these tests will fail and force a
# coordinated update of the fee model + this pin per CLAUDE.md §9.
# Verified 2026-04-30 against pm.wiki + help.kalshi.com.


def test_taker_coefficient_pins_published_schedule() -> None:
    """Per Kalshi Feb 2026: taker fee = ceil(0.07 * C * (1-C) * 100) / 100."""
    assert TAKER_COEFFICIENT == 0.07


def test_maker_coefficient_is_25pct_of_taker() -> None:
    """Per Kalshi Feb 2026: maker fee = 25% of taker (4x discount, NOT 28x).

    The Pass 1 ext memo cited 0.0025/0.07 = 0.036 (a 28x discount). That figure
    does not match Kalshi's published schedule; the memo's '~25 bps savings'
    framing is a ceiling, not the current rate. Audit confirmed 2026-04-30.
    """
    assert MAKER_DISCOUNT == 0.25
    assert pytest.approx(0.0175) == MAKER_COEFFICIENT
    # Sanity: maker is exactly 1/4 of taker.
    assert pytest.approx(0.25) == MAKER_COEFFICIENT / TAKER_COEFFICIENT


def test_known_schedule_values_at_landmark_prices() -> None:
    """Known examples from the published schedule; pin to detect drift."""
    # Taker fee at 50¢: 0.07 * 0.25 = 0.0175 → ceil to 0.02.
    assert fee_per_contract(0.50, side="taker") == pytest.approx(0.02)
    # Maker fee at 50¢: 0.0175 * 0.25 = 0.0044 → ceil to 0.01.
    assert fee_per_contract(0.50, side="maker") == pytest.approx(0.01)
    # Taker at 10¢: 0.07 * 0.09 = 0.0063 → ceil to 0.01.
    assert fee_per_contract(0.10, side="taker") == pytest.approx(0.01)
    # Maker at 10¢: 0.0175 * 0.09 = 0.001575 → ceil to 0.01 (one-cent floor).
    assert fee_per_contract(0.10, side="maker") == pytest.approx(0.01)
