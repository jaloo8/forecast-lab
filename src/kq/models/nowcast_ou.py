"""Ornstein-Uhlenbeck nowcast extension.

Replaces the Brownian-sigma shrink in :mod:`kq.models.nowcast` with
mean-reversion to a per-station diurnal climatology target. The
Brownian shrink scales sigma by ``sqrt(fraction_day_remaining)``,
which over-states morning uncertainty resolution (sigma drops too
fast at 9am, when most of the day's heating hasn't happened) and
under-states evening (sigma drops too slow at 6pm, when the daily
peak is locked in).

OU substitution. The standard OU process

    dT/dt = theta * (mu_target(t) - T) + sigma_innov * dW

has the closed-form variance after time-step ``dt``:

    Var = (sigma_innov^2 / (2 * theta)) * (1 - exp(-2 * theta * dt))

We use a discrete one-step variant that maps cleanly onto our
"daily high prior" framing:

- ``theta`` -- mean-reversion rate (1/hours). Per Pass 1 ext memo
  #9, KMDW / KAUS profile suggests theta ~= 0.10-0.15 (relaxation
  half-life ~5-7 hours).
- ``mu_target`` -- station-day climatological max (the value the
  daily high reverts toward in the absence of new information).
  When None, reduces to the standard nowcast (mu_post = max(prior,
  obs)).
- ``hours_remaining`` -- how much of the day is left (in hours).
  Replaces the dimensionless ``fraction_day_remaining`` with a unit
  the OU formula needs.

For ``theta -> 0``, the OU result reduces to the Brownian case (no
mean reversion, sigma shrinks linearly). For ``theta -> infinity``,
sigma collapses to zero immediately (instant snap to mu_target).
The default theta comes from the Pass 1 memo's empirical fit at
KMDW; tune per station as data accumulates.

Per the memo, the OU correction is most useful at the bad-NGR
stations (KMDW / KAUS) during 10am-2pm local, where Brownian
underestimates the rate at which a cold morning suggests a cold day.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

# Default mean-reversion rate (1/hour). Drawn from the Pass 1
# extension memo's empirical fit at KMDW; conservative across stations.
# theta=0 reduces to the existing Brownian nowcast exactly.
DEFAULT_THETA_PER_HOUR: Final = 0.10

# Default innovation sigma (degrees-F per sqrt-hour). Compatible with
# the prior sigma in the existing nowcast at fraction_remaining=1.
# Operators tune per-station once enough data accumulates.
DEFAULT_SIGMA_INNOV_F: Final = 3.0

# Floor on returned posterior sigma so downstream Gaussian SF math
# stays numerically stable. Same as the existing nowcast's
# SIGMA_FRACTION_FLOOR pattern.
SIGMA_F_FLOOR: Final = 0.5


@dataclass(frozen=True, slots=True)
class OUParameters:
    """Tuning knobs for the OU posterior calculator."""

    theta_per_hour: float = DEFAULT_THETA_PER_HOUR
    sigma_innov_f: float = DEFAULT_SIGMA_INNOV_F


def ou_posterior(
    *,
    prior_mu_f: float,
    t_so_far_f: float | None,
    mu_target_f: float | None,
    hours_remaining: float,
    params: OUParameters | None = None,
) -> tuple[float, float]:
    """Return ``(posterior_mu_f, posterior_sigma_f)`` after an OU update.

    ``prior_mu_f`` is the model's ex-ante daily-high prediction
    (the calibrated NGR / raw point estimate). ``t_so_far_f`` is the
    highest METAR observation today (None when no obs yet). ``mu_target_f``
    is the climatological daily-max for this station and date (None
    falls back to the existing-nowcast behavior of mu_post = max(prior, obs)).
    ``hours_remaining`` is how many hours are left in the LST settlement
    day; 0 means the day is finished.

    Math:

        var_post = (sigma_innov^2 / (2 * theta)) * (1 - exp(-2 * theta * hours))
        mu_post  = obs_anchor + (target - obs_anchor) * (1 - exp(-theta * hours))

    where ``obs_anchor = max(prior_mu, t_so_far)`` -- we never let the
    posterior mean drop below an already-observed temperature (the
    daily MAX is a non-decreasing observation). ``target`` is
    ``mu_target_f`` when supplied, else ``obs_anchor`` (no mean
    reversion).
    """
    if hours_remaining < 0:
        raise ValueError(f"hours_remaining must be >= 0, got {hours_remaining}")
    p = params or OUParameters()
    if p.theta_per_hour < 0:
        raise ValueError(f"theta_per_hour must be >= 0, got {p.theta_per_hour}")
    if p.sigma_innov_f <= 0:
        raise ValueError(f"sigma_innov_f must be > 0, got {p.sigma_innov_f}")

    obs_anchor = max(prior_mu_f, t_so_far_f) if t_so_far_f is not None else prior_mu_f
    target = mu_target_f if mu_target_f is not None else obs_anchor

    if hours_remaining <= 0.0:
        # Day is finished. Posterior collapses to the higher of
        # (prior, observed). Sigma collapses to floor.
        return obs_anchor, SIGMA_F_FLOOR

    if p.theta_per_hour == 0.0:
        # Brownian limit: var = sigma^2 * dt; mu reverts not at all.
        var_post = p.sigma_innov_f**2 * hours_remaining
        mu_post = obs_anchor
    else:
        decay = math.exp(-2.0 * p.theta_per_hour * hours_remaining)
        var_post = (p.sigma_innov_f**2 / (2.0 * p.theta_per_hour)) * (1.0 - decay)
        # Mu mean-reverts toward target proportionally to (1 - exp(-theta*dt)).
        rev = 1.0 - math.exp(-p.theta_per_hour * hours_remaining)
        mu_post = obs_anchor + (target - obs_anchor) * rev

    # Daily MAX is non-decreasing -- the posterior mean can never sit
    # below an already-observed temperature. When mean-reversion pulls
    # toward a lower climatological target, this cap kicks in.
    mu_post = max(mu_post, obs_anchor)

    sigma_post = max(SIGMA_F_FLOOR, math.sqrt(var_post))
    return mu_post, sigma_post


def hours_remaining_from_fraction(
    fraction_day_remaining: float,
    *,
    settlement_day_hours: float = 24.0,
) -> float:
    """Convert the existing-nowcast ``fraction_day_remaining`` to OU
    units. Bridge for callers that already compute fraction (built by
    :func:`kq.models.nowcast.compute_nowcast_state`)."""
    if not 0.0 <= fraction_day_remaining <= 1.0:
        raise ValueError(f"fraction_day_remaining must be in [0, 1], got {fraction_day_remaining}")
    if settlement_day_hours <= 0:
        raise ValueError(f"settlement_day_hours must be > 0, got {settlement_day_hours}")
    return fraction_day_remaining * settlement_day_hours


__all__ = [
    "DEFAULT_SIGMA_INNOV_F",
    "DEFAULT_THETA_PER_HOUR",
    "SIGMA_F_FLOOR",
    "OUParameters",
    "hours_remaining_from_fraction",
    "ou_posterior",
]
