"""Independently reconcile frozen stock-study ledgers; never run strategy engines."""

import argparse
import hashlib
import io
import json
import math
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


class Reconciliation:
    """Checks recorded accounting against a separate cash-flow reconstruction."""

    def __init__(self) -> None:
        self.checks: Counter[str] = Counter()
        self.residuals: dict[str, float] = {}

    def close(self, actual: Any, expected: float, label: str, *, atol: float = 1e-7) -> None:
        actual = float(actual)
        require(math.isfinite(actual) and math.isfinite(expected), f"Nonfinite {label}")
        residual = abs(actual - expected)
        self.residuals[label] = max(self.residuals.get(label, 0), residual)
        self.checks[label] += 1
        require(
            math.isclose(actual, expected, abs_tol=atol, rel_tol=1e-10),
            f"{label}: recorded={actual!r}, independent={expected!r}",
        )


def read_inputs(archive: Path, registration: dict[str, Any]) -> tuple[Any, ...]:
    """Read source CSVs directly: no study-loader or strategy-module imports."""
    inputs = registration["inputs"]
    require(digest(archive) == inputs["archive_sha256"], "Wrong frozen input archive")
    symbols = inputs["symbols"]
    frames = {}
    source_hashes = {}
    with zipfile.ZipFile(archive) as zipped:
        prefix = inputs["snapshot_member_root"]
        raw_manifest = zipped.read(prefix + "/manifest.json")
        require(
            hashlib.sha256(raw_manifest).hexdigest() == inputs["snapshot_manifest_sha256"],
            "Wrong source manifest",
        )
        manifest = json.loads(raw_manifest)
        for symbol in symbols:
            meta = manifest["files"][symbol]
            member = prefix + "/" + meta["file"].replace("\\", "/")
            raw = zipped.read(member)
            require(hashlib.sha256(raw).hexdigest() == meta["sha256"], "Wrong member hash")
            frame = pd.read_csv(io.BytesIO(raw))
            dates = pd.to_datetime(frame.pop("Date"), errors="raise")
            require(not dates.isna().any() and not dates.duplicated().any(), "Invalid dates")
            require(dates.is_monotonic_increasing, "Unordered source dates")
            frame.index = pd.DatetimeIndex(dates)
            frames[symbol] = frame.loc[frame.index <= pd.Timestamp("2025-12-31")]
            source_hashes[symbol] = {"member": member, "sha256": meta["sha256"]}
    first = max(frame.index.min() for frame in frames.values())
    require(first == pd.Timestamp("1999-03-10"), "Unexpected joint warmup boundary")
    dates = frames[symbols[0]].loc[first:].index
    opened, closed = [], []
    for symbol in symbols:
        frame = frames[symbol].loc[first:]
        require(frame.index.equals(dates), "Source calendar mismatch")
        price = frame[["Open", "Close", "Adj Close"]].to_numpy(float)
        require(bool(np.isfinite(price).all() and (price > 0).all()), "Invalid source price")
        # Compute the adjustment factor separately from the runner expression.
        opened.append((frame["Adj Close"] / frame.Close * frame.Open).to_numpy(float))
        closed.append(frame["Adj Close"].to_numpy(float))
    raw = frames["SPY"].loc[first:]
    require(bool((raw["Stock Splits"] == 0).all()), "Unsupported SPY splits")
    require("Capital Gains" not in raw or bool((raw["Capital Gains"] == 0).all()), "Capital gains")
    require(bool(np.isfinite(raw.Dividends).all() and (raw.Dividends >= 0).all()), "Dividends")
    return dates, np.array(opened).T, np.array(closed).T, raw, source_hashes


def expected_decision(dates: pd.DatetimeIndex, i: int, cadence: str) -> pd.Timestamp:
    if cadence in {"weekly", "monthly", "none", "initial_only"}:
        current = dates[i]
        j = i - 1
        if cadence == "weekly":
            while dates[j].isocalendar()[:2] == current.isocalendar()[:2]:
                j -= 1
        else:
            while (dates[j].year, dates[j].month) == (current.year, current.month):
                j -= 1
        return dates[j]
    return dates[i - 1]


