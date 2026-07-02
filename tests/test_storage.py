"""Tests for DuckDB storage layer: connect + bootstrap + repositories."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from kq.storage import duckdb_store
from kq.storage.duckdb_store import bootstrap, connect, is_lock_conflict
from kq.storage.repositories.forecasts import insert_forecasts
from kq.storage.repositories.kalshi import insert_kalshi_books, upsert_kalshi_markets
from kq.storage.repositories.metar import insert_metar
from kq.storage.repositories.ndfd import insert_ndfd_forecasts


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
        "ndfd_forecast",
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
        assert insert_ndfd_forecasts(con, []) == 0
    finally:
        con.close()


# ------------------------------------------------- read-only + lock handling
# 2026-07-01 audit hardening: read-only consumers (doctor, health-check,
# dashboard) must never create a database, and transient writer-lock
# conflicts get a bounded retry + a distinct predicate for "busy" semantics.


def test_connect_read_only_never_creates_db(tmp_path: Path) -> None:
    missing = tmp_path / "nowhere" / "missing.duckdb"
    with pytest.raises(duckdb.Error):
        connect(missing, read_only=True)
    assert not missing.exists()
    assert not missing.parent.exists()  # not even the parent dir


def test_connect_read_only_opens_existing_db(tmp_path: Path) -> None:
    db_path = tmp_path / "ro.duckdb"
    bootstrap(db_path)
    con = connect(db_path, read_only=True)
    try:
        row = con.execute("SELECT COUNT(*) FROM metar_obs").fetchone()
        assert row is not None and row[0] == 0
        with pytest.raises(duckdb.Error):
            con.execute("INSERT INTO metar_obs (obs_time, station) VALUES (now(), 'KLAX')")
    finally:
        con.close()


_LOCK_MSG = (
    'IO Error: Could not set lock on file "x.duckdb": Conflicting lock is held '
    "in PID 1234. See https://duckdb.org/docs/connect/concurrency"
)


def test_is_lock_conflict_predicate() -> None:
    assert is_lock_conflict(duckdb.IOException(_LOCK_MSG)) is True
    assert (
        is_lock_conflict(duckdb.IOException('IO Error: Cannot open database "x" in read-only mode'))
        is False
    )
    assert is_lock_conflict(RuntimeError("Conflicting lock is held")) is False


def test_connect_retries_lock_conflict_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two lock conflicts then success — connect() absorbs the transient
    collision (cron writers landing on the same tick) with short backoff."""
    calls: list[float] = []
    attempts = {"n": 0}
    sentinel = object()

    def _fake_connect(_path: str, read_only: bool = False) -> object:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise duckdb.IOException(_LOCK_MSG)
        return sentinel

    monkeypatch.setattr(duckdb_store.duckdb, "connect", _fake_connect)
    monkeypatch.setattr(duckdb_store.time, "sleep", calls.append)
    out = connect(tmp_path / "busy.duckdb", read_only=False)
    assert out is sentinel
    assert attempts["n"] == 3
    assert len(calls) == 2  # slept between attempts, never after the last


def test_connect_gives_up_after_bounded_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = {"n": 0}

    def _always_locked(_path: str, read_only: bool = False) -> object:
        attempts["n"] += 1
        raise duckdb.IOException(_LOCK_MSG)

    monkeypatch.setattr(duckdb_store.duckdb, "connect", _always_locked)
    monkeypatch.setattr(duckdb_store.time, "sleep", lambda _s: None)
    with pytest.raises(duckdb.IOException):
        connect(tmp_path / "busy.duckdb", lock_retries=3)
    assert attempts["n"] == 3


def test_connect_does_not_retry_non_lock_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing/corrupt DB error is NOT the transient class — no retry."""
    attempts = {"n": 0}

    def _broken(_path: str, read_only: bool = False) -> object:
        attempts["n"] += 1
        raise duckdb.IOException("IO Error: Cannot open database: not a valid DuckDB file")

    monkeypatch.setattr(duckdb_store.duckdb, "connect", _broken)
    with pytest.raises(duckdb.IOException):
        connect(tmp_path / "corrupt.duckdb")
    assert attempts["n"] == 1


# ------------------------------------ weather_forecast.member (2026-07-01 T2)
# The schema documented "NULL for deterministic" but `member` sits in the PK
# (implicitly NOT NULL) — the first deterministic ingest would crash. Honest
# resolution: sentinel member = -1 with a column DEFAULT, PK unchanged.


def test_weather_forecast_member_defaults_to_deterministic_sentinel(tmp_path: Path) -> None:
    """A deterministic row inserted WITHOUT a member value must land with the
    -1 sentinel (column DEFAULT), not crash on the PK's NOT NULL. Fails on
    the old schema (omitted member -> NULL -> constraint violation)."""
    db_path = tmp_path / "member.duckdb"
    bootstrap(db_path)
    con = connect(db_path)
    try:
        con.execute(
            """
            INSERT INTO weather_forecast
            (as_of, run_time, model, station, valid_date, forecast_high_f, forecast_low_f)
            VALUES ('2026-07-01 00:00:00', '2026-07-01 00:00:00', 'hrrr',
                    'KLAX', '2026-07-02', 78.5, 62.0)
            """
        )
        row = con.execute("SELECT member FROM weather_forecast WHERE model = 'hrrr'").fetchone()
    finally:
        con.close()
    assert row is not None and row[0] == -1


def test_weather_forecast_member_explicit_null_still_rejected(tmp_path: Path) -> None:
    """Explicit NULL member remains a constraint error (PK semantics kept):
    writers must map deterministic rows to the documented -1 sentinel."""
    db_path = tmp_path / "member_null.duckdb"
    bootstrap(db_path)
    con = connect(db_path)
    try:
        with pytest.raises(duckdb.Error):
            con.execute(
                """
                INSERT INTO weather_forecast
                (as_of, run_time, model, member, station, valid_date,
                 forecast_high_f, forecast_low_f)
                VALUES ('2026-07-01 00:00:00', '2026-07-01 00:00:00', 'hrrr',
                        NULL, 'KLAX', '2026-07-02', 78.5, 62.0)
                """
            )
    finally:
        con.close()


def test_weather_forecast_member_sentinel_upsert_idempotent(tmp_path: Path) -> None:
    """Deterministic (-1) rows keep INSERT OR REPLACE idempotency on the PK —
    the property the sentinel resolution was chosen to preserve."""
    db_path = tmp_path / "member_upsert.duckdb"
    bootstrap(db_path)
    con = connect(db_path)
    try:
        for high in (78.5, 79.5):  # second write replaces, not duplicates
            con.execute(
                """
                INSERT OR REPLACE INTO weather_forecast
                (as_of, run_time, model, member, station, valid_date,
                 forecast_high_f, forecast_low_f)
                VALUES ('2026-07-01 00:00:00', '2026-07-01 00:00:00', 'hrrr',
                        -1, 'KLAX', '2026-07-02', ?, 62.0)
                """,
                (high,),
            )
        rows = con.execute("SELECT COUNT(*), MAX(forecast_high_f) FROM weather_forecast").fetchone()
    finally:
        con.close()
    assert rows == (1, 79.5)
