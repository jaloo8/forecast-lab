"""Tests for the NDFD/NBM client."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest

from kq.clients.ndfd import (
    DETERMINISTIC_SOURCE,
    NbmDeterministicForecast,
    NdfdClient,
    _as_float,
    _extract_daily_pairs,
    _parse_historical_payload,
    _parse_iso_date,
    _parse_live_payload,
)
from kq.clients.stations import STATIONS_BY_ICAO


def _live_payload() -> dict[str, Any]:
    """Shape returned by api.open-meteo.com /v1/forecast?models=ncep_nbm_conus."""
    return {
        "latitude": 40.6413,
        "longitude": -73.7781,
        "timezone": "America/New_York",
        "daily_units": {"temperature_2m_max": "°F"},
        "daily": {
            "time": ["2026-04-29", "2026-04-30", "2026-05-01", "2026-05-02"],
            "temperature_2m_max": [55.4, 58.8, 60.0, 56.9],
        },
    }


def _historical_payload() -> dict[str, Any]:
    """Shape returned by historical-forecast-api.open-meteo.com."""
    return {
        "latitude": 40.6413,
        "longitude": -73.7781,
        "daily": {
            "time": ["2025-04-01", "2025-04-02", "2025-04-03"],
            "temperature_2m_max": [56.3, 47.5, 63.5],
        },
    }


# --------------------------- pure helpers ---------------------------


def test_as_float_handles_string_and_none() -> None:
    assert _as_float(None) is None
    assert _as_float("not-a-number") is None
    assert _as_float("60.08") == pytest.approx(60.08)
    assert _as_float(60.08) == pytest.approx(60.08)


def test_parse_iso_date_rejects_garbage() -> None:
    assert _parse_iso_date(None) is None
    assert _parse_iso_date(20260430) is None
    assert _parse_iso_date("2026/04/30") is None
    assert _parse_iso_date("2026-04-30") == date(2026, 4, 30)


def test_extract_daily_pairs_rejects_non_dict() -> None:
    assert _extract_daily_pairs(None) == []
    assert _extract_daily_pairs([1, 2, 3]) == []
    assert _extract_daily_pairs({"daily": "wrong-type"}) == []
    assert _extract_daily_pairs({"daily": {"time": "x", "temperature_2m_max": []}}) == []


def test_extract_daily_pairs_skips_malformed_rows() -> None:
    pairs = _extract_daily_pairs(
        {
            "daily": {
                "time": ["2026-04-30", "not-a-date", "2026-05-01"],
                "temperature_2m_max": [58.8, 60.0, None],
            }
        }
    )
    # row 1 dropped (bad date), row 2 dropped (None temp).
    assert pairs == [(date(2026, 4, 30), 58.8)]


def test_extract_daily_pairs_handles_unequal_length_lists() -> None:
    """Defensive: ``zip(strict=False)`` truncates rather than raising."""
    pairs = _extract_daily_pairs(
        {
            "daily": {
                "time": ["2026-04-30", "2026-05-01"],
                "temperature_2m_max": [58.8],  # one short
            }
        }
    )
    assert pairs == [(date(2026, 4, 30), 58.8)]


# --------------------------- live parser ---------------------------


def test_parse_live_payload_computes_lead_days() -> None:
    as_of = datetime(2026, 4, 29, 23, 0, tzinfo=UTC)
    rows = _parse_live_payload(_live_payload(), as_of=as_of, station_icao="KJFK")
    # Today (2026-04-29) lead=0, next day lead=1, etc.
    assert [r.lead_days for r in rows] == [0, 1, 2, 3]
    assert [r.valid_date for r in rows] == [
        date(2026, 4, 29),
        date(2026, 4, 30),
        date(2026, 5, 1),
        date(2026, 5, 2),
    ]
    # Forecast values preserved with 2-decimal rounding.
    assert rows[1].forecast_max_f == pytest.approx(58.8)
    # `as_of` stripped of tzinfo (DuckDB stores naive UTC).
    assert rows[0].as_of.tzinfo is None
    # Probabilistic columns are NULL until the qmd upgrade.
    assert rows[0].p10_max_f is None
    assert rows[0].source == DETERMINISTIC_SOURCE


def test_parse_live_payload_drops_past_dates() -> None:
    """If the live endpoint somehow returns yesterday, we drop it."""
    payload = {
        "daily": {
            "time": ["2026-04-28", "2026-04-29", "2026-04-30"],
            "temperature_2m_max": [50.0, 55.0, 60.0],
        }
    }
    as_of = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
    rows = _parse_live_payload(payload, as_of=as_of, station_icao="KJFK")
    assert [r.valid_date for r in rows] == [date(2026, 4, 29), date(2026, 4, 30)]


def test_parse_live_payload_returns_empty_on_garbage() -> None:
    as_of = datetime(2026, 4, 29, tzinfo=UTC)
    assert _parse_live_payload({}, as_of=as_of, station_icao="KJFK") == []
    assert _parse_live_payload(None, as_of=as_of, station_icao="KJFK") == []


# --------------------------- historical parser ---------------------------


def test_parse_historical_payload_anchors_lead_one() -> None:
    rows = _parse_historical_payload(_historical_payload(), station_icao="KJFK")
    # All rows are canonical lead-1.
    assert all(r.lead_days == 1 for r in rows)
    # `as_of` is backdated to (valid_date - 1) at midnight UTC. Benchmark-only
    # bookkeeping (freshest-wins ordering) — the model-training twin of this
    # trick was deleted in PR-F (audit #8); see the honesty caveat in
    # kq.clients.ndfd's module docstring for why it is tolerable here.
    assert rows[0].as_of == datetime(2025, 3, 31, 0, 0, 0)
    assert rows[1].as_of == datetime(2025, 4, 1, 0, 0, 0)
    assert rows[0].forecast_max_f == pytest.approx(56.3)


def test_parse_historical_payload_drops_null_rows() -> None:
    """Open-Meteo returns null for pre-archive dates (~before 2024-11-01)."""
    payload = {
        "daily": {
            "time": ["2024-06-01", "2024-12-01"],
            "temperature_2m_max": [None, 47.5],
        }
    }
    rows = _parse_historical_payload(payload, station_icao="KJFK")
    assert len(rows) == 1
    assert rows[0].valid_date == date(2024, 12, 1)


# --------------------------- async client end-to-end ---------------------------


async def test_fetch_forecast_end_to_end_with_mock() -> None:
    """Integration check: URL + params + station routing.

    Avoids asserting on row counts — `datetime.now()` advances, and the
    live parser drops past-date rows. The parser semantics are covered
    by ``test_parse_live_payload_*`` directly.
    """
    payload = _live_payload()
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = NdfdClient(http)
        rows = await client.fetch_forecast("KNYC", forecast_days=4)

    # Live URL (not historical) must have been hit.
    assert "api.open-meteo.com" in captured["url"]
    # Right model + tz routed through.
    assert captured["params"]["models"] == "ncep_nbm_conus"
    assert captured["params"]["timezone"] == "America/New_York"
    assert captured["params"]["forecast_days"] == "4"
    # Station tagged on every returned row.
    assert all(r.station == "KNYC" for r in rows)
    # All returned rows are non-past relative to "now" — covers the past-date drop.
    today_utc = datetime.now(UTC).date()
    assert all(r.valid_date >= today_utc for r in rows)


async def test_fetch_historical_end_to_end_with_mock() -> None:
    payload = _historical_payload()
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = NdfdClient(http)
        rows = await client.fetch_historical(
            "KNYC",
            start_date=date(2025, 4, 1),
            end_date=date(2025, 4, 3),
        )

    assert len(rows) == 3
    assert "historical-forecast-api" in captured["url"]
    assert captured["params"]["start_date"] == "2025-04-01"
    assert captured["params"]["end_date"] == "2025-04-03"


async def test_fetch_historical_rejects_inverted_range() -> None:
    async with NdfdClient() as client:
        with pytest.raises(ValueError, match="precedes"):
            await client.fetch_historical(
                "KNYC",
                start_date=date(2025, 4, 5),
                end_date=date(2025, 4, 1),
            )


async def test_fetch_unknown_station_raises() -> None:
    async with NdfdClient() as client:
        with pytest.raises(ValueError, match="unknown station"):
            await client.fetch_forecast("KZZZ")


async def test_client_requires_context_manager_or_explicit_client() -> None:
    """If neither path provides a client, calling fetch_* raises."""
    naked = NdfdClient()
    with pytest.raises(RuntimeError, match="async with"):
        await naked.fetch_forecast("KNYC")


async def test_station_object_accepted_in_addition_to_icao() -> None:
    payload = _live_payload()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = NdfdClient(http)
        rows = await client.fetch_forecast(STATIONS_BY_ICAO["KNYC"])
    assert all(r.station == "KNYC" for r in rows)


def test_dataclass_default_source_is_deterministic() -> None:
    """The qmd upgrade will populate p10..p90 + a different source."""
    row = NbmDeterministicForecast(
        as_of=datetime(2026, 4, 29),
        station="KJFK",
        valid_date=date(2026, 4, 30),
        lead_days=1,
        forecast_max_f=60.0,
    )
    assert row.source == "nbm_deterministic_openmeteo"
    assert row.p10_max_f is None
    assert row.p90_max_f is None
