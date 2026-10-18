"""Offline illustration of the guide's fixed KO/PEP example, not its private bots."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from kq.equities.expanded_replay import replay_path, require_sessions
from kq.equities.pair_replay import replay_pair

PROTOCOL_SHA = "5fb678e6d5ef86cfd7eb58c0273d6e063b58beab6a030012c8e114db5c69a405"
REFERENCE_SHA = "edaadd1db3468aa02188d3dcd6f7888025b14c163e1b9c609319fae4767863ea"


def load_symbol(history: Path, symbol: str) -> tuple[pd.DataFrame, dict]:
    """Read one hashed vendor capture; reject unpriced/invalid full-window rows."""
    receipt = json.loads((history / f"{symbol}.receipt.json").read_text())
    raw = gzip.decompress((history / f"{symbol}.json.gz").read_bytes())
    if receipt["status"] != "ok" or hashlib.sha256(raw).hexdigest() != receipt["sha256"]:
        raise ValueError("Source receipt mismatch")
    source = json.loads(raw)["chart"]["result"][0]
    if source["meta"]["currency"] != "USD" or source["meta"]["symbol"] != symbol:
        raise ValueError("Wrong source identity")
    dates = pd.to_datetime(source["timestamp"], unit="s", utc=True)
    dates = dates.tz_convert("America/New_York").tz_localize(None).normalize()
    frame = pd.DataFrame(source["indicators"]["quote"][0], index=dates).astype(float)
    frame["adjusted"] = source["indicators"]["adjclose"][0]["adjclose"]
    frame = frame.loc["2005-01-01":"2025-12-31"]
    if (
        not dates.is_unique
        or not dates.is_monotonic_increasing
        or not np.isfinite(frame).all().all()
        or not frame.gt(0).all().all()
        or frame.low.gt(frame[["open", "close"]].min(axis=1) + 1e-6).any()
        or frame.high.lt(frame[["open", "close"]].max(axis=1) - 1e-6).any()
    ):
        raise ValueError(f"Invalid historical OHLCV: {symbol}")
    return pd.DataFrame(
        {"open": frame.open * frame.adjusted / frame.close, "close": frame.adjusted}
    ), receipt


def measure(daily: pd.DataFrame) -> dict:
    nav = daily.nav
    ends = nav.groupby(nav.index.year).last()
    annual = ends / ends.shift(1, fill_value=1000) - 1
    return {
        "ending_nav": float(nav.iloc[-1]),
        "cagr": float((nav.iloc[-1] / 1000) ** (1 / 20) - 1),
        "max_drawdown": float((nav / nav.cummax().clip(lower=1000) - 1).min()),
        "worst_year": float(annual.min()),
        "annual": {str(k): float(v) for k, v in annual.items()},
        "cost_usd": float(daily.cost.sum()),
    }


def run(capture: Path, output: Path, protocol: Path) -> None:
    if output.exists():
        raise FileExistsError("Refuse to overwrite an experiment")
    if hashlib.sha256(protocol.read_bytes()).hexdigest() != PROTOCOL_SHA:
        raise ValueError("Frozen protocol changed")
    reference = capture / "sector-rerun/spy_hold_c10_daily.csv"
    if hashlib.sha256(reference.read_bytes()).hexdigest() != REFERENCE_SHA:
        raise ValueError("Reference calendar changed")
    expected = pd.DatetimeIndex(pd.read_csv(reference, parse_dates=["session_date"]).session_date)
    if len(expected) != 5031 or expected[0].year != 2006 or expected[-1].year != 2025:
        raise ValueError("Incomplete reference calendar")
    frames, receipts = {}, {}
    for symbol in ("KO", "PEP", "SPY"):
        frames[symbol], receipts[symbol] = load_symbol(capture / "history", symbol)
    dates = frames["SPY"].index
    for frame in frames.values():
        require_sessions(frame.index, dates)
    evaluated = dates.year >= 2006
    require_sessions(dates[evaluated], expected)
    opened = pd.DataFrame({s: frames[s].open for s in ("KO", "PEP")})
    closed = pd.DataFrame({s: frames[s].close for s in ("KO", "PEP")})
    start = int(np.flatnonzero(evaluated)[0])
    output.mkdir(parents=True)
    (output / "manifest.json").write_text(
        json.dumps(
            {"protocol_sha256": PROTOCOL_SHA, "receipts": receipts, "status": "running"}, indent=2
        )
    )
    results = []
    for cost in (10, 25, 50):
        for borrow in (0, 0.03, 0.10):
            name = f"pair_c{cost}_b{int(borrow * 100)}"
            daily, trades = replay_pair(opened, closed, None, cost, borrow, start=start)
            (output / f"{name}_orders.json").write_text(
                json.dumps(
                    [
                        {
                            "execution_session": str(dates[i]),
                            "signal_session": str(dates[i - 1]),
                            "direction": side,
                        }
                        for i, side in daily.attrs["orders"].items()
                    ],
                    indent=2,
                )
            )
            daily = daily.loc[evaluated]
            daily.to_csv(output / f"{name}_daily.csv")
            trades.to_csv(output / f"{name}_trades.csv", index=False)
            row = dict(
                measure(daily),
                method="pair",
                cost_bps=cost,
                borrow_rate=borrow,
                trades=len(trades),
                borrow_usd=float(daily.borrow.sum()),
                win_rate=float(trades.net_pnl.gt(0).mean()) if len(trades) else None,
            )
            results.append(row)
        spy = frames["SPY"].loc[evaluated]
        benchmark = replay_path(
            spy.index,
            spy[["open"]].to_numpy(),
            spy[["close"]].to_numpy(),
            {0: np.array([0.5])},
            cost,
        )
        benchmark.to_csv(output / f"spy50_c{cost}_daily.csv")
        results.append(dict(measure(benchmark), method="spy50", cost_bps=cost))
    (output / "results.json").write_text(json.dumps(results, indent=2))
    pd.DataFrame([{k: v for k, v in row.items() if k != "annual"} for row in results]).to_csv(
        output / "metrics.csv", index=False
    )
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "protocol_sha256": PROTOCOL_SHA,
                "reference_sha256": REFERENCE_SHA,
                "receipts": receipts,
                "status": "completed",
                "scenarios": len(results),
                "sessions": len(expected),
            },
            indent=2,
        )
    )
    print(json.dumps(results))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    args = parser.parse_args()
    run(args.capture, args.output, args.protocol)
