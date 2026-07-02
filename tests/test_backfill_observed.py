"""Tests for the observed-data backfill flow + storage."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from kq.clients.acis import DailyClimateObservation, _parse_payload
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


def _obs(
    *,
    high_f: float | None,
    low_f: float | None,
    fetched_at: datetime,
) -> DailyClimateObservation:
    return DailyClimateObservation(
        station="KLAX",
        valid_date=date(2026, 6, 11),
        high_f=high_f,
        low_f=low_f,
        source="nws_acis",
        fetched_at=fetched_at,
    )


def test_insert_observed_missing_reserve_cannot_wipe_truth(tmp_path: Path) -> None:
    """Settlement-truth guard: ACIS re-serving 'M' (parsed as NULL) for a day
    we already ingested must NOT null the stored high/low — the old blind
    INSERT OR REPLACE wiped truth on every trailing-window re-fetch.
    ``fetched_at`` still updates so staleness monitoring sees the pull."""
    db_path = tmp_path / "g.duckdb"
    bootstrap(db_path)
    t1 = datetime(2026, 6, 12, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 6, 13, 10, 0, tzinfo=UTC)
    con = connect(db_path)
    try:
        insert_observed(con, [_obs(high_f=78.0, low_f=54.0, fetched_at=t1)])
        insert_observed(con, [_obs(high_f=None, low_f=None, fetched_at=t2)])
        row = con.execute(
            "SELECT high_f, low_f, fetched_at FROM weather_observed "
            "WHERE station = 'KLAX' AND valid_date = '2026-06-11'"
        ).fetchone()
        count = con.execute("SELECT COUNT(*) FROM weather_observed").fetchone()
    finally:
        con.close()
    assert row is not None
    assert row[0] == pytest.approx(78.0)  # truth survives the 'M' re-serve
    assert row[1] == pytest.approx(54.0)
    assert row[2] == t2.replace(tzinfo=None)  # but the pull is recorded
    assert count is not None and count[0] == 1


def test_insert_observed_late_correction_updates_value(tmp_path: Path) -> None:
    """Real values still overwrite: late corrections are the entire point of
    the trailing re-fetch window — only NULL is blocked."""
    db_path = tmp_path / "c.duckdb"
    bootstrap(db_path)
    t1 = datetime(2026, 6, 12, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 6, 13, 10, 0, tzinfo=UTC)
    con = connect(db_path)
    try:
        insert_observed(con, [_obs(high_f=78.0, low_f=54.0, fetched_at=t1)])
        insert_observed(con, [_obs(high_f=79.0, low_f=53.0, fetched_at=t2)])
        row = con.execute(
            "SELECT high_f, low_f FROM weather_observed "
            "WHERE station = 'KLAX' AND valid_date = '2026-06-11'"
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    assert row[0] == pytest.approx(79.0)
    assert row[1] == pytest.approx(53.0)


def test_insert_observed_null_can_fill_in_later(tmp_path: Path) -> None:
    """The guard is one-directional: a day first seen as 'M' (NULL) is
    filled in when the real value arrives on a later pull."""
    db_path = tmp_path / "f.duckdb"
    bootstrap(db_path)
    t1 = datetime(2026, 6, 12, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 6, 13, 10, 0, tzinfo=UTC)
    con = connect(db_path)
    try:
        insert_observed(con, [_obs(high_f=None, low_f=None, fetched_at=t1)])
        insert_observed(con, [_obs(high_f=78.0, low_f=54.0, fetched_at=t2)])
        row = con.execute(
            "SELECT high_f, low_f FROM weather_observed "
            "WHERE station = 'KLAX' AND valid_date = '2026-06-11'"
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    assert row[0] == pytest.approx(78.0)
    assert row[1] == pytest.approx(54.0)


def test_backfill_rejects_reversed_date_range(tmp_path: Path) -> None:
    async def _run() -> None:
        with pytest.raises(ValueError, match="precedes"):
            await backfill(
                start_date=date(2025, 6, 10),
                end_date=date(2025, 6, 1),
                db_path=tmp_path / "b.duckdb",
            )

    asyncio.run(_run())
