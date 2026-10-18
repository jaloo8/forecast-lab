"""Offline screen of published French portfolios, not stock-level execution."""

import argparse
import hashlib
import io
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd


def load_monthly(path: Path) -> pd.DataFrame:
    """Read the first monthly block; decimal returns indexed by monthly Period."""
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    start = next(i for i, line in enumerate(lines) if re.match(r"^\s*\d{6},", line))
    end = start
    while end < len(lines) and re.match(r"^\s*\d{6},", lines[end]):
        end += 1
    frame = pd.read_csv(io.StringIO("\n".join(lines[start - 1 : end])), index_col=0)
    frame.columns = frame.columns.str.strip()
    frame.index = pd.PeriodIndex(pd.to_datetime(frame.index.astype(str), format="%Y%m"), freq="M")
    expected = pd.period_range(frame.index[0], frame.index[-1], freq="M")
    if not frame.index.equals(expected):
        raise ValueError("Duplicate, unordered or missing monthly observations")
    if not np.isfinite(frame.to_numpy()).all() or frame.isin([-99.99, -999]).any().any():
        raise ValueError("Missing or nonfinite research returns")
    if (frame < -100).any().any():
        raise ValueError("Impossible long-only monthly return")
    return frame / 100


def summarize(
    returns: pd.Series, market: pd.Series, annual_drag: float
) -> tuple[dict[str, float | int], pd.Series]:
    """Compound published returns with a hypothetical annual NAV drag."""
    if (
        len(returns) == 0
        or len(returns) % 12
        or returns.index[0].month != 1
        or returns.index[-1].month != 12
        or not returns.index.equals(market.index)
        or not returns.index.equals(pd.period_range(returns.index[0], returns.index[-1], freq="M"))
        or not 0 <= annual_drag < 1
        or not np.isfinite(returns.to_numpy()).all()
        or not np.isfinite(market.to_numpy()).all()
        or (returns < -1).any()
    ):
        raise ValueError("Require complete matching calendar years and valid returns/drag")
    gross = (1 + returns) * (1 - annual_drag) ** (1 / 12)
    annual = gross.groupby(gross.index.year).prod() - 1
    benchmark = (1 + market).groupby(market.index.year).prod() - 1
    wealth = np.r_[1.0, gross.cumprod().to_numpy()]
    metrics: dict[str, float | int] = {
        "cagr": float(wealth[-1] ** (12 / len(returns)) - 1),
        "worst_year": float(annual.min()),
        "best_year": float(annual.max()),
        "latest_year": float(annual.iloc[-1]),
        "max_month_end_drawdown": float((wealth / np.maximum.accumulate(wealth) - 1).min()),
        "positive_years": int((annual > 0).sum()),
        "years_ge_10pct": int((annual >= 0.1).sum()),
        "years_ge_20pct": int((annual >= 0.2).sum()),
        "years_beating_gross_market": int((annual > benchmark).sum()),
    }
    for first in range(int(annual.index[0]), int(annual.index[-1]) + 1, 5):
        block = annual.loc[first : first + 4]
        metrics[f"cagr_{first}_{int(block.index[-1])}"] = float(
            (1 + block).prod() ** (1 / len(block)) - 1
        )
    return metrics, annual


def run(root: Path, output: Path) -> None:
    manifest = json.loads((root / "manifest.json").read_text())
    frames = {}
    for item in manifest["files"]:
        path = root / item["csv"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["csv_sha256"]:
            raise ValueError(f"Input hash mismatch: {path.name}")
        frames[item["file"]] = load_monthly(path).loc["2006-01":"2025-12"]
    factors = frames["F-F_Research_Data_Factors_CSV.zip"]
    market = factors["Mkt-RF"] + factors["RF"]
    series = {"market": market}
    for family, name in {
        "value": "6_Portfolios_2x3_CSV.zip",
        "profitability": "6_Portfolios_ME_OP_2x3_CSV.zip",
        "momentum": "6_Portfolios_ME_Prior_12_2_CSV.zip",
        "reversal": "6_Portfolios_ME_Prior_1_0_CSV.zip",
    }.items():
        frame = frames[name]
        if len(frame.columns) != 6:
            raise ValueError("Expected six portfolios in small-low through big-high order")
        for rank, column in zip(["low", "middle", "high"], frame.columns[3:], strict=True):
            if not column.startswith(("BIG ", "ME2 ")):
                raise ValueError("Expected Big size portfolio columns")
            series[f"{family}_{rank}"] = frame[column]
    rows, annuals = [], {}
    for name, returns in series.items():
        if len(returns) != 240:
            raise ValueError("Require all 240 months in 2006-2025")
        for drag in (0.0, 0.01, 0.02):
            metrics, annual = summarize(returns, market, drag)
            rows.append({"portfolio": name, "annual_nav_drag": drag, **metrics})
            annuals[f"{name}_drag{drag:.2f}"] = annual
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output / "metrics.csv", index=False, lineterminator="\n")
    pd.DataFrame(annuals).to_csv(output / "annual.csv", index_label="year", lineterminator="\n")
    print(pd.DataFrame(rows).query("annual_nav_drag == 0").to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.input, args.output)
