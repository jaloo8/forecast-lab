"""Resumable immutable public-data captures; no account or research writes."""

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Any


def _bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write(path: Path, raw: bytes) -> None:
    """Atomically publish durable bytes without replacing an existing capture."""
    temporary = None
    try:
        with NamedTemporaryFile(
            dir=path.parent, prefix=".capture-", suffix=".tmp", delete=False
        ) as f:
            temporary = Path(f.name)
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != raw:
                raise ValueError(f"immutable capture conflict: {path.name}") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return dict(value)


def _time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is not None:
            return parsed.astimezone(UTC)
    except (ValueError, AttributeError):
        pass
    raise ValueError("expected aware timestamp")


def _plan(root: Path) -> dict[str, Any]:
    raw = (root / "plan.json").read_bytes()
    if _digest(raw) != (root / "plan.sha256").read_text():
        raise ValueError("plan digest mismatch")
    plan = _read(root / "plan.json")
    if _digest((root / "catalogue.json").read_bytes()) != plan["catalogue_sha256"]:
        raise ValueError("catalogue digest mismatch")
    return plan


def begin_capture(
    root: Path, symbols: list[str], catalogue_path: Path, start_time: str, end_time: str
) -> dict[str, Any]:
    """Create a dated plan of sorted <=10-symbol exact requests; resume identical plans."""
    if not symbols or any(
        not isinstance(s, str) or not re.fullmatch(r"[A-Z0-9.\-]{1,20}", s) for s in symbols
    ):
        raise ValueError("invalid capture symbols")
    now = datetime.now(UTC)
    if not _time(start_time) < _time(end_time) <= now:
        raise ValueError("invalid capture window")
    ordered = sorted(set(symbols))
    catalogue = catalogue_path.read_bytes()
    batches = [
        dict(
            symbols=ordered[i : i + 10],
            start_time=start_time,
            end_time=end_time,
            interval="day",
            bounds="regular",
            adjustment_type="split",
        )
        for i in range(0, len(ordered), 10)
    ]
    if (root / "plan.json").exists():
        previous = _plan(root)
        if previous["batches"] != batches or previous["catalogue_sha256"] != _digest(catalogue):
            raise ValueError("immutable capture plan conflict")
        return previous
    plan = dict(
        capture_id=now.strftime("%Y%m%dT%H%M%S%fZ"),
        created_at=now.isoformat(),
        catalogue_sha256=_digest(catalogue),
        batches=batches,
    )
    raw = _bytes(plan)
    root.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=root.parent, prefix=f".{root.name}-") as staging:
        staged = Path(staging)
        for directory in ("attempts", "accepted", "errors"):
            (staged / directory).mkdir()
        _write(staged / "catalogue.json", catalogue)
        _write(staged / "plan.sha256", _digest(raw).encode())
        _write(staged / "plan.json", raw)
        staged.rename(root)
    return plan


def _bar_sessions(item: dict[str, Any], request: dict[str, Any], captured: datetime) -> None:
    seen = set()
    for bar in item["bars"]:
        if (
            not isinstance(bar, dict)
            or bar.get("session") != "reg"
            or any(bar.get(flag) for flag in ("error", "isError", "errors"))
        ):
            raise ValueError("malformed regular bar")
        begins = _time(bar.get("begins_at", ""))
        if (
            not _time(request["start_time"]) <= begins < _time(request["end_time"])
            or begins.date() >= captured.date()
            or begins.date() in seen
        ):
            raise ValueError("outside range, unfinished or duplicate session")
        seen.add(begins.date())


