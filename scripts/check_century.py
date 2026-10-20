"""Independent monthly-study audit; does not import the simulator or its helpers."""

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import brentq

REGISTRATION = Path("docs/research/century-registration-2026-10-20.json")
REGISTRATION_SHA256 = "5d5baa3dc0b8b7a02e3c4ce1b39cad3651697adade3805bd195a30ee38caa641"
CONTROLS = ("CZERO", "CRF", "CMKT", "CEQ")


def require(condition: bool, label: str) -> None:
    if not condition:
        raise ValueError(label)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@dataclass
class Audit:
    checks: Counter[str] = field(default_factory=Counter)
    residuals: dict[str, float] = field(default_factory=dict)

    def equal(self, actual: Any, expected: Any, label: str, atol: float = 1e-7) -> None:
        left, right = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
        require(left.shape == right.shape, f"{label}: shape")
        require(bool(np.isfinite(left).all() and np.isfinite(right).all()), f"{label}: nonfinite")
        error = float(np.max(np.abs(left - right), initial=0))
        self.checks[label] += left.size
        self.residuals[label] = max(self.residuals.get(label, 0.0), error)
        require(
            bool(np.all(np.abs(left - right) <= atol + 1e-9 * np.abs(right))),
            f"{label}: residual {error}",
        )


@dataclass(frozen=True)
class Inputs:
    months: tuple[str, ...]
    symbols: tuple[str, ...]
    returns: Any
    rf: Any


def read_section(path: Path, section: str | None = None) -> pd.DataFrame:
    """Parse a bounded monthly section with csv.reader, independently of the loader."""
    rows = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines()))
    start = 0
    if section is not None:
        matches = [i for i, row in enumerate(rows) if len(row) == 1 and row[0].strip() == section]
        require(len(matches) == 1, "Missing or ambiguous source section")
        start = matches[0] + 1
    header = next(i for i in range(start, len(rows)) if rows[i] and not rows[i][0].strip())
    names = [value.strip() for value in rows[header][1:]]
    require(len(names) == len(set(names)), "Duplicate source columns")
    values, periods = [], []
    for row in rows[header + 1 :]:
        if not row or not row[0].strip().isdigit() or len(row[0].strip()) != 6:
            break
        require(len(row) == len(names) + 1, "Ragged source row")
        month = row[0].strip()
        periods.append(month[:4] + "-" + month[4:])
        values.append([float(value) for value in row[1:]])
    require(periods == sorted(set(periods)), "Duplicate or unordered source months")
    return pd.DataFrame(values, index=periods, columns=names)


def read_inputs(source: Path, registration: dict[str, Any]) -> Inputs:
    require(
        digest(source / "acquisition.json") == registration["inputs"]["raw_manifest_sha256"],
        "Input manifest drift",
    )
    count = registration["inputs"]["industry_count"]
    manifest = json.loads((source / "acquisition.json").read_bytes())
    for item in manifest["files"]:
        require(digest(source / item["file"]) == item["sha256"], "Source ZIP drift")
        require(digest(source / item["member"]) == item["member_sha256"], "Source member drift")
    industry = read_section(
        source / f"{count}_Industry_Portfolios.csv", "Average Value Weighted Returns -- Monthly"
    )
    factors = read_section(source / "F-F_Research_Data_Factors.csv")
    industry = industry.loc[(industry.index >= "1926-07") & (industry.index <= "2026-06")]
    factors = factors.loc[(factors.index >= "1926-07") & (factors.index <= "2026-06")]
    dates = tuple(str(month) for month in pd.period_range("1926-07", "2026-06", freq="M"))
    require(tuple(industry.index) == dates and tuple(factors.index) == dates, "Source coverage")
    require(industry.shape == (1200, count), "Industry dimensions")
    raw = np.column_stack((industry.to_numpy(float), factors[["Mkt-RF", "RF"]].to_numpy(float)))
    require(bool(np.isfinite(raw).all()), "Nonfinite input")
    require(not bool(np.isin(raw, [-99.99, -999]).any()), "Missing source sentinel")
    stocks = industry.to_numpy(float) * 0.01
    rf = factors["RF"].to_numpy(float) * 0.01
    market = factors["Mkt-RF"].to_numpy(float) * 0.01 + rf
    returns = np.column_stack((stocks, market))
    require(bool((returns > -1).all() and (rf > -1).all()), "Nonpositive gross input return")
    return Inputs(dates, (*industry.columns, "MKT"), returns, rf)


