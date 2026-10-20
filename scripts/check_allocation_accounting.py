"""Independent allocation-study reconciliation; never import the study engines."""

import argparse
import hashlib
import io
import itertools
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scripts.check_stock_family_accounting import (
    Reconciliation,
    check_causality,
    digest,
    independently_measure,
    require,
)

REGISTRATION = "docs/research/allocation-study-registration-2026-10-20.json"
REGISTRATION_SHA256 = "55c0b3e4e593cb72a3454464e1b21f1a701809adc9e9e6ebf76a8d9a8751086e"


def read_inputs(source: Path, registration: dict[str, Any]) -> tuple[Any, ...]:
    """Rebuild adjusted wealth-unit prices directly from frozen raw CSV bytes."""
    spec = registration["inputs"]
    require(digest(source / "manifest.json") == spec["manifest_sha256"], "Source manifest drift")
    frames, hashes = {}, {}
    for symbol in spec["symbols"]:
        name = symbol + ".csv"
        raw = (source / name).read_bytes()
        value = hashlib.sha256(raw).hexdigest()
        require(value == spec["file_sha256"][name], f"Source CSV drift: {name}")
        frame = pd.read_csv(io.BytesIO(raw))
        dates = pd.to_datetime(frame.pop("Date"), errors="raise")
        require(not dates.isna().any() and not dates.duplicated().any(), "Invalid source dates")
        require(dates.is_monotonic_increasing, "Unordered source dates")
        frame.index = pd.DatetimeIndex(dates)
        values = frame[["Open", "High", "Low", "Close", "Adj Close"]].to_numpy(float)
        require(bool(np.isfinite(values).all() and (values > 0).all()), "Invalid source prices")
        require(bool((frame.High >= frame[["Open", "Low", "Close"]].max(axis=1)).all()), "High")
        require(bool((frame.Low <= frame[["Open", "High", "Close"]].min(axis=1)).all()), "Low")
        frames[symbol] = frame.loc[: spec["truncate_at"]]
        hashes[name] = value
    first = max(frame.index.min() for frame in frames.values())
    require(first == pd.Timestamp(spec["common_start"]), "Unexpected common start")
    dates = frames[spec["symbols"][0]].loc[first:].index
    opened, closed = [], []
    for symbol in spec["symbols"]:
        frame = frames[symbol].loc[first:]
        require(frame.index.equals(dates), "Joint source calendar mismatch")
        opened.append((frame["Adj Close"] / frame.Close * frame.Open).to_numpy(float))
        closed.append(frame["Adj Close"].to_numpy(float))
    return dates, np.array(opened).T, np.array(closed).T, hashes


def monthly_references(dates: pd.DatetimeIndex, closed: np.ndarray) -> dict[Any, Any]:
    """Independent gross virtual-expert/EG signals; no account performance."""
    ends = [
        i
        for i in range(len(dates) - 1)
        if (dates[i].year, dates[i].month) != (dates[i + 1].year, dates[i + 1].month)
    ]
    grid = (
        np.array([p for p in itertools.product(range(5), repeat=6) if sum(p) == 4], dtype=float) / 4
    )
    require(grid.shape == (126, 6), "Virtual-expert inventory")
    wealth = np.full(126, 1 / 126, dtype=float)
    gradient = np.full(6, 1 / 6, dtype=float)
    references = {}
    previous = None
    for i in ends:
        if previous is not None:
            relative = closed[i] / closed[previous]
            # Normalize each step: algebraically equivalent to log-space wealth,
            # without sharing that implementation or compounding unbounded values.
            wealth *= grid @ relative
            wealth /= math.fsum(wealth)
            exponent = 0.05 * relative / float(gradient @ relative)
            gradient *= np.exp(exponent - exponent.max())
            gradient /= math.fsum(gradient)
        references[dates[i]] = {"O01": wealth @ grid * 0.98, "O02": gradient.copy() * 0.98}
        previous = i
    return references


