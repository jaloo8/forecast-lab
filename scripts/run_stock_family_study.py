"""Run the frozen279-account stock/ETF study offline; no provider or broker calls."""

import argparse
import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scripts import run_directional_study as archive_tools

from kq.equities.stock_family_study import (
    ACTIVE_POLICIES,
    POLICIES,
    SYMBOLS,
    build_signals,
    prepare_prices,
    simulate,
    simulate_integer_spy,
    summarize,
)

REGISTRATION = "docs/research/strategy-family-registration-2026-10-19.json"
REGISTRATION_SHA256 = "15c3a226c695aedf293be475bb76c9e515e92e7e1f12ad51a712eccda0a0f2b9"
AMENDMENT = "docs/research/strategy-family-amendment-01-2026-10-19.json"
AMENDMENT_SHA256 = "c2c81fbc2f596e4f129d663013b1f20b1c23cbbbc93a3cb26439bed7203c43b0"
WINDOWS = {
    "training": ("2006-01-01", "2013-12-31"),
    "evaluation": ("2014-01-01", "2025-12-31"),
    "full": ("2006-01-01", "2025-12-31"),
}
COSTS = (10, 25, 50)
NOMINAL_POLICIES = ("C02", "T01", "B01")


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_inputs(
    archive: Path, registration: dict[str, Any]
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Verify original provenance chain, then align the joint observed history."""
    if digest(archive) != registration["inputs"]["archive_sha256"]:
        raise ValueError("Archive hash differs from registration")
    frames, sources = [], []
    raw_spy = None
    with zipfile.ZipFile(archive) as zipped:
        provenance = json.loads(
            archive_tools.verified(
                zipped, archive_tools.PROVENANCE, archive_tools.PROVENANCE_SHA256
            )
        )
        pointer = "research/millennium_study/data/latest.json"
        frozen = provenance["data"][pointer]
        snapshot = archive_tools.member_path(frozen["snapshot"])
        if "Tester/" + snapshot != registration["inputs"]["snapshot_member_root"]:
            raise ValueError("Unregistered snapshot")
        actual = json.loads(
            archive_tools.verified(zipped, "Tester/" + pointer, frozen["pointer_sha256"])
        )
        if actual["snapshot"] != snapshot:
            raise ValueError("Snapshot pointer mismatch")
        if frozen["manifest_sha256"] != registration["inputs"]["snapshot_manifest_sha256"]:
            raise ValueError("Manifest differs from registration")
        manifest = json.loads(
            archive_tools.verified(
                zipped, "Tester/" + snapshot + "/manifest.json", frozen["manifest_sha256"]
            )
        )
        for symbol in SYMBOLS:
            meta = manifest["files"][symbol]
            member = "Tester/" + snapshot + "/" + archive_tools.member_path(meta["file"])
            frame = pd.read_csv(io.BytesIO(archive_tools.verified(zipped, member, meta["sha256"])))
            dates = pd.to_datetime(frame.Date, errors="raise")
            values = frame[["Open", "High", "Low", "Close", "Adj Close"]].to_numpy(float)
            if (
                not np.isfinite(values).all()
                or (values <= 0).any()
                or dates.isna().any()
                or dates.duplicated().any()
                or not dates.is_monotonic_increasing
                or (frame.High < frame[["Open", "Low", "Close"]].max(axis=1)).any()
                or (frame.Low > frame[["Open", "High", "Close"]].min(axis=1)).any()
            ):
                raise ValueError(f"Invalid source prices/dates: {symbol}")
            bars = pd.DataFrame(
                {
                    "session_date": dates,
                    "symbol": symbol,
                    "open": frame.Open * frame["Adj Close"] / frame.Close,
                    "close": frame["Adj Close"],
                }
            )
            frames.append(bars[dates <= "2025-12-31"])
            sources.append({"symbol": symbol, **meta})
            if symbol == "SPY":
                raw_spy = frame.set_index(pd.DatetimeIndex(dates)).drop(columns="Date")
    first = max(frame.session_date.min() for frame in frames)
    if first != pd.Timestamp("1999-03-10"):
        raise ValueError("Common warmup start differs from amendment")
    bars = pd.concat([frame[frame.session_date >= first] for frame in frames], ignore_index=True)
    prices = prepare_prices(bars)
    if raw_spy is None:
        raise ValueError("Missing SPY nominal source")
    raw_spy = raw_spy.reindex(prices.closed.index)
    return (
        bars,
        raw_spy,
        {
            "sources": sources,
            "frozen": frozen,
            "common_start": str(first.date()),
            "last_session": str(prices.closed.index[-1].date()),
            "sessions": len(prices.closed),
            "evaluation_sessions": int((prices.closed.index >= "2006-01-01").sum()),
            "calendar": (
                "Observed source calendar; independent exchange-calendar "
                "completeness not established"
            ),
        },
    )


def choose_training(results: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [
        r
        for r in results
        if r["panel"] == "fractional"
        and r["window"] == "training"
        and r["cost_bps"] == 25
        and r["policy"] in ACTIVE_POLICIES
    ]
    if {r["policy"] for r in eligible} != set(ACTIVE_POLICIES) or len(eligible) != 23:
        raise ValueError("Training selection incomplete or duplicated")
    ranked = sorted(
        eligible, key=lambda r: (-r["worst_year"], -r["cagr"], -r["max_drawdown"], r["policy"])
    )
    return {
        "selected_policy": ranked[0]["policy"],
        "saved_utc": datetime.now(UTC).isoformat(),
        "cost_bps": 25,
        "basis": "Training only; evaluation/full not yet computed",
        "ranked_training": ranked,
    }


def run_study(archive: Path, output: Path) -> None:  # noqa: PLR0912, PLR0915
    root = Path(__file__).resolve().parents[1]
    protocol = root / REGISTRATION
    if digest(protocol) != REGISTRATION_SHA256:
        raise ValueError("Registered protocol changed")
    if digest(root / AMENDMENT) != AMENDMENT_SHA256:
        raise ValueError("Registered warmup amendment changed")
    registration = json.loads(protocol.read_text(encoding="utf-8"))
    if tuple(p["id"] for p in registration["policies"]) != POLICIES:
        raise ValueError("Policy inventory mismatch")
    if (
        {k: tuple(v) for k, v in registration["windows"].items()} != WINDOWS
        or tuple(registration["common_rules"]["fees_bps_per_side"]) != COSTS
        or tuple(registration["nominal_spy_diagnostic"]["policies"]) != NOMINAL_POLICIES
    ):
        raise ValueError("Window, cost or nominal inventory mismatch")
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    bars, nominal, inputs = load_inputs(archive, registration)
    prices = prepare_prices(bars)
    if int((prices.closed.index >= "2006-01-01").sum()) != 5031:
        raise ValueError("Frozen source session count changed")
    signals = build_signals(prices)
    code_paths = [
        Path(__file__),
        root / "src/kq/equities/stock_family_study.py",
        root / "tests/test_stock_family_study.py",
        root / "scripts/run_directional_study.py",
        root / AMENDMENT,
        protocol,
    ]
    code_hashes = {str(p.relative_to(root)).replace("\\", "/"): digest(p) for p in code_paths}
    expected = [
        (panel, policy, cost, window)
        for window in WINDOWS
        for panel, policies in (("fractional", POLICIES), ("nominal_spy", NOMINAL_POLICIES))
        for cost in COSTS
        for policy in policies
    ]
    index = {"|".join(map(str, key)): {"status": "planned"} for key in expected}
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "trial-index.json", index)
    write_json(
        output / "started.json",
        {
            "registration_sha256": REGISTRATION_SHA256,
            "amendment_sha256": AMENDMENT_SHA256,
            "started_utc": datetime.now(UTC).isoformat(),
            "code_sha256": code_hashes,
            "inputs": inputs,
            "planned_paths": len(expected),
        },
    )
    results: list[dict[str, Any]] = []
    nominal_blocked = (
        not np.isfinite(nominal[["Stock Splits", "Dividends"]].to_numpy(float)).all()
        or (nominal["Stock Splits"] != 0).any()
        or (nominal.Dividends < 0).any()
        or ("Capital Gains" in nominal and (nominal["Capital Gains"] != 0).any())
    )
    for panel, policy, cost, window in expected:
        key = "|".join(map(str, (panel, policy, cost, window)))
        start, end = WINDOWS[window]
        window_mask = (prices.closed.index >= start) & (prices.closed.index <= end)
        if panel == "nominal_spy" and nominal_blocked:
            index[key] = {"status": "blocked", "reason": "Unsupported nominal corporate actions"}
            write_json(output / "trial-index.json", index)
            continue
        try:
            if window != "training" and not (output / "selection.json").exists():
                write_json(output / "selection.json", choose_training(results))
            if panel == "fractional":
                daily, ledger = simulate(prices, signals[policy], cost, start, end)
            else:
                daily, ledger = simulate_integer_spy(nominal, signals[policy], cost, start, end)
            result = summarize(daily)
            years = set(map(str, range(int(start[:4]), int(end[:4]) + 1)))
            if set(result["annual"]) != years or not daily.session_date.equals(
                prices.closed.loc[window_mask]
                .index.to_series()
                .reset_index(drop=True)
                .rename("session_date")
            ):
                raise ValueError("Incomplete registered calendar window")
            result.update(
                panel=panel,
                policy=policy,
                cost_bps=cost,
                window=window,
                sessions=len(daily),
                warmup_cash_sessions=int((~signals[policy].loc[window_mask].warmup_ready).sum()),
                mean_exposure_fraction=float(
                    1 - ((daily.cash + daily.get("locked_receivable", 0)) / daily.nav).mean()
                ),
                portfolio_trade_events=int((ledger.cost > 0).sum()),
                trade_count=int(
                    (ledger[[f"delta_{s}" for s in SYMBOLS]].abs() > 1e-12).sum().sum()
                    if panel == "fractional"
                    else (ledger.delta.abs() > 0).sum()
                ),
                turnover=float(ledger.cost.sum() / (cost / 10000)),
            )
            if panel == "nominal_spy":
                result.update(
                    terminal_spendable_cash=float(daily.iloc[-1].cash),
                    terminal_locked_receivable=float(daily.iloc[-1].locked_receivable),
                )
            name = f"{panel}_{policy}_c{cost}_{window}"
            for suffix, frame in (("daily", daily), ("ledger", ledger)):
                frame.to_csv(
                    output / f"{name}_{suffix}.csv.gz",
                    index=False,
                    compression={"method": "gzip", "mtime": 0},
                )
            results.append(result)
            index[key] = {"status": "complete", "output_stem": name}
            write_json(output / "results.json", results)
        except Exception as exc:
            index[key] = {"status": "failed", "error_type": type(exc).__name__, "error": str(exc)}
            write_json(output / "trial-index.json", index)
            raise
        write_json(output / "trial-index.json", index)
    if any(digest(root / path) != value for path, value in code_hashes.items()):
        raise ValueError("Implementation changed during study")
    if len(results) != (252 if nominal_blocked else 279) or any(
        item["status"] not in {"complete", "blocked"} for item in index.values()
    ):
        raise ValueError("Registered trial inventory incomplete")
    comparisons = []
    for row in results:
        peers = {
            r["policy"]: r
            for r in results
            if r["panel"] == row["panel"]
            and r["window"] == row["window"]
            and r["cost_bps"] == row["cost_bps"]
        }
        comparison = {
            "panel": row["panel"],
            "policy": row["policy"],
            "window": row["window"],
            "cost_bps": row["cost_bps"],
            "cagr_minus_same_spy": row["cagr"] - peers["C02"]["cagr"],
            "annual_minus_same_spy": {
                year: value - peers["C02"]["annual"][year] for year, value in row["annual"].items()
            },
        }
        components = {
            "E01": ("T01", "M01"),
            "E02": ("M01", "R02"),
            "E03": ("T01", "M01", "V04"),
        }.get(row["policy"])
        if components:
            comparison["cagr_minus_best_component"] = row["cagr"] - max(
                peers[p]["cagr"] for p in components
            )
        comparisons.append(comparison)
    write_json(output / "comparisons.json", comparisons)
    write_json(
        output / "manifest.json",
        {
            "completed_utc": datetime.now(UTC).isoformat(),
            "registration_sha256": REGISTRATION_SHA256,
            "amendment_sha256": AMENDMENT_SHA256,
            "code_sha256": code_hashes,
            "input_archive_sha256": digest(archive),
            "completed_paths": len(results),
            "blocked_paths": int(sum(item["status"] == "blocked" for item in index.values())),
            "external_api_spend_usd": 0,
            "output_sha256": {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()},
            "limitations": registration["prior_knowledge"],
            "quantity_conventions": {
                "fractional": "Adjusted wealth units, not broker shares",
                "nominal_spy": (
                    "Whole SPY shares; dividend receivables permanently unavailable for spending"
                ),
            },
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    run_study(arguments.archive, arguments.output)
