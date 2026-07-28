"""Shared async HTTP helper: retry on 429/5xx with exponential backoff + jitter.

Kept deliberately tiny — no dependency on tenacity/aiohttp-retry. Every client
under `kq.clients.*` should go through `request_json()` (or `request_text()`
for non-JSON bodies like RSS/Atom XML) so retry behavior, timeouts, and the
user-agent stay consistent.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx

DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
DEFAULT_USER_AGENT = "forecast-lab/0.0.1 (+https://github.com/jaloo8/forecast-lab)"
RETRYABLE_STATUSES: frozenset[int] = frozenset({408, 425, 429, 500, 502, 503, 504})


class HttpError(RuntimeError):
    """Raised when a request fails after exhausting retries."""

    def __init__(self, status: int | None, url: str, detail: str) -> None:
        super().__init__(f"HTTP {status} from {url}: {detail}")
        self.status = status
        self.url = url
        self.detail = detail


async def request_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    max_retries: int = 4,
    base_backoff_s: float = 0.5,
) -> dict[str, Any]:
    """GET `url` and return the parsed JSON body, retrying on 429/5xx.

    Backoff is `base_backoff_s * 2**attempt` with +/-25% jitter, capped at 30s.
    Non-retryable errors raise `HttpError` immediately. A 200 response whose
    body is not valid JSON (e.g. an HTML error page from an intermediary) is
    treated as retryable — same as a 502 — and raises `HttpError` (never a
    raw `JSONDecodeError`) once retries are exhausted.
    """
    last_detail = ""
    last_status: int | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = await client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            last_status, last_detail = None, f"transport error: {exc!r}"
        else:
            if resp.status_code == 200:
                try:
                    return resp.json()  # type: ignore[no-any-return]
                except ValueError:  # json.JSONDecodeError subclasses ValueError
                    last_status = 200
                    last_detail = f"non-JSON 200 body: {resp.text[:500]}"
            else:
                last_status, last_detail = resp.status_code, resp.text[:500]
                if last_status not in RETRYABLE_STATUSES:
                    raise HttpError(last_status, url, last_detail)

        if attempt == max_retries:
            break
        backoff = min(30.0, base_backoff_s * (2**attempt))
        backoff *= 1.0 + random.uniform(-0.25, 0.25)
        await asyncio.sleep(backoff)

    raise HttpError(last_status, url, last_detail or "max retries exceeded")


async def request_text(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    max_retries: int = 4,
    base_backoff_s: float = 0.5,
) -> str:
    """GET `url` and return the response body text, retrying on 429/5xx.

    Same retry/backoff policy as :func:`request_json` minus the JSON
    validation — any 200 body is a success (feeds are XML; content
    validation belongs to the parser, which fails loudly on non-XML).
    """
    last_detail = ""
    last_status: int | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = await client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            last_status, last_detail = None, f"transport error: {exc!r}"
        else:
            if resp.status_code == 200:
                return resp.text
            last_status, last_detail = resp.status_code, resp.text[:500]
            if last_status not in RETRYABLE_STATUSES:
                raise HttpError(last_status, url, last_detail)

        if attempt == max_retries:
            break
        backoff = min(30.0, base_backoff_s * (2**attempt))
        backoff *= 1.0 + random.uniform(-0.25, 0.25)
        await asyncio.sleep(backoff)

    raise HttpError(last_status, url, last_detail or "max retries exceeded")


def default_client(**overrides: Any) -> httpx.AsyncClient:
    """Factory for an `httpx.AsyncClient` with our baseline timeouts + UA."""
    kwargs: dict[str, Any] = {
        "timeout": DEFAULT_TIMEOUT,
        "headers": {"User-Agent": DEFAULT_USER_AGENT},
        "follow_redirects": True,
    }
    kwargs.update(overrides)
    return httpx.AsyncClient(**kwargs)