def insurance_reference(
    policy: str, previous_nav: float, previous_peak: float
) -> tuple[float, float, np.ndarray]:
    """Return scenario-funded floor, risky fraction and six target weights."""
    require(policy in {"I01", "I02", "I03", "I04"}, "Unknown insurance policy")
    require(previous_nav > 0 and previous_peak >= 1000, "Invalid insurance history")
    floor = 800.0 if policy in {"I01", "I02"} else 0.8 * previous_peak
    fraction = min(1.0, max(0.0, 3 * (previous_nav - floor) / previous_nav))
    weights = np.zeros(6)
    if policy in {"I01", "I03"}:
        weights[0] = fraction
    else:
        weights[:5] = fraction / 5
    weights[5] = 1 - fraction
    return floor, fraction, weights * 0.98


def check_covariance_target(
    policy: str, weights: np.ndarray, history: np.ndarray, check: Reconciliation
) -> None:
    """Check convex optimum KKT/positive equal risk budgets; no optimizer reuse."""
    require(len(history) >= 127, "Insufficient covariance history")
    daily = history[-126:] / history[-127:-1] - 1
    centered = daily - daily.mean(axis=0)
    sample = centered.T @ centered / 125
    matrix = 0.5 * sample + 0.5 * np.diag(np.diag(sample))
    require(
        bool(np.isfinite(matrix).all() and (np.linalg.eigvalsh(matrix) > 0).all()),
        "Degenerate covariance",
    )
    normalized = weights[:5] / 0.98
    check.close(weights[5], 0, "covariance_bil_zero")
    check.close(float(normalized.sum()), 1, "covariance_budget")
    require(bool((normalized >= 0).all()), "Negative covariance weight")
    # Normalization removes scale-dependent numerical tolerances.
    scaled = matrix / float(np.trace(matrix))
    gradient = scaled @ normalized
    if policy == "A01":
        require(bool((normalized <= 0.5 + 1e-7).all()), "Minimum-variance cap")
        free = (normalized > 1e-7) & (normalized < 0.5 - 1e-7)
        if free.any():
            multiplier = float(np.mean(gradient[free]))
        else:
            low = float(gradient[normalized >= 0.5 - 1e-7].max())
            high = float(gradient[normalized <= 1e-7].min())
            require(low <= high + 2e-6, "Minimum-variance vertex KKT")
            multiplier = (low + high) / 2
        for weight, component in zip(normalized, gradient, strict=True):
            if weight < 1e-7:
                require(component >= multiplier - 2e-6, "Minimum-variance lower-bound KKT")
            elif weight > 0.5 - 1e-7:
                require(component <= multiplier + 2e-6, "Minimum-variance upper-bound KKT")
            else:
                check.close(component, multiplier, "minimum_variance_stationarity", atol=2e-6)
    elif policy == "A02":
        require(bool((normalized > 0).all()), "Nonpositive ERC weight")
        contribution = normalized * gradient
        target = float(contribution.sum() / 5)
        require(target > 0, "Nonpositive ERC risk")
        for value in contribution:
            check.close(value / target, 1, "equal_risk_contribution", atol=2e-5)
    else:
        raise ValueError("Unknown covariance policy")


def check_target(
    event: dict[str, Any],
    policy: str,
    dates: pd.DatetimeIndex,
    closed: np.ndarray,
    weights: np.ndarray,
    previous_nav: float,
    previous_peak: float,
    online: dict[Any, Any],
    check: Reconciliation,
) -> tuple[float | None, float | None]:
    target = np.zeros(6)
    if policy.startswith("I"):
        floor, fraction, target = insurance_reference(policy, previous_nav, previous_peak)
        for field, expected in (
            ("reference_nav", previous_nav),
            ("reference_peak", previous_peak),
            ("floor", floor),
            ("risky_fraction", fraction),
        ):
            check.close(event[field], expected, "insurance_" + field)
    else:
        floor = fraction = None
        if policy == "C01":
            pass
        elif policy == "C02":
            target[5] = 0.98
        elif policy == "C03":
            target[0] = 0.98
        elif policy == "C04":
            target[:5] = 0.98 / 5
        elif policy.startswith("O"):
            target = online[pd.Timestamp(event["decision_date"])][policy]
        elif policy.startswith("A"):
            index = dates.get_loc(pd.Timestamp(event["decision_date"]))
            check_covariance_target(policy, weights, closed[: index + 1, :5], check)
            return None, None
        else:
            raise ValueError("Unregistered policy")
    for actual, expected in zip(weights, target, strict=True):
        check.close(actual, float(expected), "registered_target_weight", atol=1e-9)
    return floor, fraction


