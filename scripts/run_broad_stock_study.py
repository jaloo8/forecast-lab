"""Reproduce the locked, exploratory current-survivor broad stock study.

Reads the dated split-adjusted raw captures and validates the full catalogue
before constructing the exact grid used by the original 2026-09-28 study.
This is historical research, not a forecast or order path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from kq.equities.broad_scan import scan_captures
from kq.equities.historical_study import run_study


def _output_path(data_dir: Path, output: Path) -> Path:
    """Permit replacement only of a study result JSON directly in data-dir."""
    data = data_dir.resolve()
    target = output.resolve()
    if (target.parent != data or not target.name.startswith("broad-historical-study")
        or target.suffix != ".json"):
        raise ValueError("output must be a broad-historical-study*.json in data-dir")
    return target


def _complete(bars: Any, days: list[str]) -> bool:
    if not isinstance(bars, list) or [bar.get("begins_at") for bar in bars] != days:
        return False
    for bar in bars:
        if any(bar.get(flag) for flag in ("interpolated", "synthetic", "is_synthetic")):
            return False
        volume = bar.get("volume")
        if isinstance(volume, bool):
            return False
        try:
            numeric = float(volume)
        except (TypeError, ValueError):
            return False
        if not math.isfinite(numeric) or numeric <= 0:
            return False
    return True


def _assemble_source(
    data_dir: Path, coverage: pd.DataFrame
) -> tuple[dict[str, Any], tuple[str, ...], dict[str, str]]:
    """Build study source from validator coverage and byte-identical raw captures."""
    history = data_dir / "broad-history-2026-09-28"
    eligible = set(coverage.loc[coverage.coverage_status == "ranked", "symbol"])
    exclusions = dict(zip(
        coverage.loc[coverage.coverage_status != "ranked", "symbol"],
        coverage.loc[coverage.coverage_status != "ranked", "coverage_status"],
        strict=True,
    ))
    benchmark = json.loads((history / "benchmark.json").read_bytes())
    spy = benchmark["data"]["results"][0]
    days = [bar["begins_at"] for bar in spy["bars"]]
    selected: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    captures: list[str] = []
    for path in sorted(history.glob("*.json")):
        raw = path.read_bytes()
        hashes[path.name] = hashlib.sha256(raw).hexdigest()
        capture = json.loads(raw)
        captures.append(capture["captured_at"])
        for series in capture["data"]["results"]:
            symbol = series["symbol"]
            if symbol not in eligible:
                continue
            if _complete(series["bars"], days):
                if symbol in selected:
                    raise ValueError(f"duplicate stock series: {symbol}")
                selected[symbol] = series
            else:
                exclusions[symbol] = "incomplete_real_positive_volume_grid"
    stocks = tuple(sorted(selected))
    if not stocks or len(stocks) + len(exclusions) != len(coverage):
        raise ValueError("inconsistent validated candidate coverage")
    source = {
        "benchmark": "SPY", "universe": list(stocks), "adjustment_type": "split",
        "captured_at": max(captures),
        "bars": [spy, *[selected[symbol] for symbol in stocks]],
        "input_hashes": hashes,
        "universe_manifest_hash": hashlib.sha256(
            (data_dir / "universe" / "manifest.json").read_bytes()
        ).hexdigest(),
    }
    return source, stocks, exclusions


def run(data_dir: Path, output: Path) -> dict[str, Any]:
    """Validate captures, run fixed 5/20/126-session protocol, write result."""
    target = _output_path(data_dir, output)
    _, coverage = scan_captures(
        data_dir / "universe" / "manifest.json",
        data_dir / "broad-history-2026-09-28",
    )
    source, stocks, exclusions = _assemble_source(data_dir, coverage)
    result = run_study(source, stocks=stocks)
    result["label"] = "broad_current_survivors_exploratory_v1"
    days = [bar["begins_at"] for bar in source["bars"][0]["bars"]]
    result["coverage"] = {
        "candidate_count": len(coverage), "study_stock_count": len(stocks),
        "excluded": exclusions, "first_session": days[0], "last_session": days[-1],
    }
    result["protocol"]["limitations"] += (
        " Current listings selected after this short study period; no held-out optimization claim. "
        "No liquidity/executable-spread model, news signal or $100 account simulation. "
        "One-round-trip fixed friction can substantially understate small-stock trading costs."
    )
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=target.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        json.dump(result, handle, indent=2, allow_nan=False)
    try:
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/equities"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    output = args.output or args.data_dir / "broad-historical-study.json"
    try:
        result = run(args.data_dir, output)
    except (OSError, ValueError, TypeError, KeyError, IndexError, UnicodeError) as exc:
        print(f"Broad study failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "source_hash": result["source_hash"],
        "candidate_count": result["coverage"]["candidate_count"],
        "study_stock_count": result["coverage"]["study_stock_count"],
        "output": str(output),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
