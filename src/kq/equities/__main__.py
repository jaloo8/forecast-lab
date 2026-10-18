"""Run the offline stock paper pilot: python -m kq.equities --help."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from kq.equities.ledger import update_ledger
from kq.equities.report import render_report
from kq.equities.research import daily_bars, scan


def main(argv: list[str] | None = None) -> int:
    """Validate a fresh export, update paper records, and write a local report."""
    parser = argparse.ArgumentParser(description="Stock research and paper trading only")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, default=Path("data/equities/paper.sqlite"))
    parser.add_argument("--report", type=Path, default=Path("data/equities/report.html"))
    parser.add_argument("--recover-missed-sessions", action="store_true")
    args = parser.parse_args(argv)
    try:
        if any(
            (folder / "READ_ONLY_MIRROR.txt").exists() for folder in args.ledger.resolve().parents
        ):
            raise ValueError("local mirror is read-only; run paper writers on A8")
        paths = [path.resolve() for path in (args.snapshot, args.ledger, args.report)]
        if len(set(paths)) != 3:
            raise ValueError("Snapshot, ledger and report must have different paths")
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)
        snapshot_hash = hashlib.sha256(canonical.encode()).hexdigest()
        as_of = datetime.fromisoformat(snapshot["captured_at"])
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("captured_at must include its timezone")
        now = datetime.now(UTC)
        if as_of > now + timedelta(minutes=5) or now - as_of > timedelta(hours=24):
            raise ValueError("Import requires a fresh capture from the last 24 hours")
        research = scan(snapshot)
        bars = daily_bars(snapshot)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.ledger.parent.mkdir(parents=True, exist_ok=True)
        summary = update_ledger(
            args.ledger,
            research,
            bars,
            snapshot_hash=snapshot_hash,
            as_of=datetime.now(UTC),
            recover_missed_sessions=args.recover_missed_sessions,
        )
        committed = None
        if args.recover_missed_sessions:
            with closing(
                sqlite3.connect(args.ledger.resolve().as_uri() + "?mode=ro", uri=True)
            ) as con:
                committed = con.execute("SELECT value FROM state WHERE key='last_hash'").fetchone()
        if committed and committed[0] != snapshot_hash:
            print(
                json.dumps(
                    {"report": str(args.report.resolve()), "paper": summary, "same_session": True},
                    allow_nan=False,
                )
            )
            return 0
        html = render_report(snapshot, research, summary, snapshot_hash)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=args.report.parent,
            prefix=".stock-report-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(html)
        try:
            temporary.replace(args.report)
        finally:
            temporary.unlink(missing_ok=True)
    except (ValueError, TypeError, KeyError, OSError, sqlite3.Error) as exc:
        print(f"Stock paper import failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"report": str(args.report.resolve()), "paper": summary}, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
