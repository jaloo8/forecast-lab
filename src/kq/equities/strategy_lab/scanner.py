"""Immutable completed-session candidate scans, separate from account decisions."""

import hashlib
import json
import uuid
from collections import Counter
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from kq.equities.research import _number, _results, _timestamp
from kq.equities.strategy_lab.artifacts import _write, require_writable_research
from kq.equities.strategy_lab.features import score_candidates
from kq.equities.strategy_lab.registry import FAMILIES, LOOKBACKS


def _provider_error(value: dict[str, Any]) -> bool:
    return any(value.get(key) for key in ("error", "errors", "isError"))


def _normalize(series: dict[str, Any], captured: datetime) -> tuple[list[dict[str, Any]], int]:
    if (
        series.get("interval") != "day"
        or series.get("bounds") != "regular"
        or series.get("adjustment_type", "split") != "split"
        or _provider_error(series)
    ):
        raise ValueError("invalid_bar")
    if not isinstance(series.get("bars"), list):
        raise ValueError("invalid_bar")
    records, excluded, seen = [], 0, set()
    for bar in series["bars"]:
        if not isinstance(bar, dict) or _provider_error(bar):
            raise ValueError("invalid_bar")
        begins = _timestamp(bar.get("begins_at"), "begins_at")
        if begins > captured or begins.time() != time.min:
            raise ValueError("invalid_bar")
        flags = [bar.get(flag, False) for flag in ("synthetic", "is_synthetic", "interpolated")]
        if any(type(flag) is not bool for flag in flags):
            raise ValueError("invalid_bar")
        if any(flags) or bar.get("session") != "reg" or begins.date() >= captured.date():
            excluded += 1
            continue
        if begins.weekday() >= 5:
            raise ValueError("invalid_bar")
        volume = _number(bar.get("volume"), "volume", positive=False)
        if volume == 0:
            excluded += 1
            continue
        prices = {
            name: _number(bar.get(name + "_price"), name)
            for name in ("open", "high", "low", "close")
        }
        if (
            volume < 0
            or prices["high"] < max(prices.values())
            or prices["low"] > min(prices.values())
            or begins.date() in seen
        ):
            raise ValueError("invalid_bar")
        seen.add(begins.date())
        records.append(
            dict(
                symbol=series["symbol"],
                session_date=begins.date(),
                **prices,
                volume=volume,
                as_of=datetime.combine(
                    begins.date(), time(16), ZoneInfo("America/New_York")
                ).astimezone(UTC),
            )
        )
    return records, excluded


def _ranked_rows(
    bars: pd.DataFrame, candidates: list[str], coverage: dict[str, Any], decision: date
) -> list[dict[str, Any]]:
    bars = bars.loc[bars.symbol.isin(["SPY", *candidates])]
    rows = []
    for family in FAMILIES:
        for lookback in LOOKBACKS:
            scored = (
                score_candidates(bars, decision, family, lookback)
                .set_index("symbol")
                .reindex(candidates)
            )
            for symbol in candidates:
                if coverage[symbol]["status"] != "available":
                    scored.loc[symbol, ["score", "eligible", "reason"]] = [
                        None,
                        False,
                        coverage[symbol]["reason"],
                    ]
            scored["as_of"] = datetime.combine(
                decision, time(16), ZoneInfo("America/New_York")
            ).astimezone(UTC)
            scored = scored.reset_index().sort_values(
                ["eligible", "score", "symbol"], ascending=[False, False, True]
            )
            scored["rank"] = [
                i + 1 if eligible and i < 20 else None for i, eligible in enumerate(scored.eligible)
            ]
            scored["rank"] = scored["rank"].astype("Int64")
            scored["family"], scored["lookback"] = family, lookback
            rows.extend(json.loads(scored.to_json(orient="records", date_format="iso")))
    return rows


def _intent(
    snapshot: dict[str, Any], source: dict[str, Any], captured: datetime
) -> tuple[date, list[str]]:
    target = snapshot.get("completed_session", source.get("completed_session"))
    if not isinstance(target, str):
        raise ValueError("explicit intended completed_session required")
    decision = date.fromisoformat(target)
    if (
        decision.isoformat() != target
        or decision >= captured.date()
        or decision.weekday() >= 5
        or source.get("completed_session", target) != target
    ):
        raise ValueError("invalid or contradictory intended completed_session")
    requested = snapshot.get("requested_symbols")
    if (
        not isinstance(requested, list)
        or not requested
        or any(not isinstance(s, str) or not s for s in requested)
        or len(set(requested)) != len(requested)
        or "SPY" not in requested
    ):
        raise ValueError("explicit unique requested_symbols including SPY required")
    return decision, sorted(requested)


