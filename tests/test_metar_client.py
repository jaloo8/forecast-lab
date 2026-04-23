"""Tests for the METAR client."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from kq.clients.metar import MetarClient, _c_to_f, _parse_one, _parse_payload

FIXTURE = Path(__file__).parent / "fixtures" / "metar_sample.json"


def _load_fixture() -> list[dict[str, object]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_c_to_f_known_values() -> None:
    assert _c_to_f(0.0) == 32.0
    assert _c_to_f(100.0) == 212.0
    assert _c_to_f(-40.0) == -40.0
    assert _c_to_f(None) is None


def test_c_to_f_preserves_precision() -> None:
    # 15.6 C = 60.08 F
    assert _c_to_f(15.6) == pytest.approx(60.08, abs=0.01)


def test_parse_one_happy_path() -> None:
    payload = _load_fixture()
    obs = _parse_one(payload[0])
    assert obs is not None
    assert obs.station == "KLAX"
    assert obs.obs_time == datetime.fromtimestamp(1776930780, tz=UTC)
    assert obs.temp_f == pytest.approx(60.08, abs=0.01)
    assert obs.dewpoint_f == pytest.approx(53.06, abs=0.01)
    assert obs.wind_kt == 9.0
    assert obs.pressure_mb == pytest.approx(1016.6)


def test_parse_one_falls_back_from_slp_to_altim() -> None:
    payload = _load_fixture()
    # KDEN in fixture has slp=null but altim=1023.
    obs = _parse_one(payload[2])
    assert obs is not None
    assert obs.station == "KDEN"
    assert obs.temp_f is None
    assert obs.pressure_mb == pytest.approx(1023.0)


def test_parse_one_rejects_bad_shape() -> None:
    assert _parse_one({}) is None
    assert _parse_one({"icaoId": "KLAX"}) is None  # no obsTime
    assert _parse_one({"icaoId": "KLAX", "obsTime": "not-a-number"}) is None


def test_parse_payload_skips_bad_rows() -> None:
    rows = _parse_payload([{"icaoId": "KLAX"}, "not a dict", None])
    assert rows == []


def test_parse_payload_rejects_non_list() -> None:
    assert _parse_payload({"icaoId": "KLAX"}) == []


async def test_fetch_latest_end_to_end_with_mock() -> None:
    fixture = _load_fixture()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fixture)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = MetarClient(http)
        rows = await client.fetch_latest(("KLAX", "KJFK", "KDEN"))

    assert len(rows) == 3
    assert {r.station for r in rows} == {"KLAX", "KJFK", "KDEN"}


async def test_fetch_latest_empty_tuple_short_circuits() -> None:
    # No stations -> no HTTP call and empty list.
    async with MetarClient() as client:
        rows = await client.fetch_latest(())
    assert rows == []
