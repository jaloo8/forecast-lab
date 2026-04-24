"""Tests for the observed-data backfill flow + storage."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from kq.clients.acis import _parse_payload
from kq.flows.backfill_observed import backfill
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.observed import insert_observed

FIXTURE = Path(__file__).parent / "fixtures" / "acis_klax.json"


def test_insert_observed_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "obs.duckdb"
    bootstrap(db_path)
    fetched = datetime(2026, 4, 23, tzinfo=UTC)
    rows = _parse_payload(
        json.loads(FIXTURE.read_text(encoding="utf-8")),
        station_icao="KLAX",
        fetched_at=fetched,
    )
    con = connect(db_path)
    try:
        n1 = insert_observed(con, rows)
        n2 = insert_observed(con, rows)  # re-insert
        stored = con.execute("SELECT COUNT(*) FROM weather_observed").fetchone()
    finally:
        con.close()
    assert n1 == n2 == 5
    # PK on (station, valid_date) means re-insert doesn't grow the table.
    assert stored is not None and stored[0] == 5


def test_insert_observed_empty_returns_zero(tmp_path: Path) -> None:
    db_path = tmp_path / "e.duckdb"
    bootstrap(db_path)
    con = connect(db_path)
    try:
        assert insert_observed(con, []) == 0
    finally:
        con.close()


def test_insert_observed_preserves_missing_highs(tmp_path: Path) -> None:
    db_path = tmp_path / "m.duckdb"
    bootstrap(db_path)
    fetched = datetime(2026, 4, 23, tzinfo=UTC)
    rows = _parse_payload(
        json.loads(FIXTURE.read_text(encoding="utf-8")),
        station_icao="KLAX",
        fetched_at=fetched,
    )
    con = connect(db_path)
    try:
        insert_observed(con, rows)
        row = con.execute(
            "SELECT high_f, low_f FROM weather_observed WHERE valid_date = '2025-06-04'"
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    assert row[0] is None  # the 'M' day
    assert row[1] == pytest.approx(58.0)


def test_backfill_rejects_reversed_date_range(tmp_path: Path) -> None:
    async def _run() -> None:
        with pytest.raises(ValueError, match="precedes"):
            await backfill(
                start_date=date(2025, 6, 10),
                end_date=date(2025, 6, 1),
                db_path=tmp_path / "b.duckdb",
            )

    asyncio.run(_run())