def target_reference(  # noqa: PLR0912, PLR0915 -- each registered family is explicit
    policy: dict[str, Any], data: Inputs, cutoff: int
) -> Any:
    """Recompute an unscaled allocation from permitted observations only."""
    count = len(data.symbols) - 1
    kind, length = policy["family"], int(policy["lookback"])
    final = cutoff - (kind == "SKIPMOM")
    first = final - length + 1
    require(first >= 0 and final < len(data.months), "Signal warmup or cutoff")
    history = data.returns[first : final + 1, :count]
    cash = data.rf[first : final + 1]
    require(history.shape == (length, count), "Signal dimensions")
    excess = history - cash[:, None]
    gross = np.prod(1.0 + history, axis=0)
    centered = history - history.mean(axis=0)
    sigma = (
        np.sqrt(np.sum(centered * centered, axis=0) / (length - 1))
        if length > 1
        else np.zeros(count)
    )
    negative = np.where(excess < 0, excess, 0)
    downside = np.sqrt(np.sum(negative * negative, axis=0) / length)
    wealth = np.concatenate((np.ones((1, count)), np.cumprod(history + 1, axis=0)), axis=0)
    weights = np.zeros(count + 1)
    score = None
    if kind in {"MOM", "SKIPMOM"}:
        score = gross - 1
    elif kind == "VOLMOM":
        score = (gross - 1) / np.where(sigma < 0.001, 0.001, sigma)
    elif kind == "DOWNMOM":
        score = (gross - 1) / np.where(downside < 0.001, 0.001, downside)
    elif kind in ("SHORTREV", "LONGREV"):
        score = 1 - gross
    elif kind == "LOWVOL":
        score = -sigma
    elif kind == "LOWBETA":
        x = data.returns[first : final + 1, count] - cash
        design = np.column_stack((np.ones(length), x))
        if float(np.sum((x - x.mean()) ** 2)) < 1e-12:
            score = (
                -np.sum((x - x.mean())[:, None] * (excess - excess.mean(axis=0)), axis=0) / 1e-12
            )
        else:
            score = -np.linalg.lstsq(design, excess, rcond=None)[0][1]
    elif kind == "LOWDD":
        score = np.zeros(count)
        peak = np.ones(count)
        for point in wealth[1:]:
            peak = np.maximum(peak, point)
            score = np.minimum(score, point / peak - 1)
    elif kind == "ABSMOM":
        weights[:count] = np.where(gross > math.prod(cash + 1), 1 / count, 0)
    elif kind == "SMA":
        weights[:count] = np.where(wealth[-1] > np.sum(wealth[1:], axis=0) / length, 1 / count, 0)
    elif kind == "CHANNEL":
        prices = wealth[1:]
        low, span = prices.min(axis=0), np.ptp(prices, axis=0)
        score = np.full(count, 0.5)
        moving = span > 0
        score[moving] = (prices[-1, moving] - low[moving]) / span[moving]
    elif kind == "REGTREND":
        times = np.arange(length + 1, dtype=float)
        design = np.column_stack((np.ones(length + 1), times))
        logged = np.log(wealth)
        coefficients = np.linalg.lstsq(design, logged, rcond=None)[0]
        residual = logged - design @ coefficients
        variance = np.sum(residual * residual, axis=0) / (length - 1)
        se = np.sqrt(variance / np.sum((times - times.mean()) ** 2))
        score = coefficients[1] / np.maximum(se, 1e-12)
    elif kind == "CONSISTENCY":
        score = np.count_nonzero(excess > 0, axis=0) / length
    elif kind in ("INVERSEVOL", "INVERSEDOWN"):
        risk = sigma if kind == "INVERSEVOL" else downside
        inverse = np.reciprocal(np.maximum(risk, 0.001))
        weights[:count] = inverse / math.fsum(inverse)
    elif kind in ("VOLCAPEQ", "VOLCAPMKT"):
        series = (
            history.sum(axis=1) / count
            if kind == "VOLCAPEQ"
            else data.returns[first : final + 1, count]
        )
        risk = math.sqrt(float(np.sum((series - series.mean()) ** 2)) / (length - 1) * 12)
        allocation = min(1, float(policy["target_vol"]) / max(risk, 1e-12))
        if kind == "VOLCAPEQ":
            weights[:count] = allocation / count
        else:
            weights[count] = allocation
    else:
        raise ValueError("Unknown signal family " + kind)
    if score is not None:
        require(bool(np.isfinite(score).all()), "Nonfinite scores")
        ordering = np.lexsort((np.array(data.symbols[:count]), -score))
        winners = ordering[: int(policy["top_k"])]
        weights[winners] = 1 / len(winners)
    return weights


