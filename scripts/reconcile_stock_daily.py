"""Capture reviewed legacy or primary stock daily bars without writing a ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from kq.equities.session_vintages import create_review, primary_daily, reconcile_daily


def _read(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value, hashlib.sha256(raw).hexdigest()


def _bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _write_new(path: Path, raw: bytes) -> None:
    """Publish fully flushed bytes under a new name, never replacing a capture."""
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            dir=path.parent, prefix=".reconciliation-", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise ValueError(f"Output already exists: {path}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0912, PLR0915
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--create-review", action="store_true")
    mode.add_argument("--primary-only", action="store_true")
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--required", required=True, nargs="+")
    parser.add_argument("--note")
    args = parser.parse_args(argv)
    try:
        if args.primary_only:
            if args.prior or args.review or args.note:
                raise ValueError("Primary-only capture accepts no prior, review or note")
            kind = "primary"
        elif args.create_review:
            if not args.prior or args.review or not args.note or not args.note.strip():
                raise ValueError(
                    "Review creation requires prior and nonblank note, without --review"
                )
            kind = "review"
        else:
            if not args.prior or not args.review or args.note:
                raise ValueError("Legacy capture requires prior and review, without note")
            kind = "legacy"

        inputs = {"snapshot": args.snapshot}
        if args.prior:
            inputs["prior"] = args.prior
        if args.review:
            inputs["review"] = args.review
        receipt_path = args.output.with_name(args.output.name + ".sources.json")
        paths = [*inputs.values(), args.output, receipt_path]
        if len({path.resolve() for path in paths}) != len(paths):
            raise ValueError("Input, output and receipt paths must differ")
        if args.output.exists() or receipt_path.exists():
            raise ValueError("Output or receipt already exists")

        parsed = {name: _read(path) for name, path in inputs.items()}
        now = datetime.now(UTC)
        if kind == "primary":
            result = primary_daily(parsed["snapshot"][0], required=set(args.required), now=now)
        elif kind == "review":
            primary_daily(parsed["snapshot"][0], required=set(args.required), now=now)
            result = create_review(
                parsed["prior"][0], parsed["snapshot"][0], now=now, note=args.note
            )
        else:
            result = reconcile_daily(
                parsed["snapshot"][0],
                parsed["prior"][0],
                parsed["review"][0],
                required=set(args.required),
                now=now,
            )
        output_raw = _bytes(result)
        receipt = dict(
            created_at=now.isoformat(),
            kind=kind,
            inputs_sha256={name: parsed[name][1] for name in inputs},
            output_sha256=hashlib.sha256(output_raw).hexdigest(),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        _write_new(receipt_path, _bytes(receipt))
        try:
            _write_new(args.output, output_raw)
        except (ValueError, OSError):
            receipt_path.unlink(missing_ok=True)
            raise
    except (ValueError, TypeError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(f"Daily reconciliation refused: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps({"output": str(args.output.resolve()), "receipt": str(receipt_path.resolve())})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
