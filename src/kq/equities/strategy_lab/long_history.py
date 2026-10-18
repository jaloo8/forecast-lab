"""Validate hashed long-history captures without fabricating pre-listing observations."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

import pandas as pd


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Source timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _read(root: Path, name: str, digest: str) -> dict[str, Any]:
    if Path(name).name != name or not name.endswith(".json"):
        raise ValueError("Unsafe capture filename")
    raw = (root / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("Capture hash mismatch: " + name)
    value: dict[str, Any] = json.loads(raw)
    return value


def _bar(symbol: str, bar: dict[str, Any], start: datetime, end: datetime) -> dict[str, Any] | None:
    when = _time(bar["begins_at"])
    if not start <= when < end or when.time().isoformat() != "00:00:00":
        raise ValueError("Bar outside declared daily interval: " + symbol)
    if any(
        isinstance(bar.get(k), bool)
        for k in ("open_price", "high_price", "low_price", "close_price", "volume")
    ):
        raise ValueError("Boolean market value: " + symbol)
    if any(bar.get(k) for k in ("interpolated", "synthetic", "is_synthetic")):
        return None
    if bar.get("session") != "reg" or bar.get("volume") == 0:
        return None
    names = {
        "open": "open_price",
        "high": "high_price",
        "low": "low_price",
        "close": "close_price",
        "volume": "volume",
    }
    values = {name: float(bar[key]) for name, key in names.items()}
    if not all(math.isfinite(v) and v > 0 for v in values.values()):
        raise ValueError("Invalid market value: " + symbol)
    if (
        not values["low"]
        <= min(values["open"], values["close"])
        <= max(values["open"], values["close"])
        <= values["high"]
    ):
        raise ValueError("Inconsistent OHLC: " + symbol)
    day = when.date()
    as_of = (pd.Timestamp(day).tz_localize("America/New_York") + pd.Timedelta(hours=16)).tz_convert(
        "UTC"
    )
    return dict(symbol=symbol, session_date=day, as_of=as_of, **values)


def load_long_capture(root: Path) -> tuple[pd.DataFrame, dict[str, Any]]:  # noqa: PLR0912, PLR0915
    """Return symbol/date/OHLCV/simulated-as_of bars and actual source provenance.

    Synthetic/zero-volume/nonregular observations are excluded with counts. A
    bad optional price is excluded and audited; benchmark, transport and identity
    failures remain fatal. Missing held prices invalidate research outcomes.
    Calendar is observed SPY sessions, not a reconstructed exchange calendar.
    """
    receipt = json.loads((root / "receipt.json").read_bytes())
    manifest = _read(root, "manifest.json", receipt["manifest_sha256"])
    if (
        manifest["protocol"] != "long-study-v1"
        or manifest["benchmark"] != "SPY"
        or manifest["adjustment_type"] != "split"
    ):
        raise ValueError("Unsupported research capture protocol")
    universe = manifest["universe"]
    if not universe or len(set(universe)) != len(universe) or "SPY" in universe:
        raise ValueError("Invalid candidate universe")
    expected = set(universe) | {"SPY"}
    hashes = {row["file"]: row["sha256"] for row in receipt["inputs"]}
    requests = manifest["requests"]
    if (
        len(hashes) != len(receipt["inputs"])
        or len({r["file"] for r in requests}) != len(requests)
        or set(hashes) != {r["file"] for r in requests}
    ):
        raise ValueError("Missing or duplicate transport evidence")
    now = datetime.now(UTC)
    captured: dict[str, str] = {}
    windows: dict[str, list[tuple[datetime, datetime]]] = defaultdict(list)
    not_found: dict[str, list[str]] = {}
    excluded: Counter[str] = Counter()
    invalid: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for request_row in requests:
        name = request_row["file"]
        wrapper = _read(root, name, hashes[name])
        request = request_row["request"]
        captured[name] = wrapper["retrieved_at"]
        retrieved = _time(captured[name])
        start, end = _time(request["start_time"]), _time(request["end_time"])
        if not start < end <= retrieved <= now or end.date() > retrieved.date():
            raise ValueError("Invalid source interval or capture time")
        if wrapper["request"] != request or (
            request["interval"],
            request["bounds"],
            request["adjustment_type"],
        ) != ("day", "regular", "split"):
            raise ValueError("Conflicting source request")
        requested = request["symbols"]
        if (
            not requested
            or len(requested) > 10
            or len(set(requested)) != len(requested)
            or not set(requested) <= expected
        ):
            raise ValueError("Invalid request symbol coverage")
        for symbol in requested:
            windows[symbol].append((start, end))
        response = wrapper["response"]
        if response.get("isError"):
            raise ValueError("Provider error: " + name)
        data = response["structuredContent"]["data"]
        result = data.get("results") or []
        missing = data.get("not_found") or []
        returned = [r["symbol"] for r in result]
        if len(returned + missing) != len(set(returned + missing)) or set(
            returned + missing
        ) != set(requested):
            raise ValueError("Unaccounted or duplicate source symbol: " + name)
        not_found[name] = missing
        for stock in result:
            symbol = stock["symbol"]
            if (
                stock["interval"] != "day"
                or stock["bounds"] != "regular"
                or stock.get("adjustment_type", "split") != "split"
            ):
                raise ValueError("Conflicting result metadata")
            for raw in stock.get("bars") or []:
                key = symbol, raw["begins_at"]
                if key in seen:
                    raise ValueError("Duplicate daily observation: " + symbol)
                seen.add(key)
                when = _time(raw["begins_at"])
                if not start <= when < end or when.time().isoformat() != "00:00:00":
                    raise ValueError("Bar outside declared daily interval: " + symbol)
                try:
                    row = _bar(symbol, raw, start, end)
                except (ValueError, TypeError, KeyError) as exc:
                    if symbol == "SPY":
                        raise
                    invalid.append(dict(symbol=symbol, begins_at=raw["begins_at"], reason=str(exc)))
                    row = None
                if row is None:
                    excluded[symbol] += 1
                else:
                    rows.append(row)
    first, last = _time(manifest["start_time"]), _time(manifest["end_time"])
    if set(windows) != expected:
        raise ValueError("Unrequested candidate")
    for intervals in windows.values():
        intervals.sort()
        if (
            intervals[0][0] != first
            or intervals[-1][1] != last
            or any(a[1] != b[0] for a, b in pairwise(intervals))
        ):
            raise ValueError("Missing or overlapping requested history")
    frame = pd.DataFrame(rows)
    if frame.empty or not frame.symbol.eq("SPY").any():
        raise ValueError("No genuine benchmark history")
    spy_dates = set(frame.loc[frame.symbol == "SPY", "session_date"])
    latest = max(spy_dates)
    beyond = int(frame.session_date.gt(latest).sum())
    frame = frame.loc[frame.session_date <= latest].copy()
    if not frame.session_date.isin(spy_dates).all():
        raise ValueError("Stock session missing from genuine benchmark history")
    source = dict(
        captured_at=max(captured.values(), key=_time),
        first_session=str(min(spy_dates)),
        last_session=str(latest),
        candidate_count=len(universe),
        stock_count=frame.loc[frame.symbol != "SPY", "symbol"].nunique(),
        universe=universe,
        not_found=not_found,
        excluded_bars=dict(excluded),
        invalid_bars=invalid,
        beyond_benchmark=beyond,
        input_sha256=hashes,
        input_captured_at=captured,
        manifest_sha256=receipt["manifest_sha256"],
        catalogue_sha256=manifest["catalogue_sha256"],
        catalogue_captured_at=manifest["catalogue_captured_at"],
        selection_rule=manifest["selection_rule"],
        adjustment_type="split",
        limitations=[
            "Current-survivor selection; omitted dividends and delisting outcomes.",
            "Simulated historical availability, actual retrieval separately retained.",
            "Observed SPY calendar; shared missing sessions are not independently verified.",
        ],
    )
    return frame.sort_values(["session_date", "symbol"]).reset_index(drop=True), source
