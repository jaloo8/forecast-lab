"""Recover retained SPY research batches with GET only; never purchase replacements."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kq.clients.databento_batch import BatchClient
from kq.clients.databento_metadata import load_key


def sanitized(value: Any) -> Any:
    """Retain request provenance without persisting account or credential fields."""
    private_fields = {
        "api_key",
        "user_id",
        "team_id",
        "account_id",
        "email",
        "authorization",
        "password",
        "token",
        "access_token",
        "secret",
    }
    if isinstance(value, dict):
        return {
            key: sanitized(item) for key, item in value.items() if key.lower() not in private_fields
        }
    if isinstance(value, list):
        return [sanitized(item) for item in value]
    return value


def eligible(job: dict[str, Any]) -> bool:
    """Restrict recovery to the owner's existing SPY pilot/extension data."""
    symbols = job.get("symbols")
    if isinstance(symbols, str):
        symbols = symbols.split(",")
    if not isinstance(symbols, list) or not symbols:
        return False
    if job.get("state") != "done" or job.get("encoding") != "csv":
        return False
    if job.get("dataset") == "EQUS.MINI":
        return job.get("schema") == "ohlcv-1m" and symbols == ["SPY"]
    return (
        job.get("dataset") == "OPRA.PILLAR"
        and job.get("schema") in {"definition", "cmbp-1"}
        and all(isinstance(s, str) and (s == "SPY.OPT" or s.startswith("SPY   ")) for s in symbols)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--since", default="2026-10-18T00:00:00+00:00")
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Choose a new recovery evidence directory")
    args.output.mkdir(parents=True)
    report: dict[str, Any] = {
        "as_of": datetime.now(UTC).isoformat(),
        "mode": "retained_batch_recovery_get_only",
        "new_jobs_submitted": 0,
        "new_acquisition_charges_usd": "0",
        "original_catalog_reconstructed": False,
        "stream_downloads_recovered": False,
        "jobs": [],
    }
    with BatchClient(load_key(args.credentials)) as client:
        jobs = sanitized(client.list_jobs(datetime.fromisoformat(args.since)))
        (args.output / "job-list.json").write_text(json.dumps(jobs, indent=2), encoding="utf-8")
        for listed in jobs:
            job = sanitized(client.details(listed["id"]))
            directory = args.output / job["id"]
            directory.mkdir()
            (directory / "job-details.json").write_text(json.dumps(job, indent=2), encoding="utf-8")
            row: dict[str, Any] = {
                "id": job["id"],
                "state": job.get("state"),
                "dataset": job.get("dataset"),
                "schema": job.get("schema"),
                "start": job.get("start"),
                "end": job.get("end"),
                "original_cost_usd": job.get("cost_usd"),
                "record_count": job.get("record_count"),
                "eligible": eligible(job),
                "files": [],
            }
            if row["eligible"]:
                files = client.files(job["id"])
                (directory / "vendor-files.json").write_text(
                    json.dumps(files, indent=2), encoding="utf-8"
                )
                for meta in files:
                    receipt = {k: meta[k] for k in ("filename", "size", "hash")}
                    receipt["verified_download"] = False
                    if args.download:
                        raw = client.download(meta, directory / "files")
                        raw.verify()
                        receipt["verified_download"] = True
                    row["files"].append(receipt)
            report["jobs"].append(row)
            (args.output / "recovery.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
            print(
                json.dumps({k: row[k] for k in ("id", "state", "schema", "eligible")}), flush=True
            )
    report["completed"] = True
    (args.output / "recovery.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        f"Existing jobs inspected: {len(jobs)}. New submissions: 0. "
        f"Receipt: {args.output / 'recovery.json'}"
    )


if __name__ == "__main__":
    main()
