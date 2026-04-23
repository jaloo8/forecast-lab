"""Kalshi API client wrapper.

Phase 1 deliverable. Wraps the official `kalshi-python` SDK behind a typed
interface so we can swap to a custom client later without changing callers.

Auth: RSA-PSS signed requests. Key ID + private key from `.env`. Never
commit the private key.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OrderBookSnapshot:
    """BBO + depth snapshot for a single market at a single instant."""

    ticker: str
    snap_time: datetime
    yes_bid: float | None
    yes_ask: float | None
    yes_bid_size: int | None
    yes_ask_size: int | None
    volume_24h: float | None
    open_interest: float | None


class KalshiClient:
    """Thin wrapper over `kalshi-python`. Not implemented until Phase 1."""

    def __init__(self, *, env: str = "demo") -> None:
        self._env = env

    def list_weather_markets(self) -> list[str]:
        """Return tickers for all active Kalshi weather daily-high markets."""
        raise NotImplementedError("Phase 1 task")

    def get_orderbook(self, ticker: str) -> OrderBookSnapshot:
        """Fetch a single orderbook snapshot. Retries and rate-limits handled here."""
        raise NotImplementedError("Phase 1 task")
