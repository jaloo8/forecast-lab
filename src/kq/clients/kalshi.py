"""Kalshi API client (read-only v1).

Wraps the Kalshi v2 REST API behind a typed interface. v1 scope: read-only
(`list_markets`, `get_orderbook`, `get_event`). Write endpoints (order
placement, cancellation) are deliberately absent until Phase 5 gate passes.

Auth: `KALSHI_API_KEY_ID` + an RSA private key at `KALSHI_PRIVATE_KEY_PATH`.
Set `KALSHI_ENV=demo` to hit the demo environment.

Bases:
    demo -> https://demo-api.kalshi.co/trade-api/v2
    prod -> https://api.elections.kalshi.com/trade-api/v2
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal
from urllib.parse import urlsplit

import httpx

from kq.clients._http import default_client, request_json
from kq.clients._kalshi_auth import auth_headers, load_private_key
from kq.config import Settings, get_settings

BASE_URLS: Final[dict[str, str]] = {
    "demo": "https://demo-api.kalshi.co/trade-api/v2",
    "prod": "https://api.elections.kalshi.com/trade-api/v2",
}


class KalshiCredentialsError(RuntimeError):
    """Raised when Kalshi API credentials are missing or unusable."""


@dataclass(frozen=True, slots=True)
class Market:
    ticker: str
    event_ticker: str
    title: str
    status: str  # 'active' | 'closed' | 'settled' | ...
    category: str | None
    yes_ask: float | None  # dollars, 0..1
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
    snap_time: datetime
    ticker: str
    yes_bid: float | None
    yes_ask: float | None
    yes_bid_size: int | None
    yes_ask_size: int | None
    # Full ladder in cents, side -> [(price_cents, size), ...] — nearest to BBO first.
    yes_bids: tuple[tuple[int, int], ...]
    yes_asks: tuple[tuple[int, int], ...]


class KalshiClient:
    """Async read-only Kalshi client.

    Usage:
        async with KalshiClient.from_settings() as c:
            markets = await c.list_markets(event_ticker="KXHIGHLAX")
            book = await c.get_orderbook(markets[0].ticker)
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
        status: str | None = "open",
        limit: int = 200,
    ) -> list[Market]:
        """List markets, optionally filtered by event_ticker/status."""
        params: dict[str, Any] = {"limit": limit}
        if event_ticker is not None:
            params["event_ticker"] = event_ticker
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


def _parse_market(raw: dict[str, Any]) -> Market:
    return Market(
        ticker=str(raw.get("ticker", "")),
        event_ticker=str(raw.get("event_ticker", "")),
        title=str(raw.get("title", "")),
        status=str(raw.get("status", "")),
        category=_opt_str(raw.get("category")),
        yes_ask=_cents_to_dollars(raw.get("yes_ask")),
        yes_bid=_cents_to_dollars(raw.get("yes_bid")),
        last_price=_cents_to_dollars(raw.get("last_price")),
        volume=_opt_float(raw.get("volume")),
        open_interest=_opt_float(raw.get("open_interest")),
        open_time=_opt_dt(raw.get("open_time")),
        close_time=_opt_dt(raw.get("close_time")),
        expected_expiration_time=_opt_dt(raw.get("expected_expiration_time")),
        rules_primary=_opt_str(raw.get("rules_primary")),
    )


def _parse_orderbook(
    payload: dict[str, Any], *, ticker: str, snap_time: datetime
) -> OrderBookSnapshot:
    book = payload.get("orderbook") or {}
    yes_bids_raw = book.get("yes") or []  # list[[price_cents, size], ...]
    yes_asks_raw = book.get("no") or []
    # Kalshi convention: `yes` is the YES-bid side; `no` is the NO-bid side
    # (equivalently, YES-ask = 100 - NO-bid price). Normalize to YES ladder.
    yes_bids = tuple(sorted(_clean_ladder(yes_bids_raw), key=lambda r: -r[0]))
    yes_asks = tuple(
        sorted(
            ((100 - p, s) for p, s in _clean_ladder(yes_asks_raw)),
            key=lambda r: r[0],
        )
    )
    best_bid = yes_bids[0][0] / 100.0 if yes_bids else None
    best_ask = yes_asks[0][0] / 100.0 if yes_asks else None
    best_bid_size = yes_bids[0][1] if yes_bids else None
    best_ask_size = yes_asks[0][1] if yes_asks else None
    return OrderBookSnapshot(
        snap_time=snap_time,
        ticker=ticker,
        yes_bid=best_bid,
        yes_ask=best_ask,
        yes_bid_size=best_bid_size,
        yes_ask_size=best_ask_size,
        yes_bids=yes_bids,
        yes_asks=yes_asks,
    )


def _clean_ladder(raw: Any) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    if not isinstance(raw, list):
        return out
    for entry in raw:
        if not isinstance(entry, list | tuple) or len(entry) != 2:
            continue
        price, size = entry
        try:
            out.append((int(price), int(size)))
        except (TypeError, ValueError):
            continue
    return out


def _cents_to_dollars(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value) / 100.0
    except (TypeError, ValueError):
        return None


def _opt_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _opt_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _opt_dt(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