def _compare_metrics(saved: dict[str, Any], metrics: dict[str, Any], check: Reconciliation) -> None:
    for field, value in metrics.items():
        if isinstance(value, dict):
            require(set(saved[field]) == set(value), "Annual year inventory")
            for year, number in value.items():
                check.close(saved[field][year], number, "metric_" + field)
        elif isinstance(value, (int, bool)):
            require(saved[field] == value, "Metric count/flag mismatch: " + field)
        else:
            check.close(saved[field], value, "metric_" + field)


def check_trial(  # noqa: PLR0912, PLR0915
    run: Path,
    saved: dict[str, Any],
    stem: str,
    registration: dict[str, Any],
    inputs: tuple[Any, ...],
    online: dict[Any, Any],
    check: Reconciliation,
) -> dict[str, Any]:
    dates, opened, closed, _ = inputs
    symbols = registration["inputs"]["symbols"]
    policy = next(p for p in registration["policies"] if p["id"] == saved["policy"])
    start, end = registration["windows"][saved["window"]]
    chosen = np.flatnonzero((dates >= start) & (dates <= end))
    chosen_dates = dates[chosen]
    daily = pd.read_csv(run / (stem + "_daily.csv.gz"))
    ledger = pd.read_csv(run / (stem + "_ledger.csv.gz"))
    require(
        pd.DatetimeIndex(pd.to_datetime(daily.session_date)).equals(chosen_dates), "Daily dates"
    )
    require(len(daily) == saved["sessions"], "Session metric")
    require(pd.to_datetime(ledger.execution_date).is_monotonic_increasing, "Unordered ledger")
    groups: dict[pd.Timestamp, list[dict[str, Any]]] = {}
    for row in ledger.to_dict("records"):
        date = pd.Timestamp(row["execution_date"])
        require(date in chosen_dates, "Ledger outside account window")
        groups.setdefault(date, []).append(row)
    require((ledger.reason == "initial").sum() == 1, "Initial event count")
    require((ledger.reason == "terminal_prescheduled_close").sum() == 1, "Terminal event count")
    units = np.zeros(len(symbols))
    cash, rate = 1000.0, saved["cost_bps"] / 10000
    previous_nav = previous_peak = 1000.0
    turnover, trade_events, legs, sub_dollar_legs = 0.0, 0, 0, 0
    floor_breaches = 0
    smallest_leg, minimum_floor_gap = math.inf, math.inf
    measured, event_dates = [], set()
    for j, i in enumerate(chosen):
        date, op, cl = dates[i], opened[i], closed[i]
        row_measured = {"open_before": cash + float(units @ op)}
        day_cost = 0.0
        events = groups.get(date, [])
        openings = [r for r in events if r["reason"] != "terminal_prescheduled_close"]
        terminals = [r for r in events if r["reason"] == "terminal_prescheduled_close"]
        require(len(openings) <= 1 and len(terminals) <= 1, "Duplicate price instant")
        require(
            not terminals or (j == len(chosen) - 1 and events[-1] is terminals[0]), "Terminal order"
        )
        if openings:
            require(openings[0]["reason"] == ("initial" if j == 0 else "rebalance"), "Event reason")
            event_dates.add(date)
        require(j != 0 or len(openings) == 1, "Missing initial event")
        floor = None
        for at_close, subset, prices in ((False, openings, op), (True, terminals, cl)):
            if at_close:
                row_measured["open_after"] = cash + float(units @ op)
                row_measured["close_before"] = cash + float(units @ cl)
            for event in subset:
                check_causality(event, dates, int(i), policy["schedule"], at_close)
                new = np.array([float(event[f"units_{s}"]) for s in symbols])
                delta = np.array([float(event[f"delta_{s}"]) for s in symbols])
                weights = np.array([float(event[f"weight_{s}"]) for s in symbols])
                require(
                    bool(np.isfinite(weights).all() and (weights >= 0).all()), "Invalid weights"
                )
                require(float(weights.sum()) <= 0.98 + 1e-12, "Target budget exceeded")
                require(bool(np.isfinite(new).all() and (new >= 0).all()), "Short/invalid holding")
                for k, symbol in enumerate(symbols):
                    check.close(
                        event[f"price_{symbol}"], float(prices[k]), "execution_price", atol=1e-10
                    )
                    check.close(delta[k], float(new[k] - units[k]), "unit_delta", atol=1e-10)
                if at_close:
                    require(bool((new == 0).all() and (weights == 0).all()), "Unclosed terminal")
                    if policy["id"].startswith("I"):
                        expected_floor, expected_fraction, _ = insurance_reference(
                            policy["id"], previous_nav, previous_peak
                        )
                        for field, expected in (
                            ("reference_nav", previous_nav),
                            ("reference_peak", previous_peak),
                            ("floor", expected_floor),
                            ("risky_fraction", expected_fraction),
                        ):
                            check.close(event[field], expected, "terminal_insurance_" + field)
                else:
                    floor, _ = check_target(
                        event,
                        policy["id"],
                        dates,
                        closed,
                        weights,
                        previous_nav,
                        previous_peak,
                        online,
                        check,
                    )
                notionals = np.abs(delta * prices)
                gross = math.fsum(float(v) for v in notionals)
                fee = gross * rate
                before = cash + float(units @ prices)
                cash -= math.fsum(float(d * p) for d, p in zip(delta, prices, strict=True)) + fee
                after = cash + float(new @ prices)
                for field, expected in (
                    ("cost", fee),
                    ("cash", cash),
                    ("pre_nav", before),
                    ("post_nav", after),
                    ("turnover", gross),
                ):
                    check.close(event[field], expected, "ledger_" + field)
                require(cash >= -1e-7, "Borrowing")
                for quantity, price, weight in zip(new, prices, weights, strict=True):
                    check.close(quantity * price, weight * after, "post_cost_target_value")
                units = new
                turnover += gross
                day_cost += fee
                trade_events += fee > 0
                traded = notionals > 1e-12
                legs += int(traded.sum())
                sub_dollar_legs += int((traded & (notionals < 1)).sum())
                if traded.any():
                    smallest_leg = min(smallest_leg, float(notionals[traded].min()))
        row_measured.update(nav=cash + float(units @ cl), cash=cash, cost=day_cost)
        for field, value in row_measured.items():
            check.close(daily[field].iat[j], value, "daily_" + field)
        if floor is not None:
            # Compare current day's observed account marks to the floor that was
            # knowable before its open; no replacement by a future ratchet.
            floor_breaches += any(
                row_measured[f] < floor
                for f in ("open_before", "open_after", "close_before", "nav")
            )
            minimum_floor_gap = min(
                minimum_floor_gap,
                min(row_measured[f] for f in ("open_before", "open_after", "close_before", "nav"))
                - floor,
            )
            for field, expected in (
                ("reference_nav", previous_nav),
                ("reference_peak", previous_peak),
                ("floor", floor),
                (
                    "risky_fraction",
                    insurance_reference(policy["id"], previous_nav, previous_peak)[1],
                ),
            ):
                check.close(daily[field].iat[j], expected, "daily_insurance_" + field)
        for field in ("open_before", "open_after", "close_before", "nav"):
            require(
                bool(daily["floor_breached_" + field].iat[j])
                == (floor is not None and row_measured[field] < floor),
                "Daily floor-breach flag",
            )
        measured.append(row_measured)
        previous_nav = row_measured["nav"]
        previous_peak = max(previous_peak, previous_nav)
    require(bool((units == 0).all()), "Residual terminal holdings")
    scheduled = {chosen_dates[0]}
    if policy["schedule"] == "daily":
        scheduled = set(chosen_dates)
    elif policy["schedule"] == "monthly":
        scheduled.update(
            dates[i]
            for i in chosen[1:]
            if (dates[i - 1].year, dates[i - 1].month) != (dates[i].year, dates[i].month)
        )
    require(event_dates == scheduled, "Missing or extra scheduled rebalance")
    metrics = independently_measure(measured, chosen_dates)
    metrics.update(turnover=turnover, portfolio_trade_events=trade_events, trade_count=legs)
    # Optional until runner's additional metric names are fixed; the independent
    # receipt still retains reconstructed values for every trial.
    if "sub_dollar_traded_legs" in saved:
        metrics["sub_dollar_traded_legs"] = sub_dollar_legs
    if "floor_breach_sessions" in saved:
        metrics["floor_breach_sessions"] = floor_breaches
        metrics["minimum_nav_minus_floor"] = minimum_floor_gap
    if "smallest_positive_traded_leg_usd" in saved:
        if smallest_leg == math.inf:
            require(saved["smallest_positive_traded_leg_usd"] is None, "Invented traded leg")
        else:
            metrics["smallest_positive_traded_leg_usd"] = smallest_leg
    _compare_metrics(saved, metrics, check)
    return {
        "key": "|".join(str(saved[field]) for field in ("policy", "cost_bps", "window")),
        "daily_rows": len(daily),
        "ledger_rows": len(ledger),
        "traded_legs": legs,
        "sub_dollar_traded_legs": sub_dollar_legs,
        "floor_breach_sessions": floor_breaches,
        "annual_rows": len(metrics["annual"]),
        "status": "PASS",
        **{k: metrics[k] for k in ("ending_nav", "worst_year", "max_drawdown", "cagr")},
    }


