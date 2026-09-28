"""The event archive must never backdate later observations or revisions."""

import json
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kq.equities.events import append_events, events_as_of, main

OBSERVED = datetime(2026, 9, 28, 2, tzinfo=UTC)


def event(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "symbol": "MSFT", "title": "Filing", "url": "https://www.sec.gov/Archives/a",
        "published_at": "2026-09-27T12:00:00Z", "retrieved_at": "2026-09-28T00:00:00Z",
        "kind": "filing", "content": "Initial text",
    }
    row.update(changes)
    return row


def test_first_seen_idempotency_and_query_before_observation(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite"
    assert append_events(db, [event()], OBSERVED) == 1
    assert append_events(db, [event()], OBSERVED + timedelta(hours=1)) == 0
    assert events_as_of(db, OBSERVED - timedelta(microseconds=1)).empty
    result = events_as_of(db, OBSERVED)
    assert len(result) == 1
    assert list(result.columns) == [
        "symbol", "title", "url", "kind", "content", "content_hash",
        "published_at", "retrieved_at", "first_seen", "as_of",
    ]
    assert result.iloc[0]["first_seen"] == OBSERVED
    assert result.iloc[0]["as_of"] == OBSERVED
    assert len(result.iloc[0]["content_hash"]) == 64


def test_revision_is_new_version_visible_only_when_seen(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite"
    append_events(db, [event()], OBSERVED)
    revised = OBSERVED + timedelta(hours=1)
    assert append_events(db, [event(content="Corrected text")], revised) == 1
    assert events_as_of(db, OBSERVED).iloc[0]["content"] == "Initial text"
    assert events_as_of(db, revised).iloc[0]["content"] == "Corrected text"
    assert events_as_of(db, revised).iloc[0]["first_seen"] == revised


@pytest.mark.parametrize("changes", [
    {"published_at": "2026-09-29T00:00:00Z"},
    {"retrieved_at": "2026-09-29T00:00:00Z"},
    {"published_at": "2026-09-27T12:00:00"},
    {"retrieved_at": "2026-09-26T00:00:00Z"},
    {"url": "http://example.com/x"},
    {"url": "https://user:secret@example.com/x"},
    {"url": "https://@example.com/x"},
    {"symbol": ""},
    {"title": " "},
    {"kind": "tweet"},
])
def test_invalid_observations_are_rejected(tmp_path: Path, changes: dict[str, str]) -> None:
    db = tmp_path / "events.sqlite"
    with pytest.raises(ValueError):
        append_events(db, [event(**changes)], OBSERVED)
    assert not db.exists()


def test_invalid_batch_is_atomic(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite"
    with pytest.raises(ValueError):
        append_events(db, [event(), event(url="http://invalid")], OBSERVED)
    assert not db.exists()


def test_backdated_append_cannot_change_past(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite"
    append_events(db, [event()], OBSERVED)
    with pytest.raises(ValueError, match="backdated"):
        append_events(db, [event(content="Past revision")], OBSERVED - timedelta(hours=1))
    with pytest.raises(ValueError, match="backdated"):
        append_events(db, [event(symbol="AAPL", url="https://example.com/a")],
                      OBSERVED - timedelta(hours=1))
    assert events_as_of(db, OBSERVED).iloc[0]["content"] == "Initial text"


def test_rejects_naive_times_and_paper_database(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="aware"):
        append_events(tmp_path / "events.sqlite", [event()], datetime(2026, 9, 28, 4))
    with pytest.raises(ValueError, match="aware"):
        events_as_of(tmp_path / "events.sqlite", datetime(2026, 9, 28, 4))
    with pytest.raises(ValueError, match="paper"):
        append_events(tmp_path / "paper.sqlite", [event()], OBSERVED)
    with pytest.raises(ValueError, match="future"):
        append_events(tmp_path / "events.sqlite", [event()], datetime.now(UTC) + timedelta(days=1))


def test_foreign_database_is_not_modified(tmp_path: Path) -> None:
    db = tmp_path / "renamed.sqlite"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE paper_trade (id INTEGER)")
    with pytest.raises(ValueError, match="foreign"):
        append_events(db, [event()], OBSERVED)
    with sqlite3.connect(db) as connection:
        tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        assert tables == [
            ("paper_trade",)
        ]


def test_read_and_write_close_database_handles(tmp_path: Path) -> None:
    db = tmp_path / "events.sqlite"
    append_events(db, [event()], OBSERVED)
    events_as_of(db, OBSERVED)
    db.rename(tmp_path / "closed.sqlite")


def test_cli_rejects_input_as_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    capture = tmp_path / "capture.json"
    original = json.dumps({"news": [event()]})
    capture.write_text(original, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["events", "--input", str(capture),
                                    "--database", str(capture)])
    with pytest.raises(SystemExit):
        main()
    assert capture.read_text(encoding="utf-8") == original

