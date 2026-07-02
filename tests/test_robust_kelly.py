"""Tests for robust Kelly under model uncertainty."""

from __future__ import annotations

import pytest

from kq.execution import robust_kelly
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


# -------------------- docstring/implementation agreement (2026-07-01 audit)
# The module docstring's old "formal statement" (a p_worst = max(price,
# prob - q + 0.5*(1-q)) construction) was mathematically wrong: it neither
# recovered the point estimate at q = 0.5 nor described the multiplicative
# shrink the code performs. These pin the REWRITTEN statement to the
# implementation so doc and code cannot drift apart silently again.


def test_documented_multiplier_formula_matches_implementation() -> None:
    """f_robust = f_std * (1 - q) / (1 - q_pass) for q_pass < q <= 1 —
    the docstring's formal statement, checked value-for-value."""
    prob, price, q_pass = 0.7, 0.5, DEFAULT_Q_PASSTHROUGH
    f_std = kelly_fraction_yes(prob, price)
    for q in (0.55, 0.6, 0.75, 0.9, 0.99, 1.0):
        expected = f_std * (1.0 - q) / (1.0 - q_pass)
        actual = kelly_fraction_yes_robust(prob, price, conformal_threshold=q)
        assert actual == pytest.approx(expected), q


def test_module_docstring_states_the_implemented_formula() -> None:
    """The docstring must carry the real shrink formula and not the old
    wrong 'p_worst' worst-case construction."""
    doc = robust_kelly.__doc__ or ""
    assert "(1 - q) / (1 - q_pass)" in doc
    assert "p_worst" not in doc


# --------------------------- defaults pin ---------------------------


def test_defaults_pinned() -> None:
    assert DEFAULT_Q_PASSTHROUGH == 0.5
    assert DEFAULT_Q_FULL_SET == 1.0


# ------------------- default-arg + propagation pins (mutation-hardening) -------------
# Mutation testing (#28) showed the USD wrapper's §5 hard-cap defaults
# weren't pinned (every test passed them explicitly) and a custom
# q_passthrough wasn't asserted to flow through. These close that.


def test_robust_default_fraction_is_15pct() -> None:
    """Default 0.15x fraction must apply when omitted (§9 financial param).
    No conformal threshold → standard f*=0.20; $1000 * 0.15 * 0.20 = $30."""
    assert robust_fractional_kelly_stake(
        prob=0.60, price=0.50, bankroll_usd=1000.0
    ) == pytest.approx(30.0)


def test_robust_default_max_stake_is_200() -> None:
    """Default $200 hard cap must apply when omitted."""
    assert robust_fractional_kelly_stake(
        prob=0.99, price=0.10, bankroll_usd=1_000_000.0
    ) == pytest.approx(200.0)


def test_robust_stake_propagates_q_passthrough() -> None:
    """A custom `q_passthrough` must flow through the USD wrapper into the
    shrink. At q=0.6: passthrough 0.5 → shrink 0.8; passthrough 0.55 →
    shrink 0.889 → a larger stake. If the wrapper dropped the kwarg (using
    the default), both would be equal."""
    tight = robust_fractional_kelly_stake(
        prob=0.70, price=0.50, bankroll_usd=1000.0, conformal_threshold=0.60, q_passthrough=0.50
    )
    wide = robust_fractional_kelly_stake(
        prob=0.70, price=0.50, bankroll_usd=1000.0, conformal_threshold=0.60, q_passthrough=0.55
    )
    assert wide > tight
