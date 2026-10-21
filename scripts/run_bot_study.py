"""Run a fixed, offline bot-rule screen; retain all configurations and starts."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from kq.equities.bot_study import (
    COLUMNS,
    RULES,
    adjusted_prices,
    annual_returns,
    build_signals,
    metrics,
    simulate,
)

REGISTRATION = "docs/research/bot-study-registration-2026-10-21.json"
REGISTRATION_SHA256 = "d3b11968c2b8c8bcbe7050b61d317b0a9c980437a47a1d1c4403ee84cd2ebaf9"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_inputs(parent: Path, reg: dict[str, Any]) -> dict[str, pd.DataFrame]:
    result = {}
    for entry in reg["inputs"]:
        path = parent / entry["path"]
        if digest(path) != entry["sha256"]:
            raise ValueError(f"Input hash differs: {entry['symbol']}")
        raw = pd.read_csv(path, index_col="Date", parse_dates=True)
        result[entry["symbol"]] = adjusted_prices(raw).loc[:"2025-12-31"]
    return result


def prepare(
    symbol: str,
    signal_symbol: str,
    prices: dict[str, pd.DataFrame],
    signals: dict[str, pd.DataFrame],
    lag: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = prices[symbol]
    shifted = signals[signal_symbol][[*RULES, "warmup_ready"]].shift(lag, fill_value=False)
    if not frame.index.isin(shifted.index).all():
        raise ValueError(f"Missing underlying date: {symbol}")
    shifted = shifted.reindex(frame.index)
    common_ready = (
        signals[signal_symbol].warmup_ready.shift(2, fill_value=False).reindex(frame.index)
    )
    eligible = common_ready & (frame.index >= "2000-01-01")
    if symbol == "TECL":
        eligible &= frame.index >= "2012-07-02"
    return frame.loc[eligible], shifted.loc[eligible, list(RULES)]


def primary_runs(
    entry: dict[str, Any],
    frame: pd.DataFrame,
    targets: pd.DataFrame,
    reg: dict[str, Any],
    output: Path,
    lag: int,
    calendar: pd.DatetimeIndex,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    summaries, annual = [], []
    for window, (start, end) in reg["periods"].items():
        part = frame.loc[start:end]
        if part.empty:
            raise ValueError(f"No data: {entry['symbol']}/{window}")
        desired = targets.reindex(part.index)
        op, cl = part.Open.to_numpy(float), part.Close.to_numpy(float)
        for rule in RULES:
            target = desired[rule].to_numpy(bool)
            for cost in reg["costs_bps_per_side"]:
                trial = f"{entry['symbol']}__{rule}__{window}__c{cost}__lag{lag}"
                path = simulate(op, cl, target, cost)
                meta = dict(
                    trial=trial,
                    symbol=entry["symbol"],
                    kind=entry["kind"],
                    signal_symbol=entry["signal_symbol"],
                    rule=rule,
                    window=window,
                    cost_bps=cost,
                    lag=lag,
                )
                ledger_path = output / "ledgers" / f"{trial}.npz"
                np.savez_compressed(
                    ledger_path,
                    dates=part.index.to_numpy("datetime64[D]"),
                    values=path.values,
                    target=target,
                    opened=op,
                    closed=cl,
                    columns=np.array(COLUMNS),
                )
                summaries.append(
                    {**meta, **metrics(part.index, path), "ledger_sha256": digest(ledger_path)}
                )
                annual.extend({**meta, **row} for row in annual_returns(part.index, path, calendar))
    return summaries, annual


def short_runs(
    entry: dict[str, Any], frame: pd.DataFrame, targets: pd.DataFrame
) -> list[dict[str, Any]]:
    rows = []
    months = frame.index.to_period("M")
    starts = np.flatnonzero(np.r_[True, months[1:] != months[:-1]])
    op, cl = frame.Open.to_numpy(float), frame.Close.to_numpy(float)
    for rule in RULES:
        target = targets[rule].to_numpy(bool)
        for length in (5, 21, 63):
            for i in starts:
                j = int(i) + length
                if j > len(frame):
                    continue
                dates = frame.index[i:j]
                result = metrics(dates, simulate(op[i:j], cl[i:j], target[i:j], 10))
                result.pop("cagr")
                rows.append(dict(symbol=entry["symbol"], rule=rule, horizon=length, **result))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    registration_path = root / REGISTRATION
    if digest(registration_path) != REGISTRATION_SHA256:
        raise ValueError("Frozen registration changed")
    reg = json.loads(registration_path.read_text(encoding="utf-8"))
    output = args.output
    if output.exists():
        raise ValueError("Output must not exist; preserve earlier trials")
    output.mkdir(parents=True)
    (output / "ledgers").mkdir()
    (output / "signals").mkdir()
    write_json(
        output / "started.json",
        {
            "started_utc": datetime.now(UTC).isoformat(),
            "registration_sha256": REGISTRATION_SHA256,
            "source_hashes": {
                p: digest(root / p)
                for p in (REGISTRATION, "src/kq/equities/bot_study.py", "scripts/run_bot_study.py")
            },
            "inputs": reg["inputs"],
            "new_data_cost_usd": 0,
            "paid_model_calls": 0,
            "broker_orders": 0,
        },
    )
    prices = load_inputs(args.parent, reg)
    signal_symbols = sorted({x["signal_symbol"] for x in reg["inputs"]})
    signals = {s: build_signals(prices[s]) for s in signal_symbols}
    for symbol, signal in signals.items():
        signal.to_csv(output / "signals" / f"{symbol}.csv.gz", index_label="decision_date")
    summaries, annual, short = [], [], []
    for entry in reg["inputs"]:
        for lag in reg["lags_sessions"]:
            frame, targets = prepare(entry["symbol"], entry["signal_symbol"], prices, signals, lag)
            summary_rows, annual_rows = primary_runs(
                entry, frame, targets, reg, output, lag, prices["SPY"].index
            )
            summaries.extend(summary_rows)
            annual.extend(annual_rows)
            if lag == 1:
                short.extend(short_runs(entry, frame, targets))
        print(
            json.dumps(
                {
                    "completed_symbol": entry["symbol"],
                    "primary_accounts": len(summaries),
                    "fresh_starts": len(short),
                }
            ),
            flush=True,
        )
    summary = pd.DataFrame(summaries)
    summary.to_csv(output / "summary.csv", index=False)
    pd.DataFrame(annual).to_csv(output / "annual.csv.gz", index=False)
    pd.DataFrame(short).to_parquet(output / "fresh_starts.parquet", index=False)
    selection = summary.loc[
        (summary.window == "training")
        & (summary.cost_bps == 10)
        & (summary.lag == 1)
        & summary.rule.str.startswith("B")
    ]
    selection = (
        selection.sort_values(["symbol", "cagr", "rule"], ascending=[True, False, True])
        .groupby("symbol")
        .head(1)
    )
    selection.to_csv(output / "training_selection.csv", index=False)
    write_json(
        output / "completed.json",
        {
            "completed_utc": datetime.now(UTC).isoformat(),
            "primary_accounts": len(summary),
            "fresh_start_accounts": len(short),
            "annual_rows": len(annual),
            "rules": len(RULES),
            "instruments": len(reg["inputs"]),
            "public_output_hashes": {
                n: digest(output / n)
                for n in (
                    "summary.csv",
                    "annual.csv.gz",
                    "fresh_starts.parquet",
                    "training_selection.csv",
                )
            },
        },
    )


if __name__ == "__main__":
    main()
