"""Record paper-only advisory signals on A8; never execute an order."""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from kq.equities.adaptive_journal import record
from kq.equities.adaptive_reference import reference_state


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--reference-ledger", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    if any(
        (folder / "READ_ONLY_MIRROR.txt").exists()
        for folder in (args.root.resolve(), *args.root.resolve().parents)
    ):
        raise ValueError("local mirror is read-only; run the journal writer on A8")
    snapshot: dict[str, Any]
    raw = ""
    try:
        raw = args.snapshot.read_text(encoding="utf-8")
        snapshot = json.loads(raw)
        if not isinstance(snapshot, dict):
            raise ValueError("snapshot must be an object")
    except (OSError, ValueError) as exc:
        snapshot = dict(invalid_input_text=raw, source_error=str(exc))
    try:
        reference = reference_state(args.reference_ledger)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        reference = dict(source_error=str(exc))
    result = record(snapshot, reference, args.root)
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
