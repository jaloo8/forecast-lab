"""Tests for fractional-Kelly sizing."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from kq.config import Settings
from kq.execution import kelly as kelly_mod
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


# -------------------- fee-aware Kelly edge (2026-07-01 audit) --------------------
# The stake was computed from fee-free odds while the edge gate was
# fee-aware — a one-directional over-size. The fee now reduces the Kelly
# edge (b and p unchanged): f* = (p - c - fee) / (1 - c).


def test_fee_reduces_kelly_fraction_exactly() -> None:
    """f*(0.70, 0.55, fee=0.02) = (0.70 - 0.55 - 0.02) / 0.45."""
    assert kelly_fraction_yes(0.70, 0.55, fee_per_contract_usd=0.02) == pytest.approx(0.13 / 0.45)
    # Zero fee reproduces the fee-free formula bit-for-bit.
    assert kelly_fraction_yes(0.70, 0.55, fee_per_contract_usd=0.0) == kelly_fraction_yes(
        0.70, 0.55
    )


def test_fee_at_or_above_edge_zeroes_the_stake() -> None:
    """Fee equal to (binary-exact values) or above the edge → zero stake."""
    assert kelly_fraction_yes(0.75, 0.50, fee_per_contract_usd=0.25) == 0.0
    assert kelly_fraction_yes(0.55, 0.50, fee_per_contract_usd=0.08) == 0.0


def test_negative_fee_rejected() -> None:
    with pytest.raises(ValueError, match="fee_per_contract_usd"):
        kelly_fraction_yes(0.60, 0.50, fee_per_contract_usd=-0.01)


@given(
    prob=st.floats(min_value=0.01, max_value=0.99),
    price=st.floats(min_value=0.01, max_value=0.99),
    fee=st.floats(min_value=0.0001, max_value=0.05),
)
def test_positive_fee_strictly_reduces_fraction_never_increases(
    prob: float, price: float, fee: float
) -> None:
    """Property: fee > 0 never increases the Kelly fraction, and strictly
    reduces it whenever the fee-free fraction was positive."""
    fee_free = kelly_fraction_yes(prob, price)
    fee_aware = kelly_fraction_yes(prob, price, fee_per_contract_usd=fee)
    assert fee_aware <= fee_free
    if fee_free > 0.0:
        assert fee_aware < fee_free


@given(
    prob=st.floats(min_value=0.01, max_value=0.99),
    price=st.floats(min_value=0.01, max_value=0.99),
    fee=st.floats(min_value=0.0001, max_value=0.05),
    bankroll=st.floats(min_value=0.0, max_value=1_000_000.0),
)
def test_positive_fee_never_increases_stake(
    prob: float, price: float, fee: float, bankroll: float
) -> None:
    """Property: at the USD level the fee-aware stake never exceeds the
    fee-free stake (they can tie at 0 or when both hit the position cap)."""
    fee_free = fractional_kelly_stake(prob, price, bankroll)
    fee_aware = fractional_kelly_stake(prob, price, bankroll, fee_per_contract_usd=fee)
    assert fee_aware <= fee_free


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


def test_fraction_one_is_accepted_but_clamped_to_hard_cap() -> None:
    """`fraction == 1.0` passes the (0, 1] domain guard (not an error) but is
    CLAMPED to the 0.15x hard cap (CLAUDE.md §5 #7 — a hard limit, not a
    default). f*(p=0.6,c=0.5)=0.20 → $100 * 0.15 * 0.20 = $3."""
    assert fractional_kelly_stake(0.60, 0.50, 100.0, fraction=1.0) == pytest.approx(3.0)


def test_default_fraction_is_the_15pct_hard_cap() -> None:
    """Pin the §5 default 0.15x Kelly fraction (a §9 financial parameter).
    Calling WITHOUT `fraction` must apply 0.15: $1000 * 0.15 * 0.20 = $30."""
    assert fractional_kelly_stake(0.60, 0.50, 1000.0) == pytest.approx(30.0)


def test_default_max_stake_is_200() -> None:
    """Pin the §5 default $200 hard per-trade cap. Calling WITHOUT
    `max_stake_usd`, a huge edge + bankroll must cap at exactly 200."""
    assert fractional_kelly_stake(0.99, 0.10, 1_000_000.0) == pytest.approx(200.0)


# -------------------- hard-cap CLAMPS (2026-06-11 audit / PR-G) --------------------
# CLAUDE.md §5 #7 says "0.15x Kelly caps coded as hard limits" and
# docs/BANKROLL-PLAN.md claims the executor refuses to size past the caps.
# These pin that the caps are enforced clamps at the single sizing choke
# point, not merely defaults a caller can override.


def _pin_position_cap(monkeypatch: pytest.MonkeyPatch, cap_usd: float) -> None:
    """Pin the KQ_MAX_POSITION_USD setting seen by the kelly module,
    hermetically (no dependence on the machine's real `.env`)."""
    s = Settings(_env_file=None, kq_max_position_usd=cap_usd)  # type: ignore[call-arg]
    monkeypatch.setattr(kelly_mod, "get_settings", lambda: s)


def test_oversized_fraction_clamps_to_015_not_honored() -> None:
    """kelly_fraction=0.5 must size IDENTICALLY to 0.15 — clamped with a
    warning, not honored and not an error."""
    at_cap = fractional_kelly_stake(0.60, 0.50, 1000.0, fraction=0.15)
    oversized = fractional_kelly_stake(0.60, 0.50, 1000.0, fraction=0.5)
    assert oversized == at_cap == pytest.approx(30.0)


def test_oversized_max_stake_clamps_to_position_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """A caller-supplied max_stake_usd above the per-position cap is clamped
    down to it — the stake can never exceed $200."""
    _pin_position_cap(monkeypatch, 200.0)
    stake = fractional_kelly_stake(0.99, 0.10, 100_000_000.0, max_stake_usd=5_000.0)
    assert stake == pytest.approx(200.0)


def test_settings_position_cap_tightens_the_clamp(monkeypatch: pytest.MonkeyPatch) -> None:
    """KQ_MAX_POSITION_USD below $200 tightens the effective cap."""
    _pin_position_cap(monkeypatch, 100.0)
    stake = fractional_kelly_stake(0.99, 0.10, 100_000_000.0, max_stake_usd=5_000.0)
    assert stake == pytest.approx(100.0)


def test_settings_position_cap_cannot_raise_past_200(monkeypatch: pytest.MonkeyPatch) -> None:
    """KQ_MAX_POSITION_USD above $200 does NOT loosen the documented ceiling."""
    _pin_position_cap(monkeypatch, 500.0)
    stake = fractional_kelly_stake(0.99, 0.10, 100_000_000.0, max_stake_usd=5_000.0)
    assert stake == pytest.approx(200.0)


def test_caller_can_still_tighten_below_the_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    """Values below the hard caps are honored unchanged (tighten-only clamp)."""
    _pin_position_cap(monkeypatch, 200.0)
    assert fractional_kelly_stake(0.60, 0.50, 1000.0, fraction=0.05) == pytest.approx(10.0)
    assert fractional_kelly_stake(0.99, 0.10, 1_000_000.0, max_stake_usd=25.0) == pytest.approx(
        25.0
    )
