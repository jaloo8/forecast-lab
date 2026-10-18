"""Offline registered sector portfolios; no provider calls or paper-ledger writes."""

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

SYMBOLS = ("SPY", "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY")


def load_bars(archive: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return adjusted symbol/session_date/open/close rows plus verified provenance."""
    frames, sources = [], []
    with zipfile.ZipFile(archive) as zipped:
        provenance = json.loads(
            archive_tools.verified(
                zipped, archive_tools.PROVENANCE, archive_tools.PROVENANCE_SHA256
            )
        )
        pointer = "research/millennium_study/data/latest.json"
        frozen = provenance["data"][pointer]
        snapshot = archive_tools.member_path(frozen["snapshot"])
        if not snapshot.startswith(pointer.removesuffix("latest.json") + "raw/"):
            raise ValueError("Snapshot outside expected source root")
        actual = json.loads(
            archive_tools.verified(zipped, "Tester/" + pointer, frozen["pointer_sha256"])
        )
        if actual["snapshot"] != snapshot:
            raise ValueError("Snapshot pointer mismatch")
        manifest = json.loads(
            archive_tools.verified(
                zipped, "Tester/" + snapshot + "/manifest.json", frozen["manifest_sha256"]
            )
        )
        for symbol in SYMBOLS:
            meta = manifest["files"][symbol]
            member = "Tester/" + snapshot + "/" + archive_tools.member_path(meta["file"])
            raw = archive_tools.verified(zipped, member, meta["sha256"])
            frame = pd.read_csv(io.BytesIO(raw))
            values = frame[["Open", "High", "Low", "Close", "Adj Close"]].to_numpy(float)
            dates = pd.to_datetime(frame.Date, errors="raise")
            if (
                not np.isfinite(values).all()
                or (values <= 0).any()
                or dates.isna().any()
                or dates.duplicated().any()
                or not dates.is_monotonic_increasing
            ):
                raise ValueError(f"Invalid prices/dates: {symbol}")
            if (frame.High < frame[["Open", "Low", "Close"]].max(axis=1)).any() or (
                frame.Low > frame[["Open", "High", "Close"]].min(axis=1)
            ).any():
                raise ValueError(f"Inconsistent OHLC: {symbol}")
            factor = frame["Adj Close"] / frame.Close
            bars = pd.DataFrame(
                {
                    "symbol": symbol,
                    "session_date": dates,
                    "open": frame.Open * factor,
                    "close": frame["Adj Close"],
                }
            )
            frames.append(bars[dates.between("2004-01-01", "2025-12-31")])
            sources.append({"symbol": symbol, **meta})
    return pd.concat(frames, ignore_index=True), {
        "provenance_sha256": archive_tools.PROVENANCE_SHA256,
        "frozen": frozen,
        "sources": sources,
        "manifest": {k: v for k, v in manifest.items() if k != "files"},
    }


def metrics(daily: pd.DataFrame) -> dict[str, Any]:
    """Aggregate complete account paths, never overlapping mean cohort returns."""
    nav = pd.Series(daily.nav.to_numpy(float), index=pd.DatetimeIndex(daily.session_date))
    endings = nav.groupby(nav.index.year).last()
    prior = endings.shift(1, fill_value=10000.0)
    annual = endings / prior - 1
    values = np.r_[10000.0, nav.to_numpy()]
    monthly = nav.resample("ME").last()
    initial_date = nav.index[0].replace(day=1) - pd.Timedelta(days=1)
    monthly = pd.concat([pd.Series([10000.0], index=[initial_date]), monthly])
    rolling = (monthly / monthly.shift(12) - 1).dropna()
    return {
        "cagr": float((nav.iloc[-1] / 10000) ** (1 / len(annual)) - 1),
        "mean_annual": float(annual.mean()),
        "ending_wealth": float(nav.iloc[-1]),
        "max_drawdown": float((values / np.maximum.accumulate(values) - 1).min()),
        "worst_year": float(annual.min()),
        "best_year": float(annual.max()),
        "positive_years": int((annual > 0).sum()),
        "years_ge_10pct": int((annual >= 0.1).sum()),
        "years_ge_20pct": int((annual >= 0.2).sum()),
        "rolling12_min": float(rolling.min()) if len(rolling) else None,
        "rolling12_max": float(rolling.max()) if len(rolling) else None,
        "annual": {int(k): float(v) for k, v in annual.items()},
    }


def run_study(archive: Path, output: Path) -> None:
    """Save all 15 scenarios and immutable evidence into a new local directory."""
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    from kq.equities.sector_study import STRATEGIES, simulate_portfolio  # noqa: PLC0415

    bars, metadata = load_bars(archive)
    output.mkdir(parents=True, exist_ok=False)
    summaries, annual_rows, blocks = [], [], []
    for cost in (10, 25, 50):
        for strategy in STRATEGIES:
            daily, ledger = simulate_portfolio(bars, strategy, cost)
            name = f"{strategy}_c{cost}"
            daily.to_csv(output / f"{name}_daily.csv", index=False)
            ledger.to_csv(output / f"{name}_ledger.csv", index=False)
            result = metrics(daily)
            annual = result.pop("annual")
            if set(annual) != set(range(2006, 2026)) or len(daily) != 5031:
                raise ValueError("Incomplete registered evaluation window")
            result.update(
                strategy=strategy,
                cost_bps=cost,
                total_fees=float(ledger.cost.sum()),
                rebalances=int(ledger.reason.eq("rebalance").sum()),
            )
            summaries.append(result)
            annual_rows.extend(
                {"strategy": strategy, "cost_bps": cost, "year": year, "return": value}
                for year, value in annual.items()
            )
            for start in (2006, 2011, 2016, 2021):
                block = float(np.prod([1 + annual[y] for y in range(start, start + 5)]) ** 0.2 - 1)
                blocks.append(
                    {
                        "strategy": strategy,
                        "cost_bps": cost,
                        "period": f"{start}-{start + 4}",
                        "cagr": block,
                    }
                )
    annual_frame = pd.DataFrame(annual_rows)
    for row in summaries:
        sub = annual_frame[annual_frame.cost_bps.eq(row["cost_bps"])]
        benchmark = sub[sub.strategy.eq("spy_hold")].set_index("year")["return"]
        returns = sub[sub.strategy.eq(row["strategy"])].set_index("year")["return"]
        row["years_beating_spy"] = int((returns > benchmark).sum())
    pd.DataFrame(summaries).to_csv(output / "metrics.csv", index=False)
    annual_frame.pivot(index="year", columns=["strategy", "cost_bps"], values="return").to_csv(
        output / "annual.csv"
    )
    pd.DataFrame(blocks).pivot(
        index=["strategy", "cost_bps"], columns="period", values="cagr"
    ).to_csv(output / "blocks.csv")
    root = Path(__file__).resolve().parents[1]
    sources = [
        Path(__file__).resolve(),
        root / "scripts/run_directional_study.py",
        root / "src/kq/equities/sector_study.py",
        root / "docs/research/SECTOR-STRATEGY-PROTOCOL-2026-10-10.md",
    ]
    with archive.open("rb") as handle:
        metadata["archive_sha256"] = hashlib.file_digest(handle, "sha256").hexdigest()
    metadata.update(
        run_utc=datetime.now(UTC).isoformat(),
        code_protocol_sha256={
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
        },
        output_sha256={
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.glob("*.csv"))
        },
        input_rows=len(bars),
        evaluation_sessions=5031,
        limitations=(
            "Exploratory current-vintage adjusted wealth proxies; fixed surviving sector funds; "
            "prior examined history; zero-yield cash; no tax; no guaranteed annual floor "
            "or individual-stock alpha."
        ),
    )
    (output / "manifest.json").write_text(
        json.dumps(metadata, indent=2, allow_nan=False), encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run_study(args.archive, args.output)