def cppi_reference(
    policy: dict[str, Any], nav: float, peak: float, count: int
) -> tuple[Any, float]:
    floor = float(policy["floor_fraction"]) * (peak if policy["family"] == "CPPIRATCHET" else 1000)
    fraction = min(1.0, max(0.0, float(policy["multiplier"]) * (1 - floor / nav)))
    weights = np.zeros(count + 1)
    weights[count] = fraction * 0.98
    return weights, floor


def funded_rebalance(
    values: Any, cash: float, weights: Any, rate: float
) -> tuple[Any, float, float]:
    """Solve normalized funding by bracketing, not the simulator's fixed point."""
    nav = float(np.sum(values) + cash)
    require(nav > 0 and cash >= -1e-9, "Invalid wealth")
    require(bool(np.all(values >= 0) and np.all(weights >= 0)), "Short holding or target")
    require(float(np.sum(weights)) <= 1 + 1e-12, "Borrowed target")
    fraction = brentq(
        lambda q: q + rate * float(np.abs(weights * q - values / nav).sum()) - 1,
        0.0,
        1.0,
        xtol=1e-15,
    )
    purchases = weights * (nav * fraction)
    fee = rate * float(np.sum(np.abs(purchases - values)))
    remainder = nav - math.fsum(purchases) - fee
    require(remainder >= -1e-7, "Unfunded costs")
    return purchases, max(0.0, remainder), fee


def measure(frame: pd.DataFrame) -> dict[str, Any]:
    """Independent path/annual reconstruction, including pre-terminal peak."""
    endings = frame.ending_nav.to_numpy(float)
    navs = np.concatenate(([1000.0], endings))
    returns = navs[1:] / navs[:-1] - 1
    peak, drawdown = 1000.0, 0.0
    for row in frame.itertuples(index=False):
        for mark in (
            row.before_nav,
            row.after_cost_nav,
            row.ending_nav + row.terminal_fee,
            row.ending_nav,
        ):
            peak = max(peak, float(mark))
            drawdown = min(drawdown, float(mark) / peak - 1)
    annual: dict[str, float] = {}
    partial: dict[str, float] = {}
    for year in sorted({month[:4] for month in frame.month}):
        mask = np.array([month.startswith(year) for month in frame.month])
        target = annual if int(mask.sum()) == 12 else partial
        target[year] = math.prod(1 + returns[mask]) - 1
    result = {
        "months": len(frame),
        "ending_nav": endings[-1],
        "cagr": math.expm1(math.log(endings[-1] / 1000) * 12 / len(frame)),
        "max_drawdown": drawdown,
        "annual": annual,
        "partial_calendar_returns": partial,
        "warmup_months": int(sum(frame.warmup)),
        "worst_year": min(annual.values(), default=0.0),
        "losing_years": sum(value < 0 for value in annual.values()),
        "years_ge_10pct": sum(value >= 0.1 for value in annual.values()),
        "years_ge_25pct": sum(value >= 0.25 for value in annual.values()),
        "all_years_ge_10pct": bool(annual) and all(value >= 0.1 for value in annual.values()),
        "fees": math.fsum(frame.fee),
        "turnover": math.fsum(frame.turnover),
        "mean_risky_fraction": math.fsum(frame.risky_fraction) / len(frame),
        "trade_legs": int(sum(frame.trade_legs)),
        "sub_dollar_legs": int(sum(frame.sub_dollar_legs)),
    }
    for span in (12, 60, 120):
        if len(endings) >= span:
            result[f"worst_rolling_{span}m_cagr"] = min(
                (navs[j + span] / navs[j]) ** (12 / span) - 1 for j in range(len(navs) - span)
            )
    return result


