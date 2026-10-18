"""Load the dated broad archive, preserving its survivor/grid selection limitations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from kq.equities.broad_scan import scan_captures
from kq.equities.historical_study import _history


def load_archive(data_dir: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return validated OHLCV and actual source provenance for the locked 2026 archive.

    Bar schema is symbol/session_date/open/high/low/close/volume/as_of, with as_of
    explicitly the simulated session close. Retrieval time stays in source metadata.
    """
    history = data_dir / "broad-history-2026-09-28"
    manifest_path = data_dir / "universe/manifest.json"
    _, coverage = scan_captures(manifest_path, history)
    eligible = set(coverage.loc[coverage.coverage_status == "ranked", "symbol"])
    exclusions = dict(
        zip(
            coverage.loc[coverage.coverage_status != "ranked", "symbol"],
            coverage.loc[coverage.coverage_status != "ranked", "coverage_status"],
            strict=True,
        )
    )
    captures = []
    hashes = {}
    capture_times = {}
    selected: dict[str, dict[str, Any]] = {}
    spy = json.loads((history / "benchmark.json").read_bytes())["data"]["results"][0]
    days = [b["begins_at"] for b in spy["bars"]]
    for path in sorted(history.glob("*.json")):
        raw = path.read_bytes()
        hashes[path.name] = hashlib.sha256(raw).hexdigest()
        capture = json.loads(raw)
        captures.append(capture["captured_at"])
        capture_times[path.name] = capture["captured_at"]
        for row in capture["data"]["results"]:
            if row.get("adjustment_type", "split") != "split":
                raise ValueError("Contradictory archive result adjustment: " + path.name)
            symbol = row["symbol"]
            if symbol not in eligible:
                continue
            complete = [b["begins_at"] for b in row["bars"]] == days and all(
                not any(b.get(k) for k in ("synthetic", "interpolated", "is_synthetic"))
                and not isinstance(b["volume"], bool)
                and float(b["volume"]) > 0
                for b in row["bars"]
            )
            if not complete:
                exclusions[symbol] = "incomplete_real_positive_volume_grid"
            elif symbol in selected:
                raise ValueError("Duplicate archive stock " + symbol)
            else:
                selected[symbol] = row
    if not selected or len(selected) + len(exclusions) != len(coverage):
        raise ValueError("Incomplete archive coverage accounting")
    source = dict(
        benchmark="SPY",
        adjustment_type="split",
        universe=sorted(selected),
        captured_at=max(captures),
        bars=[spy, *[selected[s] for s in sorted(selected)]],
    )
    bars = _history(source, tuple(sorted(selected)))
    metadata = {
        "captured_at": max(captures),
        "first_session": days[0][:10],
        "last_session": days[-1][:10],
        "stock_count": len(selected),
        "candidate_count": len(coverage),
        "excluded": exclusions,
        "input_sha256": hashes,
        "input_captured_at": capture_times,
        "catalogue_captured_at": json.loads(manifest_path.read_bytes()).get("captured_at"),
        "catalogue_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "source_hash": hashlib.sha256(
            json.dumps(source, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "limitations": [
            "Exploratory current-survivor sample; previously inspected dates, "
            "not untouched validation.",
            "No dividends or delisting returns; complete-grid filtering also uses "
            "future availability.",
            "Simulated decision close timestamps are not actual source retrieval timestamps.",
            "Fixed cost scenarios are not executable quotes; no news or options signal.",
            "Holding periods count observed SPY bars; omissions shared by every symbol "
            "are not detected by an exchange calendar check.",
        ],
    }
    return bars, metadata
