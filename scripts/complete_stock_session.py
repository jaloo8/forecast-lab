"""Create a new evidence-labelled capture using verified completed-session sources."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from kq.equities.session_data import complete_session


def read_sources(
    paths: list[Path], field: str
) -> tuple[list[dict[str, Any]], str, str, dict[str, str]]:
    """Validate stored MCP wrappers, preserving the earliest batch observation time."""
    rows: list[dict[str, Any]] = []
    stamps: list[datetime] = []
    hashes = {}
    for path in paths:
        raw = path.read_bytes()
        capture = json.loads(raw)
        response = capture["response"]
        if response.get("isError"):
            raise ValueError(f"Source tool failed: {path.name}")
        data = response["structuredContent"]["data"]
        if data.get("closes_error"):
            raise ValueError(f"Official close lookup failed: {path.name}")
        batch = data["results"]
        if not isinstance(batch, list) or any(not isinstance(row, dict) for row in batch):
            raise ValueError(f"Malformed source rows: {path.name}")
        symbols = {
            (row.get("quote") or {}).get("symbol") if field == "quotes" else row.get("symbol")
            for row in batch
        }
        if symbols.intersection(data.get("not_found") or []):
            raise ValueError(f"Contradictory not_found: {path.name}")
        stamp = datetime.fromisoformat(capture["retrieved_at"].replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("Source retrieval timestamp must be aware")
        if stamp > datetime.now(UTC):
            raise ValueError("Source retrieval timestamp is in the future")
        stamps.append(stamp.astimezone(UTC))
        rows.extend(batch)
        hashes[str(path)] = hashlib.sha256(raw).hexdigest()
    if max(stamps) - min(stamps) > timedelta(minutes=5):
        raise ValueError("Session source batches span more than five minutes")
    return rows, min(stamps).isoformat(), max(stamps).isoformat(), hashes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--fundamentals", required=True, nargs="+", type=Path)
    parser.add_argument("--quotes", required=True, nargs="+", type=Path)
    parser.add_argument("--required", required=True, nargs="+")
    parser.add_argument("--prior", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        evidence: dict[str, Any] = {"raw_sha256": {}}
        for field in ("fundamentals", "quotes"):
            rows, stamp, latest, hashes = read_sources(getattr(args, field), field)
            evidence[field] = rows
            evidence[field + "_as_of"] = stamp
            evidence[field + "_latest_as_of"] = latest
            evidence["raw_sha256"].update(hashes)
        prior = json.loads(args.prior.read_text(encoding="utf-8")) if args.prior else None
        result = complete_session(
            json.loads(args.snapshot.read_text(encoding="utf-8")),
            evidence,
            required=set(args.required),
            now=datetime.now(UTC),
            prior=prior,
        )
        result["session_evidence"] = evidence
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, allow_nan=False)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(f"Session capture refused: {exc}")
        return 2
    print(
        json.dumps(
            {
                "output": str(args.output),
                "repaired": len(result["session_repairs"]),
                "source_errors": result.get("source_errors", []),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
