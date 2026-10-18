"""Offline registered cohorts; archive members are read as data, never extracted."""

import argparse
import hashlib
import io
import json
import sys
import zipfile
from datetime import UTC, datetime
from itertools import product
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
import pandas as pd

PROVENANCE = "Tester/research/timing_study/runs/20261007T165151049239Z/provenance.json"
PROVENANCE_SHA256 = "864e605b44217852f3602e491e614db98cd8dcf68b1a25e78d4153d3c18aa3ff"
POINTERS = (
    "research/millennium_study/data/latest.json",
    "research/timing_study/stock_data/latest.json",
)
STOCKS = ("AAPL", "MSFT", "INTC", "CSCO", "ORCL", "IBM", "NVDA", "AMZN", "GOOGL", "META", "TSLA")
PAIRS = [(r, h) for r in ("S20", "S5") for h in ("5s", "20s")] + [
    ("L12-1", h) for h in ("6m", "12m", "18m")
]
EPOCHS = {
    "2006-2012": ("2006-01-01", "2012-12-31"),
    "2013-2019": ("2013-01-01", "2019-12-31"),
    "2020-2025": ("2020-01-01", "2025-12-31"),
}
LIMITATIONS = (
    "Current-vintage adjusted Yahoo prices retrieved in 2026, not historical receipt vintages. "
    "Eleven preselected surviving stocks; survivorship and hindsight selection. "
    "Simulated as_of assumes 16:00 New York close, not original retrieval or early closes. "
    "Observed SPY sessions may omit exchange sessions. Adjusted opens proxy wealth, not fills. "
    "Every reported return is a hypothetical LONG cohort even for bearish signals; "
    "no short P&L, account CAGR, portfolio drawdown or avoidance-policy claim. "
    "Overlapping cohorts, names and cost trials are dependent; no strategy is promoted. "
    "Qualification indicates outcome coverage only; unavailable/pending outcomes prevent it."
)


def member_path(name: str) -> str:
    if (
        not name
        or "\\" in name
        or ":" in name
        or name.startswith("/")
        or any(part in {"", ".", ".."} for part in name.split("/"))
    ):
        raise ValueError(f"Unsafe archive member: {name!r}")
    return str(PurePosixPath(name))


def verified(zipped: zipfile.ZipFile, member: str, expected: str) -> bytes:
    member = member_path(member)
    if zipped.namelist().count(member) != 1:
        raise ValueError(f"Missing or duplicate archive member: {member}")
    raw = zipped.read(member)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f"SHA256 mismatch: {member}")
    return raw


