"""Offline coverage and past-strength ranks for a dated current-listings catalogue.

The catalogue is not a point-in-time historical universe. No forecast or paper
order is created. ``scan_captures`` returns the existing research.scan schema
and a coverage DataFrame with one row per catalogue stock candidate.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from kq.equities.research import BAR_COLUMNS, RESEARCH_COLUMNS, daily_bars, scan
from kq.equities.universe import load_universe

_REQUEST = {
    "interval": "day", "bounds": "regular", "adjustment_type": "split",
    "start_time": "2026-03-01T00:00:00Z", "end_time": "2026-09-28T00:00:00Z",
}
_COVERAGE_COLUMNS = [
    "symbol", "name", "exchange", "coverage_status", "bar_count",
    "excluded_bar_count", "latest_session",
    "source_as_of", "source_file", "reason", "as_of", "universe_as_of",
]


def _read_capture(  # noqa: PLR0912
    path: Path, allowed: set[str]
) -> tuple[datetime, list[str], list[dict[str, Any]], list[str], pd.DataFrame, dict[str, str]]:
    source = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(source, dict) or not isinstance(source.get("request"), dict):
        raise ValueError(f"malformed history capture: {path.name}")
    captured = datetime.fromisoformat(source["captured_at"].replace("Z", "+00:00"))
    if captured.tzinfo is None or captured.utcoffset() is None or captured > datetime.now(UTC):
        raise ValueError(f"invalid capture time: {path.name}")
    request = source["request"]
    if any(request.get(key) != value for key, value in _REQUEST.items()):
        raise ValueError(f"unsupported history request: {path.name}")
    symbols = request.get("symbols")
    if (not isinstance(symbols, list) or not symbols
        or any(not isinstance(s, str) or s not in allowed for s in symbols)
        or len(set(symbols)) != len(symbols)):
        raise ValueError(f"invalid requested symbols: {path.name}")
    data = source.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError(f"missing history results: {path.name}")
    series = data["results"]
    if any(not isinstance(item, dict) or item.get("symbol") not in symbols for item in series):
        raise ValueError(f"unexpected result symbol: {path.name}")
    returned = [item["symbol"] for item in series]
    if len(set(returned)) != len(returned):
        raise ValueError(f"duplicate result symbol: {path.name}")
    missing = data.get("not_found", [])
    if (
        not isinstance(missing, list)
        or any(not isinstance(s, str) or s not in symbols for s in missing)
        or len(set(missing)) != len(missing)
        or set(missing) & set(returned)
    ):
        raise ValueError(f"invalid not_found membership: {path.name}")
    if any(not isinstance(item.get("bars"), list) for item in series):
        raise ValueError(f"missing bars list: {path.name}")
    for item in series:
        if item.get("interval") != "day" or item.get("bounds") != "regular":
            raise ValueError(f"unsupported result format: {path.name}")
        seen_dates: set[object] = set()
        for bar in item["bars"]:
            if not isinstance(bar, dict) or bar.get("session") != "reg":
                raise ValueError(f"unsupported bar: {path.name}")
            starts = datetime.fromisoformat(str(bar.get("begins_at")).replace("Z", "+00:00"))
            if (starts.tzinfo is None or starts.utcoffset() is None
                or starts > captured or starts.date() >= captured.date()
                or starts.date() in seen_dates):
                raise ValueError(f"future or duplicate bar: {path.name}")
            seen_dates.add(starts.date())
            if any(
                bar.get(flag) is not None and type(bar[flag]) is not bool
                for flag in ("interpolated", "synthetic", "is_synthetic")
            ):
                raise ValueError(f"invalid bar flag: {path.name}")
    frames = []
    invalid: dict[str, str] = {}
    for item in series:
        try:
            frames.append(daily_bars({"captured_at": source["captured_at"], "bars": [item]}))
        except ValueError as exc:
            invalid[item["symbol"]] = str(exc)
    bars = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=BAR_COLUMNS)
    return captured.astimezone(UTC), symbols, series, missing, bars, invalid


def _snapshot(captured: datetime, series: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "captured_at": captured.isoformat(), "benchmark": "SPY",
        "bars": {"data": {"results": series}},
        "fundamentals": {"data": {"results": []}},
        "earnings": {"data": {"results": []}}, "news": [],
    }


def scan_captures(  # noqa: PLR0912, PLR0915
    manifest_path: Path, history_dir: Path
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate all source batches, rank with research.scan and expose every gap.

    Coverage statuses: not_requested, not_found, omitted, insufficient_history,
    missing_shared_session, ranked. ``as_of`` is the latest validated capture;
    ``source_as_of`` keeps the individual batch observation time.
    """
    universe = load_universe(manifest_path)
    candidates = universe.loc[
        (universe["category"] == "stock_candidate") & (universe["status"] == "candidate")
    ]
    allowed = set(candidates["symbol"])
    benchmark_path = history_dir / "benchmark.json"
    base_time, base_requested, base_series, base_missing, base_bars, base_invalid = _read_capture(
        benchmark_path, {"SPY"}
    )
    if base_requested != ["SPY"] or base_missing or base_invalid or len(base_series) != 1:
        raise ValueError("benchmark capture must contain SPY")
    requests: dict[str, tuple[str, datetime]] = {}
    results: dict[str, dict[str, Any]] = {}
    bar_frames: dict[str, pd.DataFrame] = {}
    captures: list[tuple[str, list[dict[str, Any]]]] = []
    not_found: set[str] = set()
    invalid: dict[str, str] = {}
    latest = base_time
    for path in sorted(history_dir.glob("*.json")):
        if path == benchmark_path:
            continue
        captured, symbols, series, missing, bars, failed = _read_capture(path, allowed)
        if set(symbols) & requests.keys():
            raise ValueError(f"duplicate requested symbol: {path.name}")
        latest = max(latest, captured)
        requests.update({symbol: (path.name, captured) for symbol in symbols})
        not_found.update(missing)
        invalid.update(failed)
        for item in series:
            symbol = item["symbol"]
            results[symbol] = item
            bar_frames[symbol] = bars.loc[bars["symbol"] == symbol]
        captures.append((path.name, [item for item in series if item["symbol"] not in failed]))
    benchmark_only = scan(_snapshot(latest, base_series))
    ranks = [benchmark_only]
    for _, series in captures:
        if series:
            ranks.append(scan(_snapshot(latest, [*base_series, *series])))
    rankings = pd.concat(ranks, ignore_index=True)[RESEARCH_COLUMNS]
    rankings["as_of"] = pd.to_datetime(rankings["as_of"], utc=True)
    ranked = set(rankings["symbol"])
    base_sessions = set(base_bars["session_date"].tail(127))
    base_latest = base_bars["session_date"].max()
    coverage = []
    for row in candidates.itertuples(index=False):
        symbol = str(row.symbol)
        source_file, source_time = requests.get(symbol, (None, None))
        bars = bar_frames.get(symbol)
        count = 0 if bars is None else len(bars)
        excluded_count = 0 if symbol not in results else sum(
            any(bar.get(flag) is True for flag in ("interpolated", "synthetic", "is_synthetic"))
            for bar in results[symbol]["bars"]
        )
        dates = set() if bars is None else set(bars["session_date"])
        if symbol in invalid:
            status = "invalid_bar"
        elif symbol in ranked:
            status = "ranked"
        elif symbol not in requests:
            status = "not_requested"
        elif symbol in not_found:
            status = "not_found"
        elif symbol not in results:
            status = "omitted"
        elif count < 127 or len(base_sessions) < 127:
            status = "insufficient_history"
        else:
            status = (
                "missing_shared_session"
                if not base_sessions.issubset(dates) or base_latest not in dates
                else "insufficient_history"
            )
        coverage.append({
            "symbol": symbol, "name": row.name, "exchange": row.exchange,
            "coverage_status": status, "bar_count": count, "excluded_bar_count": excluded_count,
            "latest_session": None if not dates else max(dates),
            "source_as_of": source_time, "source_file": source_file,
            "reason": invalid.get(symbol),
            "as_of": latest, "universe_as_of": row.as_of,
        })
    frame = pd.DataFrame(coverage, columns=_COVERAGE_COLUMNS)
    for column in ("as_of", "source_as_of", "universe_as_of"):
        frame[column] = pd.to_datetime(frame[column], utc=True)
    return rankings, frame.sort_values("symbol").reset_index(drop=True)


def _write(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        frame.to_csv(handle, index=False)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    """Write offline rank and coverage CSV files; never open the paper ledger."""
    parser = argparse.ArgumentParser(description="Offline broad current-listings scan")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--rankings", type=Path, required=True)
    parser.add_argument("--coverage", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.rankings.suffix != ".csv" or args.coverage.suffix != ".csv":
            raise ValueError("broad scan outputs must be CSV files")
        outputs = {args.rankings.resolve(), args.coverage.resolve()}
        protected = {args.manifest.resolve()} | {p.resolve() for p in args.history.glob("*.json")}
        protected.update((args.manifest.parent / name).resolve() for name in
                         ("nasdaqlisted.txt", "otherlisted.txt"))
        if len(outputs) != 2 or outputs & protected:
            raise ValueError("outputs must be distinct from source files")
        ranks, coverage = scan_captures(args.manifest, args.history)
        _write(args.rankings, ranks)
        _write(args.coverage, coverage)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        print(f"Broad scan failed: {exc}", file=sys.stderr)
        return 2
    print(f"Broad scan: {len(ranks)} ranking rows; {len(coverage)} catalogue candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
