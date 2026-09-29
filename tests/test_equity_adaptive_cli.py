"""Runner preserves invalid collection attempts and refuses local mirror writes."""

import importlib.util
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from kq.equities import adaptive_journal as journal
from kq.equities.adaptive_journal import load_latest
from tests.test_equity_adaptive_journal import Clock, capture, reference
from tests.test_equity_adaptive_reference import pilot


def runner():
    spec = importlib.util.spec_from_file_location(
        "adaptive_cli", "scripts/run_adaptive_research.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_logs_unparseable_capture(tmp_path: Path) -> None:
    snapshot = tmp_path / "bad.json"
    snapshot.write_text("not json")
    database = tmp_path / "paper.sqlite"
    pilot(database)
    root = tmp_path / "adaptive-research"
    with pytest.raises(ValueError):
        runner().main(
            ["--snapshot", str(snapshot), "--reference-ledger", str(database), "--root", str(root)]
        )
    assert load_latest(root)["last_attempt"]["status"] == "failure"
    assert load_latest(root)["decision"] is None


def test_cli_refuses_mirror_before_writing(tmp_path: Path) -> None:
    (tmp_path / "READ_ONLY_MIRROR.txt").write_text("server authoritative")
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps({}))
    root = tmp_path / "adaptive-research"
    with pytest.raises(ValueError, match="mirror"):
        runner().main(
            [
                "--snapshot",
                str(snapshot),
                "--reference-ledger",
                str(tmp_path / "paper.sqlite"),
                "--root",
                str(root),
            ]
        )
    assert not root.exists()


@pytest.mark.parametrize("bad_reference", ["foreign", "[]", "null"])
def test_cli_logs_foreign_reference_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad_reference: str
) -> None:
    Clock.current = datetime(2026, 9, 29, 3, tzinfo=UTC)
    monkeypatch.setattr(journal, "datetime", Clock)
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps(capture()))
    database = tmp_path / "foreign.sqlite"
    if bad_reference == "foreign":
        with sqlite3.connect(database) as con:
            con.execute("CREATE TABLE unrelated(value TEXT)")
    else:
        pilot(database)
        with sqlite3.connect(database) as con:
            con.execute("UPDATE state SET value=? WHERE key='last_summary'", (bad_reference,))
    root = tmp_path / "adaptive-research"
    first = journal.record(capture(), reference(), root)
    with pytest.raises(ValueError):
        runner().main(
            ["--snapshot", str(snapshot), "--reference-ledger", str(database), "--root", str(root)]
        )
    assert load_latest(root)["last_attempt"]["status"] == "failure"
    assert load_latest(root)["decision"] == first
