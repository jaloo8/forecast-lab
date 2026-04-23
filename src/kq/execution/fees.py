"""Kalshi fee model.

Source: https://kalshi.com/fee-schedule and mirrored analyses in the Pass 1 research.

Taker fee per contract: ceil(0.07 * C * (1 - C) * N * 100) / 100
  where C = execution price in dollars (0 < C < 1), N = contracts.
Maker fee is ~25% of the taker fee.

Round-trip at C = 0.50 works out to 3.5% of notional per side. At extremes
(0.10 / 0.90), the fee falls to ~1 cent per contract.
"""

from __future__ import annotations

import math
from typing import Literal

Side = Literal["taker", "maker"]

MAKER_DISCOUNT: float = 0.25  # maker pays 25% of taker fee (per Kalshi schedule analyses)


def fee_per_contract(price_usd: float, *, side: Side = "taker") -> float:
    """Return the Kalshi fee in dollars for a single contract at `price_usd`.

    `price_usd` must be in (0, 1). A market order at $0.50 pays $0.0175 (taker).
    """
    if not 0.0 < price_usd < 1.0:
        raise ValueError(f"price must be in (0, 1), got {price_usd}")
    base = math.ceil(0.07 * price_usd * (1.0 - price_usd) * 100.0) / 100.0
    if side == "maker":
        return round(base * MAKER_DISCOUNT, 4)
    return base


def total_fee(price_usd: float, qty: int, *, side: Side = "taker") -> float:
    """Total fee in dollars for `qty` contracts at `price_usd`."""
    if qty < 0:
        raise ValueError("qty must be non-negative")
    return round(fee_per_contract(price_usd, side=side) * qty, 4)
