"""Tests for the Open-Meteo ensemble client."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from kq.clients.openmeteo import (
    MODEL_ID_MAP,
    EnsembleForecast,
    OpenMeteoClient,
    _coerce_run_time,
    _parse_payload,
)
from kq.clients.stations import STATIONS, STATIONS_BY_ICAO

FIXTURE = Path(__file__).parent / "fixtures" / "openmeteo_gfs_klax.json"


def _load_fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_stations_match_kalshi_tickers() -> None:
    tickers = {s.kalshi_series_ticker for s in STATIONS}
    assert len(tickers) == len(STATIONS), "each station must have a unique ticker"
    # KNYC not KJFK since PR-C (audit root cause #4: NY settles on Central Park).
    for icao in ("KLAX", "KNYC", "KMDW", "KMIA", "KDEN", "KAUS"):
        assert icao in STATIONS_BY_ICAO


def test_parse_payload_produces_rows_per_member() -> None:
    payload = _load_fixture()
    as_of = datetime(2026, 4, 23, 14, 0, tzinfo=UTC)
    rows = _parse_payload(payload, as_of=as_of, model_id="gfs_seamless", station_icao="KLAX")

    # 3 days x 4 members (control 0, 1, 2, 3) = 12 rows
    assert len(rows) == 12
    assert all(isinstance(r, EnsembleForecast) for r in rows)
    assert all(r.model == "gefs" for r in rows)
    assert {r.member for r in rows} == {0, 1, 2, 3}
    assert {r.valid_date for r in rows} == {
        date(2026, 4, 23),
        date(2026, 4, 24),
        date(2026, 4, 25),
    }


def test_parse_payload_values_align() -> None:
    payload = _load_fixture()
    as_of = datetime(2026, 4, 23, 14, 0, tzinfo=UTC)
    rows = _parse_payload(payload, as_of=as_of, model_id="gfs_seamless", station_icao="KLAX")
    by_key = {(r.member, r.valid_date): r for r in rows}

    # member 2, 2026-04-24 — from the fixture:
    #   temperature_2m_max_member02[1] = 74.1
    #   temperature_2m_min_member02[1] = 58.4
    row = by_key[(2, date(2026, 4, 24))]
    assert row.forecast_high_f == pytest.approx(74.1)
    assert row.forecast_low_f == pytest.approx(58.4)

    # Control run (no explicit member) promoted to member 0.
    row0 = by_key[(0, date(2026, 4, 23))]
    assert row0.forecast_high_f == pytest.approx(74.5)
    assert row0.forecast_low_f == pytest.approx(58.1)


def test_parse_empty_payload_returns_nothing() -> None:
    rows = _parse_payload(
        {"daily": {"time": []}},
        as_of=datetime(2026, 4, 23, tzinfo=UTC),
        model_id="gfs_seamless",
        station_icao="KLAX",
    )
    assert rows == []


def test_coerce_run_time_rounds_to_cycle() -> None:
    # 14:37 UTC rounds to the 12Z cycle.
    as_of = datetime(2026, 4, 23, 14, 37, 42, tzinfo=UTC)
    rt = _coerce_run_time({}, fallback=as_of)
    assert rt == datetime(2026, 4, 23, 12, 0, tzinfo=UTC)


def test_unsupported_model_raises() -> None:
    async def _check() -> None:
        async with OpenMeteoClient() as c:
            await c.fetch_ensemble("KLAX", models=("bogus_model",))

    with pytest.raises(ValueError, match="unsupported model"):
        asyncio.run(_check())


def test_unknown_station_raises() -> None:
    async def _check() -> None:
        async with OpenMeteoClient() as c:
            await c.fetch_ensemble("KZZZ")

    with pytest.raises(ValueError, match="unknown station"):
        asyncio.run(_check())


async def test_fetch_ensemble_end_to_end_with_mock() -> None:
    fixture = _load_fixture()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fixture)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = OpenMeteoClient(http)
        rows = await client.fetch_ensemble("KLAX", models=("gfs_seamless",))

    # 3 days x 4 members = 12 rows for a single model
    assert len(rows) == 12
    assert {r.station for r in rows} == {"KLAX"}
    assert {r.model for r in rows} == {"gefs"}


def test_model_id_map_covers_expected_models() -> None:
    assert MODEL_ID_MAP["gfs_seamless"] == "gefs"
    assert MODEL_ID_MAP["ecmwf_ifs025"] == "ecmwf"
