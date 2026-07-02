"""Tests for the NWS ACIS daily-climate client."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from kq.clients.acis import AcisClient, AcisError, _parse_acis_value, _parse_payload

FIXTURE = Path(__file__).parent / "fixtures" / "acis_klax.json"


def _load() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_parse_payload_happy_path() -> None:
    fetched = datetime(2026, 4, 23, tzinfo=UTC)
    rows = _parse_payload(_load(), station_icao="KLAX", fetched_at=fetched)
    # 5 days in fixture; the 'M' day still produces a row with high_f=None
    assert len(rows) == 5
    assert {r.station for r in rows} == {"KLAX"}
    assert {r.source for r in rows} == {"nws_acis"}

    by_date = {r.valid_date: r for r in rows}
    # Numeric values in fixture are strings — parser must coerce.
    assert by_date[date(2025, 6, 1)].high_f == pytest.approx(76.0)
    assert by_date[date(2025, 6, 1)].low_f == pytest.approx(60.0)
    # Missing-value day
    assert by_date[date(2025, 6, 4)].high_f is None
    assert by_date[date(2025, 6, 4)].low_f == pytest.approx(58.0)


def test_parse_payload_skips_malformed_entries() -> None:
    payload = {
        "data": [
            ["2025-06-01", "76", "60"],
            "not a list",
            ["bad-date", "76", "60"],
            ["2025-06-02"],  # arity too small
            None,
        ]
    }
    rows = _parse_payload(
        payload, station_icao="KLAX", fetched_at=datetime(2026, 4, 23, tzinfo=UTC)
    )
    assert len(rows) == 1
    assert rows[0].valid_date == date(2025, 6, 1)


def test_parse_payload_error_body_raises_typed_error() -> None:
    """An HTTP-200 ``{"error": ...}`` body is an OUTAGE, not zero rows.

    2026-07-01 audit (Tier 1): returning [] here made a station outage
    indistinguishable from a quiet day — settlement waited forever while
    the cron stayed green. The typed error lets the flow's per-station
    fault isolation log a failure."""
    payload = {"error": "no data available for station"}
    with pytest.raises(AcisError, match=r"KLAX.*no data available"):
        _parse_payload(payload, station_icao="KLAX", fetched_at=datetime(2026, 7, 1, tzinfo=UTC))


def test_parse_payload_error_body_wins_even_with_data_key() -> None:
    """A degraded payload carrying BOTH an error and a data stub must not
    be trusted as data."""
    payload = {"error": "backend timeout", "data": []}
    with pytest.raises(AcisError, match="backend timeout"):
        _parse_payload(payload, station_icao="KMIA", fetched_at=datetime(2026, 7, 1, tzinfo=UTC))


def test_fetch_daily_error_body_raises_end_to_end() -> None:
    async def _run() -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"error": "station unavailable"})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = AcisClient(http)
            with pytest.raises(AcisError, match="station unavailable"):
                await client.fetch_daily(
                    "KLAX",
                    start_date=date(2025, 6, 1),
                    end_date=date(2025, 6, 5),
                )

    asyncio.run(_run())


def test_parse_payload_on_non_dict_returns_empty() -> None:
    assert (
        _parse_payload([], station_icao="KLAX", fetched_at=datetime(2026, 4, 23, tzinfo=UTC)) == []
    )


def test_parse_payload_missing_data_key() -> None:
    assert (
        _parse_payload(
            {"meta": {}}, station_icao="KLAX", fetched_at=datetime(2026, 4, 23, tzinfo=UTC)
        )
        == []
    )


def test_parse_acis_value_handles_sentinels() -> None:
    assert _parse_acis_value(None) is None
    assert _parse_acis_value("M") is None
    assert _parse_acis_value("") is None
    assert _parse_acis_value("76") == 76.0
    assert _parse_acis_value(76.0) == 76.0
    assert _parse_acis_value(76) == 76.0
    assert _parse_acis_value("not a number") is None


def test_fetch_daily_end_to_end_with_mock() -> None:
    async def _run() -> None:
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["sid"] = request.url.params.get("sid", "") or ""
            captured["sdate"] = request.url.params.get("sdate", "") or ""
            captured["edate"] = request.url.params.get("edate", "") or ""
            captured["elems"] = request.url.params.get("elems", "") or ""
            return httpx.Response(200, json=_load())

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = AcisClient(http)
            rows = await client.fetch_daily(
                "KLAX",
                start_date=date(2025, 6, 1),
                end_date=date(2025, 6, 5),
            )

        assert len(rows) == 5
        assert captured["sid"] == "KLAX"
        assert captured["sdate"] == "2025-06-01"
        assert captured["edate"] == "2025-06-05"
        assert captured["elems"] == "maxt,mint"

    asyncio.run(_run())


def test_fetch_daily_unknown_station_raises() -> None:
    async def _run() -> None:
        async with AcisClient() as c:
            with pytest.raises(ValueError, match="unknown station"):
                await c.fetch_daily(
                    "KZZZ",
                    start_date=date(2025, 6, 1),
                    end_date=date(2025, 6, 5),
                )

    asyncio.run(_run())


def test_fetch_daily_reversed_range_raises() -> None:
    async def _run() -> None:
        async with AcisClient() as c:
            with pytest.raises(ValueError, match="precedes"):
                await c.fetch_daily(
                    "KLAX",
                    start_date=date(2025, 6, 10),
                    end_date=date(2025, 6, 1),
                )

    asyncio.run(_run())