def check_causality(
    row: dict[str, Any], dates: pd.DatetimeIndex, i: int, cadence: str, terminal: bool
) -> None:
    decision = pd.Timestamp(row["decision_date"])
    expected = dates[i - 1] if terminal else expected_decision(dates, i, cadence)
    require(decision == expected, f"Wrong decision date: {decision} != {expected}")
    as_of = pd.Timestamp(row["as_of"])
    expected_as_of = (
        (decision + pd.Timedelta(hours=16)).tz_localize("America/New_York").tz_convert("UTC")
    )
    execution_open = (dates[i] + pd.Timedelta(hours=9, minutes=30)).tz_localize("America/New_York")
    require(as_of == expected_as_of and as_of < execution_open, "Noncausal synthetic as_of")


def nominal_target(shares: float, cash: float, price: float, weight: float, rate: float) -> int:
    """Closed-form one-asset solution, independent of engine bisection."""
    liquid = cash + shares * price
    buying = weight * liquid >= shares * price
    sign = 1 if buying else -1
    quantity = (
        weight * (liquid + sign * rate * shares * price) / (price * (1 + sign * weight * rate))
    )
    return math.floor(quantity + 1e-12)


def independently_measure(rows: list[dict[str, float]], dates: pd.DatetimeIndex) -> dict[str, Any]:
    endings: dict[str, float] = {}
    peak = close_peak = 1000.0
    drawdown = close_drawdown = 0.0
    for date, row in zip(dates, rows, strict=True):
        endings[str(date.year)] = row["nav"]
        for field in ("open_before", "open_after", "close_before", "nav"):
            peak = max(peak, row[field])
            drawdown = min(drawdown, row[field] / peak - 1)
        close_peak = max(close_peak, row["nav"])
        close_drawdown = min(close_drawdown, row["nav"] / close_peak - 1)
    annual, gaps = {}, {}
    beginning = 1000.0
    for year, ending in endings.items():
        annual[year] = ending / beginning - 1
        gaps[year] = ending - 1.10 * beginning
        beginning = ending
    values = list(annual.values())
    return {
        "ending_nav": rows[-1]["nav"],
        "total_cost": math.fsum(row["cost"] for row in rows),
        "cagr": (rows[-1]["nav"] / 1000) ** (1 / len(values)) - 1,
        "max_drawdown": drawdown,
        "close_max_drawdown": close_drawdown,
        "worst_year": min(values),
        "annual": annual,
        "annual_10pct_dollar_gap": gaps,
        "annual_additional_expense_capacity": {y: max(0.0, gap) for y, gap in gaps.items()},
        "years_ge_10pct": sum(value >= 0.1 for value in values),
        "years_ge_20pct": sum(value >= 0.2 for value in values),
        "years_10_to_20_inclusive": sum(0.1 <= value <= 0.2 for value in values),
        "years_above_20pct": sum(value > 0.2 for value in values),
        "years_below_10pct": sum(value < 0.1 for value in values),
        "losing_years": sum(value < 0 for value in values),
        "all_years_ge_10pct": all(value >= 0.1 for value in values),
        "mean_cash_fraction": math.fsum(row["cash"] / row["nav"] for row in rows) / len(rows),
        "mean_exposure_fraction": 1
        - math.fsum((row["cash"] + row.get("locked_receivable", 0)) / row["nav"] for row in rows)
        / len(rows),
    }