def _evaluate(snapshot: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    captured = _timestamp(snapshot.get("captured_at"), "captured_at")
    if captured > datetime.now(UTC) or (
        source.get("captured_at")
        and _timestamp(source["captured_at"], "source capture") > datetime.now(UTC)
    ):
        raise ValueError("future source capture")
    if snapshot.get("benchmark") != "SPY" or snapshot.get("adjustment_type") != "split":
        raise ValueError("expected split-adjusted SPY snapshot")
    decision, requested = _intent(snapshot, source, captured)
    universe = source.get("universe")
    if not isinstance(universe, list) or any(not isinstance(s, str) or not s for s in universe):
        raise ValueError("explicit candidate universe required")
    candidates = sorted(set(universe) - {"SPY"})
    series = _results(snapshot.get("bars"), "bars")
    counts = Counter(item.get("symbol") for item in series)
    if any(not isinstance(s, str) or not s for s in counts):
        raise ValueError("result symbol missing")
    missing = (
        snapshot.get("bars", {}).get("data", {}).get("not_found", [])
        if isinstance(snapshot.get("bars"), dict)
        else []
    )
    missing = set(missing) | {
        s for s, reason in snapshot.get("unavailable", {}).items() if reason == "not_found"
    }
    audited = sorted(set(requested) | set(candidates) | {str(s) for s in counts} | missing)
    records, coverage = [], {}
    for item in series:
        symbol = item["symbol"]
        try:
            if counts[symbol] != 1 or symbol in missing:
                raise ValueError("duplicate_symbol")
            normalized, excluded = _normalize(item, captured)
            records.extend(normalized)
            coverage[symbol] = dict(
                status="available",
                reason="",
                excluded_bar_count=excluded,
                latest_session=max(
                    (r["session_date"].isoformat() for r in normalized), default=None
                ),
            )
        except ValueError as exc:
            reason = "duplicate_symbol" if str(exc) == "duplicate_symbol" else "invalid_bar"
            coverage[symbol] = dict(
                status="invalid", reason=reason, latest_session=None, excluded_bar_count=0
            )
    spy = [r for r in records if r["symbol"] == "SPY"]
    if not spy or coverage["SPY"]["status"] != "available":
        raise ValueError("genuine completed benchmark bars required")
    if not any(r["session_date"] == decision for r in spy):
        raise ValueError("genuine SPY bar missing for intended completed_session")
    current_symbols = {r["symbol"] for r in records if r["session_date"] == decision}
    for symbol in audited:
        if symbol not in coverage or symbol not in requested:
            status = (
                "not_requested"
                if symbol not in requested
                else "not_found"
                if symbol in missing
                else "omitted"
            )
            coverage[symbol] = dict(
                status=status, reason=status, latest_session=None, excluded_bar_count=0
            )
        row = coverage[symbol]
        if row["status"] == "available" and symbol not in current_symbols:
            row.update(status="missing_latest", reason="missing_latest")
        row.update(symbol=symbol, is_candidate=symbol in candidates)
    rows = _ranked_rows(pd.DataFrame(records), candidates, coverage, decision)
    statuses = Counter(row["status"] for row in coverage.values())
    return dict(
        rows=rows,
        completed_session=decision.isoformat(),
        target_session=decision.isoformat(),
        captured_at=snapshot["captured_at"],
        source_captured_at=snapshot["captured_at"],
        coverage=dict(
            requested_count=len(requested),
            candidate_count=len(candidates),
            not_found_count=statuses["not_found"],
            not_requested_count=statuses["not_requested"],
            invalid_count=statuses["invalid"],
            missing_latest_count=statuses["missing_latest"],
            omitted_count=statuses["omitted"],
            excluded_bar_count=sum(r["excluded_bar_count"] for r in coverage.values()),
            rows=[coverage[s] for s in audited],
        ),
    )


def _publish_attempt(root: Path, run: Path, target: Any, error: str | None) -> None:
    attempt = dict(
        schema_version=1,
        run_id=run.name,
        status="failure" if error else "success",
        attempted_at=datetime.now(UTC).isoformat(),
        error=error,
        completed_session=target if isinstance(target, str) else None,
    )
    path = run / "scanner-attempt.json"
    _write(path, attempt)
    pointer = dict(
        run_id=run.name,
        attempt_file=f"runs/{run.name}/scanner-attempt.json",
        attempt_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    temporary = root / (".attempt-" + run.name + ".tmp")
    _write(temporary, pointer)
    temporary.replace(root / "scanner-attempt.json")


def publish_scan(snapshot: dict[str, Any], source: dict[str, Any], root: Path) -> dict[str, Any]:
    """Register source/method hashes; publish successes and every failed attempt."""
    require_writable_research(root)
    now = datetime.now(UTC)
    run_id = "scan-" + now.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
    run = root / "runs" / run_id
    run.mkdir(parents=True, exist_ok=False)
    target = snapshot.get("completed_session", source.get("completed_session"))
    try:
        package = Path(__file__).parent
        hashes = {
            name: hashlib.sha256((package / name).read_bytes()).hexdigest()
            for name in (
                "scanner.py",
                "features.py",
                "registry.py",
                "artifacts.py",
                "../research.py",
            )
        }
        manifest = dict(
            run_id=run_id,
            created_at=now.isoformat(),
            source=source,
            code_sha256=hashes,
            snapshot_sha256=hashlib.sha256(
                json.dumps(snapshot, sort_keys=True, allow_nan=False).encode()
            ).hexdigest(),
            families=FAMILIES,
            lookbacks=LOOKBACKS,
            top_rank=20,
            completed_session=target,
        )
        _write(run / "scanner-manifest.json", manifest)
        if snapshot.get("validation_errors"):
            raise ValueError(
                "Snapshot validation failed: " + json.dumps(snapshot["validation_errors"])
            )
        report = dict(
            _evaluate(snapshot, source),
            schema_version=1,
            status="success",
            run_id=run_id,
            generated_at=now.isoformat(),
            source=source,
            code_sha256=hashes,
            manifest_sha256=hashlib.sha256(
                (run / "scanner-manifest.json").read_bytes()
            ).hexdigest(),
        )
        _write(run / "scanner-report.json", report)
        pointer = dict(
            run_id=run_id,
            report_file=f"runs/{run_id}/scanner-report.json",
            report_sha256=hashlib.sha256((run / "scanner-report.json").read_bytes()).hexdigest(),
        )
        temporary = root / ("." + run_id + ".tmp")
        _write(temporary, pointer)
        temporary.replace(root / "scanner-latest.json")
    except Exception as exc:
        _write(run / "failure.json", dict(error=str(exc), prior_latest_unchanged=True))
        _publish_attempt(root, run, target, str(exc))
        raise
    _publish_attempt(root, run, target, None)
    return pointer
