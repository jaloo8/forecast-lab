"""Tests for DuckDB storage layer: connect + bootstrap + repositories."""

from __future__ import annotations

from pathlib import Path

from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.forecasts import insert_forecasts
from kq.storage.repositories.kalshi import insert_kalshi_books, upsert_kalshi_markets
from kq.storage.repositories.metar import insert_metar


def test_bootstrap_is_idempotent(tmp_path: Path) -> None:
    """Running bootstrap twice on the same path must not raise."""
    db_path = tmp_path / "a.duckdb"
    bootstrap(db_path)
    bootstrap(db_path)  # must not raise
    con = connect(db_path)
    try:
        tables = {
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
            ).fetchall()
        }
    finally:
        con.close()
    expected = {
        "weather_forecast",
        "metar_obs",
        "kalshi_market",
        "kalshi_book_snap",
        "signal",
        "paper_trade",
        "settlement",
    }
    assert expected.issubset(tables)


def test_bootstrap_safe_on_populated_db(tmp_path: Path) -> None:
    """Bootstrap called on an already-populated DB preserves the data."""
    db_path = tmp_path / "b.duckdb"
    bootstrap(db_path)
    con = connect(db_path)
    try:
        con.execute(
            """
            INSERT INTO metar_obs (obs_time, station, temp_f)
            VALUES ('2026-04-23 00:00:00', 'KLAX', 60.0)
            """
        )
    finally:
        con.close()
    bootstrap(db_path)  # re-run after data landed
    con = connect(db_path)
    try:
        row = con.execute("SELECT COUNT(*) FROM metar_obs").fetchone()
    finally:
        con.close()
    assert row is not None and row[0] == 1


def test_connect_creates_parent_dir(tmp_path: Path) -> None:
    """`connect(...)` must create missing parent directories."""
    deep = tmp_path / "nested" / "more" / "c.duckdb"
    assert not deep.parent.exists()
    con = connect(deep)
    try:
        assert deep.parent.exists()
    finally:
        con.close()


def test_inserts_with_empty_iterable_return_zero(tmp_path: Path) -> None:
    """All 4 inserters must return 0 when given an empty iterable."""
    db_path = tmp_path / "e.duckdb"
    bootstrap(db_path)
    con = connect(db_path)
    try:
        assert insert_forecasts(con, []) == 0
        assert insert_metar(con, []) == 0
        assert upsert_kalshi_markets(con, []) == 0
        assert insert_kalshi_books(con, []) == 0
    finally:
        con.close()
