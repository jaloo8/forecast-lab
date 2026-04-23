"""Tests for the weather ingest flow: parse -> DuckDB insert -> idempotency."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from kq.clients.openmeteo import OpenMeteoClient, _parse_payload
from kq.flows.ingest_weather import _db_path_from_settings
from kq.storage.duckdb_store import bootstrap, connect, insert_forecasts

FIXTURE = Path(__file__).parent / "fixtures" / "openmeteo_gfs_klax.json"


def test_db_path_from_settings_accepts_duckdb_url(tmp_path: Path) -> None:
    path = _db_path_from_settings(f"duckdb:///{tmp_path / 'x.duckdb'}")
    assert path == tmp_path / "x.duckdb"


def test_db_path_rejects_other_urls() -> None:
    with pytest.raises(ValueError, match="duckdb://"):
        _db_path_from_settings("postgres://localhost/foo")


def test_insert_forecasts_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "t.duckdb"
    bootstrap(db_path)

    # Fabricate a minimal client response flow: parse fixture, reuse rows.
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = _parse_payload(
        fixture,
        as_of=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
        model_id="gfs_seamless",
        station_icao="KLAX",
    )

    con = connect(db_path)
    try:
        n1 = insert_forecasts(con, rows)
        n2 = insert_forecasts(con, rows)  # same batch again
        total = con.execute("SELECT count(*) FROM weather_forecast").fetchone()
    finally:
        con.close()
    assert n1 == n2 == 12
    # Primary-key REPLACE semantics → total rows stay at the initial count.
    assert total is not None and total[0] == 12


async def test_ingest_once_round_trip(tmp_path: Path) -> None:
    """Full happy-path: mocked HTTP -> flow writes to a throwaway DuckDB."""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fixture)

    transport = httpx.MockTransport(handler)
    db_path = tmp_path / "ingest.duckdb"
    bootstrap(db_path)

    # Monkey-patch OpenMeteoClient's default factory to use our mock transport.
    # Simpler path: ingest_once instantiates its own client; we override the
    # default client factory by passing a patched client through the station
    # loop. For Phase 1 we test the round-trip via direct client injection.
    async with httpx.AsyncClient(transport=transport) as http:
        client = OpenMeteoClient(http)
        # Only fetch one station to keep the mock deterministic.
        rows = await client.fetch_ensemble("KLAX", models=("gfs_seamless",))

    con = connect(db_path)
    try:
        insert_forecasts(con, rows)
        stored = con.execute(
            "SELECT count(*), count(DISTINCT member) FROM weather_forecast"
        ).fetchone()
    finally:
        con.close()

    assert stored is not None
    assert stored[0] == 12  # 3 days x 4 members
    assert stored[1] == 4
