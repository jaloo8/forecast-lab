"""Domain types for Kalshi markets and order books."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Market:
    """One Kalshi market (an individual YES/NO contract).

    Prices are *dollars* (0..1) throughout this package. Kalshi's wire format
    uses integer cents; conversion happens in parsers.
    """

    ticker: str
    event_ticker: str
    title: str
    status: str  # 'active' | 'closed' | 'settled' | ...
    category: str | None
    yes_ask: float | None
    yes_bid: float | None
    last_price: float | None
    volume: float | None
    open_interest: float | None
    open_time: datetime | None
    close_time: datetime | None
    expected_expiration_time: datetime | None
    rules_primary: str | None  # resolution-source-ish text


@dataclass(frozen=True, slots=True)
class OrderBookSnapshot:
    """Point-in-time order book for a single market.

    YES ladders are normalized: `yes_asks` always contains YES-ask prices
    (not Kalshi's raw `no` side) so downstream code doesn't have to juggle
    the 100 - price conversion.
    """

    snap_time: datetime
    ticker: str
    yes_bid: float | None
    yes_ask: float | None
    yes_bid_size: int | None
    yes_ask_size: int | None
    yes_bids: tuple[tuple[int, int], ...]  # (price_cents, size), best-first
    yes_asks: tuple[tuple[int, int], ...]
