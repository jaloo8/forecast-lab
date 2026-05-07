"""Tests for robust Kelly under model uncertainty."""

from __future__ import annotations

import pytest

from kq.execution.kelly import fractional_kelly_stake, kelly_fraction_yes
from kq.execution.robust_kelly import (
    DEFAULT_Q_FULL_SET,
    DEFAULT_Q_PASSTHROUGH,
    kelly_fraction_yes_robust,
    robust_fractional_kelly_stake,
)

# --------------------------- passthrough behavior ---------------------------


def test_passthrough_when_conformal_threshold_none() -> None:
    """No conformal threshold -> identical to the standard formula."""
    standard = kelly_fraction_yes(prob=0.7, price=0.5)
    robust = kelly_fraction_yes_robust(prob=0.7, price=0.5, conformal_threshold=None)
    assert robust == pytest.approx(standard)


def test_passthrough_when_q_below_threshold() -> None:
    """q <= q_passthrough -> no shrink."""
    standard = kelly_fraction_yes(prob=0.7, price=0.5)
    robust = kelly_fraction_yes_robust(
        prob=0.7, price=0.5, conformal_threshold=DEFAULT_Q_PASSTHROUGH
    )
    assert robust == pytest.approx(standard)


def test_robust_kelly_never_exceeds_standard() -> None:
    """Robustness adjustment is one-sided -- stake never grows."""
    for q in (0.55, 0.7, 0.85, 0.95, 0.999):
        standard = kelly_fraction_yes(prob=0.7, price=0.5)
        robust = kelly_fraction_yes_robust(prob=0.7, price=0.5, conformal_threshold=q)
        assert robust <= standard + 1e-9


# --------------------------- shrink behavior ---------------------------


def test_full_set_q_collapses_stake_to_zero() -> None:
    """q at the full-set bound (1.0) should fully shrink to 0."""
    robust = kelly_fraction_yes_robust(prob=0.7, price=0.5, conformal_threshold=DEFAULT_Q_FULL_SET)
    assert robust == pytest.approx(0.0)


def test_intermediate_q_shrinks_linearly() -> None:
    """q halfway between passthrough (0.5) and full set (1.0) -> 0.5x stake."""
    standard = kelly_fraction_yes(prob=0.7, price=0.5)
    robust = kelly_fraction_yes_robust(prob=0.7, price=0.5, conformal_threshold=0.75)
    assert robust == pytest.approx(0.5 * standard, abs=1e-3)


def test_robust_kelly_always_in_unit_interval() -> None:
    """Robust Kelly should never go negative or > 1."""
    for q in (None, 0.1, 0.5, 0.7, 0.9, 1.0):
        for p in (0.51, 0.6, 0.7, 0.9):
            for c in (0.01, 0.5, 0.9):
                if c >= p:
                    continue
                f = kelly_fraction_yes_robust(prob=p, price=c, conformal_threshold=q)
                assert 0.0 <= f <= 1.0


# --------------------------- input validation ---------------------------


def test_invalid_prob_raises() -> None:
    with pytest.raises(ValueError, match=r"prob must be in"):
        kelly_fraction_yes_robust(prob=0.0, price=0.5)
    with pytest.raises(ValueError, match=r"prob must be in"):
        kelly_fraction_yes_robust(prob=1.0, price=0.5)


def test_invalid_price_raises() -> None:
    with pytest.raises(ValueError, match=r"price must be in"):
        kelly_fraction_yes_robust(prob=0.5, price=0.0)
    with pytest.raises(ValueError, match=r"price must be in"):
        kelly_fraction_yes_robust(prob=0.5, price=1.0)


def test_invalid_conformal_threshold_raises() -> None:
    with pytest.raises(ValueError, match=r"conformal_threshold"):
        kelly_fraction_yes_robust(prob=0.7, price=0.5, conformal_threshold=0.0)
    with pytest.raises(ValueError, match=r"conformal_threshold"):
        kelly_fraction_yes_robust(prob=0.7, price=0.5, conformal_threshold=1.5)


# --------------------------- USD-stake wrapper ---------------------------


def test_robust_stake_falls_back_to_standard_without_threshold() -> None:
    """When no conformal_threshold, the USD stake matches standard fractional Kelly."""
    standard = fractional_kelly_stake(
        prob=0.7, price=0.5, bankroll_usd=1000.0, fraction=0.15, max_stake_usd=200.0
    )
    robust = robust_fractional_kelly_stake(
        prob=0.7, price=0.5, bankroll_usd=1000.0, fraction=0.15, max_stake_usd=200.0
    )
    assert robust == pytest.approx(standard)


def test_robust_stake_shrinks_when_conformal_threshold_set() -> None:
    standard = robust_fractional_kelly_stake(
        prob=0.7, price=0.5, bankroll_usd=1000.0, conformal_threshold=None
    )
    shrunk = robust_fractional_kelly_stake(
        prob=0.7, price=0.5, bankroll_usd=1000.0, conformal_threshold=0.85
    )
    assert shrunk < standard


def test_robust_stake_zero_bankroll_returns_zero() -> None:
    """Zero bankroll path bypasses Kelly math entirely."""
    assert (
        robust_fractional_kelly_stake(
            prob=0.7, price=0.5, bankroll_usd=0.0, conformal_threshold=0.5
        )
        == 0.0
    )


def test_robust_stake_max_stake_caps_output() -> None:
    """A small max_stake_usd caps even when the Kelly fraction suggests more."""
    capped = robust_fractional_kelly_stake(
        prob=0.99,
        price=0.01,
        bankroll_usd=1_000_000.0,
        fraction=1.0,
        max_stake_usd=50.0,
    )
    assert capped == pytest.approx(50.0)


def test_robust_stake_invalid_fraction_raises() -> None:
    with pytest.raises(ValueError, match=r"fraction must be in"):
        robust_fractional_kelly_stake(prob=0.7, price=0.5, bankroll_usd=1000.0, fraction=0.0)


def test_robust_stake_invalid_max_stake_raises() -> None:
    with pytest.raises(ValueError, match=r"max_stake_usd"):
        robust_fractional_kelly_stake(prob=0.7, price=0.5, bankroll_usd=1000.0, max_stake_usd=0.0)


# --------------------------- defaults pin ---------------------------


def test_defaults_pinned() -> None:
    assert DEFAULT_Q_PASSTHROUGH == 0.5
    assert DEFAULT_Q_FULL_SET == 1.0
