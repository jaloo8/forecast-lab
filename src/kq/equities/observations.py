"""Immutable raw observation journal for prospective research evaluation."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kq.equities.research import _timestamp


def _encoded(snapshot: dict[str, Any]) -> bytes:
    return json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def observation_folder(root: Path, decision: dict[str, Any]) -> Path:
    """Keep each decision's revision history separate from every other selection."""
    return root / hashlib.sha256(_encoded(decision)).hexdigest()


def prior_observation(folder: Path, snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Read the last strictly earlier observation; reject conflicting or older input."""
    captured = _timestamp(snapshot.get("captured_at"), "captured_at")
    if captured > datetime.now(UTC):
        raise ValueError("future observation")
    latest: tuple[datetime, dict[str, Any]] | None = None
    for path in folder.glob("*.json"):
        stored = json.loads(path.read_text(encoding="utf-8"))
        if hashlib.sha256(_encoded(stored)).hexdigest() != path.stem:
            raise ValueError("observation digest mismatch")
        timestamp = _timestamp(stored.get("captured_at"), "captured_at")
        if timestamp > captured:
            raise ValueError("new observation is older than archived evidence")
        if timestamp == captured:
            if _encoded(snapshot) != _encoded(stored):
                raise ValueError("conflicting observation at existing capture time")
        elif latest is None or timestamp > latest[0]:
            latest = (timestamp, stored)
    return latest[1] if latest else None


def save_observation(folder: Path, snapshot: dict[str, Any]) -> Path:
    """Append an already validated snapshot; never replace an existing observation."""
    prior_observation(folder, snapshot)
    raw = _encoded(snapshot)
    target = folder / (hashlib.sha256(raw).hexdigest() + ".json")
    folder.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("xb") as handle:
            handle.write(raw)
    except FileExistsError:
        if target.read_bytes() != raw:
            raise ValueError("observation digest collision") from None
    return target
