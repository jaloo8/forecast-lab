"""Acquire/resume ONE explicitly approved pilot job; fresh credit evidence required."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from kq.clients.databento_batch import BatchClient
from kq.clients.databento_metadata import MetadataClient, load_key
from kq.equities.options_cache import CreditSnapshot, OptionsCache, Request


def request_from_receipt(item: dict[str, Any]) -> Request:
    params = item["params"]
    return Request(
        params["dataset"],
        params["schema"],
        tuple(params["symbols"].split(",")),
        datetime.fromisoformat(item["requested_start"]),
        datetime.fromisoformat(item["requested_end"]),
        params["stype_in"],
        "instrument_id",
        "csv",
        "pilot-v1",
        "raw",
        "original",
    )


def validate_job(request: Request, details: dict[str, Any]) -> None:
    expected = {
        "dataset": request.dataset,
        "schema": request.schema,
        "encoding": "csv",
        "stype_in": request.stype_in,
        "stype_out": request.stype_out,
        "pretty_px": True,
        "pretty_ts": True,
        "map_symbols": True,
        "limit": None,
    }
    if any(k not in details or details[k] != v for k, v in expected.items()):
        raise ValueError("Vendor job parameters differ from reserved request")
    if details["compression"] not in {None, "none"}:
        raise ValueError("Unexpected compression")
    if tuple(sorted(details["symbols"].split(","))) != request.symbols:
        raise ValueError("Wrong job symbols")
    if (
        datetime.fromisoformat(details["start"]) != request.start
        or datetime.fromisoformat(details["end"]) != request.end
    ):
        raise ValueError("Wrong job time bounds")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--credit-evidence", type=Path, required=True)
    parser.add_argument("--submit-approved", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = arguments()
    plan = json.loads(args.plan.read_text(encoding="utf-8-sig"))["requests"]
    if len(plan) != 7 or not 0 <= args.index < len(plan):
        raise ValueError("Expected one of the seven approved pilot requests")
    request = request_from_receipt(plan[args.index])
    key = load_key(args.credentials)
    receipts = args.root / "runs" / request.key
    receipts.mkdir(parents=True, exist_ok=True)

    def save(name: str, value: object) -> None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        (receipts / f"{stamp}-{name}.json").write_text(
            json.dumps(value, indent=2, allow_nan=False), encoding="utf-8"
        )

    with OptionsCache(args.root, budget=Decimal("85")) as cache, BatchClient(key) as client:
        try:
            job = cache.job(request.key)
        except ValueError:
            job = None
        if job is None:
            if not args.submit_approved:
                raise ValueError("No existing job: explicit submit approval required") from None
            evidence = json.loads(args.credit_evidence.read_text(encoding="utf-8-sig"))
            if evidence.get("cash_budget_usd") != "0" or not evidence.get("license_evidence"):
                raise ValueError("Zero-cash authorization and license evidence required")
            credits = CreditSnapshot(
                Decimal(evidence["available"]),
                datetime.fromisoformat(evidence["observed_at"]),
                datetime.fromisoformat(evidence["expires_at"]),
                evidence.get("verified") is True,
            )
            with MetadataClient(key) as metadata:
                estimate = metadata.estimate(
                    dataset=request.dataset,
                    schema=request.schema,
                    symbols=list(request.symbols),
                    stype_in=request.stype_in,
                    start=request.start.isoformat(),
                    end=request.end.isoformat(),
                )
            save("estimate", estimate)
            if Decimal(estimate["estimated_usd"]) > Decimal("0.50"):
                raise ValueError("Pilot estimate changed: stop before spending")
            result = client.submit(cache, request, Decimal("1"), credits)
            save("submission", {k: v for k, v in result.items() if k not in {"api_key", "user_id"}})
            job = cache.job(request.key)
        if job.state == "complete":
            cached_paths = cache.local_files(request)
            print(
                json.dumps(
                    {
                        "state": "cached",
                        "job_id": job.job_id,
                        "files": len(cached_paths),
                        "cost": str(job.actual_cost),
                    }
                )
            )
            return
        if job.job_id is None:
            raise ValueError("Uncertain submission: reconcile existing vendor job; do not resubmit")
        details = client.details(job.job_id)
        save("details", {k: v for k, v in details.items() if k not in {"api_key", "user_id"}})
        if details["state"] != "done":
            print(json.dumps({"state": details["state"], "job_id": job.job_id}))
            return
        validate_job(request, details)
        manifest = client.files(job.job_id)
        save("vendor-manifest", manifest)
        files = tuple(client.download(f, receipts / "delivery") for f in manifest)
        evidence = json.loads(args.credit_evidence.read_text(encoding="utf-8-sig"))
        cache.import_files(
            request.key,
            files,
            complete=True,
            actual_cost=Decimal(str(details["cost_usd"])),
            license_evidence=evidence["license_evidence"],
            conditions=json.dumps(
                {"job": job.job_id, "record_count": details["record_count"], "manifest": manifest}
            ),
        )
        print(
            json.dumps(
                {
                    "state": "complete",
                    "job_id": job.job_id,
                    "cost": details["cost_usd"],
                    "records": details["record_count"],
                }
            )
        )


if __name__ == "__main__":
    main()
