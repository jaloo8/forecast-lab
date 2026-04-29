"""Kalshi v2 read-only client.

Public surface:
    KalshiClient, KalshiCredentialsError, BASE_URLS  (from .client)
    Market, OrderBookSnapshot                        (from ._types)

See docs/research/PASS-1-FEASIBILITY.md and CLAUDE.md §5 for scope.
"""

from __future__ import annotations

from kq.clients.kalshi._parsers import _parse_market, _parse_orderbook
from kq.clients.kalshi._ticker_parser import (
    WeatherMarketRef,
    build_weather_market_ticker,
    parse_weather_market_ticker,
)
from kq.clients.kalshi._types import Market, OrderBookSnapshot
from kq.clients.kalshi.client import BASE_URLS, KalshiClient, KalshiCredentialsError

__all__ = [
    "BASE_URLS",
    "KalshiClient",
    "KalshiCredentialsError",
    "Market",
    "OrderBookSnapshot",
    "WeatherMarketRef",
    "_parse_market",  # exported for tests
    "_parse_orderbook",  # exported for tests
    "build_weather_market_ticker",
    "parse_weather_market_ticker",
]
