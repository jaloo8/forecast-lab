"""Advanced event version, source metadata, and migration regressions."""

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kq.equities.events import APPLICATION_ID, append_events, events_as_of

OBSERVED = datetime(2026, 9, 28, 2, tzinfo=UTC)


def event(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "symbol": "MSFT",
        "title": "Filing",
        "url": "https://www.sec.gov/Archives/a",
        "published_at": "2026-09-27T12:00:00Z",
        "retrieved_at": "2026-09-28T00:00:00Z",
        "kind": "filing",
        "content": "Initial text",
    }
    row.update(changes)
    return row


def test_restored_prior_text_becomes_latest_without_erasing_original(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite"
    second = OBSERVED + timedelta(minutes=10)
    restored = OBSERVED + timedelta(minutes=20)
    append_events(db, [event()], OBSERVED)
    append_events(db, [event(content="Corrected text")], second)
    assert append_events(db, [event(retrieved_at=restored.isoformat())], restored) == 1
    assert events_as_of(db, OBSERVED).iloc[0]["content"] == "Initial text"
    assert events_as_of(db, second).iloc[0]["content"] == "Corrected text"
    latest = events_as_of(db, restored).iloc[0]
    assert latest["content"] == "Initial text"
    assert latest["first_seen"] == restored
    assert latest["retrieved_at"] == restored


def test_same_current_content_with_later_retrieval_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite"
    append_events(db, [event()], OBSERVED)
    later = OBSERVED + timedelta(minutes=10)
    assert append_events(db, [event(retrieved_at=later.isoformat())], later) == 0
    row = events_as_of(db, later).iloc[0]
    assert row["first_seen"] == OBSERVED
    assert row["retrieved_at"] == datetime(2026, 9, 28, 0, tzinfo=UTC)


def test_corrected_publication_time_is_a_new_metadata_observation(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite"
    append_events(db, [event()], OBSERVED)
    later = OBSERVED + timedelta(minutes=10)
    assert (
        append_events(
            db, [event(published_at="2026-09-28T00:30:00Z", retrieved_at=later.isoformat())], later
        )
        == 1
    )
    assert events_as_of(db, OBSERVED).iloc[0]["published_at"] == datetime(
        2026, 9, 27, 12, tzinfo=UTC
    )
    current = events_as_of(db, later).iloc[0]
    assert current["published_at"] == datetime(2026, 9, 28, 0, 30, tzinfo=UTC)
    assert current["first_seen"] == later


def test_same_observation_time_cannot_change_publication(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite"
    append_events(db, [event()], OBSERVED)
    with pytest.raises(ValueError, match="same observation time"):
        append_events(
            db,
            [event(published_at="2026-09-28T00:30:00Z", retrieved_at="2026-09-28T01:00:00Z")],
            OBSERVED,
        )


def test_idempotent_observation_advances_backdate_watermark(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite"
    append_events(db, [event()], OBSERVED)
    later = OBSERVED + timedelta(hours=1)
    assert append_events(db, [event()], later) == 0
    with pytest.raises(ValueError, match="backdated"):
        append_events(db, [event(content="Late revision")], OBSERVED + timedelta(minutes=30))
    assert events_as_of(db, later).iloc[0]["content"] == "Initial text"


def test_existing_version_database_is_migrated_without_losing_history(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite"
    first = OBSERVED - timedelta(minutes=10)
    with sqlite3.connect(db) as connection:
        connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        connection.execute(
            "CREATE TABLE event_version (symbol TEXT,url TEXT,kind TEXT,content_hash TEXT,"
            "title TEXT,content TEXT,published_at TEXT,retrieved_at TEXT,first_seen TEXT,"
            "PRIMARY KEY(symbol,url,kind,content_hash))"
        )
        connection.execute(
            "INSERT INTO event_version VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "MSFT",
                "https://www.sec.gov/Archives/a",
                "filing",
                "original-hash",
                "Filing",
                "Initial text",
                "2026-09-27T12:00:00+00:00",
                "2026-09-28T00:00:00+00:00",
                first.isoformat(),
            ),
        )
    assert events_as_of(db, first).iloc[0]["content"] == "Initial text"
    assert append_events(db, [event(content="Corrected text")], OBSERVED) == 1
    assert events_as_of(db, first).iloc[0]["content"] == "Initial text"
    assert events_as_of(db, OBSERVED).iloc[0]["content"] == "Corrected text"
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM event_version").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM event_observation").fetchone()[0] == 2
