"""Tests for the Kalshi fee model. Uses Hypothesis for property checks."""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from kq.execution.fees import fee_per_contract, total_fee


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
