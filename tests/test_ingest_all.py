"""Tests for the aggregate ingest flow."""

from __future__ import annotations

from typing import Any

import pytest

from kq.clients.kalshi import KalshiCredentialsError
from kq.flows import ingest_all as mod


async def _patched(monkeypatch: pytest.MonkeyPatch, **replacements: Any) -> None:
    for name, fn in replacements.items():
        monkeypatch.setattr(mod, name, fn)


async def _ndfd_ok() -> int:
    """Default NDFD stub for tests that don't care about NDFD specifically."""
    return 0


async def _observed_ok() -> int:
    """Default observed-truth stub for tests that don't care about it."""
    return 0


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
        ingest_ndfd_once=_ndfd_ok,
        ingest_observed_once=_observed_ok,
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
        ingest_ndfd_once=_ndfd_ok,
        ingest_observed_once=_observed_ok,
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
        ingest_ndfd_once=_ndfd_ok,
        ingest_observed_once=_observed_ok,
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
        ingest_ndfd_once=boom_one,
        ingest_observed_once=boom_one,
        ingest_kalshi_once=boom_two,
    )
    results = await mod.ingest_all()
    assert all(not r.ok for r in results)
    # main() would exit 1 here; we don't call it to avoid asyncio.run inside
    # the event loop, but we assert the invariant it relies on.


async def test_ndfd_in_ingest_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """NDFD ingest is wired into the aggregate flow alongside weather/metar/kalshi."""

    async def w() -> int:
        return 1

    async def m() -> int:
        return 2

    async def n() -> int:
        return 42

    async def k() -> tuple[int, int]:
        return 3, 12

    await _patched(
        monkeypatch,
        ingest_weather_once=w,
        ingest_metar_once=m,
        ingest_ndfd_once=n,
        ingest_observed_once=_observed_ok,
        ingest_kalshi_once=k,
    )
    results = await mod.ingest_all()
    names = {r.name: r for r in results}
    assert "ndfd" in names
    assert names["ndfd"].ok is True
    assert names["ndfd"].rows == 42


async def test_ndfd_failure_does_not_block_others(monkeypatch: pytest.MonkeyPatch) -> None:
    """A flaky NDFD upstream must not bring down weather/metar/kalshi."""

    async def w() -> int:
        return 5

    async def m() -> int:
        return 5

    async def n() -> int:
        raise RuntimeError("openmeteo blip")

    async def k() -> tuple[int, int]:
        return 1, 2

    await _patched(
        monkeypatch,
        ingest_weather_once=w,
        ingest_metar_once=m,
        ingest_ndfd_once=n,
        ingest_observed_once=_observed_ok,
        ingest_kalshi_once=k,
    )
    results = await mod.ingest_all()
    names = {r.name: r for r in results}
    assert names["weather"].ok and names["metar"].ok and names["kalshi"].ok
    assert names["ndfd"].ok is False
    assert "openmeteo blip" in names["ndfd"].detail


async def test_observed_in_ingest_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """Observed truth (ACIS) is the fifth lane — without it settlement can
    never fire (2026-06-11 audit #7)."""

    async def w() -> int:
        return 1

    async def m() -> int:
        return 2

    async def o() -> int:
        return 24

    async def k() -> tuple[int, int]:
        return 3, 12

    await _patched(
        monkeypatch,
        ingest_weather_once=w,
        ingest_metar_once=m,
        ingest_ndfd_once=_ndfd_ok,
        ingest_observed_once=o,
        ingest_kalshi_once=k,
    )
    results = await mod.ingest_all()
    names = {r.name: r for r in results}
    assert "observed" in names
    assert names["observed"].ok is True
    assert names["observed"].rows == 24


async def test_observed_failure_does_not_block_others(monkeypatch: pytest.MonkeyPatch) -> None:
    """A flaky ACIS upstream must not bring down the other lanes."""

    async def w() -> int:
        return 5

    async def m() -> int:
        return 5

    async def o() -> int:
        raise RuntimeError("acis blip")

    async def k() -> tuple[int, int]:
        return 1, 2

    await _patched(
        monkeypatch,
        ingest_weather_once=w,
        ingest_metar_once=m,
        ingest_ndfd_once=_ndfd_ok,
        ingest_observed_once=o,
        ingest_kalshi_once=k,
    )
    results = await mod.ingest_all()
    names = {r.name: r for r in results}
    assert names["weather"].ok and names["metar"].ok and names["kalshi"].ok
    assert names["observed"].ok is False
    assert "acis blip" in names["observed"].detail
