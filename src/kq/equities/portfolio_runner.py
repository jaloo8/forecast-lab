"""One shared capture into separate, protocol-pinned virtual accounts."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from kq.equities.ledger import _eligible, update_ledger
from kq.equities.portfolio_metrics import account_metrics, benchmark, benchmark_revision
from kq.equities.portfolios import PortfolioSpec, portfolio_research, portfolio_specs
from kq.equities.research import daily_bars


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Invalid object: {path.name}")
    return value


def _write(path: Path, value: dict[str, Any], *, immutable: bool = False) -> None:
    text = json.dumps(value, sort_keys=True, allow_nan=False, indent=2)
    if immutable:
        if path.exists():
            if _read(path) != value:
                raise ValueError(f"Conflicting immutable record: {path.name}")
            return
        with path.open("x", encoding="utf-8") as handle:
            handle.write(text)
    else:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)


def _manifest(root: Path, digest: str, now: datetime, bars: pd.DataFrame) -> dict[str, Any]:
    specs = portfolio_specs()
    manifest_path = root / "manifest.json"
    manifest = _read(manifest_path) if manifest_path.exists() else None
    protocols = [asdict(spec) for spec in specs]
    if manifest is None:
        if any(root.glob("*/paper.sqlite")):
            raise ValueError("Existing account databases without launch manifest")
        manifest = dict(
            launched_at=now.isoformat(),
            protocols=protocols,
            initial_capture=digest,
            initial_session=str(bars.session_date.max()),
        )
        _write(manifest_path, manifest, immutable=True)
    elif manifest["protocols"] != protocols:
        raise ValueError("Portfolio protocol differs from launch manifest")
    return manifest


def _intent(root: Path, digest: str) -> Path:
    path = root / "in-progress.json"
    if path.exists() and _read(path)["snapshot_hash"] != digest:
        raise ValueError("Recover unfinished capture before importing newer data")
    _write(path, {"snapshot_hash": digest}, immutable=True)
    return path


def _account(
    root: Path,
    spec: PortfolioSpec,
    frame: pd.DataFrame,
    bars: pd.DataFrame,
    digest: str,
    now: datetime,
    prior: dict[str, Any],
    evidence_error: str,
    recovery: bool,
) -> dict[str, Any]:
    row: dict[str, Any] = {**asdict(spec), "as_of": now.isoformat()}
    try:
        if evidence_error:
            raise ValueError(evidence_error)
        path = root / spec.portfolio_id / "paper.sqlite"
        if recovery:
            with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as con:
                state = dict(con.execute("SELECT key,value FROM state"))
            if (
                state.get("last_hash") != digest
                or state.get("protocol_id") != spec.protocol_id
                or state.get("holding_sessions") != str(spec.holding_sessions)
            ):
                raise ValueError("No committed account result for recovery; fresh capture required")
            summary = json.loads(state["last_summary"])
        else:
            _held_coverage(path, bars)
            summary = update_ledger(
                path,
                frame,
                bars,
                snapshot_hash=digest,
                as_of=now,
                holding_sessions=spec.holding_sessions,
                protocol_id=spec.protocol_id,
            )
        metrics = account_metrics(
            summary,
            prior.get("metrics", prior.get("last_valid_metrics", {})),
            bars,
        )
        if not metrics["valid"]:
            raise ValueError(
                f"Account evidence invalid: {summary['pause_reason'] or 'stale marks'}"
            )
        with closing(
            sqlite3.connect(
                (root / spec.portfolio_id / "paper.sqlite").resolve().as_uri() + "?mode=ro",
                uri=True,
            )
        ) as con:
            launch = con.execute("SELECT value FROM state WHERE key='launched_at'").fetchone()
        row.update(
            status="ok",
            summary=summary,
            metrics=metrics,
            launched_at=launch[0] if launch else None,
            selected=frame.loc[frame.status == "ranked", "symbol"].tolist(),
            candidate_count=len(frame),
        )
    except (ValueError, TypeError, KeyError, OSError, sqlite3.Error) as exc:
        row.update(
            status="error",
            error=str(exc),
            last_valid_metrics=prior.get("metrics", prior.get("last_valid_metrics", {})),
        )
    return row


def _held_coverage(path: Path, bars: pd.DataFrame) -> None:
    if not path.exists():
        return
    spy = set(bars.loc[bars.symbol == "SPY", "session_date"])
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as con:
        pending = con.execute("SELECT symbol,created_at FROM paper_orders WHERE status='pending'")
        required = [
            (symbol, {d for d in spy if _eligible(d.isoformat(), created)})
            for symbol, created in pending
        ]
        for symbol, entry in con.execute(
            "SELECT symbol,entry_date FROM paper_trades WHERE exit_date IS NULL"
        ):
            required.append((symbol, {d for d in spy if d.isoformat() >= entry}))
    for symbol, sessions in required:
        actual = set(bars.loc[(bars.symbol == symbol) & (bars.volume > 0), "session_date"])
        if sessions - actual:
            raise ValueError(f"missing stock session for {symbol}: {sorted(sessions - actual)}")


def _process(
    root: Path,
    source: dict[str, Any],
    digest: str,
    now: datetime,
    bars: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
    recovery: bool,
) -> dict[str, Any]:
    specs = portfolio_specs()
    manifest = _manifest(root, digest, now, bars)
    latest_path = root / "latest.json"
    previous = _read(latest_path) if latest_path.exists() else {}
    captured = datetime.fromisoformat(source["captured_at"])
    if previous:
        old_time = datetime.fromisoformat(previous["source_as_of"])
        if captured < old_time:
            raise ValueError("Older capture cannot replace latest portfolio evidence")
        if captured == old_time and previous["snapshot_hash"] != digest:
            raise ValueError("Conflicting capture timestamp")
        if previous["snapshot_hash"] == digest and previous["status"] == "ok":
            return previous
    captures = root / "captures"
    captures.mkdir(exist_ok=True)
    original = captures / f"{digest}.json"
    if original.exists():
        if _read(original) != source:
            raise ValueError("Archived capture differs from original")
    else:
        _write(original, source, immutable=True)
    latest_session = str(bars.loc[bars.symbol == "SPY", "session_date"].max())
    cutoff = captured.astimezone(UTC).date() - timedelta(days=1)
    expected = {day.date() for day in pd.bdate_range(manifest["initial_session"], cutoff)}
    observed = set(bars.loc[(bars.symbol == "SPY") & (bars.volume > 0), "session_date"])
    calendar_error = bool(expected - observed)
    reference = previous.get("benchmark_capture", manifest["initial_capture"])
    revised = benchmark_revision(
        bars, daily_bars(_read(captures / f"{reference}.json")), manifest["launched_at"]
    )
    prior_rows = {row["portfolio_id"]: row for row in previous.get("accounts", [])}
    _intent(root, digest)
    evidence_error = (
        "unverified_calendar: missing completed weekday"
        if calendar_error
        else "benchmark revision: prospective SPY evidence changed"
        if revised
        else ""
    )
    rows = [
        _account(
            root,
            spec,
            frames[spec.portfolio_id],
            bars,
            digest,
            now,
            prior_rows.get(spec.portfolio_id, {}),
            evidence_error,
            recovery,
        )
        for spec in specs
    ]
    launches = {row["launched_at"] for row in rows if row["status"] == "ok"}
    common_start = (
        next(iter(launches))
        if len(launches) == 1 and all(row["status"] == "ok" for row in rows)
        else None
    )
    report = dict(
        as_of=now.isoformat(),
        source_as_of=source["captured_at"],
        snapshot_hash=digest,
        source_errors=source.get("source_errors", []),
        recovery=recovery,
        benchmark_capture=reference if calendar_error or revised else digest,
        launched_at=common_start or manifest["launched_at"],
        session_date=latest_session,
        accounts=rows,
        benchmark=(
            {"status": "invalid", "equity": None, "return": None}
            if calendar_error or revised or common_start is None
            else benchmark(bars, common_start)
        ),
        status="ok" if all(r["status"] == "ok" for r in rows) else "partial_failure",
    )
    history = root / "runs"
    history.mkdir(exist_ok=True)
    _write(
        history / f"{now.strftime('%Y%m%dT%H%M%S%f')}-{digest[:12]}.json", report, immutable=True
    )
    _write(latest_path, report)
    return report


def run_portfolios(snapshot: Path, root: Path) -> dict[str, Any]:
    """Validate one fresh shared capture; update nine isolated virtual books."""
    if root.name != "parallel-books" or root.resolve() in snapshot.resolve().parents:
        raise ValueError("Use a dedicated parallel-books root outside the source capture")
    source = _read(snapshot)
    now = datetime.now(UTC)
    captured = datetime.fromisoformat(source["captured_at"])
    canonical = json.dumps(source, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    if captured.tzinfo is None or now < captured:
        raise ValueError("Capture must be aware UTC and cannot be future")
    recovery = now - captured > timedelta(hours=24)
    if recovery and not (
        (root / "in-progress.json").exists()
        and _read(root / "in-progress.json")["snapshot_hash"] == digest
        and _read(root / "captures" / f"{digest}.json") == source
    ):
        raise ValueError("Capture must be fresh within 24 hours unless recovering archived results")
    bars = daily_bars(source)
    frames = {spec.portfolio_id: portfolio_research(source, spec) for spec in portfolio_specs()}
    root.mkdir(parents=True, exist_ok=True)
    lock = root / "writer.lock"
    with lock.open("x", encoding="utf-8") as handle:
        handle.write(now.isoformat())
    try:
        pending = root / "in-progress.json"
        if pending.exists() and _read(pending)["snapshot_hash"] != digest:
            raise ValueError("Recover unfinished capture before importing newer data")
        report = _process(root, source, digest, now, bars, frames, recovery)
        pending.unlink(missing_ok=True)
        return report
    finally:
        lock.unlink()