def check_trial(  # noqa: PLR0912, PLR0915
    run: Path,
    saved: dict[str, Any],
    stem: str,
    registration: dict[str, Any],
    inputs: tuple[Any, ...],
    check: Reconciliation,
) -> dict[str, Any]:
    dates, opened, closed, raw, _ = inputs
    symbols = registration["inputs"]["symbols"]
    nominal = saved["panel"] == "nominal_spy"
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
    groups: dict[pd.Timestamp, list[dict[str, Any]]] = {}
    require(pd.to_datetime(ledger.execution_date).is_monotonic_increasing, "Unordered ledger")
    for row in ledger.to_dict("records"):
        date = pd.Timestamp(row["execution_date"])
        require(date in chosen_dates, "Ledger outside account window")
        groups.setdefault(date, []).append(row)
    require((ledger.reason == "initial").sum() == 1, "Initial ledger event count")
    require((ledger.reason == "terminal_prescheduled_close").sum() == 1, "Terminal event count")
    units = np.zeros(1 if nominal else len(symbols))
    cash, locked, rate = 1000.0, 0.0, saved["cost_bps"] / 10000
    turnover, trade_events, legs = 0.0, 0, 0
    measured = []
    prior_calendar: set[pd.Timestamp] = set()
    for j, i in enumerate(chosen):
        date = dates[i]
        op = np.array([float(raw.Open.iloc[i])]) if nominal else opened[i]
        cl = np.array([float(raw.Close.iloc[i])]) if nominal else closed[i]
        credit = float(units[0] * raw.Dividends.iloc[i]) if nominal else 0.0
        locked += credit
        row_measured = {"open_before": cash + float(units @ op) + locked}
        day_cost = 0.0
        events = groups.get(date, [])
        openings = [r for r in events if r["reason"] != "terminal_prescheduled_close"]
        terminals = [r for r in events if r["reason"] == "terminal_prescheduled_close"]
        require(len(openings) <= 1 and len(terminals) <= 1, "Multiple events at same price instant")
        require(
            not terminals or (j == len(chosen) - 1 and events[-1] is terminals[0]), "Terminal order"
        )
        if openings:
            require(openings[0]["reason"] == ("initial" if j == 0 else "rebalance"), "Event reason")
            prior_calendar.add(date)
        require(j != 0 or len(openings) == 1, "Missing initial event")
        for at_close, subset, prices in ((False, openings, op), (True, terminals, cl)):
            if at_close:
                row_measured["open_after"] = cash + float(units @ op) + locked
                row_measured["close_before"] = cash + float(units @ cl) + locked
            for event in subset:
                check_causality(event, dates, int(i), policy["cadence"], at_close)
                if nominal:
                    new = np.array([float(event["shares"])])
                    delta = np.array([float(event["delta"])])
                    weights = np.array([float(event["target_weight"])])
                    check.close(event["price"], float(prices[0]), "execution_price", atol=1e-10)
                    require(float(new[0]).is_integer(), "Fractional nominal share")
                    expected_shares = (
                        0
                        if at_close
                        else nominal_target(
                            float(units[0]), cash, float(prices[0]), float(weights[0]), rate
                        )
                    )
                    require(new[0] == expected_shares, "Nominal sizing or locked-cash error")
                else:
                    new = np.array([float(event[f"units_{s}"]) for s in symbols])
                    delta = np.array([float(event[f"delta_{s}"]) for s in symbols])
                    weights = np.array([float(event[f"weight_{s}"]) for s in symbols])
                    for k, symbol in enumerate(symbols):
                        check.close(
                            event[f"price_{symbol}"],
                            float(prices[k]),
                            "execution_price",
                            atol=1e-10,
                        )
                require(
                    bool(np.isfinite(weights).all() and (weights >= 0).all()), "Invalid weights"
                )
                require(float(weights.sum()) <= 0.98 + 1e-12, "Target risk budget exceeded")
                require(bool((new >= 0).all()), "Short holding")
                if at_close:
                    require(bool((new == 0).all() and (weights == 0).all()), "Unclosed terminal")
                for actual, expected in zip(delta, new - units, strict=True):
                    check.close(actual, float(expected), "unit_delta", atol=1e-10)
                gross = math.fsum(abs(float(d * p)) for d, p in zip(delta, prices, strict=True))
                fee = gross * rate
                before = cash + float(units @ prices) + locked
                cash -= math.fsum(float(d * p) for d, p in zip(delta, prices, strict=True)) + fee
                after = cash + float(new @ prices) + locked
                check.close(event["cost"], fee, "ledger_cost")
                check.close(event["cash"], cash, "ledger_cash")
                require(cash >= -1e-7, "Borrowing")
                if nominal:
                    check.close(event["locked_receivable"], locked, "ledger_locked_receivable")
                else:
                    check.close(event["pre_nav"], before, "ledger_pre_nav")
                    check.close(event["post_nav"], after, "ledger_post_nav")
                    check.close(event["turnover"], gross, "ledger_turnover")
                    for quantity, price, weight in zip(new, prices, weights, strict=True):
                        check.close(quantity * price, weight * after, "post_cost_target_value")
                units = new
                turnover += gross
                day_cost += fee
                trade_events += fee > 0
                legs += int((np.abs(delta) > (0 if nominal else 1e-12)).sum())
        row_measured.update(nav=cash + float(units @ cl) + locked, cash=cash, cost=day_cost)
        if nominal:
            row_measured.update(
                shares=float(units[0]), locked_receivable=locked, dividend_receivable_added=credit
            )
        for field, value in row_measured.items():
            check.close(daily[field].iat[j], value, "daily_" + field)
        measured.append(row_measured)
    require(bool((units == 0).all()), "Residual terminal holdings")
    if policy["cadence"] in {"monthly", "weekly", "none", "initial_only"}:
        scheduled = {chosen_dates[0]}
        if policy["cadence"] in {"monthly", "weekly"}:
            for i in chosen[1:]:
                previous, current = dates[i - 1], dates[i]
                boundary = (
                    previous.isocalendar()[:2] != current.isocalendar()[:2]
                    if policy["cadence"] == "weekly"
                    else (previous.year, previous.month) != (current.year, current.month)
                )
                if boundary:
                    scheduled.add(current)
        require(prior_calendar == scheduled, "Missing or extra scheduled rebalance")
    metrics = independently_measure(measured, chosen_dates)
    metrics.update(turnover=turnover, portfolio_trade_events=trade_events, trade_count=legs)
    if nominal:
        metrics.update(terminal_spendable_cash=cash, terminal_locked_receivable=locked)
    for field, value in metrics.items():
        if isinstance(value, dict):
            require(set(saved[field]) == set(value), "Annual year inventory")
            for year, number in value.items():
                check.close(saved[field][year], number, "metric_" + field)
        elif isinstance(value, (int, bool)):
            require(saved[field] == value, "Metric count/flag mismatch: " + field)
        else:
            check.close(saved[field], value, "metric_" + field)
    return {
        "key": "|".join(str(saved[field]) for field in ("panel", "policy", "cost_bps", "window")),
        "daily_rows": len(daily),
        "ledger_rows": len(ledger),
        "traded_legs": legs,
        "annual_rows": len(metrics["annual"]),
        "status": "PASS",
        "ending_nav": metrics["ending_nav"],
        "worst_year": metrics["worst_year"],
        "max_drawdown": metrics["max_drawdown"],
        "cagr": metrics["cagr"],
    }


