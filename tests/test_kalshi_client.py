"""Tests for the Kalshi read-only client."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from kq.clients.kalshi import (
    KalshiClient,
    KalshiCredentialsError,
    _parse_market,
    _parse_orderbook,
)


def _build_client(
    api_key_id: str,
    key_path: Path,
    *,
    client: httpx.AsyncClient,
) -> KalshiClient:
    return KalshiClient(
        api_key_id=api_key_id,
        private_key_path=key_path,
        env="demo",
        client=client,
    )


def test_parse_market_canonicalizes_prices_to_dollars() -> None:
    raw = {
        "ticker": "KXHIGHLAX-26APR23-75",
        "event_ticker": "KXHIGHLAX",
        "title": "LA high today >= 75F",
        "status": "open",
        "yes_ask": 42,  # cents
        "yes_bid": 38,
        "last_price": 40,
        "volume": 1234,
        "open_interest": 567,
        "open_time": "2026-04-23T08:00:00Z",
        "close_time": "2026-04-23T20:00:00Z",
        "expected_expiration_time": "2026-04-24T05:00:00Z",
        "rules_primary": "Settles on NWS Daily Climate Report for KLAX.",
    }
    m = _parse_market(raw)
    assert m.yes_ask == pytest.approx(0.42)
    assert m.yes_bid == pytest.approx(0.38)
    assert m.last_price == pytest.approx(0.40)
    assert m.open_time == datetime(2026, 4, 23, 8, 0, tzinfo=UTC)
    assert m.close_time == datetime(2026, 4, 23, 20, 0, tzinfo=UTC)


def test_parse_orderbook_normalizes_no_side_to_yes_ask() -> None:
    # Kalshi returns `yes` = YES-bid ladder (price=YES-side bid price),
    # and `no` = NO-bid ladder (where yes_ask = 100 - no_bid_price).
    payload = {
        "orderbook": {
            "yes": [[38, 10], [37, 20]],  # best YES bid at 38c
            "no": [[55, 30], [54, 15]],  # best YES ask = 100-55 = 45c
        }
    }
    snap = _parse_orderbook(
        payload, ticker="KXHIGHLAX-TEST", snap_time=datetime(2026, 4, 23, tzinfo=UTC)
    )
    assert snap.yes_bid == pytest.approx(0.38)
    assert snap.yes_ask == pytest.approx(0.45)
    assert snap.yes_bid_size == 10
    assert snap.yes_ask_size == 30
    # YES bid ladder sorted best-first (desc by price)
    assert snap.yes_bids == ((38, 10), (37, 20))
    # YES ask ladder sorted best-first (asc by converted price)
    assert snap.yes_asks == ((45, 30), (46, 15))


def test_parse_orderbook_handles_empty_sides() -> None:
    snap = _parse_orderbook(
        {"orderbook": {"yes": [], "no": []}},
        ticker="X",
        snap_time=datetime(2026, 4, 23, tzinfo=UTC),
    )
    assert snap.yes_bid is None
    assert snap.yes_ask is None
    assert snap.yes_bids == ()
    assert snap.yes_asks == ()


def test_client_refuses_without_api_key(rsa_private_key_file: Path) -> None:
    with pytest.raises(KalshiCredentialsError):
        KalshiClient(api_key_id="", private_key_path=rsa_private_key_file, env="demo")


def test_client_refuses_without_key_file(tmp_path: Path) -> None:
    with pytest.raises(KalshiCredentialsError):
        KalshiClient(
            api_key_id="some-id",
            private_key_path=tmp_path / "does-not-exist.pem",
            env="demo",
        )


async def test_list_markets_end_to_end(rsa_private_key_file: Path) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["ua"] = request.headers.get("user-agent")
        captured["kalshi_key"] = request.headers.get("KALSHI-ACCESS-KEY")
        captured["kalshi_ts"] = request.headers.get("KALSHI-ACCESS-TIMESTAMP")
        captured["kalshi_sig"] = request.headers.get("KALSHI-ACCESS-SIGNATURE")
        return httpx.Response(
            200,
            json={
                "markets": [
                    {
                        "ticker": "KXHIGHLAX-X-75",
                        "event_ticker": "KXHIGHLAX",
                        "title": "LA high >= 75F",
                        "status": "open",
                        "yes_ask": 42,
                        "yes_bid": 38,
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = _build_client("my-key-id", rsa_private_key_file, client=http)
        markets = await client.list_markets(event_ticker="KXHIGHLAX")

    assert len(markets) == 1
    assert markets[0].ticker == "KXHIGHLAX-X-75"
    assert captured["kalshi_key"] == "my-key-id"
    # Auth headers are all non-empty
    assert captured["kalshi_ts"]
    assert captured["kalshi_sig"]
    # URL includes the query param
    assert "event_ticker=KXHIGHLAX" in str(captured["url"])


async def test_list_markets_filters_by_series_ticker(rsa_private_key_file: Path) -> None:
    """`series_ticker=` is forwarded as a query param — the weather-station path.

    Regression guard: stations carry Kalshi SERIES tickers; querying them by
    `event_ticker` returns nothing on prod (the bug the prod switch surfaced).
    `ingest_kalshi` / `paper_trade` rely on the series_ticker filter.
    """
    captured: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"markets": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = _build_client("id", rsa_private_key_file, client=http)
        await client.list_markets(series_ticker="KXHIGHLAX")

    assert "series_ticker=KXHIGHLAX" in str(captured["url"])
    assert "event_ticker=" not in str(captured["url"])


async def test_get_orderbook_end_to_end(rsa_private_key_file: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/markets/KXHIGHLAX-TEST/orderbook" in str(request.url)
        return httpx.Response(
            200,
            json={"orderbook": {"yes": [[38, 10]], "no": [[55, 30]]}},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = _build_client("id", rsa_private_key_file, client=http)
        snap = await client.get_orderbook("KXHIGHLAX-TEST")

    assert snap.ticker == "KXHIGHLAX-TEST"
    assert snap.yes_bid == pytest.approx(0.38)
    assert snap.yes_ask == pytest.approx(0.45)


# ----------------------------- edge cases (PR #5) -----------------------------


def test_orderbook_malformed_ladder_entries_dropped() -> None:
    """Kalshi could return 3-tuples or missing-size entries during upgrades.
    The parser must drop them, not blow up."""
    payload = {
        "orderbook": {
            "yes": [
                [38, 10],
                [37],  # missing size — dropped
                [36, 20, "extra"],  # wrong arity — dropped
                "not a list",  # wrong type — dropped
                [35, "not-a-number"],  # bad size — dropped
            ],
            "no": [[55, 30]],
        }
    }
    snap = _parse_orderbook(payload, ticker="X", snap_time=datetime(2026, 4, 23, tzinfo=UTC))
    assert snap.yes_bids == ((38, 10),)
    assert snap.yes_asks == ((45, 30),)


def test_parse_market_handles_null_prices() -> None:
    raw = {
        "ticker": "X",
        "event_ticker": "KXHIGHLAX",
        "title": "t",
        "status": "open",
        "yes_ask": None,
        "yes_bid": None,
        "last_price": None,
        "volume": None,
        "open_interest": None,
    }
    m = _parse_market(raw)
    assert m.yes_ask is None
    assert m.yes_bid is None
    assert m.last_price is None
    assert m.volume is None
    assert m.open_interest is None


def test_parse_market_malformed_dates_become_none() -> None:
    raw = {
        "ticker": "X",
        "event_ticker": "E",
        "title": "t",
        "status": "open",
        "open_time": "not-an-iso-date",
        "close_time": 12345,  # wrong type entirely
        "expected_expiration_time": None,
    }
    m = _parse_market(raw)
    assert m.open_time is None
    assert m.close_time is None
    assert m.expected_expiration_time is None
