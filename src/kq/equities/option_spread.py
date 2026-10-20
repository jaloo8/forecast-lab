"""Offline one-contract quote arithmetic; no broker, signal or performance API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import isclose, isfinite
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class CallQuote:
    symbol: str
    expiry: date
    strike: float
    as_of: datetime
    bid: float
    ask: float
    bid_size: int
    ask_size: int
    multiplier: int = 100

    def validate(self, at: datetime) -> None:
        if at.utcoffset() is None or self.as_of.utcoffset() is None:
            raise ValueError("Timezone-aware evidence required")
        age = (at - self.as_of).total_seconds()
        if not 0 <= age <= 5:
            raise ValueError("Stale or future quote")
        if (
            self.symbol != "SPY"
            or self.multiplier != 100
            or not all(isfinite(x) and x > 0 for x in (self.strike, self.bid, self.ask))
            or self.bid > self.ask
            or any(type(x) is not int or x < 1 for x in (self.bid_size, self.ask_size))
        ):
            raise ValueError("Invalid standard contract or executable quote")


def spread_cashflow(
    long: CallQuote,
    short: CallQuote,
    at: datetime,
    *,
    entering: bool,
    signal_at: datetime | None = None,
    cash_limit: float = 100,
) -> float:
    """Signed cash for one $1-wide SPY call spread, at observed bid/ask plus costs.

    Prices are per share; cash is dollars. Synthetic quotes test arithmetic only.
    The caller must retain contract identity and unresolved exits across a trade.
    """
    long.validate(at)
    short.validate(at)
    if abs((long.as_of - short.as_of).total_seconds()) > 1:
        raise ValueError("Unsynchronized legs")
    if long.expiry != short.expiry or not isclose(short.strike - long.strike, 1):
        raise ValueError("Mismatched expiration or spread width")
    if long.expiry != at.astimezone(ZoneInfo("America/New_York")).date() + timedelta(days=1):
        raise ValueError("Not the candidate's one-calendar-day expiration")
    if not entering:
        return 100 * (long.bid - short.ask - 0.02) - 1.30
    if (
        signal_at is None
        or signal_at.utcoffset() is None
        or min(long.as_of, short.as_of) <= signal_at
    ):
        raise ValueError("Entry must use quotes after the completed signal")
    debit = long.ask - short.bid + 0.02
    if not 0 < debit < 1:
        raise ValueError("Invalid executable debit")
    cost = 100 * debit + 1.30
    if not isfinite(cash_limit) or cost + 1.30 > min(cash_limit, 100):
        raise ValueError("Debit and exit reserve exceed research cash limit")
    return -cost
