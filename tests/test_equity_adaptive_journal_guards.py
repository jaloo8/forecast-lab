"""Journal must retain hostile source evidence without revising accepted decisions."""

from __future__ import annotations

import copy
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from kq.equities import adaptive_journal as journal
from tests.test_equity_adaptive_journal import Clock, capture, next_capture, reference


@pytest.fixture(autouse=True)
def wall_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    Clock.current = datetime(2026, 9, 29, 3, tzinfo=UTC)
    monkeypatch.setattr(journal, "datetime", Clock)


def test_synthetic_duplicate_cannot_mask_revised_real_history(tmp_path: Path) -> None:
    accepted_snapshot = capture()
    first = journal.record(accepted_snapshot, reference(), tmp_path)
    snapshot, ref = next_capture()
    original = copy.deepcopy(snapshot["bars"][0]["bars"][5])
    snapshot["bars"][0]["bars"][5]["high_price"] += 1
    original["synthetic"] = True
    snapshot["bars"][0]["bars"].append(original)
    with pytest.raises(ValueError, match="prior history revised"):
        journal.record(snapshot, ref, tmp_path)
    latest = journal.load_latest(tmp_path)
    assert latest["decision"] == first
    assert latest["last_attempt"]["status"] == "failure"


@pytest.mark.parametrize("bad", ["nan_price", "malformed_bars"])
def test_invalid_snapshot_attempt_is_recorded_without_replacing_decision(
    tmp_path: Path, bad: str
) -> None:
    first = journal.record(capture(), reference(), tmp_path)
    snapshot = capture()
    if bad == "nan_price":
        snapshot["bars"][0]["bars"][-1]["high_price"] = float("nan")
    else:
        snapshot["bars"] = {"bad": "shape"}
    with pytest.raises(ValueError):
        journal.record(snapshot, reference(), tmp_path)
    latest = journal.load_latest(tmp_path)
    assert latest["decision"] == first
    assert latest["last_attempt"]["status"] == "failure"
    with sqlite3.connect(tmp_path / "journal.sqlite") as con:
        stored = con.execute("SELECT evidence FROM attempts ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert "nan" in stored if bad == "nan_price" else "bad" in stored
    json.loads(stored, parse_constant=lambda value: pytest.fail(f"nonstandard JSON {value}"))
