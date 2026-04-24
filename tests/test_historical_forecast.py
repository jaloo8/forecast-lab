"""Tests for the Open-Meteo historical deterministic backfill."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from kq.clients.openmeteo import (
    HIST_MEMBER,
    HIST_MODEL_NAME,
    OpenMeteoClient,
    _parse_historical_payload,
)

FIXTURE = Path(__file__).parent / "fixtures" / "openmeteo_historical_klax.json"


def _load() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_parse_historical_produces_one_row_per_day() -> None:
    rows = _parse_historical_payload(
        _load(),
        as_of=datetime(2026, 4, 23, 14, 0, tzinfo=UTC),
        station_icao="KLAX",
    )
    assert len(rows) == 3
    assert {r.valid_date for r in rows} == {
        date(2025, 6, 1),
        date(2025, 6, 2),
        date(2025, 6, 3),
    }
    # All rows share the sentinel model + member — distinguishable from ensemble.
    assert {r.model for r in rows} == {HIST_MODEL_NAME}
    assert {r.member for r in rows} == {HIST_MEMBER}


def test_parse_historical_values_align() -> None:
    rows = _parse_historical_payload(
        _load(),
        as_of=datetime(2026, 4, 23, tzinfo=UTC),
        station_icao="KLAX",
    )
    by_date = {r.valid_date: r for r in rows}
    # 2025-06-01: temperature_2m_max[0] = 77.0, min[0] = 61.2
    assert by_date[date(2025, 6, 1)].forecast_high_f == pytest.approx(77.0)
    assert by_date[date(2025, 6, 1)].forecast_low_f == pytest.approx(61.2)


def test_parse_historical_empty_daily_returns_empty() -> None:
    assert (
        _parse_historical_payload(
            {"daily": {"time": []}},
            as_of=datetime(2026, 4, 23, tzinfo=UTC),
            station_icao="KLAX",
        )
        == []
    )


def test_parse_historical_missing_series_falls_back_to_none() -> None:
    """If the API returns `time` but `temperature_2m_max` is missing entirely,
    we still produce rows; the missing field is None."""
    payload = {
        "daily": {
            "time": ["2025-06-01"],
            # temperature_2m_max intentionally absent
            "temperature_2m_min": [61.2],
        }
    }
    rows = _parse_historical_payload(
        payload,
        as_of=datetime(2026, 4, 23, tzinfo=UTC),
        station_icao="KLAX",
    )
    assert len(rows) == 1
    assert rows[0].forecast_high_f is None
    assert rows[0].forecast_low_f == pytest.approx(61.2)


def test_fetch_historical_end_to_end_with_mock() -> None:
    async def _run() -> None:
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            # Verify we hit the historical endpoint, not the ensemble one.
            captured["host"] = request.url.host
            captured["start_date"] = request.url.params.get("start_date", "") or ""
            captured["end_date"] = request.url.params.get("end_date", "") or ""
            return httpx.Response(200, json=_load())

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = OpenMeteoClient(http)
            rows = await client.fetch_historical_deterministic(
                "KLAX",
                start_date=date(2025, 6, 1),
                end_date=date(2025, 6, 3),
            )

        assert captured["host"] == "historical-forecast-api.open-meteo.com"
        assert captured["start_date"] == "2025-06-01"
        assert captured["end_date"] == "2025-06-03"
        assert len(rows) == 3

    asyncio.run(_run())


def test_fetch_historical_rejects_reversed_date_range() -> None:
    async def _run() -> None:
        async with OpenMeteoClient() as c:
            with pytest.raises(ValueError, match="precedes"):
                await c.fetch_historical_deterministic(
                    "KLAX",
                    start_date=date(2025, 6, 10),
                    end_date=date(2025, 6, 1),
                )

    asyncio.run(_run())


def test_fetch_historical_unknown_station_raises() -> None:
    async def _run() -> None:
        async with OpenMeteoClient() as c:
            with pytest.raises(ValueError, match="unknown station"):
                await c.fetch_historical_deterministic(
                    "KZZZ",
                    start_date=date(2025, 6, 1),
                    end_date=date(2025, 6, 3),
                )

    asyncio.run(_run())
