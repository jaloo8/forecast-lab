"""KalshiClient: the authenticated async HTTP surface."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal
from urllib.parse import urlsplit

import httpx

from kq.clients._http import default_client, request_json
from kq.clients.kalshi._parsers import _parse_market, _parse_orderbook
from kq.clients.kalshi._types import Market, OrderBookSnapshot
from kq.clients.kalshi.auth import auth_headers, load_private_key
from kq.config import Settings, get_settings

BASE_URLS: Final[dict[str, str]] = {
    "demo": "https://demo-api.kalshi.co/trade-api/v2",
    "prod": "https://api.elections.kalshi.com/trade-api/v2",
}


class KalshiCredentialsError(RuntimeError):
    """Raised when Kalshi API credentials are missing or unusable."""


class KalshiClient:
    """Async read-only Kalshi client.

    Usage:
        async with KalshiClient.from_settings() as c:
            markets = await c.list_markets(event_ticker="KXHIGHLAX")
            book = await c.get_orderbook(markets[0].ticker)

    Write endpoints (order placement, cancellation) are deliberately absent
    until the Phase 5 live-trading gate passes.
    """

    def __init__(
        self,
        *,
        api_key_id: str,
        private_key_path: Path,
        env: Literal["demo", "prod"] = "demo",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key_id:
            raise KalshiCredentialsError("KALSHI_API_KEY_ID is empty")
        if not private_key_path or not private_key_path.exists():
            raise KalshiCredentialsError(f"Kalshi private key not found at {private_key_path!r}")
        self._api_key_id = api_key_id
        self._private_key = load_private_key(private_key_path)
        self._base = BASE_URLS[env]
        self._client = client
        self._owns_client = client is None

    @classmethod
    def from_settings(
        cls, settings: Settings | None = None, *, client: httpx.AsyncClient | None = None
    ) -> KalshiClient:
        """Build a client from `.env`-driven settings. Raises if creds are missing."""
        s = settings or get_settings()
        return cls(
            api_key_id=s.kalshi_api_key_id,
            private_key_path=s.kalshi_private_key_path,
            env=s.kalshi_env,
            client=client,
        )

    async def __aenter__(self) -> KalshiClient:
        if self._client is None:
            self._client = default_client()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def list_markets(
        self,
        *,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
        status: str | None = "open",
        limit: int = 200,
    ) -> list[Market]:
        """List markets, optionally filtered by event/series ticker + status.

        Use ``series_ticker`` (e.g. ``KXHIGHLAX``) to get every current market
        across a series' open events — that's what the weather stations need,
        since their dated events change daily. Use ``event_ticker`` only when
        you have a specific dated event (e.g. ``KXHIGHLAX-26MAY31``); passing a
        bare series ticker as ``event_ticker`` matches no event and returns [].
        """
        params: dict[str, Any] = {"limit": limit}
        if event_ticker is not None:
            params["event_ticker"] = event_ticker
        if series_ticker is not None:
            params["series_ticker"] = series_ticker
        if status is not None:
            params["status"] = status
        payload = await self._get("/markets", params=params)
        return [_parse_market(m) for m in payload.get("markets", []) if isinstance(m, dict)]

    async def get_orderbook(self, ticker: str) -> OrderBookSnapshot:
        """Fetch the current order book for a single market."""
        payload = await self._get(f"/markets/{ticker}/orderbook")
        return _parse_orderbook(payload, ticker=ticker, snap_time=datetime.now(tz=UTC))

    async def _get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("use `async with KalshiClient(...)` or pass a client")
        url = f"{self._base}{path}"
        headers = auth_headers(
            api_key_id=self._api_key_id,
            private_key=self._private_key,
            method="GET",
            path=urlsplit(url).path,  # path only, no query string
        )
        return await request_json(self._client, url, params=params, headers=headers)
