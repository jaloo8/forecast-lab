"""Fractional Kelly sizing for binary Kalshi contracts.

Full Kelly for a YES contract priced at `c` with true probability `p`:

    f* = (p - c) / (1 - c)   if p > c else 0

Fractional Kelly multiplies by a fraction (default 0.15). The executor must
*additionally* cap by a hard per-trade USD limit — Kelly alone is not a risk
control. See CLAUDE.md §5 for bankroll-level caps.
"""

from __future__ import annotations


def kelly_fraction_yes(prob: float, price: float) -> float:
    """Full-Kelly stake fraction for buying YES. Returns 0 if no edge."""
    if not 0.0 < prob < 1.0:
        raise ValueError(f"prob must be in (0, 1), got {prob}")
    if not 0.0 < price < 1.0:
        raise ValueError(f"price must be in (0, 1), got {price}")
    if prob <= price:
        return 0.0
    return (prob - price) / (1.0 - price)


def fractional_kelly_stake(
    prob: float,
    price: float,
    bankroll_usd: float,
    *,
    fraction: float = 0.15,
    max_stake_usd: float = 200.0,
) -> float:
    """Return the USD stake to put on YES, applying fractional-Kelly and a hard cap."""
    if bankroll_usd <= 0:
        return 0.0
    if not 0.0 < fraction <= 1.0:
        raise ValueError(f"fraction must be in (0, 1], got {fraction}")
    if max_stake_usd <= 0:
        raise ValueError("max_stake_usd must be positive")
    f_star = kelly_fraction_yes(prob, price)
    stake = bankroll_usd * fraction * f_star
    return float(min(stake, max_stake_usd))