def review(archive: Path, run: Path) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    registration_path = root / "docs/research/strategy-family-registration-2026-10-19.json"
    registration = json.loads(registration_path.read_text(encoding="utf-8"))
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    require(digest(registration_path) == manifest["registration_sha256"], "Registration drift")
    for path, expected in manifest["code_sha256"].items():
        require(digest(root / path) == expected, "Implementation drift: " + path)
    expected_files = set(manifest["output_sha256"]) | {"manifest.json"}
    require(
        {p.name for p in run.iterdir() if p.is_file()} == expected_files, "Unexpected run files"
    )
    for name, expected in manifest["output_sha256"].items():
        require(digest(run / name) == expected, "Output integrity: " + name)
    require(manifest["blocked_paths"] == 0 and manifest["completed_paths"] == 279, "Incomplete run")
    results = json.loads((run / "results.json").read_text(encoding="utf-8"))
    index = json.loads((run / "trial-index.json").read_text(encoding="utf-8"))
    expected_keys = {
        f"{panel}|{policy}|{cost}|{window}"
        for panel, policies in (
            ("fractional", [p["id"] for p in registration["policies"]]),
            ("nominal_spy", registration["nominal_spy_diagnostic"]["policies"]),
        )
        for policy in policies
        for cost in registration["common_rules"]["fees_bps_per_side"]
        for window in registration["windows"]
    }
    keyed = {
        "|".join(str(r[k]) for k in ("panel", "policy", "cost_bps", "window")): r for r in results
    }
    require(len(results) == len(keyed) == len(expected_keys) == 279, "Duplicate or missing results")
    require(set(keyed) == set(index) == expected_keys, "Wrong trial membership")
    require(all(item["status"] == "complete" for item in index.values()), "Unfinished trial")
    inputs = read_inputs(archive, registration)
    check = Reconciliation()
    receipts = []
    for key in sorted(expected_keys):
        row = keyed[key]
        expected_stem = f"{row['panel']}_{row['policy']}_c{row['cost_bps']}_{row['window']}"
        require(index[key]["output_stem"] == expected_stem, "Wrong trial output stem")
        try:
            receipts.append(check_trial(run, row, expected_stem, registration, inputs, check))
        except Exception as exc:
            raise ValueError(f"{key}: {exc}") from exc
    # Reconcile the frozen training selection using independently recomputed metrics.
    eligible = registration["selection"]["eligible_ids"]
    ranked = sorted(
        (
            r
            for r in receipts
            if r["key"].split("|")[1] in eligible
            and r["key"].endswith("|25|training")
            and r["key"].startswith("fractional|")
        ),
        key=lambda r: (-r["worst_year"], -r["cagr"], -r["max_drawdown"], r["key"].split("|")[1]),
    )
    selection = json.loads((run / "selection.json").read_text(encoding="utf-8"))
    expected_order = [r["key"].split("|")[1] for r in ranked]
    require(len(expected_order) == 23, "Selection inventory")
    require(selection["selected_policy"] == expected_order[0], "Selected policy")
    require(
        [r["policy"] for r in selection["ranked_training"]] == expected_order, "Training ranking"
    )
    return {
        "schema_version": 1,
        "status": "PASS",
        "reviewed_utc": datetime.now(UTC).isoformat(),
        "run": str(run.relative_to(root)).replace("\\", "/")
        if run.is_relative_to(root)
        else run.name,
        "checker": "scripts/check_stock_family_accounting.py",
        "checker_sha256": digest(Path(__file__)),
        "registration_sha256": digest(registration_path),
        "manifest_sha256": digest(run / "manifest.json"),
        "results_sha256": digest(run / "results.json"),
        "input_archive_sha256": digest(archive),
        "source_members": inputs[4],
        "engine_sha256": manifest["code_sha256"]["src/kq/equities/stock_family_study.py"],
        "validated_paths": len(receipts),
        "daily_rows": sum(r["daily_rows"] for r in receipts),
        "ledger_rows": sum(r["ledger_rows"] for r in receipts),
        "traded_legs": sum(r["traded_legs"] for r in receipts),
        "annual_rows": sum(r["annual_rows"] for r in receipts),
        "numeric_checks": dict(sorted(check.checks.items())),
        "maximum_absolute_residual_by_field": dict(sorted(check.residuals.items())),
        "tolerances": {
            "absolute_default": 1e-7,
            "absolute_prices_and_unit_deltas": 1e-10,
            "relative": 1e-10,
        },
        "verified_scope": [
            "All 279 registered trial keys and file hashes; "
            "frozen source archive/manifest/11 CSV member hashes",
            "Direct source price factors; every ledger price, unit delta, "
            "cost and self-financed cash flow",
            "Every synthetic decision date/as_of; observed monthly/weekly event schedules",
            "Fractional recorded-target post-cost holdings; "
            "closed-form whole-share sizing excluding locked dividends",
            "Every daily opening/closing NAV, cash, costs, "
            "previous-holder dividend entitlement and locked receivable",
            "All annual returns, worst years, event/close drawdowns, CAGR, "
            "fee/turnover/trade/cash/exposure metrics",
            "Per-year dollar expense capacities/gaps and independently ranked training selection",
        ],
        "limits": [
            "Recorded target weights are inputs to accounting validation; "
            "no independent policy-formula or breakout-state reconstruction",
            "Warmup_cash_sessions is not independently reconstructed; "
            "strategy mapping/causality fixtures reviewed separately",
            "comparisons.json arithmetic is not independently recalculated here; "
            "its stored bytes are hash-verified",
            "Observed source dates and adjusted prices are not "
            "independent exchange/provider/broker verification",
            "Synthetic 16:00 decision timestamps do not establish "
            "historical publication latency or early-close availability",
            "Nominal dividends remain permanently unspendable; "
            "no actual payment-date, settlement, tax or broker-fill proof",
            "This is a ledger reconciliation of historical simulations, "
            "not additional strategy backtests or a future-return claim",
        ],
        "trials": receipts,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Keep previous review receipts; use a new output path")
    result = review(args.archive.resolve(), args.run.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("status", "validated_paths", "daily_rows", "ledger_rows", "annual_rows")
            }
        )
    )
