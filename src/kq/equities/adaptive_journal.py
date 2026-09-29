"""Immutable advisory observations; no paper or brokerage execution."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from kq.equities.adaptive import METHOD_HASH, PROTOCOL, signals
from kq.equities.events import _validate
from kq.equities.forward_study import _records
from kq.equities.research import _results, _timestamp, daily_bars

APPLICATION_ID = 1094992210


def _encoded(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_encoded(value).encode()).hexdigest()


def _check(con: sqlite3.Connection, *, initialize: bool = False) -> None:
    app_id = con.execute("PRAGMA application_id").fetchone()[0]
    tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if app_id == 0 and not tables and initialize:
        con.execute(f"PRAGMA application_id={APPLICATION_ID}")
        con.execute(
            "CREATE TABLE decisions(session TEXT PRIMARY KEY, artifact TEXT NOT NULL, "
            "digest TEXT NOT NULL, evidence TEXT NOT NULL)"
        )
        con.execute(
            "CREATE TABLE attempts(id INTEGER PRIMARY KEY, attempted_at TEXT NOT NULL, "
            "status TEXT NOT NULL, error TEXT NOT NULL, evidence TEXT NOT NULL)"
        )
    elif app_id != APPLICATION_ID or tables != {"decisions", "attempts"}:
        raise ValueError("foreign or damaged adaptive journal")


def _latest(con: sqlite3.Connection) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    row = con.execute(
        "SELECT artifact,digest,evidence,session FROM decisions ORDER BY session DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None, None
    artifact, digest, evidence = json.loads(row[0]), row[1], json.loads(row[2])
    if (
        _digest(artifact) != digest
        or artifact.get("source_hash") != _digest(evidence["snapshot"])
        or artifact.get("session_date") != row[3]
    ):
        raise ValueError("adaptive journal digest mismatch")
    if artifact.get("reference_hash") != _digest(evidence["reference"]):
        raise ValueError("adaptive reference digest mismatch")
    if artifact.get("method_hash") != METHOD_HASH or artifact.get("protocol") != PROTOCOL:
        raise ValueError("adaptive method changed")
    return artifact, evidence


def _history(snapshot: dict[str, Any]) -> dict[tuple[str, str], list[float]]:
    valid = {
        (row.symbol, row.session_date.isoformat()) for row in daily_bars(snapshot).itertuples()
    }
    history = {}
    for series in _results(snapshot.get("bars", []), "bars"):
        for bar in series["bars"]:
            key = (series["symbol"], _timestamp(bar["begins_at"], "begins_at").date().isoformat())
            if key in valid:
                history[key] = [
                    float(bar[field])
                    for field in ("open_price", "high_price", "low_price", "close_price", "volume")
                ]
    return history


def _validate_reference(reference: dict[str, Any], session: str, now: datetime) -> None:
    if (
        reference.get("kind") != "original_pilot_read_only"
        or reference.get("session_date") != session
    ):
        raise ValueError("reference pilot session does not match research capture")
    observed = _timestamp(reference.get("observed_at"), "reference.observed_at")
    source = _timestamp(reference.get("source_as_of"), "reference.source_as_of")
    if not source <= observed <= now or now - observed > timedelta(minutes=5):
        raise ValueError("reference observation is stale or future")
    if now - source > timedelta(hours=24):
        raise ValueError("reference source is stale")
    digest = reference.get("source_hash")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(c not in "0123456789abcdef" for c in digest)
    ):
        raise ValueError("invalid reference source hash")


def _prepare(
    snapshot: dict[str, Any], reference: dict[str, Any], con: sqlite3.Connection, now: datetime
) -> dict[str, Any]:
    captured = _timestamp(snapshot.get("captured_at"), "captured_at")
    if not now - timedelta(hours=24) <= captured <= now:
        raise ValueError("capture is stale or future")
    bars = daily_bars(snapshot)
    spy = bars.loc[(bars.symbol == "SPY") & bars.volume.gt(0)]
    if spy.empty:
        raise ValueError("SPY history unavailable")
    session = spy.session_date.max().isoformat()
    _validate_reference(reference, session, now)
    previous, evidence = _latest(con)
    if previous is not None and evidence is not None:
        if session < previous["session_date"] or captured < _timestamp(
            previous["input_captured_at"], "prior"
        ):
            raise ValueError("older evidence cannot rewind journal")
        if session == previous["session_date"]:
            original_ref = {k: v for k, v in evidence["reference"].items() if k != "observed_at"}
            incoming_ref = {k: v for k, v in reference.items() if k != "observed_at"}
            if _digest(snapshot) != previous["source_hash"] or original_ref != incoming_ref:
                raise ValueError("same-session revision preserved; original decision retained")
            return previous
        old, new = _history(evidence["snapshot"]), _history(snapshot)
        if any(new.get(key) != values for key, values in old.items()):
            raise ValueError("prior history revised or missing")
    frame = signals(snapshot, reference["states"], now=now)
    news = snapshot.get("news", [])
    if not isinstance(news, list) or any(not isinstance(event, dict) for event in news):
        raise ValueError("news must be a list of source records")
    for event in news:
        _validate(event, captured)
    rows = _records(frame)
    for row in rows:
        row["event_refs"] = [
            dict(
                url=e["url"], retrieved_at=e["retrieved_at"], content_hash=_validate(e, captured)[3]
            )
            for e in news
            if e["symbol"] == row["symbol"]
        ]
    artifact = dict(
        created_at=now.isoformat(),
        input_captured_at=captured.isoformat(),
        session_date=session,
        source_hash=_digest(snapshot),
        reference_hash=_digest(reference),
        method_hash=METHOD_HASH,
        protocol=PROTOCOL,
        reference_kind=reference["kind"],
        reference=reference,
        rows=rows,
        source_errors=snapshot.get("source_errors", []),
        news=news,
        mode="advisory_only",
    )
    evidence_text = _encoded(dict(snapshot=snapshot, reference=reference))
    con.execute(
        "INSERT INTO decisions VALUES(?,?,?,?)",
        (session, _encoded(artifact), _digest(artifact), evidence_text),
    )
    return artifact


def record(snapshot: dict[str, Any], reference: dict[str, Any], root: Path) -> dict[str, Any]:
    """Record current advisory evidence transactionally, preserving failed attempts.

    The original pilot supplies reference states only. No account is created
    and no BUY/SELL row becomes an order. Call this writer only on A8.
    """
    now = datetime.now(UTC)
    evidence = _encoded(dict(snapshot=snapshot, reference=reference))
    root.mkdir(parents=True, exist_ok=True)
    error: ValueError | None = None
    artifact: dict[str, Any] = {}
    with closing(sqlite3.connect(root / "journal.sqlite")) as con, con:
        con.execute("BEGIN IMMEDIATE")
        _check(con, initialize=True)
        try:
            artifact = _prepare(snapshot, reference, con, now)
        except (ValueError, KeyError, TypeError) as exc:
            error = ValueError(str(exc))
        con.execute(
            "INSERT INTO attempts(attempted_at,status,error,evidence) VALUES(?,?,?,?)",
            (now.isoformat(), "failure" if error else "success", str(error or ""), evidence),
        )
    if error is not None:
        raise error
    return artifact


def load_latest(root: Path) -> dict[str, Any]:
    """Return verified latest advice and latest attempt through SQLite read-only mode."""
    path = root / "journal.sqlite"
    if not path.is_file():
        raise FileNotFoundError(path)
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as con:
        con.execute("BEGIN")
        _check(con)
        artifact, _ = _latest(con)
        attempt = con.execute(
            "SELECT attempted_at,status,error FROM attempts ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(
        decision=artifact,
        last_attempt=dict(zip(("attempted_at", "status", "error"), attempt, strict=True))
        if attempt
        else None,
    )
