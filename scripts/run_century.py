"""Execute the frozen monthly industry-index study; all inputs already local."""

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from kq.equities.century import (
    CONTROLS,
    causal_regimes,
    load_monthly,
    max_mean_bootstrap,
    simulate_monthly,
    static_target,
)

REGISTRATION = Path("docs/research/century-registration-2026-10-20.json")
EXPECTED_REGISTRATION = "5d5baa3dc0b8b7a02e3c4ce1b39cad3651697adade3805bd195a30ee38caa641"
SOURCE_FILES = (
    "src/kq/equities/century.py",
    "scripts/run_century.py",
    "scripts/check_century.py",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def select_training(results: list[dict[str, Any]]) -> dict[str, Any]:
    primary = [
        r for r in results if r["window"] == "training" and r["cost_bps"] == 25 and r["lag"] == 2
    ]
    if len({r["policy"] for r in primary}) != len(primary):
        raise ValueError("Duplicate training policy")
    benchmarks = [r for r in primary if r["policy"] == "CMKT"]
    if len(benchmarks) != 1:
        raise ValueError("Exactly one training market control required")
    benchmark = benchmarks[0]
    candidates = [r for r in primary if r["policy"] not in CONTROLS]
    stable = sorted(
        [r for r in candidates if r["cagr"] > 0 and r["max_drawdown"] > benchmark["max_drawdown"]],
        key=lambda r: (-r["max_drawdown"], -r["cagr"], r["policy"]),
    )
    ranked = sorted(candidates, key=lambda r: (-r["cagr"], r["policy"]))
    return {
        "saved_utc": datetime.now(UTC).isoformat(),
        "basis": "Training1933-1975 only; evaluation/full/century not yet simulated",
        "stable": [r["policy"] for r in stable[:5]],
        "growth10": [r["policy"] for r in ranked if r["cagr"] >= 0.1][:5],
        "growth25": [r["policy"] for r in ranked if r["cagr"] >= 0.25][:5],
    }


def classify(results: list[dict[str, Any]], identities: list[str]) -> dict[str, Any]:
    keyed = {(r["policy"], r["window"], r["cost_bps"], r["lag"]): r for r in results}
    if len(keyed) != len(results) or len(set(identities)) != len(identities):
        raise ValueError("Duplicate account or candidate identity")
    rows = []
    for identity in identities:
        full = keyed[identity, "full", 25, 2]
        later = keyed[identity, "evaluation", 25, 2]
        cases = [
            (keyed[identity, w, c, lag], keyed["CMKT", w, c, lag])
            for w in ("full", "evaluation")
            for c in (10, 25, 50)
            for lag in (1, 2)
        ]
        rows.append(
            {
                "policy": identity,
                "family": full["family"],
                "full_cagr": full["cagr"],
                "evaluation_cagr": later["cagr"],
                "full_drawdown": full["max_drawdown"],
                "evaluation_drawdown": later["max_drawdown"],
                "positive_primary_both": full["cagr"] > 0 and later["cagr"] > 0,
                "positive_all12": all(r["cagr"] > 0 for r, _ in cases),
                "stable_all12": all(
                    r["cagr"] > 0 and r["max_drawdown"] > b["max_drawdown"] for r, b in cases
                ),
                "growth10_primary_both": full["cagr"] >= 0.1 and later["cagr"] >= 0.1,
                "growth25_primary_both": full["cagr"] >= 0.25 and later["cagr"] >= 0.25,
            }
        )
    flags = (
        "positive_primary_both",
        "positive_all12",
        "stable_all12",
        "growth10_primary_both",
        "growth25_primary_both",
    )
    counts = {name: sum(r[name] for r in rows) for name in flags}
    return {
        "scope": "200 related configurations; categories overlap; provisional index research only",
        "desired_counts": {"stable": 100, "growth10": 50, "growth25": 50},
        "counts": counts,
        "rows": rows,
        "unique_qualifying_configurations": sum(
            r["stable_all12"] or r["growth10_primary_both"] or r["growth25_primary_both"]
            for r in rows
        ),
    }


def diagnostics(frame: pd.DataFrame, regimes: dict[str, str]) -> dict[str, Any]:
    returns = (
        frame.ending_nav.to_numpy(float) / np.r_[1000.0, frame.ending_nav.to_numpy(float)[:-1]] - 1
    )
    labels = np.array([regimes[m] for m in frame.month])
    grouped = {}
    for label in sorted(set(labels)):
        selected = labels == label
        grouped[label] = {
            "months": int(selected.sum()),
            "mean_net_monthly_return": float(returns[selected].mean()),
            "positive_month_fraction": float(np.mean(returns[selected] > 0)),
            "mean_risky_fraction": float(frame.risky_fraction.to_numpy()[selected].mean()),
            "sum_cash_pnl_usd": float(frame.cash_pnl.to_numpy()[selected].sum()),
            "sum_risky_pnl_usd": float(frame.risky_pnl.to_numpy()[selected].sum()),
            "sum_fees_usd": float(frame.fee.to_numpy()[selected].sum()),
        }
    periods = {}
    for start in (1933, 1943, 1953, 1963, 1973, 1983, 1993, 2003, 2013, 2023):
        selected = (frame.month >= f"{start}-01") & (frame.month <= f"{start + 9}-12")
        block = returns[selected]
        actual_end = int(frame.loc[selected, "month"].iloc[-1][:4])
        periods[f"{start}-{actual_end}"] = float(np.prod(1 + block) ** (12 / len(block)) - 1)
    stresses = {}
    for start, end in (
        ("1937-03", "1938-03"),
        ("1973-01", "1974-12"),
        ("1987-10", "1987-10"),
        ("2000-03", "2002-10"),
        ("2007-10", "2009-03"),
        ("2020-02", "2020-04"),
        ("2022-01", "2022-12"),
    ):
        selected = (frame.month >= start) & (frame.month <= end)
        stresses[f"{start}:{end}"] = float(np.prod(1 + returns[selected]) - 1)
    return {"causal_states": grouped, "decade_cagr": periods, "stress_total_return": stresses}


def _run(  # noqa: PLR0912, PLR0915 -- ordered phases preserve training-before-evaluation audit
    source: Path, output: Path, review: Path
) -> None:
    if digest(REGISTRATION) != EXPECTED_REGISTRATION:
        raise ValueError("Registration changed")
    config = json.loads(REGISTRATION.read_bytes())
    receipt = json.loads(review.read_bytes())
    if (
        not isinstance(receipt, dict)
        or receipt.get("status") != "PASS"
        or receipt.get("registration_sha256") != EXPECTED_REGISTRATION
    ):
        raise ValueError("Pre-performance review required")
    hashes = {p: digest(Path(p)) for p in SOURCE_FILES}
    if receipt.get("source_sha256") != hashes:
        raise ValueError("Reviewed source changed")
    if digest(source / "acquisition.json") != config["inputs"]["raw_manifest_sha256"]:
        raise ValueError("Input acquisition manifest changed")
    acquired = json.loads((source / "acquisition.json").read_bytes())
    for row in acquired["files"]:
        if digest(source / row["file"]) != row["sha256"]:
            raise ValueError("Downloaded ZIP changed")
        if digest(source / row["member"]) != row["member_sha256"]:
            raise ValueError("Source CSV changed")
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    save(
        output / "started.json",
        {
            "started_utc": datetime.now(UTC).isoformat(),
            "registration_sha256": EXPECTED_REGISTRATION,
            "source_sha256": hashes,
            "input_manifest_sha256": digest(source / "acquisition.json"),
            "planned_accounts": config["planned_accounts"],
        },
    )
    data = load_monthly(source, config["inputs"]["industry_count"])
    candidates = config["policies"]
    policies = [*candidates, *({"id": p, "family": "control"} for p in CONTROLS)]
    targets = {}
    first = data.months.index("1933-01")
    for policy in candidates:
        if policy["family"].startswith("CPPI"):
            continue
        for lag in (1, 2):
            panel = np.zeros_like(data.returns)
            for pos in range(first, len(data.months)):
                panel[pos] = static_target(policy, data, pos - lag)
            targets[f"{policy['id']}_l{lag}"] = panel
    np.savez_compressed(output / "static-targets.npz", **targets)
    save(
        output / "signal-index.json",
        {
            "months": data.months,
            "symbols": data.symbols,
            "as_of": {
                f"lag{lag}": [
                    str(pd.Period(data.months[pos - lag], freq="M").end_time.date())
                    if pos >= first
                    else None
                    for pos in range(len(data.months))
                ]
                for lag in (1, 2)
            },
            "scope": (
                "Candidate targets before1933 are zero/cash; controls available from1926; "
                "information as_of is synthetic month-end, not original publication time."
            ),
        },
    )
    results: list[dict[str, Any]] = []
    regime_records: dict[str, Any] = {}
    primary_later: dict[str, np.ndarray[Any, Any]] = {}
    path_hashes: dict[str, str] = {}
    failures: list[dict[str, str]] = []
    for window in ("training", "evaluation", "full", "century"):
        start, end = config["windows"][window]
        for cost in (10, 25, 50):
            for lag in (1, 2):
                for policy in policies:
                    identity = policy["id"]
                    stem = f"{identity}_c{cost}_l{lag}_{window}"
                    try:
                        frame, summary = simulate_monthly(
                            data,
                            policy,
                            start,
                            end,
                            cost,
                            lag,
                            targets.get(f"{identity}_l{lag}"),
                        )
                        frame.to_csv(
                            output / f"{stem}.csv.gz",
                            index=False,
                            compression={"method": "gzip", "mtime": 0},
                        )
                        np.savez_compressed(
                            output / f"{stem}.positions.npz",
                            risky_after_cost=frame.attrs["risky_after_cost"],
                        )
                        summary.update(
                            policy=identity,
                            family=policy["family"],
                            cost_bps=cost,
                            lag=lag,
                            window=window,
                        )
                        results.append(summary)
                        if cost == 25 and lag == 2:
                            if window == "full":
                                regime_records[identity] = diagnostics(
                                    frame, causal_regimes(data, lag)
                                )
                                if identity not in CONTROLS:
                                    ends = frame.ending_nav.to_numpy(float)
                                    returns = ends / np.r_[1000.0, ends[:-1]] - 1
                                    path_hashes[identity] = hashlib.sha256(
                                        returns.astype("<f8").tobytes()
                                    ).hexdigest()
                            elif window == "evaluation":
                                ends = frame.ending_nav.to_numpy(float)
                                primary_later[identity] = ends / np.r_[1000.0, ends[:-1]] - 1
                    except Exception as exc:
                        failures.append({"account": stem, "error": f"{type(exc).__name__}: {exc}"})
                        save(output / "failures.json", failures)
        save(output / "results-partial.json", results)
        print(
            json.dumps(
                {
                    "window": window,
                    "completed": len(results),
                    "failures": len(failures),
                    "seconds": round(time.perf_counter() - started, 1),
                }
            ),
            flush=True,
        )
        if failures:
            raise RuntimeError("Incomplete study; retained all completed and failed accounts")
        if window == "training":
            save(output / "selection.json", select_training(results))
    identities = [p["id"] for p in candidates]
    save(output / "results.json", results)
    save(output / "regimes.json", regime_records)
    save(output / "classification.json", classify(results, identities))
    century_cases = [
        {**r, "window": "full" if r["window"] == "century" else r["window"]}
        for r in results
        if r["window"] in {"century", "evaluation"}
    ]
    save(
        output / "classification-century.json",
        {
            **classify(century_cases, identities),
            "full_means": (
                "1926-07 to2026-06;78 initial RF-only candidate months; controls invest immediately"
            ),
        },
    )
    groups = {
        value: [p for p, h in path_hashes.items() if h == value]
        for value in sorted(set(path_hashes.values()))
    }
    save(
        output / "path-uniqueness.json",
        {
            "scope": (
                "Exact float64 primary-full monthly net-return paths; not independent algorithms"
            ),
            "candidate_count": len(path_hashes),
            "unique_machine_paths": len(groups),
            "sha256_by_policy": path_hashes,
            "duplicate_groups": [group for group in groups.values() if len(group) > 1],
        },
    )
    excess = np.column_stack([primary_later[p] - primary_later["CMKT"] for p in identities])
    bootstrap = max_mean_bootstrap(excess)
    bootstrap["policies"] = identities
    save(output / "bootstrap.json", bootstrap)
    if {p: digest(Path(p)) for p in SOURCE_FILES} != hashes:
        raise RuntimeError("Source changed while running")
    payloads = [
        {"path": p.name, "bytes": p.stat().st_size, "sha256": digest(p)}
        for p in sorted(output.iterdir())
        if p.is_file()
    ]
    save(
        output / "manifest.json",
        {
            "completed_utc": datetime.now(UTC).isoformat(),
            "accounts": len(results),
            "files": payloads,
            "seconds": time.perf_counter() - started,
        },
    )
    print(
        json.dumps(
            {
                "completed": len(results),
                "failures": 0,
                "seconds": round(time.perf_counter() - started, 1),
            }
        ),
        flush=True,
    )


def run(source: Path, output: Path, review: Path) -> None:
    existed = output.exists()
    try:
        _run(source, output, review)
    except Exception as exc:
        if not existed and output.is_dir():
            save(
                output / "run-error.json",
                {
                    "recorded_utc": datetime.now(UTC).isoformat(),
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "scope": "Setup, execution or analysis failed; all partial outputs preserved.",
                },
            )
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    args = parser.parse_args()
    run(args.source, args.output, args.review)


if __name__ == "__main__":
    main()
