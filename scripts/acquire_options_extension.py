"""Resume serial SPY jobs under the explicitly approved additional $10 credit cap."""

import argparse
import json
import time
from datetime import UTC, datetime
from decimal import ROUND_UP, Decimal
from pathlib import Path

from scripts.acquire_options_pilot import request_from_receipt, validate_job

from kq.clients.databento_batch import BatchClient
from kq.clients.databento_metadata import MetadataClient, load_key
from kq.equities.options_cache import CreditSnapshot, OptionsCache


def reserve_amount(estimate: str) -> Decimal:
    amount = Decimal(estimate)
    if not amount.is_finite() or amount < 0:
        raise ValueError("Invalid cost estimate")
    return (amount * Decimal("1.12") + Decimal("0.0001")).quantize(
        Decimal("0.0001"), rounding=ROUND_UP
    )


def credit_evidence(args: argparse.Namespace) -> tuple[dict, CreditSnapshot]:
    if not args.submit_approved:
        raise ValueError("Explicit extension approval required")
    evidence = json.loads(args.credit_evidence.read_text(encoding="utf-8-sig"))
    if evidence.get("cash_budget_usd") != "0" or evidence.get("additional_cap_usd") != "10":
        raise ValueError("Expected $10 additional credits and $0 cash authorization")
    credits = CreditSnapshot(
        Decimal(evidence["available"]),
        datetime.fromisoformat(evidence["observed_at"]),
        datetime.fromisoformat(evidence["expires_at"]),
        evidence.get("verified") is True,
        deduct_imports=True,
    )
    return evidence, credits


def wait_done(client: BatchClient, job_id: str, deadline: float) -> dict | None:
    while True:
        details = client.details(job_id)
        if details["state"] == "done":
            return details
        if details["state"] not in {"queued", "processing", "received"}:
            raise ValueError(f"Unexpected job state: {details['state']}")
        if time.monotonic() >= deadline:
            print(json.dumps({"state": details["state"], "job_id": job_id}), flush=True)
            return None
        time.sleep(2)


def run(args: argparse.Namespace) -> None:
    evidence, credits = credit_evidence(args)
    items = json.loads(args.plan.read_text(encoding="utf-8-sig"))
    key = load_key(args.credentials)
    deadline = time.monotonic() + 240
    with OptionsCache(args.root, budget=Decimal("85")) as cache, BatchClient(key) as client:
        pilot = json.loads(args.pilot_plan.read_text())["requests"]
        if len(pilot) != 7 or any(
            cache.job(request_from_receipt(p).key).reserved_cost != Decimal("1") for p in pilot
        ):
            raise ValueError("Expected original $7 cumulative reservation baseline")
        for index, item in enumerate(items):
            request = request_from_receipt(item)
            try:
                job = cache.job(request.key)
            except ValueError:
                job = None
            if job and job.state == "complete":
                continue
            if time.monotonic() >= deadline:
                print(json.dumps({"state": "refresh_credit_evidence", "next": index}), flush=True)
                return
            receipts = args.root / "runs" / request.key
            receipts.mkdir(parents=True, exist_ok=True)

            def save(name: str, value: object, directory: Path = receipts) -> None:
                stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
                (directory / f"{stamp}-{name}.json").write_text(json.dumps(value, indent=2))

            if job is None:
                credits.validate(Decimal("0"), datetime.now(UTC))
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
                result = client.submit(
                    cache,
                    request,
                    reserve_amount(estimate["estimated_usd"]),
                    credits,
                    extension=True,
                )
                save(
                    "submission",
                    {k: v for k, v in result.items() if k not in {"api_key", "user_id"}},
                )
                job = cache.job(request.key)
            if job.job_id is None:
                raise ValueError("Uncertain submission; reconcile vendor job without resubmitting")
            details = wait_done(client, job.job_id, deadline)
            if details is None:
                return
            validate_job(request, details)
            save("details", {k: v for k, v in details.items() if k not in {"api_key", "user_id"}})
            manifest = client.files(job.job_id)
            save("vendor-manifest", manifest)
            files = tuple(client.download(f, receipts / "delivery") for f in manifest)
            actual = Decimal(str(details["cost_usd"]))
            cache.import_files(
                request.key,
                files,
                complete=True,
                actual_cost=actual,
                license_evidence=evidence["license_evidence"],
                conditions=json.dumps({"record_count": details["record_count"]}),
            )
            print(
                json.dumps(
                    {
                        "state": "complete",
                        "index": index,
                        "total": len(items),
                        "cost": str(actual),
                        "records": details["record_count"],
                    }
                ),
                flush=True,
            )
            if actual > job.reserved_cost:
                raise ValueError("Actual cost exceeded reservation; stop and reconcile")
    print(json.dumps({"state": "all_complete", "total": len(items)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "plan", "pilot-plan", "credentials", "credit-evidence"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--submit-approved", action="store_true")
    run(parser.parse_args())
