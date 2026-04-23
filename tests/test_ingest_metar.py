"""Tests for the METAR ingest flow."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from kq.clients.metar import MetarClient
from kq.storage.duckdb_store import bootstrap, connect, insert_metar

FIXTURE = Path(__file__).parent / "fixtures" / "metar_sample.json"


async def test_ingest_round_trip_idempotent(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fixture)

    transport = httpx.MockTransport(handler)
    db_path = tmp_path / "metar.duckdb"
    bootstrap(db_path)

    async with httpx.AsyncClient(transport=transport) as http:
        client = MetarClient(http)
        rows = await client.fetch_latest(("KLAX", "KJFK", "KDEN"))

    con = connect(db_path)
    try:
        n1 = insert_metar(con, rows)
        n2 = insert_metar(con, rows)  # re-insert same batch
        stored = con.execute("SELECT COUNT(*) FROM metar_obs").fetchone()
    finally:
        con.close()

    assert n1 == n2 == 3
    # PK on (obs_time, station) means re-insert doesn't grow the table.
    assert stored is not None and stored[0] == 3
