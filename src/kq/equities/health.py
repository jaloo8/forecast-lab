"""Read-only, point-in-time collection health for the isolated stock pilot.

``collection_health`` returns check,status,detail,as_of (aware UTC). Statuses
describe observed local evidence; scheduler configuration alone never proves a
successful automated run. Weekday session expectations are heuristic because
this module has no exchange-holiday calendar.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from kq.equities.dashboard_data import load_dashboard
from kq.equities.events import APPLICATION_ID
from kq.equities.research import daily_bars

_NY = ZoneInfo("America/New_York")
_PACIFIC = ZoneInfo("America/Los_Angeles")
_COLUMNS = ["check", "status", "detail", "as_of"]


def _aware(value: Any, label: str, now: datetime) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{label} is not an aware timestamp") from exc
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} is not an aware timestamp")
    stamp = value.astimezone(UTC)
    if stamp > now:
        raise ValueError(f"{label} is in the future")
    return stamp


def _latest_expected(now: datetime) -> date:
    local = now.astimezone(_NY)
    day = local.date()
    if local.weekday() >= 5 or local.time() < time(16):
        day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _latest_due(now: datetime) -> datetime:
    local = now.astimezone(_PACIFIC)
    day = local.date()
    if local.weekday() >= 5 or local.time() < time(18):
        day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return datetime.combine(day, time(18), _PACIFIC).astimezone(UTC)


def _paper(  # noqa: PLR0911, PLR0912
    data_dir: Path, now: datetime
) -> tuple[tuple[str, str], tuple[str, str]]:
    if not (data_dir / "paper.sqlite").is_file():
        return ("never_run", "No paper ledger exists."), ("never_run", "No paper session exists.")
    try:
        loaded = load_dashboard(data_dir)
        latest = loaded["latest_snapshot"]
        source = _aware(latest["source_as_of"], "paper source", now)
        imported = _aware(latest["imported_at"], "paper import", now)
        if source > imported:
            raise ValueError("paper source is later than its import")
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
        detail = f"Paper ledger validation failed: {exc}"
        return ("failure", detail), ("failure", detail)
    imported_row = (
        "ok",
        f"Committed source {source.isoformat()}; imported {imported.isoformat()}.",
    )
    try:
        stored_day = loaded["state"].get("last_processed_session")
        if stored_day:
            session = date.fromisoformat(stored_day)
        elif isinstance(loaded["source"], dict):
            bars = daily_bars(loaded["source"])
            spy = bars.loc[bars["symbol"] == "SPY", "session_date"]
            if spy.empty:
                return imported_row, ("unverified", "Matching source has no completed SPY session.")
            session = max(spy)
        else:
            return imported_row, ("unverified", "No matching source or processed-session date.")
        expected = _latest_expected(now)
        note = "Weekday heuristic; exchange holidays are not modeled."
        if session > expected:
            return imported_row, (
                "failure",
                f"Processed session {session} is ahead of expected {expected}.",
            )
        if session < expected:
            previous = expected - timedelta(days=1)
            while previous.weekday() >= 5:
                previous -= timedelta(days=1)
            due = datetime.combine(expected, time(18), _PACIFIC).astimezone(UTC)
            if session == previous and now < due:
                return imported_row, (
                    "awaiting_refresh",
                    f"Last session {session}; {expected} refresh due {due.isoformat()}. {note}",
                )
            return imported_row, ("stale", f"Last session {session}; expected {expected}. {note}")
        local = now.astimezone(_NY)
        if local.weekday() >= 5 or local.time() < time(16):
            return imported_row, (
                "no_new_session",
                f"Last completed weekday session {session}; {note}",
            )
        return imported_row, ("ok", f"Last processed session {session}; {note}")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return imported_row, ("failure", f"Processed-session evidence invalid: {exc}")


def _events(data_dir: Path, now: datetime) -> tuple[str, str]:
    path = data_dir / "events.sqlite"
    if not path.is_file():
        return "never_run", "No event archive exists."
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as con:
            con.execute("PRAGMA query_only=ON")
            if int(con.execute("PRAGMA application_id").fetchone()[0]) != APPLICATION_ID:
                raise ValueError("unexpected event database identity")
            count = int(con.execute("SELECT COUNT(*) FROM event_version").fetchone()[0])
            row = con.execute("SELECT last_observed_at FROM event_meta WHERE id=1").fetchone()
        if not count or row is None:
            return "never_run", "Event archive has no recorded observations."
        observed = _aware(row[0], "event observation", now)
        age = now - observed
        detail = f"{count} archived versions; last observation {observed.isoformat()}. "
        detail += "This does not prove complete daily news or filing coverage."
        return ("stale" if age > timedelta(hours=72) else "ok"), detail
    except (OSError, ValueError, TypeError, sqlite3.Error) as exc:
        return "failure", f"Event archive validation failed: {exc}"


def _scheduler(data_dir: Path, now: datetime) -> tuple[str, str]:  # noqa: PLR0911, PLR0912
    path = data_dir / "scheduler-audit.json"
    if not path.is_file():
        return "unverified", "No captured scheduler audit; configuration and runs unverified."
    try:
        audit = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(audit, dict) or type(audit.get("configured")) is not bool:
            raise ValueError("malformed scheduler audit")
        captured = _aware(audit.get("captured_at"), "scheduler audit", now)
        next_due_raw = audit.get("next_due_at")
        next_due = None
        if next_due_raw is not None:
            next_due = datetime.fromisoformat(str(next_due_raw).replace("Z", "+00:00"))
            if next_due.tzinfo is None or next_due.utcoffset() is None:
                raise ValueError("next_due_at is not aware")
            next_due = next_due.astimezone(UTC)
            if next_due <= captured:
                raise ValueError("next_due_at precedes scheduler audit")
        result, run_raw = audit.get("last_result"), audit.get("last_run_at")
        if (result is None) != (run_raw is None) or result not in {None, "success", "failure"}:
            raise ValueError("incomplete scheduler run evidence")
        run = _aware(run_raw, "scheduler run", now) if run_raw is not None else None
        if run is not None and run > captured:
            raise ValueError("scheduler run postdates audit capture")
        if not audit["configured"]:
            return "unverified", "Scheduler is not confirmed configured."
        due = next_due if next_due is not None else _latest_due(now)
        if result == "failure":
            assert run is not None
            return "failure", f"Captured scheduler audit reports failed run at {run.isoformat()}."
        if run is None:
            if due > captured and now >= due:
                return "never_run", f"Scheduled run due {due.isoformat()} with no success recorded."
            return (
                "configured_unverified",
                "Schedule configured; no successful automated run recorded.",
            )
        if now >= due and run < due:
            return (
                "stale",
                f"Last successful run {run.isoformat()}; next run due {due.isoformat()}.",
            )
        return "ok", f"Captured scheduler audit reports successful run {run.isoformat()}."
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return "failure", f"Scheduler audit invalid: {exc}"


def collection_health(data_dir: Path, now: datetime) -> pd.DataFrame:
    """Read local evidence without creating files; evaluate at injected aware UTC time.

    Statuses include ok, no_new_session, awaiting_refresh, never_run,
    configured_unverified, unverified, stale and failure. Scheduler success
    requires a captured run.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    current = now.astimezone(UTC)
    paper_import, paper_session = _paper(data_dir, current)
    checks = [
        ("paper_import", *paper_import),
        ("paper_session", *paper_session),
        ("event_archive", *_events(data_dir, current)),
        ("scheduler", *_scheduler(data_dir, current)),
    ]
    frame = pd.DataFrame(
        [(check, status, detail, current) for check, status, detail in checks], columns=_COLUMNS
    )
    frame["as_of"] = pd.to_datetime(frame["as_of"], utc=True)
    return frame
