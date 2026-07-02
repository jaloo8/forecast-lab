"""Tests for the OU nowcast extension."""

from __future__ import annotations

import math

import pytest

from kq.models import nowcast_ou as nowcast_ou_module
from kq.models.nowcast_ou import (
    DEFAULT_SIGMA_INNOV_F,
    DEFAULT_THETA_PER_HOUR,
    SIGMA_F_FLOOR,
    OUParameters,
    hours_remaining_from_fraction,
    ou_posterior,
)

# --------------------------- module honesty ---------------------------


def test_module_docstring_declares_not_wired() -> None:
    """2026-07-01 audit (Tier 4): this module has zero production callers.

    Until an opt-in config flag wires `ou_posterior` through the paper-trade
    nowcast path, the module docstring must say so — presenting dead code as
    the operational replacement is exactly the mislabeling class the audit
    flagged. If you just wired it for real: delete this test AND rewrite the
    docstring's status header."""
    doc = nowcast_ou_module.__doc__ or ""
    assert "NOT WIRED" in doc
    assert "candidate" in doc.lower()


# --------------------------- ou_posterior ---------------------------


def test_zero_hours_remaining_returns_observed_anchor() -> None:
    """Day finished -> posterior_mu = max(prior, obs); sigma collapses."""
    mu, sigma = ou_posterior(
        prior_mu_f=70.0,
        t_so_far_f=72.5,
        mu_target_f=75.0,
        hours_remaining=0.0,
    )
    assert mu == pytest.approx(72.5)  # higher of (70, 72.5)
    assert sigma == pytest.approx(SIGMA_F_FLOOR)


def test_zero_hours_remaining_no_obs_returns_prior() -> None:
    mu, sigma = ou_posterior(
        prior_mu_f=70.0,
        t_so_far_f=None,
        mu_target_f=75.0,
        hours_remaining=0.0,
    )
    assert mu == pytest.approx(70.0)
    assert sigma == pytest.approx(SIGMA_F_FLOOR)


def test_brownian_limit_when_theta_zero() -> None:
    """theta=0 -> var = sigma^2 * dt; mu doesn't revert."""
    params = OUParameters(theta_per_hour=0.0, sigma_innov_f=3.0)
    mu, sigma = ou_posterior(
        prior_mu_f=70.0,
        t_so_far_f=None,
        mu_target_f=75.0,
        hours_remaining=4.0,
        params=params,
    )
    expected_var = 3.0**2 * 4.0
    assert sigma == pytest.approx(math.sqrt(expected_var))
    # No mean reversion at theta=0.
    assert mu == pytest.approx(70.0)


def test_mean_reverts_toward_target_when_theta_positive() -> None:
    """theta>0 -> posterior_mu lies between obs_anchor and target."""
    params = OUParameters(theta_per_hour=0.2, sigma_innov_f=3.0)
    mu, _ = ou_posterior(
        prior_mu_f=70.0,
        t_so_far_f=None,
        mu_target_f=80.0,
        hours_remaining=4.0,
        params=params,
    )
    assert 70.0 < mu < 80.0


def test_no_target_falls_back_to_obs_anchor() -> None:
    """mu_target=None -> mu_post = obs_anchor (no reversion target)."""
    params = OUParameters(theta_per_hour=0.2)
    mu, _ = ou_posterior(
        prior_mu_f=70.0,
        t_so_far_f=72.0,
        mu_target_f=None,
        hours_remaining=4.0,
        params=params,
    )
    assert mu == pytest.approx(72.0)


def test_obs_anchor_never_drops_below_observed() -> None:
    """Daily MAX is non-decreasing -- posterior_mu must be >= t_so_far."""
    params = OUParameters(theta_per_hour=0.2)
    mu, _ = ou_posterior(
        prior_mu_f=70.0,
        t_so_far_f=80.0,  # already higher than prior
        mu_target_f=65.0,  # mean-revert target is lower -- shouldn't pull mu below 80
        hours_remaining=10.0,
        params=params,
    )
    assert mu >= 80.0


def test_high_theta_collapses_sigma_fast() -> None:
    """At theta -> infinity, var_post -> sigma^2 / (2 theta) -- shrinks
    rapidly. Compared to a low-theta run with same params, sigma is smaller."""
    high_theta = OUParameters(theta_per_hour=2.0, sigma_innov_f=3.0)
    low_theta = OUParameters(theta_per_hour=0.05, sigma_innov_f=3.0)
    _, sigma_high = ou_posterior(
        prior_mu_f=70.0,
        t_so_far_f=None,
        mu_target_f=None,
        hours_remaining=4.0,
        params=high_theta,
    )
    _, sigma_low = ou_posterior(
        prior_mu_f=70.0,
        t_so_far_f=None,
        mu_target_f=None,
        hours_remaining=4.0,
        params=low_theta,
    )
    assert sigma_high < sigma_low


def test_sigma_never_below_floor() -> None:
    params = OUParameters(theta_per_hour=10.0, sigma_innov_f=0.5)
    _, sigma = ou_posterior(
        prior_mu_f=70.0,
        t_so_far_f=None,
        mu_target_f=None,
        hours_remaining=10.0,
        params=params,
    )
    assert sigma >= SIGMA_F_FLOOR


# --------------------------- input validation ---------------------------


def test_negative_hours_remaining_raises() -> None:
    with pytest.raises(ValueError, match=r"hours_remaining"):
        ou_posterior(
            prior_mu_f=70.0,
            t_so_far_f=None,
            mu_target_f=None,
            hours_remaining=-1.0,
        )


def test_negative_theta_raises() -> None:
    with pytest.raises(ValueError, match=r"theta_per_hour"):
        ou_posterior(
            prior_mu_f=70.0,
            t_so_far_f=None,
            mu_target_f=None,
            hours_remaining=1.0,
            params=OUParameters(theta_per_hour=-0.1),
        )


def test_zero_sigma_innov_raises() -> None:
    with pytest.raises(ValueError, match=r"sigma_innov_f"):
        ou_posterior(
            prior_mu_f=70.0,
            t_so_far_f=None,
            mu_target_f=None,
            hours_remaining=1.0,
            params=OUParameters(sigma_innov_f=0.0),
        )


# --------------------------- bridge helper ---------------------------


def test_hours_remaining_from_fraction_default_24h() -> None:
    assert hours_remaining_from_fraction(1.0) == pytest.approx(24.0)
    assert hours_remaining_from_fraction(0.5) == pytest.approx(12.0)
    assert hours_remaining_from_fraction(0.0) == pytest.approx(0.0)


def test_hours_remaining_from_fraction_custom_day_length() -> None:
    """Long winter days vs short summer days adjusted via override."""
    assert hours_remaining_from_fraction(0.5, settlement_day_hours=23.0) == pytest.approx(11.5)


def test_hours_remaining_from_fraction_validates_inputs() -> None:
    with pytest.raises(ValueError, match=r"fraction_day_remaining"):
        hours_remaining_from_fraction(1.5)
    with pytest.raises(ValueError, match=r"settlement_day_hours"):
        hours_remaining_from_fraction(0.5, settlement_day_hours=0.0)


# --------------------------- defaults pin ---------------------------


def test_defaults_pinned() -> None:
    """Pin defaults so changes are deliberate."""
    assert DEFAULT_THETA_PER_HOUR == 0.10
    assert DEFAULT_SIGMA_INNOV_F == 3.0
    assert SIGMA_F_FLOOR == 0.5
