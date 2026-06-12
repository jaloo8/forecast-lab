"""Domain types for Kalshi markets and order books."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Market:
    """One Kalshi market (an individual YES/NO contract).

    Prices are *dollars* (0..1) throughout this package. Kalshi's prod wire
    format serves dollar-strings (``yes_bid_dollars: "0.0500"``); the legacy /
    demo format served integer cents (``yes_bid: 5``). Conversion happens in
    parsers — both formats are accepted, prod-style preferred.

    ``strike_type`` + ``floor_strike`` / ``cap_strike`` carry the contract's
    resolution semantics straight from the API (verified against prod
    2026-06-11):

    * ``"greater"`` — YES iff value > ``floor_strike`` (``-T79`` = "80° or above")
    * ``"less"``    — YES iff value < ``cap_strike``   (``-T72`` = "71° or below")
    * ``"between"`` — YES iff ``floor_strike`` <= value <= ``cap_strike``
      (``-B78.5`` = "78° to 79°")

    Never infer these from ticker text — the 2026-06-11 audit found low-tail
    ``-T<n>`` tickers are *less* contracts, not greater.
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
    strike_type: str | None = None  # 'greater' | 'less' | 'between' | None
    floor_strike: float | None = None
    cap_strike: float | None = None


@dataclass(frozen=True, slots=True)
class OrderBookSnapshot:
    """Point-in-time order book for a single market.

    YES ladders are normalized: `yes_asks` always contains YES-ask prices
    (not Kalshi's raw `no` side) so downstream code doesn't have to juggle
    the complement conversion.

    Ladder prices are **dollars** (0..1) and sizes are **floats** — Kalshi
    prod has fractional trading enabled, so contract sizes like ``4985.18``
    are real (``orderbook_fp`` wire format, verified 2026-06-11). The legacy
    integer-cent ``orderbook`` format is still accepted and normalized to
    the same dollar/float representation.
    """

    snap_time: datetime
    ticker: str
    yes_bid: float | None
    yes_ask: float | None
    yes_bid_size: float | None
    yes_ask_size: float | None
    yes_bids: tuple[tuple[float, float], ...]  # (price_dollars, size), best-first
    yes_asks: tuple[tuple[float, float], ...]