def _validate(wrapper: dict[str, Any], request: dict[str, Any], created: str) -> dict[str, Any]:
    if wrapper.get("request") != request:
        raise ValueError("request identity mismatch")
    captured = _time(wrapper.get("retrieved_at", ""))
    if not _time(created) <= captured <= datetime.now(UTC) or _time(request["end_time"]) > captured:
        raise ValueError("invalid actual retrieval timestamp")
    response = wrapper.get("response")
    if not isinstance(response, dict):
        raise ValueError("missing MCP response")
    content = response.get("structuredContent")
    if not isinstance(content, dict) or not isinstance(content.get("data"), dict):
        raise ValueError("missing structured results")
    data = content["data"]
    if any(
        layer.get("isError") or layer.get("error") or layer.get("errors")
        for layer in (wrapper, response, content, data)
    ):
        raise ValueError("provider error response")
    results, missing = data.get("results"), data.get("not_found", [])
    if not isinstance(results, list) or not isinstance(missing, list):
        raise ValueError("malformed result lists")
    found = []
    for item in results:
        if (
            not isinstance(item, dict)
            or item.get("symbol") not in request["symbols"]
            or item.get("interval") != "day"
            or item.get("bounds") != "regular"
            or item.get("adjustment_type", "split") != "split"
            or not isinstance(item.get("bars"), list)
            or any(item.get(flag) for flag in ("error", "isError", "errors"))
        ):
            raise ValueError("invalid result identity or format")
        _bar_sessions(item, request, captured)
        found.append(item["symbol"])
    if (
        any(not isinstance(s, str) or s not in request["symbols"] for s in missing)
        or len(set(found)) != len(found)
        or len(set(missing)) != len(missing)
        or set(found) & set(missing)
        or set(found) | set(missing) != set(request["symbols"])
    ):
        raise ValueError("duplicate, contradictory or omitted response membership")
    return dict(data)


def record_batch(
    root: Path, index: int, wrapper: dict[str, Any], *, check_progress: bool = True
) -> dict[str, Any]:
    """Preserve attempts and accept once; bulk receipts never assert capture completion.

    With check_progress=False, call progress explicitly after bulk acceptance to
    verify every accepted digest and publish the complete snapshot.
    """
    plan = _plan(root)
    if type(index) is not int or not 0 <= index < len(plan["batches"]):
        raise ValueError("unknown batch index")
    raw = _bytes(wrapper)
    digest = _digest(raw)
    name = f"{index:04}-{digest}.json"
    _write(root / "attempts" / name, raw)
    try:
        _validate(wrapper, plan["batches"][index], plan["created_at"])
        _write(root / "accepted" / f"{index:04}.json", _bytes({"sha256": digest}))
    except ValueError as exc:
        _write(
            root / "errors" / name, _bytes({"index": index, "sha256": digest, "error": str(exc)})
        )
        raise
    if not check_progress:
        return dict(index=index, sha256=digest, accepted=True, complete=None)
    return progress(root)


def progress(root: Path) -> dict[str, Any]:
    """Verify capture digests and report transport completion separately from coverage."""
    plan = _plan(root)
    pending, accepted, results, times = [], [], [], []
    unavailable: dict[str, str] = {}
    for index, request in enumerate(plan["batches"]):
        pointer = root / "accepted" / f"{index:04}.json"
        if not pointer.exists():
            pending.append(index)
            continue
        digest = _read(pointer).get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("invalid accepted digest")
        path = root / "attempts" / f"{index:04}-{digest}.json"
        if not path.is_file() or _digest(path.read_bytes()) != digest:
            raise ValueError("accepted attempt digest mismatch")
        wrapper = _read(path)
        data = _validate(wrapper, request, plan["created_at"])
        results.extend(data["results"])
        times.append(wrapper["retrieved_at"])
        unavailable.update({s: "not_found" for s in data.get("not_found", [])})
        unavailable.update(
            {item["symbol"]: "empty_history" for item in data["results"] if not item["bars"]}
        )
        accepted.append(index)
    snapshot_path = None
    if not pending:
        snapshot = dict(
            capture_id=plan["capture_id"],
            plan_sha256=_digest(_bytes(plan)),
            retrieved_at=max(times, key=_time),
            results=results,
            unavailable=unavailable,
        )
        path = root / "snapshot.json"
        _write(path, _bytes(snapshot))
        snapshot_path = str(path.resolve())
    return dict(
        complete=not pending,
        coverage_complete=not pending and not unavailable,
        pending_batches=pending,
        accepted_batches=accepted,
        unavailable=unavailable,
        errors=[_read(path) for path in sorted((root / "errors").glob("*.json"))],
        snapshot_path=snapshot_path,
    )
