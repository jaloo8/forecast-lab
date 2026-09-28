"""Immutable, point-in-time evidence versions in an isolated SQLite file.

``events_as_of`` returns symbol, title, url, kind, content, content_hash,
published_at, retrieved_at, first_seen, as_of. All timestamps are aware UTC;
one latest-known version is returned per (symbol, url, kind).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd

APPLICATION_ID = 1162953806  # "EVNT"
COLUMNS = [
    "symbol", "title", "url", "kind", "content", "content_hash",
    "published_at", "retrieved_at", "first_seen", "as_of",
]


def _aware(value: Any, field: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field} must be an aware ISO timestamp") from exc
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be an aware timestamp")
    return value.astimezone(UTC)


def _path(path: Path) -> Path:
    if path.name.lower() == "paper.sqlite":
        raise ValueError("paper.sqlite is reserved for the paper ledger")
    return path


def _validate(event: dict[str, Any], observed: datetime) -> tuple[str, ...]:
    symbol = event.get("symbol")
    title = event.get("title")
    url = event.get("url")
    kind = event.get("kind")
    content = event.get("content", "")
    if not isinstance(symbol, str) or re.fullmatch(r"[A-Z][A-Z0-9.-]*", symbol) is None:
        raise ValueError("event symbol must be an uppercase ticker")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("event title required")
    if not isinstance(url, str):
        raise ValueError("event URL must be HTTPS")
    parsed = urlparse(url)
    if (parsed.scheme != "https" or not parsed.hostname
            or parsed.username is not None or parsed.password is not None):
        raise ValueError("event URL must be HTTPS without credentials")
    if kind not in ("news", "filing"):
        raise ValueError("event kind must be news or filing")
    if not isinstance(content, str):
        raise ValueError("event content must be text")
    published = _aware(event.get("published_at"), "published_at")
    retrieved = _aware(event.get("retrieved_at"), "retrieved_at")
    if retrieved < published:
        raise ValueError("retrieved_at precedes published_at")
    if observed < published or observed < retrieved:
        raise ValueError("observed_at precedes source timestamps")
    canonical = json.dumps(
        [symbol, url, kind, title, content], ensure_ascii=False, separators=(",", ":")
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return (
        symbol, url, kind, digest, title, content,
        published.isoformat(), retrieved.isoformat(), observed.isoformat(),
    )


def _check_database(connection: sqlite3.Connection) -> None:
    app_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
    tables = {
        str(row[0]) for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    if app_id != APPLICATION_ID and (app_id != 0 or tables):
        raise ValueError("foreign SQLite database refused")
    if app_id == APPLICATION_ID and "event_version" not in tables:
        raise ValueError("foreign or damaged event database refused")


def append_events(path: Path, events: list[dict[str, Any]], observed_at: datetime) -> int:
    """Append validated versions atomically; return new-version count.

    Observation time must be actual wall time or earlier, no earlier than source
    times, and no earlier than the latest observation already in this database.
    Identical later observations preserve the original ``first_seen``.
    """
    path = _path(path)
    observed = _aware(observed_at, "observed_at")
    if observed > datetime.now(UTC):
        raise ValueError("future observed_at")
    if not isinstance(events, list) or any(not isinstance(item, dict) for item in events):
        raise ValueError("events must be a list of objects")
    rows = [_validate(event, observed) for event in events]
    versions: dict[tuple[str, str, str], str] = {}
    for row in rows:
        key = (row[0], row[1], row[2])
        if key in versions and versions[key] != row[3]:
            raise ValueError("conflicting versions in one observation batch")
        versions[key] = row[3]
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        _check_database(connection)
        connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS event_version ("
            "symbol TEXT NOT NULL, url TEXT NOT NULL, kind TEXT NOT NULL, "
            "content_hash TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL, "
            "published_at TEXT NOT NULL, retrieved_at TEXT NOT NULL, first_seen TEXT NOT NULL, "
            "PRIMARY KEY (symbol, url, kind, content_hash))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS event_observation ("
            "symbol TEXT NOT NULL, url TEXT NOT NULL, kind TEXT NOT NULL, "
            "first_seen TEXT NOT NULL, content_hash TEXT NOT NULL, "
            "published_at TEXT NOT NULL, retrieved_at TEXT NOT NULL, "
            "PRIMARY KEY (symbol, url, kind, first_seen))"
        )
        columns = {
            str(item[1]) for item in connection.execute("PRAGMA table_info(event_observation)")
        }
        for name in ("published_at", "retrieved_at"):
            if name not in columns:
                connection.execute(f"ALTER TABLE event_observation ADD COLUMN {name} TEXT")
                connection.execute(
                    f"UPDATE event_observation SET {name}=(SELECT v.{name} FROM event_version v "
                    "WHERE v.symbol=event_observation.symbol AND v.url=event_observation.url "
                    "AND v.kind=event_observation.kind "
                    "AND v.content_hash=event_observation.content_hash)"
                )
        connection.execute(
            "INSERT OR IGNORE INTO event_observation "
            "SELECT symbol,url,kind,first_seen,content_hash,published_at,retrieved_at "
            "FROM event_version"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS event_meta (id INTEGER PRIMARY KEY CHECK(id=1), "
            "last_observed_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT OR IGNORE INTO event_meta VALUES (1, COALESCE("
            "(SELECT MAX(first_seen) FROM event_observation), ?))", (observed.isoformat(),)
        )
        watermark = connection.execute(
            "SELECT last_observed_at FROM event_meta WHERE id=1"
        ).fetchone()[0]
        if observed < datetime.fromisoformat(str(watermark)):
            raise ValueError("backdated observation refused")
        inserted = 0
        for row in rows:
            conflict = connection.execute(
                "SELECT content_hash,published_at FROM event_observation "
                "WHERE symbol=? AND url=? AND kind=? "
                "AND first_seen=?", (row[0], row[1], row[2], row[8])
            ).fetchone()
            if conflict is not None and conflict != (row[3], row[6]):
                raise ValueError("conflicting versions at same observation time")
            current = connection.execute(
                "SELECT content_hash,published_at FROM event_observation "
                "WHERE symbol=? AND url=? AND kind=? "
                "ORDER BY first_seen DESC LIMIT 1", row[:3]
            ).fetchone()
            if current is not None and current == (row[3], row[6]):
                continue
            connection.execute(
                "INSERT OR IGNORE INTO event_version VALUES (?,?,?,?,?,?,?,?,?)", row
            )
            connection.execute(
                "INSERT INTO event_observation VALUES (?,?,?,?,?,?,?)",
                (row[0], row[1], row[2], row[8], row[3], row[6], row[7]),
            )
            inserted += 1
        connection.execute(
            "UPDATE event_meta SET last_observed_at=? WHERE id=1", (observed.isoformat(),)
        )
        return inserted


def events_as_of(path: Path, as_of: datetime) -> pd.DataFrame:
    """Read latest versions visible at UTC ``as_of`` without changing the DB."""
    path = _path(path)
    queried = _aware(as_of, "as_of")
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        _check_database(connection)
        if int(connection.execute("PRAGMA application_id").fetchone()[0]) != APPLICATION_ID:
            return pd.DataFrame(columns=COLUMNS)
        has_observations = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_observation'"
        ).fetchone() is not None
        if has_observations:
            raw = connection.execute(
                "SELECT v.symbol,v.title,v.url,v.kind,v.content,v.content_hash,"
                "o.published_at,o.retrieved_at,o.first_seen FROM event_observation o "
                "JOIN event_version v ON v.symbol=o.symbol AND v.url=o.url "
                "AND v.kind=o.kind AND v.content_hash=o.content_hash "
                "WHERE o.first_seen<=? AND o.first_seen=("
                "SELECT MAX(x.first_seen) FROM event_observation x WHERE x.symbol=o.symbol "
                "AND x.url=o.url AND x.kind=o.kind AND x.first_seen<=?) "
                "ORDER BY v.symbol,v.url,v.kind", (queried.isoformat(), queried.isoformat()),
            ).fetchall()
        else:
            raw = connection.execute(
                "SELECT symbol,title,url,kind,content,content_hash,"
                "published_at,retrieved_at,first_seen FROM ("
                "SELECT *, ROW_NUMBER() OVER (PARTITION BY symbol,url,kind "
                "ORDER BY first_seen DESC,content_hash DESC) AS rank FROM event_version "
                "WHERE first_seen<=?) WHERE rank=1 ORDER BY symbol,url,kind",
                (queried.isoformat(),),
            ).fetchall()
    records = [
        (*row[:6], *[datetime.fromisoformat(str(value)) for value in row[6:]], queried)
        for row in raw
    ]
    return pd.DataFrame(records, columns=COLUMNS)


def main() -> None:
    """Archive ``news`` from a captured JSON export at the actual wall clock."""
    parser = argparse.ArgumentParser(description="Archive timestamped stock evidence")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.database.resolve():
        parser.error("input and database must be separate files")
    payload: Any = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("news"), list):
        parser.error("input must be a captured JSON object with a news list")
    inserted = append_events(args.database, payload["news"], datetime.now(UTC))
    print(f"Archived {inserted} new event versions in {args.database}")


if __name__ == "__main__":
    main()
