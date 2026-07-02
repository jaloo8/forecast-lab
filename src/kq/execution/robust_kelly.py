"""Robust Kelly sizing under model uncertainty.

Standard fractional Kelly (kelly.py) treats the model probability
``prob`` as known. In practice it isn't -- the conformal calibrator
(PR #32) gives us a calibrated prediction *set*: ``[1-q, q]`` is the
indecisive band where the model abstains. Predictions in this band
have empirical coverage barely above target; predictions outside it
have tighter coverage.

Robust Kelly **shrinks the stake when the prediction is uncertain**:
the standard Kelly fraction is multiplied by a factor that decreases
linearly as the conformal threshold ``q`` widens. If ``q`` is wide
(low confidence), the multiplier approaches 0 -- the stake collapses.
If ``q`` is tight (at or below the passthrough bound), the multiplier
is 1 -- the stake is exactly the standard formulation.

Formal statement (this is what the implementation computes):

    f_std(p, c)       = max(0, (p - c) / (1 - c))
    f_robust(p, c, q) = f_std(p, c)                            if q <= q_pass
                      = f_std(p, c) * (1 - q) / (1 - q_pass)   if q_pass < q <= 1

with ``q_pass = 0.5`` by default (``q = 0.5`` is the singleton
prediction set; ``q = 1`` is the full set). Properties, all pinned
by tests:

- **Shrinkage under conformal width**: for ``q > q_pass`` the
  multiplier ``(1 - q) / (1 - q_pass)`` lies in ``[0, 1)`` and is
  strictly decreasing in ``q``; at ``q = 1`` (full set -- the model
  says nothing) the stake is exactly 0.
- **Never exceeds standard Kelly**: the multiplier is <= 1
  everywhere, so ``f_robust <= f_std`` for every input; the
  adjustment is one-sided.
- **Continuity at the passthrough bound**: the multiplier is 1 at
  ``q = q_pass``, so there is no jump when a prediction crosses it.
- **Passthrough on None**: when no conformal threshold is supplied,
  the function returns exactly ``kelly_fraction_yes`` -- callers can
  swap in robust Kelly without auditing the existing call sites.

Reference: Vovk et al. 2005 for the conformal-prediction-set
interpretation of ``q``.
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
