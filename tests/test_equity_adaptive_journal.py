"""Prospective advice must retain original decisions and adverse evidence."""

from __future__ import annotations

import copy
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from kq.equities import adaptive_journal as journal


class Clock(datetime):
    current = datetime(2026, 9, 29, 3, tzinfo=UTC)

    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        return cls.current.astimezone(tz)


def capture() -> dict[str, Any]:
    days = pd.bdate_range("2026-06-29", "2026-09-28")
    days = days[~days.isin(pd.to_datetime(["2026-07-03", "2026-09-07"]))]
    series = []
    for symbol in ("AAA", "SPY"):
        bars = []
        for i, day in enumerate(days):
            price = 100 + i + (i % 2) if symbol == "AAA" else 100
            bars.append(
                dict(
                    begins_at=day.isoformat() + "Z",
                    open_price=price,
                    close_price=price,
                    high_price=price,
                    low_price=price,
                    volume=1_000_000,
                    session="reg",
                )
            )
        series.append(dict(symbol=symbol, interval="day", bounds="regular", bars=bars))
    return dict(
        captured_at="2026-09-29T02:00:00Z",
        price_as_of="2026-09-29T02:00:00Z",
        benchmark="SPY",
        adjustment_type="split",
        universe=["AAA"],
        bars=series,
    )


def reference() -> dict[str, Any]:
    return dict(
        kind="original_pilot_read_only",
        observed_at="2026-09-29T02:59:00Z",
        session_date="2026-09-28",
        source_as_of="2026-09-29T02:00:00Z",
        source_hash="a" * 64,
        states={"AAA": "held"},
    )


@pytest.fixture(autouse=True)
def wall_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    Clock.current = datetime(2026, 9, 29, 3, tzinfo=UTC)
    monkeypatch.setattr(journal, "datetime", Clock)


def test_retry_retains_actual_first_decision_and_reference(tmp_path: Path) -> None:
    first = journal.record(capture(), reference(), tmp_path)
    later = reference()
    later["observed_at"] = "2026-09-29T03:01:00Z"
    Clock.current += timedelta(minutes=2)
    assert journal.record(capture(), later, tmp_path) == first
    assert first["created_at"] == "2026-09-29T03:00:00+00:00"
    assert first["rows"][0]["action"] == "HOLD"
    assert journal.load_latest(tmp_path)["decision"] == first


@pytest.mark.parametrize("change", ["price", "state"])
def test_same_session_revision_preserved_without_replacing_decision(
    tmp_path: Path, change: str
) -> None:
    first = journal.record(capture(), reference(), tmp_path)
    snapshot, ref = capture(), reference()
    if change == "price":
        snapshot["bars"][0]["bars"][-1]["volume"] += 1
    else:
        ref["states"] = {}
    with pytest.raises(ValueError, match="same-session revision"):
        journal.record(snapshot, ref, tmp_path)
    latest = journal.load_latest(tmp_path)
    assert latest["decision"] == first
    assert latest["last_attempt"]["status"] == "failure"
    with sqlite3.connect(tmp_path / "journal.sqlite") as con:
        attempt = json.loads(
            con.execute("SELECT evidence FROM attempts ORDER BY id DESC LIMIT 1").fetchone()[0]
        )
    assert attempt["snapshot"] == snapshot
    assert attempt["reference"] == ref


def next_capture() -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot, ref = capture(), reference()
    snapshot["captured_at"] = snapshot["price_as_of"] = "2026-09-30T02:00:00Z"
    for series in snapshot["bars"]:
        bar = copy.deepcopy(series["bars"][-1])
        bar["begins_at"] = "2026-09-29T00:00:00Z"
        series["bars"].append(bar)
    ref.update(
        observed_at="2026-09-30T02:59:00Z",
        session_date="2026-09-29",
        source_as_of="2026-09-30T02:00:00Z",
    )
    Clock.current = datetime(2026, 9, 30, 3, tzinfo=UTC)
    return snapshot, ref


@pytest.mark.parametrize("change", ["revision", "omission"])
def test_prior_capture_history_cannot_change(tmp_path: Path, change: str) -> None:
    journal.record(capture(), reference(), tmp_path)
    snapshot, ref = next_capture()
    if change == "revision":
        snapshot["bars"][0]["bars"][0]["high_price"] += 1
    else:
        snapshot["bars"][0]["bars"].pop(0)
    with pytest.raises(ValueError, match="history"):
        journal.record(snapshot, ref, tmp_path)
    assert journal.load_latest(tmp_path)["decision"]["session_date"] == "2026-09-28"


def test_new_session_records_and_old_evidence_cannot_rewind(tmp_path: Path) -> None:
    journal.record(capture(), reference(), tmp_path)
    snapshot, ref = next_capture()
    assert journal.record(snapshot, ref, tmp_path)["session_date"] == "2026-09-29"
    with pytest.raises(ValueError):
        journal.record(capture(), reference(), tmp_path)


@pytest.mark.parametrize("change", ["future", "stale", "reference_session", "reference_future"])
def test_invalid_evidence_never_creates_decision(tmp_path: Path, change: str) -> None:
    snapshot, ref = capture(), reference()
    if change == "future":
        snapshot["captured_at"] = "2026-10-01T02:00:00Z"
    elif change == "stale":
        Clock.current += timedelta(days=2)
    elif change == "reference_future":
        ref["observed_at"] = "2026-10-01T00:00:00Z"
    else:
        ref["session_date"] = "2026-09-25"
    with pytest.raises(ValueError):
        journal.record(snapshot, ref, tmp_path)
    result = journal.load_latest(tmp_path)
    assert result["decision"] is None
    assert result["last_attempt"]["status"] == "failure"


def test_foreign_database_and_corrupted_decision_refused(tmp_path: Path) -> None:
    with sqlite3.connect(tmp_path / "journal.sqlite") as con:
        con.execute("CREATE TABLE unrelated(value TEXT)")
    before = (tmp_path / "journal.sqlite").read_bytes()
    with pytest.raises(ValueError, match="foreign"):
        journal.record(capture(), reference(), tmp_path)
    assert (tmp_path / "journal.sqlite").read_bytes() == before
    other = tmp_path / "valid"
    journal.record(capture(), reference(), other)
    with sqlite3.connect(other / "journal.sqlite") as con:
        con.execute("UPDATE decisions SET artifact='{}'")
    with pytest.raises(ValueError, match="digest"):
        journal.load_latest(other)
