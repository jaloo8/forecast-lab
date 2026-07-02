"""Fractional Kelly sizing for binary Kalshi contracts.

Full Kelly for a YES contract priced at `c` with true probability `p`:

    f* = (p - c) / (1 - c)   if p > c else 0

Fractional Kelly multiplies by a fraction (default 0.15). Per CLAUDE.md §5 #7
("0.15x Kelly caps coded as hard limits") and docs/BANKROLL-PLAN.md, the
0.15x fraction and the $200 per-position stake are ENFORCED CLAMPS, not
defaults: a caller passing a larger `fraction` or `max_stake_usd` is clamped
back to the cap (with a structlog warning), never honored. Every sizing path
— backtest engine, weather + NBA paper executors, future live executor —
flows through :func:`fractional_kelly_stake`, making this the single
enforcement point. Changing the caps requires editing this source (§9).
"""

from __future__ import annotations

from typing import Final

import structlog

from kq.config import get_settings

log = structlog.get_logger(__name__)

# CLAUDE.md §5 #7 hard limits. KQ_MAX_POSITION_USD may tighten the position
# cap below $200 but can never raise it past the documented ceiling.
HARD_KELLY_FRACTION_CAP: Final = 0.15
HARD_POSITION_CAP_USD: Final = 200.0


def kelly_fraction_yes(prob: float, price: float) -> float:
    """Full-Kelly stake fraction for buying YES. Returns 0 if no edge."""
    if not 0.0 < prob < 1.0:
        raise ValueError(f"prob must be in (0, 1), got {prob}")
    if not 0.0 < price < 1.0:
        raise ValueError(f"price must be in (0, 1), got {price}")
    if prob <= price:
        return 0.0
    return (prob - price) / (1.0 - price)


def _position_cap_usd() -> float:
    """Effective per-position cap: min(documented $200, KQ_MAX_POSITION_USD)."""
    return min(HARD_POSITION_CAP_USD, get_settings().kq_max_position_usd)


def fractional_kelly_stake(
    prob: float,
    price: float,
    bankroll_usd: float,
    *,
    fraction: float = HARD_KELLY_FRACTION_CAP,
    max_stake_usd: float = HARD_POSITION_CAP_USD,
) -> float:
    """Return the USD stake to put on YES, applying fractional-Kelly and hard caps.

    `fraction` and `max_stake_usd` can only TIGHTEN the hard caps: values
    above 0.15x Kelly or the per-position USD cap are clamped down with a
    warning, not honored (and not an error — the trade still sizes, at the
    cap). Out-of-domain values still raise.
    """
    if bankroll_usd <= 0:
        return 0.0
    if not 0.0 < fraction <= 1.0:
        raise ValueError(f"fraction must be in (0, 1], got {fraction}")
    if max_stake_usd <= 0:
        raise ValueError("max_stake_usd must be positive")
    if fraction > HARD_KELLY_FRACTION_CAP:
        log.warning(
            "kelly.fraction_clamped",
            requested=fraction,
            clamped_to=HARD_KELLY_FRACTION_CAP,
        )
        fraction = HARD_KELLY_FRACTION_CAP
    position_cap = _position_cap_usd()
    if max_stake_usd > position_cap:
        log.warning(
            "kelly.max_stake_clamped",
            requested=max_stake_usd,
            clamped_to=position_cap,
        )
        max_stake_usd = position_cap
    f_star = kelly_fraction_yes(prob, price)
    stake = bankroll_usd * fraction * f_star
    return float(min(stake, max_stake_usd))
