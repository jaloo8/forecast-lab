"""Tests for fractional-Kelly sizing."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from kq.execution.kelly import fractional_kelly_stake, kelly_fraction_yes


def test_no_edge_means_zero_stake() -> None:
    assert kelly_fraction_yes(prob=0.50, price=0.50) == 0
    assert kelly_fraction_yes(prob=0.40, price=0.60) == 0
    assert fractional_kelly_stake(prob=0.50, price=0.50, bankroll_usd=1000.0) == 0.0


def test_edge_produces_positive_stake() -> None:
    # Full-Kelly for p=0.6 at c=0.5 is (0.6-0.5)/0.5 = 0.20
    assert kelly_fraction_yes(0.60, 0.50) == pytest.approx(0.20)
    # Fractional (0.15) on a $1000 bankroll = $1000 * 0.15 * 0.20 = $30
    assert fractional_kelly_stake(0.60, 0.50, 1000.0, fraction=0.15) == pytest.approx(30.0)


def test_hard_cap_enforced() -> None:
    # Even with huge bankroll and huge edge, the cap applies
    stake = fractional_kelly_stake(
        prob=0.99, price=0.10, bankroll_usd=1_000_000.0, fraction=0.15, max_stake_usd=200.0
    )
    assert stake == 200.0


def test_zero_bankroll_zero_stake() -> None:
    assert fractional_kelly_stake(0.60, 0.50, 0.0) == 0.0


@given(
    prob=st.floats(min_value=0.01, max_value=0.99),
    price=st.floats(min_value=0.01, max_value=0.99),
    bankroll=st.floats(min_value=0.0, max_value=1_000_000.0),
)
def test_stake_nonneg_and_bounded(prob: float, price: float, bankroll: float) -> None:
    stake = fractional_kelly_stake(prob, price, bankroll, max_stake_usd=500.0)
    assert 0.0 <= stake <= 500.0


def test_rejects_bad_probabilities() -> None:
    with pytest.raises(ValueError):
        kelly_fraction_yes(0.0, 0.50)
    with pytest.raises(ValueError):
        kelly_fraction_yes(0.50, 1.0)
