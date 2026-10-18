"""Publish an immutable completed-session stock scan on the authoritative A8 host."""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from kq.equities.strategy_lab.artifacts import require_writable_research
from kq.equities.strategy_lab.authority import require_authority
from kq.equities.strategy_lab.scanner import publish_scan


def _source(snapshot: dict[str, Any], raw: bytes) -> dict[str, Any]:
    metadata = snapshot.get("source_metadata")
    if not isinstance(metadata, dict) or any(
        not metadata.get(key)
        for key in (
            "catalogue_sha256",
            "catalogue_captured_at",
            "input_sha256",
            "input_captured_at",
        )
    ):
        raise ValueError("source_metadata requires catalogue and raw-file hashes and capture times")
    hashes, captured = metadata["input_sha256"], metadata["input_captured_at"]
    if (
        not isinstance(hashes, dict)
        or not isinstance(captured, dict)
        or set(hashes) != set(captured)
    ):
        raise ValueError("raw-file hashes and capture times must identify the same inputs")
    universe = snapshot.get("universe")
    if (
        not isinstance(universe, list)
        or not universe
        or any(not isinstance(s, str) for s in universe)
    ):
        raise ValueError("snapshot requires an explicit candidate universe")
    return dict(
        metadata,
        universe=universe,
        raw_snapshot_sha256=hashlib.sha256(raw).hexdigest(),
        source_errors=snapshot.get("source_errors", {}),
        unavailable=snapshot.get("unavailable", {}),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("data/equities/strategy-lab"))
    args = parser.parse_args()
    try:
        require_authority(args.root)
        require_writable_research(args.root)
        raw = args.snapshot.read_bytes()
        snapshot = json.loads(raw)
        if not isinstance(snapshot, dict):
            raise ValueError("snapshot must be a JSON object")
        result = publish_scan(snapshot, _source(snapshot, raw), args.root)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(f"Scanner failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