def load_archive(archive: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    frames, sources = [], []
    with zipfile.ZipFile(archive) as zipped:
        provenance = json.loads(verified(zipped, PROVENANCE, PROVENANCE_SHA256))
        if set(provenance["data"]) != set(POINTERS):
            raise ValueError("Unexpected provenance pointers")
        for pointer, symbols in zip(POINTERS, [("SPY",), STOCKS], strict=True):
            frozen = provenance["data"][pointer]
            snapshot = member_path(frozen["snapshot"])
            if not snapshot.startswith(pointer.removesuffix("latest.json") + "raw/"):
                raise ValueError("Snapshot outside registered source root")
            actual = json.loads(verified(zipped, "Tester/" + pointer, frozen["pointer_sha256"]))
            if actual["snapshot"] != snapshot:
                raise ValueError("Pointer does not match frozen snapshot")
            manifest = json.loads(
                verified(zipped, "Tester/" + snapshot + "/manifest.json", frozen["manifest_sha256"])
            )
            if not set(symbols) <= set(manifest["files"]):
                raise ValueError("Frozen snapshot missing required symbol")
            for symbol in symbols:
                meta = manifest["files"][symbol]
                file = member_path(meta["file"])
                raw = verified(zipped, "Tester/" + snapshot + "/" + file, meta["sha256"])
                frame = pd.read_csv(io.BytesIO(raw))
                values = frame[["Open", "High", "Low", "Close", "Adj Close"]].to_numpy(float)
                if not np.isfinite(values).all() or (values <= 0).any():
                    raise ValueError(f"Invalid raw prices: {symbol}")
                if (frame.High < frame[["Open", "Close", "Low"]].max(axis=1)).any() or (
                    frame.Low > frame[["Open", "Close", "High"]].min(axis=1)
                ).any():
                    raise ValueError(f"Inconsistent raw OHLC: {symbol}")
                dates = pd.to_datetime(frame.Date, errors="raise")
                if (
                    dates.isna().any()
                    or dates.duplicated().any()
                    or not dates.is_monotonic_increasing
                ):
                    raise ValueError(f"Invalid session dates: {symbol}")
                bars = pd.DataFrame(
                    {
                        "symbol": symbol,
                        "session_date": dates,
                        "open": frame.Open * (frame["Adj Close"] / frame.Close),
                        "close": frame["Adj Close"],
                    }
                )
                frames.append(bars[dates.between("1997-01-01", "2025-12-31")])
                sources.append(
                    {
                        "symbol": symbol,
                        "pointer": pointer,
                        **frozen,
                        "file": file,
                        "price_sha256": meta["sha256"],
                        "retrieved_utc": meta.get("retrieved_utc"),
                        "manifest_metadata": {k: v for k, v in manifest.items() if k != "files"},
                    }
                )
    bars = pd.concat(frames, ignore_index=True)
    if set(bars.symbol) != {*STOCKS, "SPY"}:
        raise ValueError("No permitted-period prices for required symbol")
    return bars, {
        "provenance_member": PROVENANCE,
        "provenance_sha256": PROVENANCE_SHA256,
        "archive_source_sha256": provenance.get("source_sha256", {}),
        "sources": sources,
    }


def summarize(cohorts: pd.DataFrame, cost_bps: int) -> list[dict[str, Any]]:
    frame = cohorts.copy()
    signs = {"bearish": -1, "neutral": 0, "bullish": 1, "unscored": None}
    frame["signal_class"] = frame.signal.map({-1: "bearish", 0: "neutral", 1: "bullish"})
    frame.loc[frame.status.eq("excluded") | frame.signal.isna(), "signal_class"] = "unscored"
    frame["epoch"] = "unresolved"
    resolved = frame.exit_date.notna() & ~frame.status.isin(["pending", "excluded"])
    frame.loc[resolved, "epoch"] = "cross_boundary"
    for name, (start, end) in EPOCHS.items():
        inside = frame.decision_date.between(start, end) & frame.exit_date.between(start, end)
        frame.loc[resolved & inside, "epoch"] = name
    results = []
    for epoch in ["overall", *EPOCHS, "cross_boundary", "unresolved"]:
        subset = frame if epoch == "overall" else frame[frame.epoch == epoch]
        groups = subset.groupby(["rule", "horizon", "signal_class"], dropna=False)
        observed = {(r, h, s): g for (r, h, s), g in groups}
        keys = set(observed) | {(r, h, s) for (r, h), s in product(PAIRS, signs)}
        for rule, horizon, signal_class in sorted(keys, key=str):
            group = observed.get((rule, horizon, signal_class), subset.iloc[:0])
            complete = group[group.status == "complete"]
            counts = group.status.value_counts(dropna=False)
            row = {
                "rule": rule,
                "horizon": horizon,
                "signal": signs[signal_class],
                "signal_class": signal_class,
                "cost_bps": cost_bps,
                "epoch": epoch,
                "count": len(group),
                **{
                    s: int(counts.get(s, 0))
                    for s in ("complete", "excluded", "unavailable", "pending")
                },
                "reason_counts": {
                    str(k): int(v) for k, v in group.reason.value_counts(dropna=False).items()
                },
            }
            row["qualified"] = bool(len(complete) and not row["unavailable"] and not row["pending"])
            for label, column, operation in [
                ("mean_net_long_return", "net_return", "mean"),
                ("median_net_long_return", "net_return", "median"),
                ("worst_long_cohort", "net_return", "min"),
                ("mean_excess", "excess_vs_spy", "mean"),
                ("worst_excess", "excess_vs_spy", "min"),
                ("best_excess", "excess_vs_spy", "max"),
                ("absolute_hit_rate", "absolute_hit", "mean"),
                ("relative_hit_rate", "relative_hit", "mean"),
            ]:
                value = getattr(complete[column], operation)() if len(complete) else np.nan
                row[label] = float(value) if pd.notna(value) and np.isfinite(value) else None
            results.append(row)
    return results


def run_study(archive: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"Output must be a new directory: {output}")
    bars, metadata = load_archive(archive)
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    from kq.equities.directional_study import simulate_directional  # noqa: PLC0415

    output.mkdir(parents=True, exist_ok=False)
    summaries = []
    for cost in (10, 25, 50):
        cohorts = simulate_directional(bars, cost_bps=cost)
        cohorts.to_csv(output / f"cohorts_c{cost}.csv", index=False)
        summaries.extend(summarize(cohorts, cost))
    code_paths = [
        Path(__file__).resolve(),
        root / "src/kq/equities/directional_study.py",
        root / "docs/research/STOCK-DIRECTION-PROTOCOL-2026-10-10.md",
    ]
    with archive.open("rb") as source:
        metadata["archive_sha256"] = hashlib.file_digest(source, "sha256").hexdigest()
    metadata.update(
        {
            "run_utc": datetime.now(UTC).isoformat(),
            "limitations": LIMITATIONS,
            "untested_arms": ["earnings", "social/news", "economic relationships"],
            "code_protocol_sha256": {
                str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in code_paths
            },
            "cohort_sha256": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in output.glob("cohorts_*.csv")
            },
        }
    )
    (output / "summary.json").write_text(
        json.dumps({"metadata": metadata, "groups": summaries}, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    columns = list(summaries[0])
    lines = [
        "# Registered directional cohorts",
        "",
        LIMITATIONS,
        "",
        "Earnings, social/news and economic relationship arms: NOT TESTED.",
        "",
        "Neutral signals and unscored excluded decisions remain visible. "
        "Epochs require decision AND "
        "exit inside the block; cross_boundary and unresolved retain all other rows. "
        "Empty-group statistics are null. Full hashes/source clocks: summary.json.",
        "",
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in summaries:
        lines.append("| " + " | ".join(str(row[c]) for c in columns) + " |")
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run_study(args.archive, args.output)
