"""Rescreen preserved QuantLab annual results; do not relabel this as new backtests."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

STUDIES = {"high_return_study": 980, "timing_study": 2100, "combo_study": 288}


def screen(row: dict[str, Any]) -> dict[str, Any]:
    start, end = date.fromisoformat(row["start"]), date.fromisoformat(row["end"])
    first = start.year + (start.month != 1 or start.day != 1)
    last = end.year - (end.month != 12 or end.day != 31)
    expected = list(range(first, last + 1))
    annual = row["calendar_years"]
    if not expected or [v["year"] for v in annual] != expected:
        raise ValueError("Annual results do not cover exactly the complete calendar years")
    returns = [float(v["return"]) for v in annual]
    if any(not math.isfinite(v) or v < -1 for v in returns):
        raise ValueError("Invalid annual return")
    result = {
        key: row[key]
        for key in (
            "strategy",
            "family",
            "leverage",
            "case",
            "derived_prefix_not_additional_simulation",
            "scenario_id",
            "asset",
            "period",
            "policy",
            "cost_bps",
            "delay",
            "start",
            "end",
            "cagr",
            "max_drawdown",
            "ending_nav",
        )
        if key in row
    }
    result.update(
        complete_year_count=len(returns),
        worst_complete_year=min(returns),
        years_below_10=sum(v < 0.1 for v in returns),
        years_10_to_20=sum(0.1 <= v <= 0.2 for v in returns),
        years_above_20=sum(v > 0.2 for v in returns),
        losing_years=sum(v < 0 for v in returns),
        all_complete_years_at_least_10=all(v >= 0.1 for v in returns),
        at_least_ten_complete_years=len(returns) >= 10,
        annual_returns=[
            {"year": year, "return": value} for year, value in zip(expected, returns, strict=True)
        ],
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quantlab", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Choose a new output; preserve old audit evidence")
    output: dict[str, Any] = {
        "mode": "new_threshold_audit_of_preexisting_results_not_new_backtests",
        "as_of": datetime.now(UTC).isoformat(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "threshold": 0.1,
        "upper_reference": 0.2,
        "above_upper_is_not_rejected": True,
        "long_window_context": (
            "At least ten complete years; shorter-window passes are reported separately, "
            "never proof of annual reliability."
        ),
        "source_input_requirement": (
            "Separate owner-private QuantLab results; this repository does not contain "
            "the full underlying workspace."
        ),
        "limitations": [
            "Original data, accounting, selection and cost limitations carry forward unchanged.",
            "Some leverage histories are synthetic, not attainable fund records.",
            "Timing-study stocks are hindsight survivors, not a point-in-time universe.",
            "Training prefixes and overlapping windows are not independent observations.",
            "No original engine or input dataset is rerun; this audits archived annual rows.",
        ],
        "studies": {},
    }
    for study, expected in STUDIES.items():
        pointer = args.quantlab / "research" / study / "latest.json"
        run = args.quantlab / json.loads(pointer.read_text())["run"]
        source = run / "results.json"
        saved = json.loads(source.read_text())
        if len(saved["scenarios"]) != expected:
            raise ValueError("Study scope changed; review the registered audit inventory")
        rows = [screen(row) for row in saved["scenarios"]]
        long = [row for row in rows if row["at_least_ten_complete_years"]]
        output["studies"][study] = {
            "source_path": source.relative_to(args.quantlab).as_posix(),
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "scenario_count": len(rows),
            "long_window_scenarios": len(long),
            "long_window_passes": sum(row["all_complete_years_at_least_10"] for row in long),
            "short_window_passes": sum(
                row["all_complete_years_at_least_10"]
                for row in rows
                if not row["at_least_ten_complete_years"]
            ),
            "unavailable_preserved": saved.get("unavailable", []),
            "rows": rows,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                k: {
                    f: v[f]
                    for f in (
                        "scenario_count",
                        "long_window_scenarios",
                        "long_window_passes",
                        "short_window_passes",
                    )
                }
                for k, v in output["studies"].items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
