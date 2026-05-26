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


# ----------------------------- edge cases (PR #5) -----------------------------


def test_invalid_fraction_rejected() -> None:
    """`fraction` must be in (0, 1] — full Kelly allowed but not zero or >1."""
    with pytest.raises(ValueError, match="fraction"):
        fractional_kelly_stake(0.60, 0.50, 1000.0, fraction=0.0)
    with pytest.raises(ValueError, match="fraction"):
        fractional_kelly_stake(0.60, 0.50, 1000.0, fraction=1.5)
    with pytest.raises(ValueError, match="fraction"):
        fractional_kelly_stake(0.60, 0.50, 1000.0, fraction=-0.1)


def test_invalid_max_stake_rejected() -> None:
    with pytest.raises(ValueError, match="max_stake_usd"):
        fractional_kelly_stake(0.60, 0.50, 1000.0, max_stake_usd=0)
    with pytest.raises(ValueError, match="max_stake_usd"):
        fractional_kelly_stake(0.60, 0.50, 1000.0, max_stake_usd=-10.0)


# -------------------- boundary + default pins (mutation-hardening) --------------------
# Mutation testing (mutmut, #28) surfaced that the open-interval guards
# weren't tested at their boundaries and the §5 hard-cap defaults weren't
# pinned — a default change would mutate freely. These close that.


def test_kelly_fraction_yes_rejects_interval_boundaries() -> None:
    """`prob` and `price` live in the OPEN interval (0, 1). Pin that the
    boundaries (0.0, 1.0) and out-of-range (>1) all raise — not just the
    one-sided cases the original tests covered."""
    for bad_prob in (1.0, 1.5, 0.0):
        with pytest.raises(ValueError, match="prob"):
            kelly_fraction_yes(bad_prob, 0.50)
    for bad_price in (1.0, 1.5, 0.0):
        with pytest.raises(ValueError, match="price"):
            kelly_fraction_yes(0.50, bad_price)


def test_fraction_one_is_full_kelly_accepted() -> None:
    """`fraction == 1.0` is the CLOSED upper bound (full Kelly) — must be
    accepted, not rejected. f*(p=0.6,c=0.5)=0.20 → $100 * 1.0 * 0.20 = $20."""
    assert fractional_kelly_stake(0.60, 0.50, 100.0, fraction=1.0) == pytest.approx(20.0)


def test_default_fraction_is_the_15pct_hard_cap() -> None:
    """Pin the §5 default 0.15x Kelly fraction (a §9 financial parameter).
    Calling WITHOUT `fraction` must apply 0.15: $1000 * 0.15 * 0.20 = $30."""
    assert fractional_kelly_stake(0.60, 0.50, 1000.0) == pytest.approx(30.0)


def test_default_max_stake_is_200() -> None:
    """Pin the §5 default $200 hard per-trade cap. Calling WITHOUT
    `max_stake_usd`, a huge edge + bankroll must cap at exactly 200."""
    assert fractional_kelly_stake(0.99, 0.10, 1_000_000.0) == pytest.approx(200.0)
