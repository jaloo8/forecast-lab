"""Inspect free metadata or price an explicit JSON plan; never fetch market data."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from kq.clients.databento_metadata import MetadataClient, load_key


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--plan", type=Path, help="JSON list of named, bounded estimate requests")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Receipt already exists; choose a new output path")
    report: dict[str, object] = {
        "as_of": datetime.now(UTC).isoformat(),
        "mode": "free_metadata_only",
        "data_jobs_submitted": 0,
        "market_data_downloaded": False,
        "credit_balance": "Not inspected by this API; verify in the account portal",
    }
    with MetadataClient(load_key(args.credentials)) as client:
        if args.plan is None:
            datasets = client.get("metadata.list_datasets")
            report["datasets"] = datasets
            report["coverage"] = {
                dataset: {
                    "range": client.get("metadata.get_dataset_range", {"dataset": dataset}),
                    "schemas": client.get("metadata.list_schemas", {"dataset": dataset}),
                }
                for dataset in ("OPRA.PILLAR", "DBEQ.BASIC", "EQUS.MINI", "XNAS.ITCH")
                if dataset in datasets
            }
        else:
            plan = json.loads(args.plan.read_text(encoding="utf-8-sig"))
            if not isinstance(plan, list) or not 1 <= len(plan) <= 100:
                raise ValueError("Plan must contain 1 to 100 explicit requests")
            estimates = []
            for entry in plan:
                request = dict(entry)
                name = request.pop("name")
                try:
                    estimates.append({"name": name, **client.estimate(**request)})
                except RuntimeError as exc:
                    estimates.append({"name": name, "status": "unpriced", "error": str(exc)})
            report["estimates"] = estimates
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=args.output.parent,
        delete=False,
    ) as out:
        json.dump(report, out, indent=2)
        out.flush()
        os.fsync(out.fileno())
        temporary = Path(out.name)
    temporary.replace(args.output)
    print(f"Free metadata receipt saved: {args.output}")
    print("No batch or time-series endpoint called.")


if __name__ == "__main__":
    main()
