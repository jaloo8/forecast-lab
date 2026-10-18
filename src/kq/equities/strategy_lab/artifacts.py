"""Immutable, research-only run artifacts; no paper ledger dependency."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import pandas as pd

from kq.equities.strategy_lab.engine import compare
from kq.equities.strategy_lab.registry import selection_specs


def _write(path: Path, value: dict[str, Any]) -> None:
    """Serialize first, then atomically publish durable bytes without replacement."""
    raw = json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode("utf-8")
    temporary = None
    try:
        with NamedTemporaryFile(
            dir=path.parent, prefix=".artifact-", suffix=".tmp", delete=False
        ) as f:
            temporary = Path(f.name)
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def require_writable_research(root: Path) -> None:
    """Refuse all local read-only mirrors before producing any artifacts."""
    if any(
        (p / "READ_ONLY_MIRROR.txt").exists() for p in (root.resolve(), *root.resolve().parents)
    ):
        raise ValueError("Research writer refuses a read-only mirror")


def publish_run(bars: pd.DataFrame, source: dict[str, Any], root: Path) -> dict[str, Any]:
    """Register hypotheses before computation; publish only fully written reports."""
    require_writable_research(root)
    started = datetime.now(UTC)
    run_id = started.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
    run = root / "runs" / run_id
    run.mkdir(parents=True, exist_ok=False)
    try:
        package = Path(__file__).resolve().parent
        files = [
            *package.glob("*.py"),
            *[
                package.parent / name
                for name in ("historical_study.py", "broad_scan.py", "research.py", "universe.py")
            ],
        ]
        code_hashes = {
            file.relative_to(package.parent).as_posix(): hashlib.sha256(
                file.read_bytes()
            ).hexdigest()
            for file in sorted(files)
        }
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "created_at": started.isoformat(),
            "method": "stock-strategy-lab-v1",
            "code_sha256": code_hashes,
            "method_hash": hashlib.sha256(
                json.dumps(code_hashes, sort_keys=True).encode()
            ).hexdigest(),
            "source": source,
            "selections": [
                dict(selection_id=s.selection_id, family=s.family, lookback=s.lookback, size=s.size)
                for s in selection_specs()
            ],
            "holding_sessions": [5, 20],
            "cost_bps_each_side": [10, 25, 50],
            "capital": "equal all-in slots; unused slots remain cash; not a trading account",
            "evidence": "exploratory survivors; no untouched validation or profitability claim",
        }
        _write(run / "manifest.json", manifest)
        result = compare(bars)
        report = {
            **result,
            "schema_version": 1,
            "status": "success",
            "run_id": run_id,
            "captured_at": datetime.now(UTC).isoformat(),
            "source": source,
            "method_hash": manifest["method_hash"],
            "code_sha256": code_hashes,
            "manifest_sha256": hashlib.sha256((run / "manifest.json").read_bytes()).hexdigest(),
        }
        _write(run / "report.json", report)
        pointer = {
            "run_id": run_id,
            "report_file": f"runs/{run_id}/report.json",
            "report_sha256": hashlib.sha256((run / "report.json").read_bytes()).hexdigest(),
        }
        temporary = root / (".latest-" + run_id + ".tmp")
        _write(temporary, pointer)
        temporary.replace(root / "latest.json")
    except Exception as exc:
        _write(
            run / "failure.json",
            {
                "failed_at": datetime.now(UTC).isoformat(),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "prior_latest_unchanged": True,
            },
        )
        raise
    return pointer
