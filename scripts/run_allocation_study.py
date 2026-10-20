"""Run the separately registered six-asset allocation study without network access."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from kq.equities.allocation_signals import build_signals
from kq.equities.allocation_study import Prices, simulate
from kq.equities.stock_family_study import summarize

REGISTRATION = "docs/research/allocation-study-registration-2026-10-20.json"
REGISTRATION_SHA256 = "55c0b3e4e593cb72a3454464e1b21f1a701809adc9e9e6ebf76a8d9a8751086e"
SYMBOLS = ("SPY", "EFA", "IEF", "VNQ", "GLD", "BIL")
POLICIES = ("C01", "C02", "C03", "C04", "A01", "A02", "I01", "I02", "I03", "I04", "O01", "O02")
SOURCE_FILES = (
    "src/kq/equities/allocation_signals.py",
    "src/kq/equities/allocation_study.py",
    "src/kq/equities/stock_family_study.py",
    "scripts/run_allocation_study.py",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_registration() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    path = root / REGISTRATION
    if digest(path) != REGISTRATION_SHA256:
        raise ValueError("Frozen allocation registration changed")
    value: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if (
        tuple(p["id"] for p in value["policies"]) != POLICIES
        or tuple(value["inputs"]["symbols"]) != SYMBOLS
        or value["planned_accounts"] != 108
    ):
        raise ValueError("Unexpected registration inventory")
    return value


def load_inputs(source: Path, registration: dict[str, Any]) -> tuple[Prices, dict[str, Any]]:
    """Verify each private input before constructing the six-asset price panel."""
    specification = registration["inputs"]
    manifest_path = source / "manifest.json"
    if digest(manifest_path) != specification["manifest_sha256"]:
        raise ValueError("Source manifest differs from registration")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    opened, closed = {}, {}
    dates: pd.DatetimeIndex | None = None
    for symbol in SYMBOLS:
        meta = manifest["files"][symbol]
        path = source / meta["file"]
        if (
            digest(path) != meta["sha256"]
            or digest(path) != specification["file_sha256"][path.name]
        ):
            raise ValueError(f"Source hash differs: {symbol}")
        frame = pd.read_csv(path)
        parsed = pd.DatetimeIndex(pd.to_datetime(frame.pop("Date"), errors="raise"))
        values = frame[["Open", "High", "Low", "Close", "Adj Close"]].to_numpy(float)
        if (
            parsed.isna().any()
            or parsed.has_duplicates
            or not parsed.is_monotonic_increasing
            or parsed.tz is not None
            or not parsed.equals(parsed.normalize())
            or not np.isfinite(values).all()
            or (values <= 0).any()
            or (frame.High < frame[["Open", "Low", "Close"]].max(axis=1)).any()
            or (frame.Low > frame[["Open", "High", "Close"]].min(axis=1)).any()
        ):
            raise ValueError(f"Invalid source dates/prices: {symbol}")
        frame.index = parsed
        frame = frame.loc[specification["common_start"] : specification["truncate_at"]]
        if dates is not None and not dates.equals(frame.index):
            raise ValueError(f"Missing or mismatched observed session: {symbol}")
        dates = frame.index
        opened[symbol] = frame.Open * frame["Adj Close"] / frame.Close
        closed[symbol] = frame["Adj Close"]
    prices = Prices(pd.DataFrame(opened), pd.DataFrame(closed))
    if (
        prices.closed.empty
        or str(prices.closed.index[0].date()) != "2007-05-30"
        or str(prices.closed.index[-1].date()) != "2025-12-31"
        or len(prices.closed) != 4679
    ):
        raise ValueError("Registered common source interval changed")
    return prices, {
        "manifest_sha256": specification["manifest_sha256"],
        "file_sha256": specification["file_sha256"],
        "common_start": "2007-05-30",
        "end": "2025-12-31",
        "sessions": len(prices.closed),
        "after_2025_excluded": True,
    }


def select_training(results: list[dict[str, Any]], registration: dict[str, Any]) -> dict[str, Any]:
    eligible = set(registration["selection"]["eligible"])
    candidates = [
        r
        for r in results
        if r["window"] == "training" and r["cost_bps"] == 25 and r["policy"] in eligible
    ]
    if len(candidates) != 8 or {r["policy"] for r in candidates} != eligible:
        raise ValueError("Incomplete training selection")
    ranked = sorted(
        candidates,
        key=lambda r: (-r["worst_year"], -r["cagr"], -r["max_drawdown"], r["policy"]),
    )
    return {
        "selected_policy": ranked[0]["policy"],
        "saved_utc": datetime.now(UTC).isoformat(),
        "basis": "Training 2008-2015 only; evaluation/full not computed",
        "ranked_training": ranked,
    }


def metrics(
    daily: pd.DataFrame, ledger: pd.DataFrame, policy: str, cost: int, window: str
) -> dict[str, Any]:
    result = summarize(daily)
    traded = np.abs(
        ledger[[f"delta_{s}" for s in SYMBOLS]].to_numpy(float)
        * ledger[[f"price_{s}" for s in SYMBOLS]].to_numpy(float)
    )
    result.update(
        panel="fractional",
        policy=policy,
        cost_bps=cost,
        window=window,
        sessions=len(daily),
        mean_exposure_fraction=float((1 - daily.cash / daily.nav).mean()),
        portfolio_trade_events=int((ledger.cost > 0).sum()),
        trade_count=int((traded > 1e-12).sum()),
        turnover=float(traded.sum()),
        sub_dollar_traded_legs=int(((traded > 1e-12) & (traded < 1)).sum()),
        smallest_positive_traded_leg_usd=float(traded[traded > 1e-12].min())
        if (traded > 1e-12).any()
        else None,
    )
    if policy.startswith("I"):
        breach_columns = (
            "floor_breached_open_before",
            "floor_breached_open_after",
            "floor_breached_close_before",
            "floor_breached_nav",
        )
        result["floor_breach_sessions"] = int(daily[list(breach_columns)].any(axis=1).sum())
        result["minimum_nav_minus_floor"] = float(
            (
                daily[["open_before", "open_after", "close_before", "nav"]].min(axis=1)
                - daily.floor
            ).min()
        )
    return result


def run_study(source: Path, output: Path, review: Path) -> None:  # noqa: PLR0912, PLR0915
    root = Path(__file__).resolve().parents[1]
    registration = read_registration()
    if output.exists():
        raise FileExistsError("Use a new output directory; all prior results are preserved")
    code_hashes = {name: digest(root / name) for name in SOURCE_FILES}
    approval = json.loads(review.read_text(encoding="utf-8"))
    if (
        approval.get("status") != "PASS"
        or approval.get("registration_sha256") != REGISTRATION_SHA256
        or any(approval.get("code_sha256", {}).get(k) != v for k, v in code_hashes.items())
    ):
        raise ValueError("Current source hashes need a passing pre-performance static review")
    prices, inputs = load_inputs(source, registration)
    expected = [
        (policy, cost, window)
        for window in registration["windows"]
        for cost in registration["costs_bps"]
        for policy in POLICIES
    ]
    index = {"|".join(map(str, key)): {"status": "planned"} for key in expected}
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "trial-index.json", index)
    write_json(
        output / "started.json",
        {
            "started_utc": datetime.now(UTC).isoformat(),
            "registration_sha256": REGISTRATION_SHA256,
            "code_sha256": code_hashes,
            "review_sha256": digest(review),
            "inputs": inputs,
            "planned_paths": len(expected),
        },
    )
    try:
        signals = build_signals(prices)
    except Exception as exc:
        write_json(
            output / "setup-error.json",
            {"stage": "signals", "error_type": type(exc).__name__, "error": str(exc)},
        )
        raise
    for policy, panel in signals.items():
        panel.to_csv(
            output / f"signals_{policy}.csv.gz",
            index=True,
            compression={"method": "gzip", "mtime": 0},
        )
    results: list[dict[str, Any]] = []
    for policy, cost, window in expected:
        key = "|".join(map(str, (policy, cost, window)))
        start, end = registration["windows"][window]
        if window != "training" and not (output / "selection.json").exists():
            write_json(output / "selection.json", select_training(results, registration))
            print(json.dumps({"training_complete": 36, "selection_saved": True}), flush=True)
        try:
            daily, ledger = simulate(prices, signals, policy, cost, start, end)
            result = metrics(daily, ledger, policy, cost, window)
            wanted_dates = prices.closed.loc[start:end].index
            actual_dates = pd.DatetimeIndex(pd.to_datetime(daily.session_date))
            years = {str(year) for year in range(int(start[:4]), int(end[:4]) + 1)}
            if not actual_dates.equals(wanted_dates) or set(result["annual"]) != years:
                raise ValueError("Incomplete registered session/year window")
            stem = f"fractional_{policy}_c{cost}_{window}"
            for suffix, frame in (("daily", daily), ("ledger", ledger)):
                frame.to_csv(
                    output / f"{stem}_{suffix}.csv.gz",
                    index=False,
                    compression={"method": "gzip", "mtime": 0},
                )
            results.append(result)
            index[key] = {"status": "complete", "output_stem": stem}
            write_json(output / "results.json", results)
        except Exception as exc:
            index[key] = {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            write_json(output / "trial-index.json", index)
            raise
        write_json(output / "trial-index.json", index)
        if len(results) % 12 == 0:
            print(json.dumps({"completed_accounts": len(results), "planned": 108}), flush=True)
    if len(results) != 108 or any(row["status"] != "complete" for row in index.values()):
        raise ValueError("Trial inventory incomplete")
    if any(digest(root / name) != value for name, value in code_hashes.items()):
        raise ValueError("Source changed during the study")
    comparisons = []
    for row in results:
        spy = next(
            r
            for r in results
            if r["policy"] == "C03"
            and r["window"] == row["window"]
            and r["cost_bps"] == row["cost_bps"]
        )
        comparisons.append(
            {
                "policy": row["policy"],
                "window": row["window"],
                "cost_bps": row["cost_bps"],
                "cagr_minus_same_spy": row["cagr"] - spy["cagr"],
                "annual_minus_same_spy": {
                    y: value - spy["annual"][y] for y, value in row["annual"].items()
                },
            }
        )
    write_json(output / "comparisons.json", comparisons)
    write_json(
        output / "manifest.json",
        {
            "completed_utc": datetime.now(UTC).isoformat(),
            "registration_sha256": REGISTRATION_SHA256,
            "code_sha256": code_hashes,
            "inputs": inputs,
            "completed_paths": len(results),
            "blocked_paths": 0,
            "external_api_spend_usd": 0,
            "output_sha256": {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()},
            "limitations": registration["account"]["practical_limits"],
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    arguments = parser.parse_args()
    run_study(arguments.source, arguments.output, arguments.review)
