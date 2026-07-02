"""Tests for the retry/backoff HTTP helper."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from kq.clients import _http
from kq.clients._http import HttpError, request_json


async def test_happy_path_returns_json() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        body = await request_json(client, "https://example.test/api")
    assert body == {"ok": True}


async def test_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    # No real sleeping in tests.
    async def _no_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr(_http.asyncio, "sleep", _no_sleep)

    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(503, text="upstream down")
        return httpx.Response(200, json={"done": True})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        body = await request_json(client, "https://example.test/api")
    assert body == {"done": True}
    assert len(calls) == 3


async def test_non_retryable_raises_immediately() -> None:
    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(404, text="nope")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(HttpError) as exc_info:
            await request_json(client, "https://example.test/api")
    assert exc_info.value.status == 404
    assert len(calls) == 1


async def test_exhausts_retries_and_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr(_http.asyncio, "sleep", _no_sleep)

    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(500, text="boom")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(HttpError) as exc_info:
            await request_json(client, "https://example.test/api", max_retries=2)
    assert exc_info.value.status == 500
    assert len(calls) == 3  # initial attempt + 2 retries


async def test_user_agent_default_present() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["ua"] = request.headers.get("user-agent")
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    client = _http.default_client(transport=transport)
    try:
        await request_json(client, "https://example.test/api")
    finally:
        await client.aclose()
    assert captured["ua"] and "forecast-lab" in captured["ua"]


# ----------------------------- edge cases (PR #5) -----------------------------


async def test_transport_error_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """ConnectError during the first attempt should trigger a retry, not fail fast."""

    async def _no_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr(_http.asyncio, "sleep", _no_sleep)

    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        body = await request_json(client, "https://example.test/api")
    assert body == {"ok": True}
    assert len(calls) == 2


async def test_zero_retries_still_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """`max_retries=0` means exactly one attempt; failure raises immediately."""

    async def _no_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr(_http.asyncio, "sleep", _no_sleep)

    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503, text="boom")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(HttpError):
            await request_json(client, "https://example.test/api", max_retries=0)
    assert len(calls) == 1


async def test_non_json_200_is_retried_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 200 with a non-JSON body (e.g. an HTML error page from a proxy)
    gets the same retry treatment as a 502 — 2026-07-01 audit (Tier 2):
    it used to raise a raw JSONDecodeError and bypass retry entirely."""

    async def _no_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr(_http.asyncio, "sleep", _no_sleep)

    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(200, text="<html>Service Temporarily Unavailable</html>")
        return httpx.Response(200, json={"recovered": True})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        body = await request_json(client, "https://example.test/api")
    assert body == {"recovered": True}
    assert len(calls) == 3


async def test_non_json_200_exhausts_retries_as_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persistent non-JSON 200s raise the client's typed HttpError — never
    a raw JSONDecodeError."""

    async def _no_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr(_http.asyncio, "sleep", _no_sleep)

    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, text="not json at all")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(HttpError) as exc_info:
            await request_json(client, "https://example.test/api", max_retries=2)
    assert exc_info.value.status == 200
    assert "non-JSON" in exc_info.value.detail
    assert len(calls) == 3  # initial attempt + 2 retries


async def test_headers_forwarded() -> None:
    """Custom headers are sent with the request (needed for Kalshi auth)."""
    captured: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["x-custom"] = request.headers.get("x-custom")
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        await request_json(
            client,
            "https://example.test/api",
            headers={"X-Custom": "forecast-lab-test"},
        )
    assert captured["x-custom"] == "forecast-lab-test"
