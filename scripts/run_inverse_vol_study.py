"""Offline allocation-only comparison using the original sector study accounting."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scripts.run_sector_study import load_bars, metrics

from kq.equities.sector_study import INVVOL_STRATEGIES, STRATEGIES, simulate_portfolio


def summarize(daily: pd.DataFrame, ledger: pd.DataFrame) -> dict[str, Any]:
    """Original metrics plus zero-RF daily ratio, fees and NAV-normalized turnover."""
    returns = np.diff(np.r_[10000.0, daily.nav]) / np.r_[10000.0, daily.nav[:-1]]
    volatility = float(returns.std(ddof=1))
    turnover = float((ledger.turnover / ledger.pre_nav).sum())
    return {
        **metrics(daily),
        "total_fees": float(ledger.cost.sum()),
        "turnover_nav": turnover,
        "annual_turnover_nav": turnover / 20,
        "sharpe_zero_rf": float(returns.mean() / volatility * np.sqrt(252)) if volatility else None,
    }


def paired(frame: pd.DataFrame, keys: list[str], value: str) -> pd.DataFrame:
    """Match variant to original at identical cost/period; delta = variant - original."""
    variants = frame[frame.strategy.isin(INVVOL_STRATEGIES)].copy()
    variants["strategy"] = variants.strategy.str.removesuffix("_invvol")
    result = variants.merge(
        frame, on=["strategy", *keys], suffixes=("_invvol", "_original"), validate="one_to_one"
    )
    result["delta"] = result[value + "_invvol"] - result[value + "_original"]
    return result


def run_study(archive: Path, output: Path, baseline: Path) -> None:
    """Save all 24 scenarios, validate original paths, and retain frozen provenance."""
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    root = Path(__file__).resolve().parents[1]
    protocol = root / "docs/research/INVERSE-VOLATILITY-2026-10-18.md"
    frozen_protocol = protocol.read_bytes()
    bars, metadata = load_bars(archive)
    output.mkdir(parents=True, exist_ok=False)
    (output / "protocol.md").write_bytes(frozen_protocol)
    summaries, blocks, verified = [], [], []
    annual_rows: list[dict[str, Any]] = []
    sessions = None
    for cost in (10, 25, 50):
        for strategy in STRATEGIES + INVVOL_STRATEGIES:
            daily, ledger = simulate_portfolio(bars, strategy, cost)
            if sessions is None:
                sessions = daily.session_date.copy()
            pd.testing.assert_series_equal(daily.session_date, sessions, check_exact=True)
            result = summarize(daily, ledger)
            annual = result.pop("annual")
            if len(daily) != 5031 or set(annual) != set(range(2006, 2026)):
                raise ValueError("Incomplete frozen evaluation window")
            for kind, frame in (("daily", daily), ("ledger", ledger)):
                name = f"{strategy}_c{cost}_{kind}.csv"
                frame.to_csv(output / name, index=False)
                if strategy in STRATEGIES:
                    if (output / name).read_bytes() != (baseline / name).read_bytes():
                        raise ValueError(f"Original output changed: {name}")
                    verified.append(name)
            summaries.append({"strategy": strategy, "cost_bps": cost, **result})
            annual_rows.extend(
                {"strategy": strategy, "cost_bps": cost, "year": year, "return": value}
                for year, value in annual.items()
            )
            for start in (2006, 2011, 2016, 2021):
                blocks.append(
                    {
                        "strategy": strategy,
                        "cost_bps": cost,
                        "period": f"{start}-{start + 4}",
                        "cagr": np.prod([1 + annual[y] for y in range(start, start + 5)]) ** 0.2
                        - 1,
                    }
                )
    annual_frame, block_frame = pd.DataFrame(annual_rows), pd.DataFrame(blocks)
    for name, frame in {
        "metrics": pd.DataFrame(summaries),
        "annual": annual_frame,
        "blocks": block_frame,
        "annual_paired": paired(annual_frame, ["cost_bps", "year"], "return"),
        "blocks_paired": paired(block_frame, ["cost_bps", "period"], "cagr"),
    }.items():
        frame.to_csv(output / f"{name}.csv", index=False)
    sources = [
        Path(__file__),
        root / "src/kq/equities/sector_study.py",
        root / "scripts/run_sector_study.py",
        root / "scripts/run_directional_study.py",
    ]
    with archive.open("rb") as handle:
        metadata["archive_sha256"] = hashlib.file_digest(handle, "sha256").hexdigest()
    metadata.update(
        run_utc=datetime.now(UTC).isoformat(),
        evaluation_sessions=5031,
        original_files_byte_identical=verified,
        protocol_sha256=hashlib.sha256(frozen_protocol).hexdigest(),
        source_sha256={
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
        },
        output_sha256={
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.glob("*.csv"))
        },
        limitations="All history previously viewed; exploratory; current-vintage adjusted prices; "
        "fixed surviving ETFs; zero-yield cash; zero-RF ratio; no taxes or holdout.",
    )
    (output / "manifest.json").write_text(
        json.dumps(metadata, indent=2, allow_nan=False), encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/inverse-vol-20261018"))
    parser.add_argument("--baseline", type=Path, default=Path("data/audit-20261018/sector-rerun"))
    args = parser.parse_args()
    run_study(args.archive, args.output, args.baseline)