def review(source: Path, run: Path) -> dict[str, Any]:  # noqa: PLR0915
    root = Path(__file__).resolve().parents[1]
    path = root / REGISTRATION
    require(digest(path) == REGISTRATION_SHA256, "Frozen registration changed")
    registration = json.loads(path.read_text(encoding="utf-8"))
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    require(manifest["registration_sha256"] == REGISTRATION_SHA256, "Manifest registration drift")
    require(
        set(manifest["code_sha256"])
        == {
            "src/kq/equities/allocation_signals.py",
            "src/kq/equities/allocation_study.py",
            "src/kq/equities/stock_family_study.py",
            "scripts/run_allocation_study.py",
        },
        "Source hash inventory",
    )
    for name, expected in manifest["code_sha256"].items():
        require(digest(root / name) == expected, "Implementation drift: " + name)
    expected_files = set(manifest["output_sha256"]) | {"manifest.json"}
    require(
        {p.name for p in run.iterdir() if p.is_file()} == expected_files, "Unexpected run files"
    )
    for name, expected in manifest["output_sha256"].items():
        require(digest(run / name) == expected, "Output integrity: " + name)
    results = json.loads((run / "results.json").read_text(encoding="utf-8"))
    index = json.loads((run / "trial-index.json").read_text(encoding="utf-8"))
    expected_keys = {
        f"{p['id']}|{cost}|{window}"
        for p in registration["policies"]
        for cost in registration["costs_bps"]
        for window in registration["windows"]
    }
    require(len(expected_keys) == registration["planned_accounts"] == 108, "Registered inventory")
    keyed = {"|".join(str(r[k]) for k in ("policy", "cost_bps", "window")): r for r in results}
    require(len(keyed) == len(results), "Duplicate result")
    require(set(index) == expected_keys, "Missing trial inventory")
    completed = {key for key, row in index.items() if row["status"] == "complete"}
    failures = {key: row for key, row in index.items() if row["status"] != "complete"}
    require(set(keyed) == completed, "Missing completed results or disguised failed result")
    require(manifest["completed_paths"] == len(completed), "Manifest completion count")
    require(manifest["blocked_paths"] == len(failures), "Manifest failure count")
    for key, row in failures.items():
        require(row["status"] in {"blocked", "failed"}, "Unfinished planned account: " + key)
        require(bool(row.get("error") or row.get("reason")), "Failure missing explanation")
    inputs = read_inputs(source, registration)
    online = monthly_references(inputs[0], inputs[2])
    check, receipts = Reconciliation(), []
    for key in sorted(completed):
        row = keyed[key]
        require(
            {"sub_dollar_traded_legs", "smallest_positive_traded_leg_usd"} <= set(row),
            "Missing practical feasibility metrics",
        )
        if row["policy"].startswith("I"):
            require(
                {"floor_breach_sessions", "minimum_nav_minus_floor"} <= set(row),
                "Missing floor metrics",
            )
        stem = index[key]["output_stem"]
        require(Path(stem).name == stem, "Unsafe output stem")
        try:
            receipts.append(check_trial(run, row, stem, registration, inputs, online, check))
        except Exception as exc:
            raise ValueError(f"{key}: {exc}") from exc
    eligible = registration["selection"]["eligible"]
    ranked = sorted(
        (
            r
            for r in receipts
            if r["key"].split("|")[0] in eligible and r["key"].endswith("|25|training")
        ),
        key=lambda r: (-r["worst_year"], -r["cagr"], -r["max_drawdown"], r["key"].split("|")[0]),
    )
    require(len(ranked) == 8, "Training selection incomplete; cannot validate winner")
    selection = json.loads((run / "selection.json").read_text(encoding="utf-8"))
    order = [r["key"].split("|")[0] for r in ranked]
    require(selection["selected_policy"] == order[0], "Selected policy")
    require([r["policy"] for r in selection["ranked_training"]] == order, "Training ranking")
    for row in selection["ranked_training"]:
        require(row == keyed[f"{row['policy']}|25|training"], "Selection metric record changed")
    comparisons = json.loads((run / "comparisons.json").read_text(encoding="utf-8"))
    comparison_keys = set()
    for row in comparisons:
        key = "|".join(str(row[k]) for k in ("policy", "cost_bps", "window"))
        require(key not in comparison_keys and key in keyed, "Comparison inventory")
        comparison_keys.add(key)
        result = keyed[key]
        benchmark = keyed[f"C03|{row['cost_bps']}|{row['window']}"]
        check.close(row["cagr_minus_same_spy"], result["cagr"] - benchmark["cagr"], "same_spy_cagr")
        require(set(row["annual_minus_same_spy"]) == set(result["annual"]), "Comparison years")
        for year, value in row["annual_minus_same_spy"].items():
            check.close(
                value, result["annual"][year] - benchmark["annual"][year], "same_spy_annual"
            )
    require(comparison_keys == completed, "Missing comparison")
    return {
        "schema_version": 1,
        "status": "PASS" if not failures else "PASS_WITH_RETAINED_FAILURES",
        "reviewed_utc": datetime.now(UTC).isoformat(),
        "checker": "scripts/check_allocation_accounting.py",
        "checker_sha256": digest(Path(__file__)),
        "registration_sha256": REGISTRATION_SHA256,
        "manifest_sha256": digest(run / "manifest.json"),
        "results_sha256": digest(run / "results.json"),
        "source_sha256": inputs[3],
        "validated_paths": len(receipts),
        "retained_failed_paths": failures,
        "daily_rows": sum(r["daily_rows"] for r in receipts),
        "ledger_rows": sum(r["ledger_rows"] for r in receipts),
        "annual_rows": sum(r["annual_rows"] for r in receipts),
        "numeric_checks": dict(sorted(check.checks.items())),
        "maximum_absolute_residual_by_field": dict(sorted(check.residuals.items())),
        "verified_scope": [
            "All 108 trial memberships, retained failures, input/output/code hashes",
            "Every execution price, unit delta, cash flow, funded fee and post-cost target holding",
            "Every daily NAV, annual return, drawdown, CAGR, training ranking and SPY comparison",
            "Previous-session/month-end decision dates, synthetic as_of and exact event schedules",
            "Control formulas and independent monthly virtual-expert/EG updates",
            "Covariance shrinkage and minimum-variance KKT/equal-risk-contribution conditions",
            "Each insurance scenario's actual previous NAV, peak, floor and target fraction",
        ],
        "limits": [
            "Adjusted wealth units are not literal broker shares or verified executable fills",
            "Source date coverage and prices are not independently exchange-verified",
            "Synthetic close timestamps do not prove historical publication latency",
            "Historical reconciliation supplies no future-return guarantee or strategy promotion",
            "Selection timestamp is preserved evidence, not an independent execution observer",
        ],
        "trials": receipts,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Keep old review receipts; use a new output path")
    result = review(args.source.resolve(), args.run.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                k: result[k]
                for k in ("status", "validated_paths", "daily_rows", "ledger_rows", "annual_rows")
            }
        )
    )