def compare_summary(summary: dict[str, Any], expected: dict[str, Any], audit: Audit) -> None:
    for name, value in expected.items():
        if name in {"annual", "partial_calendar_returns"}:
            require(set(summary[name]) == set(value), "Annual year inventory")
            for year, annual_return in value.items():
                audit.equal(summary[name][year], annual_return, "annual_return")
        else:
            audit.equal(summary[name], value, "summary_" + name)


def audit_account(  # noqa: PLR0912, PLR0915 -- complete sequential account replay
    frame: pd.DataFrame,
    data: Inputs,
    policy: dict[str, Any],
    start: str,
    end: str,
    cost: int,
    lag: int,
    targets: Any,
    audit: Audit,
    ledger: Any = None,
) -> dict[str, Any]:
    count = len(data.symbols) - 1
    first, last = data.months.index(start), data.months.index(end)
    require(tuple(frame.month) == data.months[first : last + 1], "Account month inventory")
    positions, cash = np.zeros(count + 1), 1000.0
    history: list[float] = []
    rate = cost / 10000
    breaches = 0
    expected_rows, position_rows, conservation = [], [], []
    for local, row in enumerate(frame.itertuples(index=False)):
        pos = first + local
        cutoff = pos - lag
        if cutoff < 0:
            require(bool(pd.isna(row.as_of)), "as_of")
        else:
            require(
                row.as_of == str(pd.Period(data.months[cutoff], freq="M").end_time.date()),
                "as_of",
            )
        before = float(positions.sum() + cash)
        reference = history[local - lag] if local >= lag else 1000.0
        peak = max([1000.0, *history[: local - lag + 1]]) if local >= lag else 1000.0
        weights, floor = np.zeros(count + 1), None
        warmup = policy["id"] not in CONTROLS and data.months[pos] < "1933-01"
        require(isinstance(row.warmup, bool) and row.warmup == warmup, "warmup")
        if warmup:
            pass
        elif policy["id"] == "CMKT":
            weights[-1] = 0.98
        elif policy["id"] == "CEQ":
            weights[:count] = 0.98 / count
        elif policy["family"].startswith("CPPI"):
            weights, floor = cppi_reference(policy, reference, peak, count)
        elif policy["id"] not in CONTROLS:
            weights = targets[pos] * 0.98
        previous = positions.copy()
        if policy["id"] == "CMKT" and local:
            fee = 0.0
        else:
            positions, cash, fee = funded_rebalance(positions, cash, weights, rate)
        holdings = positions.copy()
        cash_after = cash
        trades = np.abs(holdings - previous)
        turnover = float(trades.sum())
        legs = int(np.count_nonzero(trades > 1e-9))
        small = int(np.count_nonzero((trades > 1e-9) & (trades < 1)))
        after = float(holdings.sum() + cash)
        risky = float(np.sum(holdings * data.returns[pos]))
        riskless = cash * float(data.rf[pos]) if policy["id"] != "CZERO" else 0.0
        positions = holdings * (1 + data.returns[pos])
        cash += riskless
        pre_terminal = float(positions.sum() + cash)
        terminal = 0.0
        if pos == last:
            liquidation = float(positions.sum())
            terminal = rate * liquidation
            legs += int(np.count_nonzero(positions > 1e-9))
            small += int(np.count_nonzero((positions > 1e-9) & (positions < 1)))
            turnover += liquidation
            cash += liquidation - terminal
            positions = np.zeros(count + 1)
        ending = float(positions.sum() + cash)
        history.append(ending)
        expected = {
            "before_nav": before,
            "after_cost_nav": after,
            "cash_after_cost": cash_after,
            "ending_before_terminal": pre_terminal,
            "ending_nav": ending,
            "fee": fee + terminal,
            "terminal_fee": terminal,
            "turnover": turnover,
            "risky_pnl": risky,
            "cash_pnl": riskless,
            "risky_fraction": float(holdings.sum()) / after,
            "reference_nav": reference,
            "reference_peak": peak,
            "trade_legs": legs,
            "sub_dollar_legs": small,
        }
        expected_rows.append(expected)
        position_rows.append(holdings)
        conservation.append(before - fee + risky + riskless - terminal)
        if floor is not None and min(before, after, pre_terminal, ending) < floor:
            breaches += 1
    for name in expected_rows[0]:
        audit.equal(frame[name].to_numpy(), [row[name] for row in expected_rows], "account_" + name)
    audit.equal(history, conservation, "account_conservation")
    if ledger is not None:
        audit.equal(ledger["risky_after_cost"], position_rows, "asset_risky_after_cost")
    return {"floor_breach_months": breaches, "metrics": measure(frame)}


