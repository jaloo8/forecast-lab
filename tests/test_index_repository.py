"""Guarded-upsert tests for the index_daily repository (Phase C)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from kq.clients.yahoo_chart import IndexDailyBar
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.index_daily import insert_index_daily, load_daily_closes


def _bar(
    d: date,
    close: float | None,
    *,
    symbol: str = "SPX",
    fetched: datetime | None = None,
) -> IndexDailyBar:
    return IndexDailyBar(
        symbol=symbol,
        valid_date=d,
        open=close,
        high=close,
        low=close,
        close=close,
        source="yahoo_chart",
        fetched_at=fetched or datetime(2026, 7, 2, 23, 0, tzinfo=UTC),
    )


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "t.duckdb"
    bootstrap(path)
    return path


def test_insert_is_idempotent_on_symbol_date(db: Path) -> None:
    con = connect(db)
    try:
        rows = [_bar(date(2026, 7, 1), 7455.0), _bar(date(2026, 7, 2), 7483.24)]
        assert insert_index_daily(con, rows) == 2
        assert insert_index_daily(con, rows) == 2  # re-run: no dupes, no crash
        n = con.execute("SELECT COUNT(*) FROM index_daily").fetchone()
        assert n is not None and n[0] == 2
    finally:
        con.close()


def test_null_never_overwrites_stored_value(db: Path) -> None:
    """A degraded vendor payload (NULL close) must not wipe stored truth;
    the fetched_at watermark still advances so staleness stays observable."""
    con = connect(db)
    try:
        insert_index_daily(con, [_bar(date(2026, 7, 2), 7483.24)])
        later = datetime(2026, 7, 3, 1, 0, tzinfo=UTC)
        insert_index_daily(con, [_bar(date(2026, 7, 2), None, fetched=later)])
        row = con.execute(
            "SELECT close, fetched_at FROM index_daily WHERE valid_date = DATE '2026-07-02'"
        ).fetchone()
        assert row is not None
        assert row[0] == pytest.approx(7483.24)
        assert row[1] == datetime(2026, 7, 3, 1, 0)  # naive UTC
    finally:
        con.close()


def test_real_value_updates_stored_value(db: Path) -> None:
    """Late vendor corrections are the point of the trailing re-fetch."""
    con = connect(db)
    try:
        insert_index_daily(con, [_bar(date(2026, 7, 2), 7483.00)])
        insert_index_daily(con, [_bar(date(2026, 7, 2), 7483.24)])
        row = con.execute("SELECT close FROM index_daily").fetchone()
        assert row is not None and row[0] == pytest.approx(7483.24)
    finally:
        con.close()


def test_load_daily_closes_sorted_and_null_free(db: Path) -> None:
    con = connect(db)
    try:
        insert_index_daily(
            con,
            [
                _bar(date(2026, 7, 2), 7483.24),
                _bar(date(2026, 6, 30), 7440.0),
                _bar(date(2026, 7, 1), None),  # unhealed vendor gap — excluded
                _bar(date(2026, 7, 1), 30000.0, symbol="NDX"),  # other symbol — excluded
            ],
        )
        df = load_daily_closes(con, "SPX")
        assert list(df["valid_date"]) == [date(2026, 6, 30), date(2026, 7, 2)]
        assert df["close"].to_list() == pytest.approx([7440.0, 7483.24])
    finally:
        con.close()


def test_empty_batch_is_a_noop(db: Path) -> None:
    con = connect(db)
    try:
        assert insert_index_daily(con, []) == 0
    finally:
        con.close()
