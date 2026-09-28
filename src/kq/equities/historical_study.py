"""Offline, exploratory 5/20/126-session stock momentum study."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import tempfile
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

STOCKS = ("AAPL", "MSFT", "AMZN", "JPM", "XOM", "COST")
HORIZONS = (5, 20, 126)
BLOCKS = (("2010-2018", 2010, 2018), ("2019-2022", 2019, 2022), ("2023-2026", 2023, 2026))
FRICTION = 0.999 / 1.001
NY = ZoneInfo("America/New_York")


def _time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be a UTC string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid UTC timestamp") from exc
    offset = parsed.utcoffset()
    if parsed.tzinfo is None or offset is None or offset.total_seconds():
        raise ValueError("timestamp must be UTC")
    return parsed.astimezone(UTC)


def _price(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("boolean is not a price or volume")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid price or volume") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError("price and volume must be finite and positive")
    return result


def _history(source: dict[str, Any]) -> pd.DataFrame:  # noqa: PLR0912
    """Validated daily bars: symbol, session_date, OHLC, volume, as_of (UTC)."""
    if source.get("benchmark") != "SPY" or set(source.get("universe", [])) != set(STOCKS):
        raise ValueError("expected fixed six-stock universe and SPY")
    if source.get("adjustment_type") != "split":
        raise ValueError("expected split-adjusted prices")
    raw = source.get("bars")
    if not isinstance(raw, list) or len(raw) != 7:
        raise ValueError("expected seven complete histories")
    records: list[dict[str, Any]] = []
    dates_by_symbol: dict[str, tuple[date, ...]] = {}
    for series in raw:
        symbol = series.get("symbol")
        if symbol not in (*STOCKS, "SPY") or symbol in dates_by_symbol:
            raise ValueError("duplicate or unknown history symbol")
        if series.get("interval") != "day" or series.get("bounds") != "regular":
            raise ValueError("expected regular daily bars")
        bars = series.get("bars")
        if not isinstance(bars, list) or not bars:
            raise ValueError("empty price history")
        days: list[date] = []
        for bar in bars:
            if bar.get("session") != "reg" or any(
                bar.get(flag) for flag in ("interpolated", "is_synthetic", "synthetic")
            ):
                raise ValueError("synthetic or nonregular bar")
            begins = _time(bar.get("begins_at"))
            if begins.time() != time.min:
                raise ValueError("daily bar must begin at midnight UTC")
            day = begins.date()
            if not date(2010, 1, 1) <= day <= date(2026, 9, 25):
                raise ValueError("session outside locked study period")
            if days and day <= days[-1]:
                raise ValueError("duplicate or unordered sessions")
            opened, high, low, closed = (
                _price(bar[key]) for key in ("open_price", "high_price", "low_price", "close_price")
            )
            if high < max(opened, closed) or low > min(opened, closed) or low > high:
                raise ValueError("inconsistent OHLC bar")
            volume = _price(bar.get("volume"))
            as_of = datetime.combine(day, time(16), NY).astimezone(UTC)
            records.append(
                dict(
                    symbol=symbol,
                    session_date=day,
                    open=opened,
                    high=high,
                    low=low,
                    close=closed,
                    volume=volume,
                    as_of=as_of,
                )
            )
            days.append(day)
        dates_by_symbol[symbol] = tuple(days)
    if set(dates_by_symbol) != {*STOCKS, "SPY"} or len(set(dates_by_symbol.values())) != 1:
        raise ValueError("stock and SPY sessions must match exactly")
    captured = _time(source.get("captured_at"))
    if captured <= max(record["as_of"] for record in records):
        raise ValueError("capture precedes completed regular-session bars")
    return pd.DataFrame.from_records(records)


def _group(block: str, horizon: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    nets = [float(row["net_return"]) for row in rows]
    invested = [row for row in rows if row["selected"]]
    return {
        "block": block,
        "horizon_sessions": horizon,
        "cohort_count": len(rows),
        "invested_count": len(invested),
        "mean_net_return": statistics.mean(nets) if nets else None,
        "median_net_return": statistics.median(nets) if nets else None,
        "positive_fraction_invested": (
            sum(row["net_return"] > 0 for row in invested) / len(invested) if invested else None
        ),
        "mean_excess_vs_matched_spy": (
            statistics.mean(row["excess_vs_matched_spy"] for row in rows) if rows else None
        ),
        "mean_spy_market_net_return": (
            statistics.mean(row["spy_market_net_return"] for row in rows) if rows else None
        ),
        "worst_cohort": min(rows, key=lambda row: row["net_return"]) if rows else None,
        "best_cohort": max(rows, key=lambda row: row["net_return"]) if rows else None,
    }


def run_study(source: dict[str, Any]) -> dict[str, Any]:
    """Apply fixed nonoverlapping cohorts; returns JSON-ready study and raw rows."""
    frame = _history(source)
    canonical = json.dumps(source, sort_keys=True, separators=(",", ":"), allow_nan=False)
    source_hash = hashlib.sha256(canonical.encode()).hexdigest()
    prices = {
        symbol: frame.loc[frame["symbol"] == symbol].reset_index(drop=True)
        for symbol in (*STOCKS, "SPY")
    }
    spy = prices["SPY"]
    days = spy["session_date"].tolist()
    cohorts: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    for block, first_year, last_year in BLOCKS:
        indices = [i for i, day in enumerate(days) if first_year <= day.year <= last_year]
        for horizon in HORIZONS:
            block_rows: list[dict[str, Any]] = []
            if indices:
                signal = max(indices[0], horizon)
                while signal + horizon <= indices[-1]:
                    benchmark_momentum = (
                        float(spy.at[signal, "close"]) / float(spy.at[signal - horizon, "close"])
                        - 1
                    )
                    scores = [
                        (
                            symbol,
                            float(prices[symbol].at[signal, "close"])
                            / float(prices[symbol].at[signal - horizon, "close"])
                            - 1
                            - benchmark_momentum,
                        )
                        for symbol in STOCKS
                    ]
                    chosen = sorted(
                        (item for item in scores if item[1] > 0),
                        key=lambda item: (-item[1], item[0]),
                    )[:3]
                    gross_by_symbol = {
                        symbol: float(prices[symbol].at[signal + horizon, "close"])
                        / float(prices[symbol].at[signal + 1, "open"])
                        - 1
                        for symbol, _ in chosen
                    }
                    gross = statistics.mean(gross_by_symbol.values()) if chosen else 0.0
                    net = (1 + gross) * FRICTION - 1 if chosen else 0.0
                    spy_market = (
                        float(spy.at[signal + horizon, "close"])
                        / float(spy.at[signal + 1, "open"])
                        * FRICTION
                        - 1
                    )
                    matched = spy_market if chosen else 0.0
                    row = {
                        "block": block,
                        "horizon_sessions": horizon,
                        "signal_date": days[signal].isoformat(),
                        "signal_as_of": spy.at[signal, "as_of"].isoformat(),
                        "entry_date": days[signal + 1].isoformat(),
                        "exit_date": days[signal + horizon].isoformat(),
                        "selected": [symbol for symbol, _ in chosen],
                        "selected_excess_momentum": {symbol: score for symbol, score in chosen},
                        "selected_gross_returns": gross_by_symbol,
                        "gross_return": gross,
                        "net_return": net,
                        "matched_spy_net_return": matched,
                        "spy_market_net_return": spy_market,
                        "excess_vs_matched_spy": net - matched,
                        "source_hash": source_hash,
                        "source_captured_at": _time(source["captured_at"]).isoformat(),
                    }
                    block_rows.append(row)
                    signal += horizon
            cohorts.extend(block_rows)
            groups.append(_group(block, horizon, block_rows))
    return {
        "label": "historical_momentum_study_v1",
        "captured_at": source["captured_at"],
        "source_hash": source_hash,
        "protocol": {
            "stocks": list(STOCKS),
            "benchmark": "SPY",
            "lookback_hold_sessions": list(HORIZONS),
            "friction_each_side_bps": 10,
            "blocks": [name for name, _, _ in BLOCKS],
            "limitations": (
                "Survivor-biased price-only study; no dividends or delisting returns. "
                "Sessions align to provider SPY history; omissions shared by all symbols "
                "are not detected, so holding periods count observed bars."
            ),
        },
        "groups": groups,
        "cohorts": cohorts,
    }


def main(argv: list[str] | None = None) -> int:
    """Run the locked offline protocol without opening a forward paper ledger."""
    parser = argparse.ArgumentParser(description="Offline historical stock paper research")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.input.resolve() == args.output.resolve() or args.output.suffix != ".json":
            raise ValueError("output must be a separate JSON file")
        source = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(source, dict):
            raise ValueError("source must be a JSON object")
        result = run_study(source)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=args.output.parent,
            prefix=".historical-study-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(result, handle, allow_nan=False, indent=2)
        try:
            temporary.replace(args.output)
        finally:
            temporary.unlink(missing_ok=True)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Historical study failed: {exc}", file=sys.stderr)
        return 2
    print(f"Historical study: {len(result['cohorts'])} cohorts; {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