def regimes_reference(data: Inputs, lag: int) -> dict[str, str]:
    labels = {}
    risks: list[float] = []
    for cutoff in range(11, len(data.months)):
        block = data.returns[cutoff - 11 : cutoff + 1, -1]
        risk = math.sqrt(float(np.sum((block - block.mean()) ** 2)) / 11)
        risks.append(risk)
        if cutoff + lag >= len(data.months):
            continue
        trend = (
            "up"
            if math.prod(1 + block) > math.prod(1 + data.rf[cutoff - 11 : cutoff + 1])
            else "down"
        )
        level = "high_vol" if risk > float(np.median(risks)) else "low_vol"
        labels[data.months[cutoff + lag]] = trend + "_" + level
    return labels


def bootstrap_reference(excess: Any, repeats: int = 2000) -> dict[str, Any]:
    """Same registered random experiment, different reduction via index counts."""
    matrix = np.asarray(excess, dtype=float)
    require(matrix.ndim == 2 and len(matrix) >= 12, "Bootstrap dimensions")
    require(bool(np.isfinite(matrix).all()), "Bootstrap nonfinite")
    means = matrix.sum(axis=0) / len(matrix)
    centered = matrix - means
    rng = np.random.default_rng(20261020)
    max_exceed = np.zeros(matrix.shape[1], dtype=int)
    own_exceed = np.zeros(matrix.shape[1], dtype=int)
    for _ in range(repeats):
        sample = [int(rng.integers(len(matrix)))]
        for _t in range(1, len(matrix)):
            restart = rng.random() < 1 / 6
            sample.append(
                int(rng.integers(len(matrix))) if restart else (sample[-1] + 1) % len(matrix)
            )
        # Integer observation counts preserve a common resample across columns.
        counts = np.bincount(sample, minlength=len(matrix))
        averages = (counts @ centered) / len(matrix)
        max_exceed += np.max(averages) >= means
        own_exceed += averages >= means
    return {
        "mean_monthly_excess": means,
        "familywise_p": (max_exceed + 1) / (repeats + 1),
        "unadjusted_p": (own_exceed + 1) / (repeats + 1),
    }


def selection_reference(results: list[dict[str, Any]]) -> dict[str, Any]:
    primary = {
        r["policy"]: r
        for r in results
        if (r["window"], r["cost_bps"], r["lag"]) == ("training", 25, 2)
    }
    benchmark = primary["CMKT"]
    identities = [name for name in primary if name not in CONTROLS]
    stable = [
        name
        for name in identities
        if primary[name]["cagr"] > 0 and primary[name]["max_drawdown"] > benchmark["max_drawdown"]
    ]
    stable.sort(key=lambda name: (-primary[name]["max_drawdown"], -primary[name]["cagr"], name))
    ranked = sorted(identities, key=lambda name: (-primary[name]["cagr"], name))
    return {
        "stable": stable[:5],
        "growth10": [name for name in ranked if primary[name]["cagr"] >= 0.1][:5],
        "growth25": [name for name in ranked if primary[name]["cagr"] >= 0.25][:5],
    }


def classification_reference(
    results: list[dict[str, Any]], identities: list[str]
) -> dict[str, Any]:
    index = {(r["policy"], r["window"], r["cost_bps"], r["lag"]): r for r in results}
    rows = []
    for identity in identities:
        full, later = index[identity, "full", 25, 2], index[identity, "evaluation", 25, 2]
        pairs = [
            (index[identity, window, cost, lag], index["CMKT", window, cost, lag])
            for window in ("full", "evaluation")
            for cost in (10, 25, 50)
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
                "positive_primary_both": min(full["cagr"], later["cagr"]) > 0,
                "positive_all12": all(result["cagr"] > 0 for result, _ in pairs),
                "stable_all12": all(
                    result["cagr"] > 0 and result["max_drawdown"] > benchmark["max_drawdown"]
                    for result, benchmark in pairs
                ),
                "growth10_primary_both": min(full["cagr"], later["cagr"]) >= 0.1,
                "growth25_primary_both": min(full["cagr"], later["cagr"]) >= 0.25,
            }
        )
    flags = [name for name in rows[0] if name.endswith(("both", "all12"))]
    return {
        "rows": rows,
        "counts": {name: sum(bool(row[name]) for row in rows) for name in flags},
        "unique_qualifying_configurations": sum(
            row["stable_all12"] or row["growth10_primary_both"] or row["growth25_primary_both"]
            for row in rows
        ),
    }


