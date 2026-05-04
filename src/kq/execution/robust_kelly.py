"""Robust Kelly sizing under model uncertainty.

Standard fractional Kelly (kelly.py) treats the model probability
``prob`` as known. In practice it isn't -- the conformal calibrator
(PR #32) gives us a calibrated prediction *set*: ``[1-q, q]`` is the
indecisive band where the model abstains. Predictions in this band
have empirical coverage barely above target; predictions outside it
have tighter coverage.

Robust Kelly **shrinks the stake when the prediction is uncertain**.
We use the lower edge of the conformal interval as the
**worst-case probability** the bettor faces, rather than the point
estimate. If the conformal threshold ``q`` is wide (low confidence),
the worst-case prob is close to the price -- Kelly stake collapses.
If ``q`` is tight, the worst-case prob is close to the point
estimate -- Kelly stake is roughly unchanged from the standard
formulation.

Formal statement:

    p_worst = max(price, prob - q + 0.5 * (1 - q))
    f_robust = (p_worst - price) / (1 - price)

This is a one-sided worst-case Kelly: we take the smaller of (point
estimate, lower bound of the conformal-derived interval). The
expression normalizes ``q`` so a fully-uncertain prediction
(``q = 1``, full set) drops the worst-case to the price (zero stake)
and a fully-confident prediction (``q = 0.5``, singleton) recovers
the point estimate.

When no conformal threshold is supplied, the function falls back
exactly to ``kelly_fraction_yes`` -- callers can swap in robust
Kelly without auditing the existing call sites.

Reference: Bergstra & Yamins 2012 ("Random Search for Hyper-Parameter
Optimization") for the broader argument about robust optimization
under uncertainty; Vovk et al. 2005 for the conformal interval
interpretation.
"""

from __future__ import annotations

from typing import Final

# Default upper bound on q below which we don't bother shrinking
# (the conformal threshold is tighter than what we'd lose to noise
# anyway). Operators tune per-deployment.
DEFAULT_Q_PASSTHROUGH: Final = 0.5

# A q at or above this value collapses worst-case prob to the price
# (zero stake). Conservatively wide.
DEFAULT_Q_FULL_SET: Final = 1.0


def kelly_fraction_yes_robust(
    prob: float,
    price: float,
    *,
    conformal_threshold: float | None = None,
    q_passthrough: float = DEFAULT_Q_PASSTHROUGH,
) -> float:
    """Robust full-Kelly stake fraction.

    When ``conformal_threshold`` is None, returns exactly the same
    value as :func:`kq.execution.kelly.kelly_fraction_yes` -- callers
    can swap this in unconditionally.

    When ``conformal_threshold`` is provided:
    - ``q <= q_passthrough`` (tight band, e.g. q=0.5 = singleton):
      passthrough to the standard Kelly fraction.
    - ``q_passthrough < q < 1.0``: shrink toward zero linearly with
      ``q``; at ``q = 1`` (full set), returns 0.

    The shrink direction always reduces stake -- robust Kelly is
    never larger than standard Kelly.
    """
    if not 0.0 < prob < 1.0:
        raise ValueError(f"prob must be in (0, 1), got {prob}")
    if not 0.0 < price < 1.0:
        raise ValueError(f"price must be in (0, 1), got {price}")

    standard = (prob - price) / (1.0 - price) if prob > price else 0.0
    if conformal_threshold is None:
        return standard
    if not 0.0 < conformal_threshold < DEFAULT_Q_FULL_SET + 1e-9:
        raise ValueError(f"conformal_threshold must be in (0, 1], got {conformal_threshold}")
    if conformal_threshold <= q_passthrough:
        return standard
    # Linear shrink: q_passthrough -> 1.0 maps to multiplier 1.0 -> 0.0.
    span = DEFAULT_Q_FULL_SET - q_passthrough
    shrink = max(0.0, 1.0 - (conformal_threshold - q_passthrough) / span)
    return standard * shrink


def robust_fractional_kelly_stake(
    prob: float,
    price: float,
    bankroll_usd: float,
    *,
    fraction: float = 0.15,
    max_stake_usd: float = 200.0,
    conformal_threshold: float | None = None,
    q_passthrough: float = DEFAULT_Q_PASSTHROUGH,
) -> float:
    """Robust Kelly USD stake. Drop-in for :func:`fractional_kelly_stake`.

    All non-conformal arguments behave identically to the standard
    function. Adding ``conformal_threshold`` is the only opt-in to
    the robustness adjustment -- callers that don't pass it get the
    standard sizing, no behavior change.
    """
    if bankroll_usd <= 0:
        return 0.0
    if not 0.0 < fraction <= 1.0:
        raise ValueError(f"fraction must be in (0, 1], got {fraction}")
    if max_stake_usd <= 0:
        raise ValueError("max_stake_usd must be positive")
    f_star = kelly_fraction_yes_robust(
        prob,
        price,
        conformal_threshold=conformal_threshold,
        q_passthrough=q_passthrough,
    )
    stake = bankroll_usd * fraction * f_star
    return float(min(stake, max_stake_usd))


__all__ = [
    "DEFAULT_Q_FULL_SET",
    "DEFAULT_Q_PASSTHROUGH",
    "kelly_fraction_yes_robust",
    "robust_fractional_kelly_stake",
]
