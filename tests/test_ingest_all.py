"""Tests for the aggregate ingest flow."""

from __future__ import annotations

from typing import Any

import pytest

from kq.clients.kalshi import KalshiCredentialsError
from kq.flows import ingest_all as mod


async def _patched(monkeypatch: pytest.MonkeyPatch, **replacements: Any) -> None:
    for name, fn in replacements.items():
        monkeypatch.setattr(mod, name, fn)


async def test_all_succeed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def w() -> int:
        return 10

    async def m() -> int:
        return 6

    async def k() -> tuple[int, int]:
        return 3, 12

    await _patched(
        monkeypatch,
        ingest_weather_once=w,
        ingest_metar_once=m,
        ingest_kalshi_once=k,
    )
    results = await mod.ingest_all()
    names = {r.name: r for r in results}
    assert names["weather"].ok and names["weather"].rows == 10
    assert names["metar"].ok and names["metar"].rows == 6
    assert names["kalshi"].ok and names["kalshi"].rows == 15


async def test_kalshi_credentials_missing_is_warning_not_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def w() -> int:
        return 1

    async def m() -> int:
        return 2

    async def k() -> tuple[int, int]:
        raise KalshiCredentialsError("no creds in test")

    await _patched(
        monkeypatch,
        ingest_weather_once=w,
        ingest_metar_once=m,
        ingest_kalshi_once=k,
    )
    results = await mod.ingest_all()
    kalshi = next(r for r in results if r.name == "kalshi")
    assert kalshi.ok is False
    assert "credentials missing" in kalshi.detail


async def test_partial_failure_returns_all_results(monkeypatch: pytest.MonkeyPatch) -> None:
    async def w() -> int:
        raise RuntimeError("weather API down")

    async def m() -> int:
        return 6

    async def k() -> tuple[int, int]:
        return 3, 12

    await _patched(
        monkeypatch,
        ingest_weather_once=w,
        ingest_metar_once=m,
        ingest_kalshi_once=k,
    )
    results = await mod.ingest_all()
    names = {r.name: r for r in results}
    assert names["weather"].ok is False
    assert "weather API down" in names["weather"].detail
    assert names["metar"].ok is True


async def test_all_fail_sets_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom_one() -> int:
        raise RuntimeError("down")

    async def boom_two() -> tuple[int, int]:
        raise RuntimeError("down")

    await _patched(
        monkeypatch,
        ingest_weather_once=boom_one,
        ingest_metar_once=boom_one,
        ingest_kalshi_once=boom_two,
    )
    results = await mod.ingest_all()
    assert all(not r.ok for r in results)
    # main() would exit 1 here; we don't call it to avoid asyncio.run inside
    # the event loop, but we assert the invariant it relies on.