def diagnostics_reference(frame: pd.DataFrame, labels: dict[str, str]) -> dict[str, Any]:
    ends = frame.ending_nav.to_numpy(float)
    monthly = ends / np.r_[1000.0, ends[:-1]] - 1
    groups = {}
    for state in sorted({labels[month] for month in frame.month}):
        chosen = np.array([labels[month] == state for month in frame.month])
        block = frame.loc[chosen]
        groups[state] = {
            "months": int(chosen.sum()),
            "mean_net_monthly_return": math.fsum(monthly[chosen]) / int(chosen.sum()),
            "positive_month_fraction": float(np.count_nonzero(monthly[chosen] > 0) / chosen.sum()),
            "mean_risky_fraction": math.fsum(block.risky_fraction) / len(block),
            "sum_cash_pnl_usd": math.fsum(block.cash_pnl),
            "sum_risky_pnl_usd": math.fsum(block.risky_pnl),
            "sum_fees_usd": math.fsum(block.fee),
        }
    decades = {}
    for year in range(1933, 2024, 10):
        chosen = (frame.month >= f"{year}-01") & (frame.month <= f"{year + 9}-12")
        last_year = min(year + 9, 2025)
        require(int(chosen.sum()) == 12 * (last_year - year + 1), "Diagnostic period coverage")
        decades[f"{year}-{last_year}"] = (
            math.prod(1 + monthly[chosen]) ** (12 / int(chosen.sum())) - 1
        )
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
        chosen = (frame.month >= start) & (frame.month <= end)
        stresses[start + ":" + end] = math.prod(1 + monthly[chosen]) - 1
    return {"causal_states": groups, "decade_cagr": decades, "stress_total_return": stresses}


def compare_tree(actual: Any, expected: Any, audit: Audit, label: str) -> None:
    if isinstance(expected, dict):
        require(set(actual) == set(expected), label + " keys")
        for name, value in expected.items():
            compare_tree(actual[name], value, audit, label + "." + name)
    elif isinstance(expected, list):
        require(len(actual) == len(expected), label + " length")
        for a, b in zip(actual, expected, strict=True):
            compare_tree(a, b, audit, label)
    elif isinstance(expected, str):
        require(actual == expected, label + " value")
    else:
        audit.equal(actual, expected, label)


