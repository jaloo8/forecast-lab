"""Run the finite registered published-option-index analysis without network calls."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from kq.equities.option_benchmarks import analyze, load_levels


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(  # noqa: PLR0912 - finite manifest validation and preserved refusals
    protocol: Path, expected_sha: str, sources: Path, benchmark: Path, output: Path
) -> None:
    if sha(protocol) != expected_sha:
        raise ValueError("Registration hash mismatch")
    registration = json.loads(protocol.read_text(encoding="utf-8"))
    inventory_path = sources / "inventory.json"
    if sha(inventory_path) != registration["source_manifest_sha256"]:
        raise ValueError("Source manifest hash mismatch")
    if sha(benchmark) != registration["benchmark"]["sha256"]:
        raise ValueError("Benchmark hash mismatch")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    records = {x["ticker"]: x for x in inventory["sources"] if x["status"] == 200}
    if set(records) != set(registration["tickers"]):
        raise ValueError("Source universe differs from registration")
    inputs = {}
    for ticker, record in records.items():
        path = sources / f"{ticker}_History.csv"
        if sha(path) != record["sha256"]:
            raise ValueError("Index source hash mismatch")
        inputs[ticker] = load_levels(path, ticker)
    spy = load_levels(benchmark, "Adj Close", date_column="Date")
    output.mkdir(parents=True, exist_ok=False)
    results = []
    with (output / "fresh-starts.jsonl").open("w", encoding="utf-8") as stream:
        for ticker in registration["tickers"]:
            for name in registration["windows"]:
                for drag in registration["annual_cost_drags"]:
                    identity = {"ticker": ticker, "window": name, "annual_drag": drag}
                    try:
                        result = analyze(inputs[ticker], spy, name, drag)
                        for fresh in result["fresh_starts"]:
                            for trial in fresh.pop("trials"):
                                stream.write(
                                    json.dumps(
                                        {
                                            **identity,
                                            "horizon": fresh["horizon_observations"],
                                            **trial,
                                        },
                                        allow_nan=False,
                                    )
                                    + "\n"
                                )
                        results.append({**identity, "status": "completed", **result})
                    except ValueError as error:
                        results.append({**identity, "status": "refused", "reason": str(error)})
    if len(results) != registration["scenarios"]:
        raise ValueError("Scenario count differs from registration")
    summary = {
        "study": registration["study"],
        "evidence_level": registration["evidence_level"],
        "registration_sha256": expected_sha,
        "scenarios": len(results),
        "results": results,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    root = Path(__file__).resolve().parents[1]
    manifest = {
        "registration_sha256": expected_sha,
        "source_inventory_sha256": sha(inventory_path),
        "benchmark_sha256": sha(benchmark),
        "implementation": {
            str(p.relative_to(root)): sha(p)
            for p in [root / "src/kq/equities/option_benchmarks.py", Path(__file__).resolve()]
        },
        "outputs": {p.name: sha(p) for p in output.iterdir() if p.is_file()},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "scenarios": len(results),
                "completed": sum(x["status"] == "completed" for x in results),
                "output": str(output),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--registration-sha256", required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    run(
        arguments.protocol,
        arguments.registration_sha256,
        arguments.sources,
        arguments.benchmark,
        arguments.output,
    )
