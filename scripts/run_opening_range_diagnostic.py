"""Replay the frozen underlying signal from a hashed Yahoo minute capture."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from kq.equities.opening_range import underlying_diagnostic


def run(capture: Path, receipt_path: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError("Refuse to overwrite research evidence")
    raw = capture.read_bytes()
    receipt = json.loads(receipt_path.read_text())
    if hashlib.sha256(raw).hexdigest() != receipt["sha256"]:
        raise ValueError("Source hash mismatch")
    source = json.loads(raw)["chart"]["result"][0]
    if source["meta"]["symbol"] != "SPY" or source["meta"]["currency"] != "USD":
        raise ValueError("Wrong source identity")
    dates = pd.to_datetime(source["timestamp"], unit="s", utc=True)
    retrieved = pd.Timestamp(receipt["retrieved_at"])
    if retrieved.tz is None or (dates + pd.Timedelta(minutes=1) > retrieved).any():
        raise ValueError("Uncompleted or future source bars")
    bars = pd.DataFrame(source["indicators"]["quote"][0], index=dates)
    result = underlying_diagnostic(bars)
    scored = result.loc[result.status.eq("underlying_only")]
    summary = {
        "status": "underlying_only_not_options",
        "source": receipt,
        "counts": result.status.value_counts().to_dict(),
        "sessions": result.session.tolist(),
        "trades": len(scored),
        "mean_raw_return": float(scored.raw_return.mean()) if len(scored) else None,
        "mean_net_5bp": float(scored.net_5bp.mean()) if len(scored) else None,
        "wins_raw": int(scored.raw_return.gt(0).sum()) if len(scored) else 0,
        "limitations": [
            "No option prices or listed-chain eligibility",
            "No annualized performance or independent holdout",
            "Full-session coverage checked only within supplied dates",
        ],
    }
    output.mkdir(parents=True)
    result.to_csv(output / "underlying-diagnostic.csv", index=False)
    (output / "results.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.capture, args.receipt, args.output)
