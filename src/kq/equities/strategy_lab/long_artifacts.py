"""A8-only immutable publication for isolated long-history research."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kq.equities.strategy_lab.artifacts import _write, require_writable_research
from kq.equities.strategy_lab.authority import RELEASE, require_authority
from kq.equities.strategy_lab.long_history import load_long_capture
from kq.equities.strategy_lab.long_study import ARMS, EPOCHS, HOLDS, compare_long

LONG_ROOT = RELEASE / "data/equities/strategy-lab/long-history"


def _pointer(root: Path, name: str, value: dict[str, Any]) -> None:
    temporary = root / (".pointer-" + uuid.uuid4().hex + ".tmp")
    _write(temporary, value)
    temporary.replace(root / name)


def publish_long(capture: Path, root: Path) -> dict[str, Any]:
    """Register source/code identities before computing; preserve failed attempts."""
    require_authority(root)
    require_writable_research(root)
    if root.resolve() != LONG_ROOT.resolve():
        raise ValueError("Long study requires its isolated long-history root")
    root.mkdir(parents=True, exist_ok=True)
    lock = root / "writer.lock"
    with lock.open("x") as f:
        f.write(datetime.now(UTC).isoformat())
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
    run = root / "runs" / run_id
    try:
        run.mkdir(parents=True, exist_ok=False)
        package = Path(__file__).parent
        names = (
            "long_history.py",
            "long_study.py",
            "long_artifacts.py",
            "engine_accounting.py",
            "artifacts.py",
            "authority.py",
        )
        code = {name: hashlib.sha256((package / name).read_bytes()).hexdigest() for name in names}
        manifest = dict(
            run_id=run_id,
            created_at=datetime.now(UTC).isoformat(),
            method="long-study-v1",
            code_sha256=code,
            capture_path=str(capture),
            receipt_sha256=hashlib.sha256((capture / "receipt.json").read_bytes()).hexdigest()
            if (capture / "receipt.json").exists()
            else None,
            arms=list(ARMS),
            holds=list(HOLDS),
            selection_sizes=[1, 3, 5],
            costs_bps_each_side=[10, 25, 50],
            epochs=EPOCHS,
            capital="Reset $100 research cohorts; $10 all-in slots; no sequential account",
            evidence="Exploratory survivors; no untouched validation or winner selection",
        )
        _write(run / "manifest.json", manifest)
        bars, source = load_long_capture(capture)
        _write(run / "source.json", source)
        result = compare_long(bars)
        report = dict(
            result,
            run_id=run_id,
            status="success",
            source=source,
            captured_at=datetime.now(UTC).isoformat(),
            code_sha256=code,
            manifest_sha256=hashlib.sha256((run / "manifest.json").read_bytes()).hexdigest(),
        )
        _write(run / "report.json", report)
        pointer = dict(
            run_id=run_id,
            report_file=f"runs/{run_id}/report.json",
            report_sha256=hashlib.sha256((run / "report.json").read_bytes()).hexdigest(),
        )
        _pointer(root, "latest.json", pointer)
        _pointer(root, "latest-attempt.json", dict(pointer, status="success"))
        return pointer
    except Exception as exc:
        failure = dict(
            run_id=run_id,
            failed_at=datetime.now(UTC).isoformat(),
            error_type=type(exc).__name__,
            error=str(exc),
            status="failure",
        )
        _write(run / "failure.json", failure)
        _pointer(
            root,
            "latest-attempt.json",
            dict(
                failure,
                failure_file=f"runs/{run_id}/failure.json",
                failure_sha256=hashlib.sha256((run / "failure.json").read_bytes()).hexdigest(),
            ),
        )
        raise
    finally:
        lock.unlink()