def run(source: Path, output: Path) -> dict[str, Any]:  # noqa: PLR0912, PLR0915
    require(digest(REGISTRATION) == REGISTRATION_SHA256, "Registration drift")
    spec = json.loads(REGISTRATION.read_bytes())
    data = read_inputs(source, spec)
    audit = Audit()
    policies = spec["policies"] + [{"id": name, "family": "control"} for name in CONTROLS]
    identities = [p["id"] for p in spec["policies"]]
    require(len(identities) == len(set(identities)) == 200, "Candidate inventory")
    require(set(Counter(p["family"] for p in spec["policies"]).values()) == {10}, "Family variants")
    manifest = json.loads((output / "manifest.json").read_bytes())
    require(manifest["accounts"] == 4896, "Manifest accounts")
    entries = [entry["path"] for entry in manifest["files"]]
    require(len(entries) == len(set(entries)), "Duplicate output manifest entry")
    require(
        set(entries)
        == {path.name for path in output.iterdir() if path.is_file()} - {"manifest.json"},
        "Output manifest inventory",
    )
    require(
        not (output / "failures.json").exists() and not (output / "run-error.json").exists(),
        "Run contains a retained failure",
    )
    for entry in manifest["files"]:
        payload = output / entry["path"]
        require(payload.stat().st_size == entry["bytes"], "Output size drift")
        require(digest(payload) == entry["sha256"], "Output hash drift")
    started = json.loads((output / "started.json").read_bytes())
    require(started["registration_sha256"] == REGISTRATION_SHA256, "Run registration")
    for name, value in started["source_sha256"].items():
        require(digest(Path(name)) == value, "Run source drift: " + name)
    metadata = json.loads((output / "signal-index.json").read_bytes())
    require(tuple(metadata["months"]) == data.months, "Signal months")
    require(tuple(metadata["symbols"]) == data.symbols, "Signal symbols")
    refs = {}
    with np.load(output / "static-targets.npz", allow_pickle=False) as saved:
        keys = {
            f"{p['id']}_l{lag}"
            for p in policies
            if p["id"] not in CONTROLS and not p["family"].startswith("CPPI")
            for lag in (1, 2)
        }
        require(set(saved.files) == keys, "Target inventory")
        first = data.months.index("1933-01")
        for lag in (1, 2):
            dates = [
                str(pd.Period(data.months[pos - lag], freq="M").end_time.date())
                if pos >= first
                else None
                for pos in range(len(data.months))
            ]
            require(metadata["as_of"][f"lag{lag}"] == dates, "Signal timestamp cutoff")
            for policy in policies:
                name = f"{policy['id']}_l{lag}"
                if name not in keys:
                    continue
                reference = np.zeros((len(data.months), len(data.symbols)))
                for pos in range(first, len(data.months)):
                    reference[pos] = target_reference(policy, data, pos - lag)
                audit.equal(saved[name], reference, "static_target", atol=2e-10)
                refs[name] = reference
    results = json.loads((output / "results.json").read_bytes())
    keyed = {(r["policy"], r["cost_bps"], r["lag"], r["window"]): r for r in results}
    expected_keys = {
        (policy["id"], cost, lag, window)
        for policy in policies
        for cost in (10, 25, 50)
        for lag in (1, 2)
        for window in spec["windows"]
    }
    require(len(results) == len(keyed) == 4896 and set(keyed) == expected_keys, "Result inventory")
    metrics, later, regimes, floor_breaches, full_hashes = [], {}, {}, {}, {}
    label_refs = regimes_reference(data, 2)
    for window, (start, end) in spec["windows"].items():
        for cost in (10, 25, 50):
            for lag in (1, 2):
                for policy in policies:
                    stem = f"{policy['id']}_c{cost}_l{lag}_{window}"
                    frame = pd.read_csv(output / (stem + ".csv.gz"), float_precision="round_trip")
                    ledger_path = output / (stem + ".positions.npz")
                    require(ledger_path.exists(), "Missing per-asset ledger: " + stem)
                    with np.load(ledger_path, allow_pickle=False) as ledger:
                        require(
                            set(ledger.files) == {"risky_after_cost"}
                            and ledger["risky_after_cost"].shape == (len(frame), len(data.symbols)),
                            "Per-asset ledger schema",
                        )
                        verified = audit_account(
                            frame,
                            data,
                            policy,
                            start,
                            end,
                            cost,
                            lag,
                            refs.get(f"{policy['id']}_l{lag}"),
                            audit,
                            {"risky_after_cost": ledger["risky_after_cost"]},
                        )
                    summary = keyed[policy["id"], cost, lag, window]
                    require(summary["family"] == policy["family"], "Summary family")
                    compare_summary(summary, verified["metrics"], audit)
                    metrics.append(
                        {
                            **verified["metrics"],
                            "policy": policy["id"],
                            "family": policy["family"],
                            "window": window,
                            "cost_bps": cost,
                            "lag": lag,
                        }
                    )
                    if policy["family"].startswith("CPPI"):
                        floor_breaches[stem] = verified["floor_breach_months"]
                    if cost == 25 and lag == 2:
                        if window == "evaluation":
                            nav = frame.ending_nav.to_numpy(float)
                            later[policy["id"]] = nav / np.r_[1000.0, nav[:-1]] - 1
                        elif window == "full":
                            regimes[policy["id"]] = diagnostics_reference(frame, label_refs)
                            if policy["id"] not in CONTROLS:
                                nav = frame.ending_nav.to_numpy(float)
                                returns = nav / np.r_[1000.0, nav[:-1]] - 1
                                full_hashes[policy["id"]] = hashlib.sha256(
                                    returns.astype("<f8").tobytes()
                                ).hexdigest()
        print(
            json.dumps({"independently_checked_window": window, "accounts": len(metrics)}),
            flush=True,
        )
    chosen = selection_reference(metrics)
    actual_selection = json.loads((output / "selection.json").read_bytes())
    require(
        datetime.fromisoformat(started["started_utc"])
        <= datetime.fromisoformat(actual_selection["saved_utc"])
        <= datetime.fromisoformat(manifest["completed_utc"]),
        "Selection timestamp ordering",
    )
    for name, value in chosen.items():
        require(actual_selection[name] == value, "Training selection " + name)
    classification = classification_reference(metrics, identities)
    actual_classification = json.loads((output / "classification.json").read_bytes())
    for name, value in classification.items():
        compare_tree(actual_classification[name], value, audit, "classification." + name)
    century_inputs = [
        {**r, "window": "full" if r["window"] == "century" else "evaluation"}
        for r in metrics
        if r["window"] in {"century", "evaluation"}
    ]
    century_classification = classification_reference(century_inputs, identities)
    century_actual = json.loads((output / "classification-century.json").read_bytes())
    for name, value in century_classification.items():
        compare_tree(century_actual[name], value, audit, "classification_century." + name)
    uniqueness = json.loads((output / "path-uniqueness.json").read_bytes())
    groups: dict[str, list[str]] = {}
    for identity in identities:
        groups.setdefault(full_hashes[identity], []).append(identity)
    require(uniqueness["candidate_count"] == 200, "Uniqueness candidate inventory")
    require(uniqueness["unique_machine_paths"] == len(groups), "Unique path count")
    require(uniqueness["sha256_by_policy"] == full_hashes, "Exact return path hashes")
    require(
        sorted(sorted(group) for group in uniqueness["duplicate_groups"])
        == sorted(sorted(group) for group in groups.values() if len(group) > 1),
        "Duplicate path membership",
    )
    compare_tree(json.loads((output / "regimes.json").read_bytes()), regimes, audit, "regime")
    excess = np.column_stack([later[name] - later["CMKT"] for name in identities])
    bootstrap = bootstrap_reference(excess)
    actual_bootstrap = json.loads((output / "bootstrap.json").read_bytes())
    require(actual_bootstrap["policies"] == identities, "Bootstrap policy order")
    for name, value in {"replicates": 2000, "seed": 20261020, "mean_block_months": 6}.items():
        require(actual_bootstrap[name] == value, "Bootstrap registration " + name)
    for name, value in bootstrap.items():
        audit.equal(actual_bootstrap[name], value, "bootstrap_" + name, atol=1e-12)
    return {
        "status": "PASS",
        "checked_utc": datetime.now(UTC).isoformat(),
        "registration_sha256": REGISTRATION_SHA256,
        "checker_sha256": digest(Path(__file__)),
        "input_manifest_sha256": digest(source / "acquisition.json"),
        "run_manifest_sha256": digest(output / "manifest.json"),
        "accounts": len(metrics),
        "candidate_configurations": 200,
        "families": 20,
        "controls": 4,
        "monthly_rows": sum(result["months"] for result in metrics),
        "annual_rows": sum(len(result["annual"]) for result in metrics),
        "numeric_comparisons": dict(sorted(audit.checks.items())),
        "maximum_absolute_residual": dict(sorted(audit.residuals.items())),
        "training_selection": chosen,
        "classification_counts": classification["counts"],
        "century_classification_counts": century_classification["counts"],
        "partial_calendar_rows": sum(len(result["partial_calendar_returns"]) for result in metrics),
        "candidate_cash_warmup_rows": sum(result["warmup_months"] for result in metrics),
        "unique_machine_paths": len(groups),
        "cppi_accounts_with_floor_breaches": sum(value > 0 for value in floor_breaches.values()),
        "cppi_floor_breach_months": sum(floor_breaches.values()),
        "scope": (
            "All recorded accounts, all asset holdings, all targets, selection, metrics, "
            "regimes and 200 bootstrap comparisons; no sample."
        ),
        "limitation": (
            "Monthly current-vintage research proxies; no intramonth loss, historical "
            "publication, instrument execution or future-return proof."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.source, args.run)
    except Exception as exc:
        failure = {
            "status": "FAIL",
            "checked_utc": datetime.now(UTC).isoformat(),
            "error": type(exc).__name__ + ": " + str(exc),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
        raise
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "accounts": result["accounts"]}), flush=True)


if __name__ == "__main__":
    main()
