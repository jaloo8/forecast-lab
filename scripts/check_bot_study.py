"""Independent bot-study arithmetic and signal audit; never imports its simulator."""

import argparse
import hashlib
import json
import math
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

RULES = ("C00", "C01", "C02", *(f"B{i:02}" for i in range(1, 13)))
REGISTRATION = Path("docs/research/bot-study-registration-2026-10-21.json")
REGISTRATION_HASH = "d3b11968c2b8c8bcbe7050b61d317b0a9c980437a47a1d1c4403ee84cd2ebaf9"
LEDGER_COLUMNS = (
    "open_before",
    "open_after",
    "cash_open",
    "units_open",
    "nav_close",
    "cash_close",
    "units_close",
    "notional_open",
    "fee_open",
    "notional_close",
    "fee_close",
    "close_before_fee",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@dataclass
class Audit:
    checks: Counter[str] = field(default_factory=Counter)
    residuals: dict[str, float] = field(default_factory=dict)

    def equal(self, actual: Any, expected: Any, label: str) -> None:
        left, right = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
        require(left.shape == right.shape, f"{label}: shape")
        require(bool(np.isfinite(left).all() and np.isfinite(right).all()), f"{label}: finite")
        error = float(np.max(abs(left - right), initial=0))
        self.checks[label] += left.size
        self.residuals[label] = max(error, self.residuals.get(label, 0))
        require(bool(np.allclose(left, right, atol=1e-8, rtol=1e-10)), f"{label}: {error}")


def rolling(values: Any, count: int, function: Callable[[Any], float]) -> Any:
    """Use bounded explicit slices rather than the engine's rolling implementation."""
    result = np.full(len(values), np.nan)
    for end in range(count - 1, len(values)):
        window = values[end - count + 1 : end + 1]
        if np.isfinite(window).all():
            result[end] = function(window)
    return result


def average(values: Any) -> float:
    return math.fsum(float(value) for value in values) / len(values)


def deviation(values: Any, ddof: int = 0) -> float:
    center = average(values)
    return math.sqrt(
        math.fsum((float(value) - center) ** 2 for value in values) / (len(values) - ddof)
    )


def ema(values: Any, count: int) -> Any:
    alpha = 2 / (count + 1)
    result = np.empty(len(values))
    result[0] = values[0]
    for i in range(1, len(values)):
        result[i] = alpha * values[i] + (1 - alpha) * result[i - 1]
    return result


def previous(values: Any, count: int = 1) -> Any:
    result = np.full(len(values), np.nan)
    if count < len(values):
        result[count:] = values[:-count]
    return result


def state_path(entry: Any, leave: Any, warmup: int, max_hold: int = 0) -> Any:
    """Decision-state lifetime; exit wins and there is no same-decision reentry."""
    active = False
    entered = -1
    result = np.zeros(len(entry), dtype=bool)
    for i in range(warmup - 1, len(entry)):
        if active:
            timed_out = bool(max_hold and i - entered >= max_hold)
            if bool(leave[i]) or timed_out:
                active = False
        elif entry[i]:
            active, entered = True, i
        result[i] = active
    return result


def independent_signals(bars: dict[str, Any], warmup: int = 252) -> dict[str, Any]:
    """Calculate the frozen 15 paths from adjusted bars without engine helpers."""
    close, high, low, opening, volume = (
        np.asarray(bars[key], dtype=float) for key in ("close", "high", "low", "open", "volume")
    )
    old = previous(close)
    means = {n: rolling(close, n, average) for n in (10, 20, 50, 200)}
    std20 = rolling(close, 20, deviation)
    lower, upper = means[20] - 2 * std20, means[20] + 2 * std20
    macd = ema(close, 12) - ema(close, 26)
    macd_active = macd > ema(macd, 9)
    ema20 = ema(close, 20)
    tr = np.fmax(high - low, np.fmax(abs(high - old), abs(low - old)))
    atr20 = rolling(tr, 20, average)
    floor14, ceiling14 = rolling(low, 14, min), rolling(high, 14, max)
    raw_k = np.full(len(close), np.nan)
    np.divide(100 * (close - floor14), ceiling14 - floor14, out=raw_k, where=ceiling14 > floor14)
    slow_k = rolling(raw_k, 3, average)
    inside = (lower > ema20 - 1.5 * atr20) & (upper < ema20 + 1.5 * atr20)
    old_inside = np.zeros(len(close), dtype=bool)
    old_inside[1:] = inside[:-1]
    volume_ratio = volume / previous(rolling(volume, 20, average))
    gap = opening / old - 1
    returns = close / old - 1
    old_risk = previous(rolling(returns, 20, lambda values: deviation(values, 1)))
    ibs = np.full(len(close), np.nan)
    np.divide(close - low, high - low, out=ibs, where=high > low)
    never = np.zeros(len(close), dtype=bool)
    state_definitions = {
        "C02": (
            close > previous(rolling(close, 55, max)),
            close < previous(rolling(close, 20, min)),
            0,
        ),
        "B02": (close > upper, close < means[20], 0),
        "B03": ((old < previous(lower)) & (close >= lower), close >= means[20], 5),
        "B04": ((previous(slow_k) <= 20) & (slow_k > 20), slow_k >= 80, 10),
        "B05": (close > ema20 + 2 * atr20, close < ema20, 0),
        "B06": (old_inside & ~inside & (close > means[20]), close < means[20], 10),
        "B07": (
            (close > previous(rolling(close, 20, max))) & (volume_ratio > 1.5),
            close < means[10],
            10,
        ),
        "B08": (
            (gap >= 0.02) & (gap <= 0.15) & (close > opening) & (volume_ratio >= 1.5),
            never,
            1,
        ),
        "B09": (
            (gap >= -0.15) & (gap <= -0.02) & (close > opening) & (volume_ratio >= 1.5),
            never,
            1,
        ),
        "B10": ((returns <= -2 * old_risk) & (close > means[200]), never, 5),
        "B11": ((tr > 2 * previous(rolling(tr, 20, average))) & (ibs >= 0.8), never, 3),
    }
    output = {
        "C00": np.ones(len(close), dtype=bool),
        "C01": close > means[200],
        "B01": macd_active,
        "B12": (macd_active.astype(int) + (close > means[50]) + (close > previous(close, 20))) >= 2,
    }
    for key, (entry, leave, duration) in state_definitions.items():
        output[key] = state_path(entry, leave, warmup, duration)
    for values in output.values():
        values[: warmup - 1] = False
    return {key: output[key] for key in RULES}


def replay(opened: Any, closed: Any, target: Any, bps: int) -> tuple[Any, int]:
    """A fresh funded ledger reconstructed directly from the registered policy."""
    rate = bps * 0.0001
    cash, held = 1000.0, 0.0
    rows, skipped = [], 0
    for day in range(len(opened)):
        price = float(opened[day])
        initial_mark = cash + held * price
        quantity, charge = 0.0, 0.0
        if bool(target[day]) and held == 0:
            quantity = (cash * 0.98) / (price * (1 + rate))
            if quantity * price < 1:
                quantity = 0
                skipped += 1
        elif not bool(target[day]) and held > 0:
            quantity = -held
            if abs(quantity) * price < 1:
                quantity = 0
                skipped += 1
        value = quantity * price
        charge = abs(value) * rate
        cash -= value + charge
        held += quantity
        open_cash, open_units = cash, held
        terminal_value = -held * float(closed[day]) if day + 1 == len(opened) else 0
        terminal_fee = abs(terminal_value) * rate
        if terminal_value:
            cash -= terminal_value + terminal_fee
            held = 0.0
        rows.append(
            (
                initial_mark,
                open_cash + open_units * price,
                open_cash,
                open_units,
                cash + held * float(closed[day]),
                cash,
                held,
                value,
                charge,
                terminal_value,
                terminal_fee,
                open_cash + open_units * float(closed[day]),
            )
        )
    return np.asarray(rows, dtype=float), skipped


def reconstructed_metrics(dates: Any, ledger: Any, closed: Any, skipped: int) -> dict[str, Any]:
    peak, drawdown = 1000.0, 0.0
    for row, closing in zip(ledger, closed, strict=True):
        for mark in (row[0], row[1], row[2] + row[3] * closing, row[4]):
            peak = max(peak, float(mark))
            drawdown = min(drawdown, float(mark) / peak - 1)
    dates = pd.DatetimeIndex(dates)
    final = ledger[-1, 5]
    duration = ((dates[-1] - dates[0]).days + 1) / 365.25
    return {
        "start": str(dates[0].date()),
        "end": str(dates[-1].date()),
        "sessions": len(dates),
        "ending_cash": final,
        "return": final / 1000 - 1,
        "cagr": math.expm1(math.log(final / 1000) / duration),
        "drawdown": drawdown,
        "trades": int(np.count_nonzero(ledger[:, 7]) + np.count_nonzero(ledger[:, 9])),
        "fees": math.fsum(ledger[:, 8]) + math.fsum(ledger[:, 10]),
        "turnover_dollars": math.fsum(abs(ledger[:, 7])) + math.fsum(abs(ledger[:, 9])),
        "exposed_sessions": int(np.count_nonzero(ledger[:, 3])),
        "skipped_tickets": skipped,
    }


def read_sources(parent: Path, registration: dict[str, Any]) -> dict[str, Any]:
    sources = {}
    for item in registration["inputs"]:
        source = parent / item["path"]
        require(digest(source) == item["sha256"], f"Raw source changed: {item['symbol']}")
        raw = pd.read_csv(source, index_col="Date", parse_dates=True).loc[:"2025-12-31"]
        require(raw.index.is_unique and raw.index.is_monotonic_increasing, "Raw dates")
        ratio = raw["Adj Close"].to_numpy() / raw["Close"].to_numpy()
        values = {
            name.lower(): raw[name].to_numpy() * ratio for name in ("Open", "High", "Low", "Close")
        }
        values["volume"] = raw.Volume.to_numpy()
        values["dates"] = raw.index
        sources[item["symbol"]] = values
    return sources


def expected_input(
    entry: dict[str, Any],
    sources: dict[str, Any],
    signals: dict[str, Any],
    lag: int,
) -> tuple[Any, Any, Any, dict[str, Any]]:
    asset, underlying = sources[entry["symbol"]], sources[entry["signal_symbol"]]
    positions = underlying["dates"].get_indexer(asset["dates"])
    require(bool((positions >= 0).all()), "Missing underlying session")
    eligible = (positions >= 253) & (asset["dates"] >= "2000-01-01")
    if entry["symbol"] == "TECL":
        eligible &= asset["dates"] >= "2012-07-02"
    indices = positions[eligible] - lag
    desired = {rule: signals[entry["signal_symbol"]][rule][indices] for rule in RULES}
    return asset["dates"][eligible], asset["open"][eligible], asset["close"][eligible], desired


def verify_summary(audit: Audit, row: Any, metrics: dict[str, Any], *, short: bool = False) -> None:
    for key, value in metrics.items():
        if key == "cagr" and short:
            continue
        if key in {"start", "end"}:
            require(str(row[key])[:10] == value, f"Summary {key}")
        else:
            audit.equal(row[key], value, f"metric_{key}")


def verify_annual(audit: Audit, actual: Any, dates: Any, ledger: Any, calendar: Any) -> None:
    years = sorted(set(dates.year))
    require(actual.year.tolist() == years, "Annual year coverage")
    previous_nav = 1000.0
    for row, year in zip(actual.to_dict("records"), years, strict=True):
        selected = dates.year == year
        ending = ledger[selected, 4][-1]
        audit.equal(row["return"], ending / previous_nav - 1, "annual_return")
        audit.equal(row["ending_nav"], ending, "annual_ending")
        expected_dates = calendar[calendar.year == year]
        complete = len(dates[selected]) == len(expected_dates) and bool(
            np.array_equal(dates[selected], expected_dates)
        )
        require(bool(row["complete_calendar_year"]) == complete, "Annual complete-year flag")
        previous_nav = ending


def verify_primary(
    audit: Audit,
    output: Path,
    registration: dict[str, Any],
    sources: dict[str, Any],
    signals: dict[str, Any],
    summary: Any,
    annual: Any,
) -> int:
    require(len(summary) == registration["planned_primary_accounts"], "Primary account count")
    require(summary.trial.is_unique, "Duplicate primary trial")
    require(len(list((output / "ledgers").glob("*.npz"))) == len(summary), "Ledger file count")
    reported = summary.set_index("trial")
    annual_groups = annual.groupby("trial", sort=False)
    expected_trials, daily_rows = set(), 0
    for entry in registration["inputs"]:
        symbol = entry["symbol"]
        for lag in registration["lags_sessions"]:
            dates, opened, closed, desired = expected_input(entry, sources, signals, lag)
            for window, (start, end) in registration["periods"].items():
                mask = (dates >= start) & (dates <= end)
                part_dates, part_open, part_close = dates[mask], opened[mask], closed[mask]
                for rule in RULES:
                    target = desired[rule][mask]
                    for bps in registration["costs_bps_per_side"]:
                        trial = f"{symbol}__{rule}__{window}__c{bps}__lag{lag}"
                        expected_trials.add(trial)
                        row = reported.loc[trial]
                        metadata = {
                            "symbol": symbol,
                            "kind": entry["kind"],
                            "signal_symbol": entry["signal_symbol"],
                            "rule": rule,
                            "window": window,
                            "cost_bps": bps,
                            "lag": lag,
                        }
                        for key, expected_value in metadata.items():
                            require(row[key] == expected_value, f"Trial metadata: {key}")
                        path = output / "ledgers" / f"{trial}.npz"
                        require(digest(path) == row.ledger_sha256, "Ledger hash")
                        ledger, skipped = replay(part_open, part_close, target, bps)
                        with np.load(path, allow_pickle=False) as saved:
                            require(tuple(saved["columns"]) == LEDGER_COLUMNS, "Ledger columns")
                            require(
                                np.array_equal(
                                    saved["dates"], part_dates.to_numpy("datetime64[D]")
                                ),
                                "Ledger dates",
                            )
                            audit.equal(saved["target"], target, "execution_target")
                            audit.equal(saved["opened"], part_open, "source_open")
                            audit.equal(saved["closed"], part_close, "source_close")
                            audit.equal(saved["values"], ledger, "ledger_field")
                        result = reconstructed_metrics(part_dates, ledger, part_close, skipped)
                        verify_summary(audit, row, result)
                        verify_annual(
                            audit,
                            annual_groups.get_group(trial),
                            part_dates,
                            ledger,
                            sources["SPY"]["dates"],
                        )
                        daily_rows += len(ledger)
        print(
            json.dumps({"independently_checked_symbol": symbol, "daily_rows": daily_rows}),
            flush=True,
        )
    require(expected_trials == set(summary.trial), "Primary configuration coverage")
    require(set(annual.trial) == expected_trials, "Annual trial coverage")
    return daily_rows


def verify_cohorts(
    audit: Audit,
    registration: dict[str, Any],
    sources: dict[str, Any],
    signals: dict[str, Any],
    short: Any,
) -> int:
    keys = ["symbol", "rule", "horizon", "start"]
    require(not short.duplicated(keys).any(), "Duplicate fresh start")
    require("cagr" not in short.columns, "Short periods must not be annualized")
    groups = short.groupby(["symbol", "rule", "horizon"], sort=False)
    checked, sessions = 0, 0
    for entry in registration["inputs"]:
        dates, opening, closing, targets = expected_input(entry, sources, signals, 1)
        monthly = dates.to_period("M")
        starts = [i for i in range(len(dates)) if i == 0 or monthly[i] != monthly[i - 1]]
        for rule in RULES:
            for horizon in registration["short_periods"]["horizons_sessions"]:
                valid_starts = [i for i in starts if i + horizon <= len(dates)]
                group = groups.get_group((entry["symbol"], rule, horizon)).sort_values("start")
                require(len(group) == len(valid_starts), "Fresh-start count")
                for row, begin in zip(group.to_dict("records"), valid_starts, strict=True):
                    end = begin + horizon
                    ledger, skipped = replay(
                        opening[begin:end], closing[begin:end], targets[rule][begin:end], 10
                    )
                    metrics = reconstructed_metrics(
                        dates[begin:end], ledger, closing[begin:end], skipped
                    )
                    verify_summary(audit, row, metrics, short=True)
                    checked += 1
                    sessions += horizon
    require(checked == len(short), "Fresh-start total coverage")
    return sessions


def check_run(parent: Path, output: Path) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    require(digest(root / REGISTRATION) == REGISTRATION_HASH, "Frozen registration drift")
    registration = json.loads((root / REGISTRATION).read_text(encoding="utf-8"))
    started = json.loads((output / "started.json").read_text(encoding="utf-8"))
    complete = json.loads((output / "completed.json").read_text(encoding="utf-8"))
    require(started["registration_sha256"] == REGISTRATION_HASH, "Run registration")
    for name, expected in started["source_hashes"].items():
        require(digest(root / name) == expected, f"Engine source drift: {name}")
    for name, expected in complete["public_output_hashes"].items():
        require(digest(output / name) == expected, f"Output drift: {name}")
    require(started["inputs"] == registration["inputs"], "Run input manifest")
    sources = read_sources(parent, registration)
    audit = Audit()
    signals = {}
    for symbol in sorted({entry["signal_symbol"] for entry in registration["inputs"]}):
        source = sources[symbol]
        signals[symbol] = independent_signals(source)
        saved = pd.read_csv(
            output / "signals" / f"{symbol}.csv.gz", index_col="decision_date", parse_dates=True
        )
        require(saved.index.equals(source["dates"]), "Saved signal dates")
        for rule in RULES:
            audit.equal(saved[rule].to_numpy(), signals[symbol][rule], "signal_cell")
        audit.equal(saved.warmup_ready, np.arange(len(saved)) >= 251, "signal_warmup")
        expected_as_of = (
            (saved.index + pd.Timedelta(hours=16)).tz_localize("America/New_York").tz_convert("UTC")
        )
        require(
            np.array_equal(pd.to_datetime(saved.as_of, utc=True), expected_as_of), "Signal as_of"
        )
    summary = pd.read_csv(output / "summary.csv")
    annual = pd.read_csv(output / "annual.csv.gz")
    short = pd.read_parquet(output / "fresh_starts.parquet")
    daily_rows = verify_primary(audit, output, registration, sources, signals, summary, annual)
    cohort_rows = verify_cohorts(audit, registration, sources, signals, short)
    eligible = summary.loc[
        (summary.window == "training")
        & (summary.cost_bps == 10)
        & (summary.lag == 1)
        & summary.rule.str.startswith("B")
    ]
    expected_selection = (
        eligible.sort_values(["symbol", "cagr", "rule"], ascending=[True, False, True])
        .groupby("symbol")
        .head(1)
    )
    actual_selection = pd.read_csv(output / "training_selection.csv")
    require(
        actual_selection.trial.tolist() == expected_selection.trial.tolist(),
        "Training-only selection",
    )
    require(complete["primary_accounts"] == len(summary), "Completion primary count")
    require(complete["fresh_start_accounts"] == len(short), "Completion cohort count")
    require(complete["annual_rows"] == len(annual), "Completion annual count")
    require(complete["rules"] == len(RULES), "Completion rule count")
    require(complete["instruments"] == len(registration["inputs"]), "Completion instrument count")
    return {
        "status": "PASS",
        "checked_utc": datetime.now(UTC).isoformat(),
        "scope": (
            "All primary funded daily ledgers, all annual returns, all fresh-start summaries, "
            "all22signal series and training-only choices independently reconstructed; "
            "no simulator import."
        ),
        "registration_sha256": REGISTRATION_HASH,
        "checker_sha256": digest(Path(__file__)),
        "primary_accounts": len(summary),
        "daily_rows": daily_rows,
        "annual_rows": len(annual),
        "fresh_start_accounts": len(short),
        "fresh_start_daily_rows_reconstructed": cohort_rows,
        "checks": dict(audit.checks),
        "maximum_absolute_residuals": audit.residuals,
        "limits": (
            "Arithmetic/causality agreement is not evidence of predictive alpha, "
            "nominal share feasibility, options fills or future profit. "
            "Current-vintage inputs and survivor selection remain."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "Audit output already exists")
    result = check_run(args.parent, args.run)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("status", "primary_accounts", "daily_rows", "fresh_start_accounts")
            }
        )
    )


if __name__ == "__main__":
    main()
