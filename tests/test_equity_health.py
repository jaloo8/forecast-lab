"""Read-only collection health, including scheduler proof and weekend timing."""

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from kq.equities.events import append_events
from kq.equities.health import collection_health

SUNDAY = datetime(2026, 9, 28, 2, tzinfo=UTC)  # Sunday 19:00 Pacific.
MONDAY_CLOSED = datetime(2026, 9, 28, 22, tzinfo=UTC)


def _paper(tmp_path: Path) -> None:
    source = {"captured_at": "2026-09-26T03:00:00Z", "benchmark": "SPY", "bars": []}
    (tmp_path / "snapshot-friday.json").write_text(json.dumps(source), encoding="utf-8")
    canonical = json.dumps(source, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    with sqlite3.connect(tmp_path / "paper.sqlite") as con:
        con.executescript("""
            CREATE TABLE state(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE snapshots(source_as_of TEXT,snapshot_hash TEXT,imported_at TEXT);
            CREATE TABLE paper_orders(id INTEGER,status TEXT,reserved REAL);
            CREATE TABLE paper_trades(id INTEGER,exit_date TEXT,net_pnl REAL);
            CREATE TABLE forecasts(id INTEGER,created_at TEXT,symbol TEXT,horizon INTEGER,
                exit_date TEXT,stock_return REAL,benchmark_return REAL);
        """)
        state = {
            "last_hash": digest, "last_source_as_of": "2026-09-26T03:00:00+00:00",
            "last_processed_session": "2026-09-25",
            "last_summary": json.dumps({
                "cash": 100.0, "reserved_cash": 0.0, "pnl": 0.0,
                "pending_count": 0, "open_count": 0, "closed_count": 0,
                "forecast_by_horizon": [],
            }),
        }
        con.executemany("INSERT INTO state VALUES (?,?)", state.items())
        con.execute("INSERT INTO snapshots VALUES (?,?,?)", (
            state["last_source_as_of"], digest, "2026-09-26T03:10:00+00:00"
        ))


def _audit(tmp_path: Path, **changes: object) -> Path:
    audit: dict[str, object] = {
        "captured_at": "2026-09-27T22:00:00Z", "configured": True,
        "last_run_at": None, "last_result": None,
        "next_due_at": "2026-09-29T01:00:00Z",
        "detail": "Weekdays 18:00 Pacific; first scheduled run pending",
    }
    audit.update(changes)
    path = tmp_path / "scheduler-audit.json"
    path.write_text(json.dumps(audit), encoding="utf-8")
    return path


def _statuses(tmp_path: Path, now: datetime) -> dict[str, str]:
    frame = collection_health(tmp_path, now)
    assert list(frame.columns) == ["check", "status", "detail", "as_of"]
    assert frame["as_of"].dt.tz is not None
    assert set(frame["check"]) == {
        "paper_import", "paper_session", "event_archive", "scheduler",
    }
    return dict(zip(frame["check"], frame["status"], strict=True))


def test_missing_inputs_are_explicit_and_create_no_files(tmp_path: Path) -> None:
    assert _statuses(tmp_path, SUNDAY) == {
        "paper_import": "never_run", "paper_session": "never_run",
        "event_archive": "never_run", "scheduler": "unverified",
    }
    assert list(tmp_path.iterdir()) == []


def test_sunday_no_new_session_and_configured_schedule_is_not_a_run(tmp_path: Path) -> None:
    _paper(tmp_path)
    _audit(tmp_path)
    before = (tmp_path / "paper.sqlite").read_bytes()
    statuses = _statuses(tmp_path, SUNDAY)
    assert statuses["paper_import"] == "ok"
    assert statuses["paper_session"] == "no_new_session"
    assert statuses["scheduler"] == "configured_unverified"
    assert (tmp_path / "paper.sqlite").read_bytes() == before
    later = _statuses(tmp_path, MONDAY_CLOSED)
    assert later["paper_session"] == "awaiting_refresh"
    assert later["scheduler"] == "configured_unverified"
    after_due = _statuses(tmp_path, datetime(2026, 9, 29, 2, tzinfo=UTC))
    assert after_due["paper_session"] == "stale"
    assert after_due["scheduler"] == "never_run"


def test_older_gap_is_stale_even_before_today_refresh(tmp_path: Path) -> None:
    _paper(tmp_path)
    with sqlite3.connect(tmp_path / "paper.sqlite") as con:
        con.execute("UPDATE state SET value='2026-09-24' WHERE key='last_processed_session'")
    assert _statuses(tmp_path, MONDAY_CLOSED)["paper_session"] == "stale"


def test_failed_run_is_distinct_from_success_and_unverified(tmp_path: Path) -> None:
    _audit(tmp_path, last_run_at="2026-09-27T01:00:00Z", last_result="failure")
    assert _statuses(tmp_path, SUNDAY)["scheduler"] == "failure"
    _audit(tmp_path, last_run_at="2026-09-27T01:00:00Z", last_result="success")
    assert _statuses(tmp_path, SUNDAY)["scheduler"] == "ok"


@pytest.mark.parametrize("damage", ["invalid_json", "future_audit", "future_run", "naive_run"])
def test_corrupt_or_future_scheduler_audit_is_failure(tmp_path: Path, damage: str) -> None:
    path = _audit(tmp_path)
    if damage == "invalid_json":
        path.write_text("{broken", encoding="utf-8")
    elif damage == "future_audit":
        _audit(tmp_path, captured_at="2026-09-30T00:00:00Z")
    elif damage == "future_run":
        _audit(tmp_path, last_run_at="2026-09-30T00:00:00Z", last_result="success")
    else:
        _audit(tmp_path, last_run_at="2026-09-27T01:00:00", last_result="success")
    assert _statuses(tmp_path, SUNDAY)["scheduler"] == "failure"


def test_event_observation_freshness_and_database_read_only(tmp_path: Path) -> None:
    event = {
        "symbol": "AAA", "title": "Release", "url": "https://example.org/release",
        "kind": "news", "content": "", "published_at": "2026-09-25T20:00:00Z",
        "retrieved_at": "2026-09-26T00:00:00Z",
    }
    append_events(tmp_path / "events.sqlite", [event], datetime(2026, 9, 26, 1, tzinfo=UTC))
    before = (tmp_path / "events.sqlite").read_bytes()
    assert _statuses(tmp_path, SUNDAY)["event_archive"] == "ok"
    assert _statuses(tmp_path, datetime(2026, 9, 30, 6, tzinfo=UTC))["event_archive"] == "stale"
    assert (tmp_path / "events.sqlite").read_bytes() == before


def test_future_and_corrupt_event_archive_are_failures(tmp_path: Path) -> None:
    event = {
        "symbol": "AAA", "title": "Release", "url": "https://example.org/release",
        "kind": "news", "published_at": "2026-09-25T20:00:00Z",
        "retrieved_at": "2026-09-26T00:00:00Z",
    }
    path = tmp_path / "events.sqlite"
    append_events(path, [event], datetime(2026, 9, 26, 1, tzinfo=UTC))
    with sqlite3.connect(path) as con:
        con.execute("UPDATE event_meta SET last_observed_at='2026-10-01T00:00:00Z'")
    assert _statuses(tmp_path, SUNDAY)["event_archive"] == "failure"
    path.write_bytes(b"not a SQLite database")
    assert _statuses(tmp_path, SUNDAY)["event_archive"] == "failure"


def test_corrupt_or_future_paper_state_and_naive_now(tmp_path: Path) -> None:
    _paper(tmp_path)
    with sqlite3.connect(tmp_path / "paper.sqlite") as con:
        con.execute("UPDATE snapshots SET imported_at='2026-10-01T00:00:00Z'")
    assert _statuses(tmp_path, SUNDAY)["paper_import"] == "failure"
    with pytest.raises(ValueError, match="aware"):
        collection_health(tmp_path, datetime(2026, 9, 27))
