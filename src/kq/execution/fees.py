"""Kalshi fee model.

Source: Kalshi's published fee schedule, last verified 2026-04-30 against
two independent third-party citations (pm.wiki, kalshi-help-center). Both
confirm the Feb 2026 schedule:

    Taker fee per contract = ceil(0.07 * C * (1 - C) * 100) / 100
    Maker fee per contract = ceil(0.0175 * C * (1 - C) * 100) / 100

Where ``C`` is the execution price in dollars in (0, 1). ``Maker = 25% of
taker`` is the relationship — i.e., a 4x discount. Round-trip at C = 0.50
works out to 3.5% of notional per side (taker) or 0.875% (maker). At
extremes (0.10 / 0.90), the fee falls to ~0.6¢ (taker) / ~0.16¢ (maker)
per contract.

**Audit note (2026-04-30):** the Pass 1 extension memo (see
docs/research/PASS-1-EXTENSION-EMOS-EXECUTION.md) cited a maker rate of
``0.0025 * C * (1 - C)`` (a 28x discount, ~3.6% of taker) for the bonus
paragraph on maker/taker discipline. That figure does NOT match Kalshi's
published Feb 2026 schedule (25% / 4x discount); the memo's expected
savings of "~25 bps per round-trip" should be read as a ceiling for what
the strategy *could* save, not the current schedule. PR #17's maker/taker
integration uses the correct 25% rate; PR #20 (this commit) adds the
citation pin AND fixes a previously-unnoticed maker-rounding bug (the
old code applied the 25% discount to the already-rounded taker fee
instead of rounding up per side independently — off by half a cent at
50¢, which inflated reported maker savings).
"""

from __future__ import annotations

import math
from typing import Final, Literal

Side = Literal["taker", "maker"]

# Maker fee is 25% of taker fee per Kalshi's Feb 2026 schedule (verified
# 2026-04-30; see module docstring for citations + audit note). Changing
# this constant is a financial-parameter modification per CLAUDE.md §9
# and requires explicit user signoff — re-verify the live schedule before
# any change.
MAKER_DISCOUNT: Final[float] = 0.25
TAKER_COEFFICIENT: Final[float] = 0.07
MAKER_COEFFICIENT: Final[float] = TAKER_COEFFICIENT * MAKER_DISCOUNT  # 0.0175


def fee_per_contract(price_usd: float, *, side: Side = "taker") -> float:
    """Return the Kalshi fee in dollars for a single contract at ``price_usd``.

    Per Kalshi's published Feb 2026 schedule, the per-side formula is:

        fee = ceil(coefficient * price * (1 - price) * 100) / 100

    where ``coefficient = 0.07`` for taker and ``0.0175`` (= 25% of taker)
    for maker. **Critically, both sides round up to the nearest cent
    independently** — applying ``MAKER_DISCOUNT`` to the already-rounded
    taker fee gives the wrong answer (off by half a cent at C=0.50, which
    inflates reported "maker savings" in any cost calculation).

    Example: at C=0.50, taker pays 1.75¢ → ceil to 2¢; maker pays 0.4375¢ →
    ceil to 1¢. Maker is half-priced before rounding but ROUNDS UP to a
    full cent (the Kalshi minimum), so the realized discount is 50% not 75%.

    ``price_usd`` must be in (0, 1).
    """
    if not 0.0 < price_usd < 1.0:
        raise ValueError(f"price must be in (0, 1), got {price_usd}")
    coefficient = MAKER_COEFFICIENT if side == "maker" else TAKER_COEFFICIENT
    return math.ceil(coefficient * price_usd * (1.0 - price_usd) * 100.0) / 100.0


def total_fee(price_usd: float, qty: int, *, side: Side = "taker") -> float:
    """Total fee in dollars for `qty` contracts at `price_usd`."""
    if qty < 0:
        raise ValueError("qty must be non-negative")
    return round(fee_per_contract(price_usd, side=side) * qty, 4)
