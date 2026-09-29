"""Advisory position context cannot mutate or misidentify a paper account."""

import json
import sqlite3
from pathlib import Path

import pytest

from kq.equities.adaptive_reference import reference_state


def pilot(path: Path) -> None:
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE state(key TEXT PRIMARY KEY,value TEXT)")
        con.executemany(
            "INSERT INTO state VALUES(?,?)",
            [
                ("protocol_id", "legacy-v1"),
                ("last_hash", "a" * 64),
                ("last_source_as_of", "2026-09-29T01:00:00Z"),
                ("last_processed_session", "2026-09-28"),
                ("last_summary", json.dumps({"equity_valid": True, "stale_symbols": []})),
            ],
        )
        con.execute("CREATE TABLE paper_trades(symbol TEXT,exit_date TEXT)")
        con.executemany(
            "INSERT INTO paper_trades VALUES(?,?)", [("AAPL", None), ("XOM", "2026-09-25")]
        )
        con.execute("CREATE TABLE paper_orders(symbol TEXT,status TEXT)")
        con.executemany(
            "INSERT INTO paper_orders VALUES(?,?)", [("MSFT", "pending"), ("AAPL", "filled")]
        )


def test_reference_reads_only_open_and_pending_without_writing(tmp_path: Path) -> None:
    path = tmp_path / "paper.sqlite"
    pilot(path)
    before = path.read_bytes()
    reference = reference_state(path)
    assert reference["states"] == {"AAPL": "held", "MSFT": "pending_entry"}
    assert reference["kind"] == "original_pilot_read_only"
    assert reference["session_date"] == "2026-09-28"
    assert reference["observed_at"] > reference["source_as_of"]
    assert path.read_bytes() == before


@pytest.mark.parametrize("failure", ["foreign", "invalid", "duplicate", "malformed"])
def test_ambiguous_or_invalid_reference_is_refused(tmp_path: Path, failure: str) -> None:
    path = tmp_path / "paper.sqlite"
    pilot(path)
    with sqlite3.connect(path) as con:
        if failure == "foreign":
            con.execute("UPDATE state SET value='other' WHERE key='protocol_id'")
        elif failure == "invalid":
            con.execute(
                "UPDATE state SET value=? WHERE key='last_summary'",
                (json.dumps({"equity_valid": False}),),
            )
        elif failure == "malformed":
            con.execute("UPDATE state SET value='[]' WHERE key='last_summary'")
        else:
            con.execute("INSERT INTO paper_orders VALUES('AAPL','pending')")
    before = path.read_bytes()
    with pytest.raises(ValueError):
        reference_state(path)
    assert path.read_bytes() == before


def test_missing_reference_does_not_create_database(tmp_path: Path) -> None:
    path = tmp_path / "paper.sqlite"
    with pytest.raises(FileNotFoundError):
        reference_state(path)
    assert not path.exists()
