"""Consistent read-only reference positions for advisory signals."""

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def reference_state(database: Path) -> dict[str, Any]:
    """Read the original pilot without creating a file or changing its strategy."""
    if not database.is_file():
        raise FileNotFoundError(database)
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as con:
        con.execute("BEGIN")
        state = dict(con.execute("SELECT key,value FROM state"))
        if state.get("protocol_id") != "legacy-v1":
            raise ValueError("reference must be the original pilot")
        summary = json.loads(state["last_summary"])
        if (
            not isinstance(summary, dict)
            or summary.get("equity_valid") is not True
            or summary.get("stale_symbols")
        ):
            raise ValueError("reference position evidence is invalid")
        positions = list(con.execute("SELECT symbol FROM paper_trades WHERE exit_date IS NULL"))
        pending = list(con.execute("SELECT symbol FROM paper_orders WHERE status='pending'"))
        names = [row[0] for row in positions + pending]
        if len(names) != len(set(names)):
            raise ValueError("ambiguous duplicate reference position")
        states = {row[0]: "held" for row in positions}
        states.update({row[0]: "pending_entry" for row in pending})
        return dict(
            kind="original_pilot_read_only",
            observed_at=datetime.now(UTC).isoformat(),
            session_date=state["last_processed_session"],
            source_as_of=state["last_source_as_of"],
            source_hash=state["last_hash"],
            states=states,
        )
