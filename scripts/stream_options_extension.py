"""Explicit bounded streaming acquisition; same $10 incremental reservation cap."""

import argparse
import json
import time
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from scripts.acquire_options_extension import credit_evidence, reserve_amount
from scripts.acquire_options_pilot import request_from_receipt

from kq.clients.databento_metadata import MetadataClient, load_key
from kq.clients.databento_stream import StreamClient, stream_params
from kq.equities.options_cache import OptionsCache


def run(args: argparse.Namespace) -> None:
    evidence, credits = credit_evidence(args)
    deadline = time.monotonic() + 240
    items = json.loads(args.plan.read_text())
    key = load_key(args.credentials)
    with OptionsCache(args.root, budget=Decimal("85")) as cache, StreamClient(key) as client:
        pilot = json.loads(args.pilot_plan.read_text())["requests"]
        if len(pilot) != 7 or any(
            cache.job(request_from_receipt(p).key).reserved_cost != Decimal("1") for p in pilot
        ):
            raise ValueError("Expected original $7 reservation baseline")
        for index, item in enumerate(items):
            aligned = dict(
                item, requested_start=item["params"]["start"], requested_end=item["params"]["end"]
            )
            request = request_from_receipt(aligned)
            request = replace(request, source_version=item.get("source_version", "original"))
            stream_params(request)
            try:
                job = cache.job(request.key)
            except ValueError:
                job = None
            if job:
                if job.state == "complete":
                    continue
                raise ValueError("Existing unresolved acquisition: resume/reconcile, do not stream")
            if time.monotonic() >= deadline:
                print(json.dumps({"state": "refresh_credit_evidence", "next": index}), flush=True)
                return
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
                count = metadata.get("metadata.get_record_count", estimate["params"])
            directory = args.root / "runs" / request.key
            directory.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
            (directory / f"{stamp}-stream-estimate.json").write_text(
                json.dumps({"estimate": estimate, "expected_records": count}, indent=2)
            )
            client.acquire(
                cache,
                request,
                reserve_amount(estimate["estimated_usd"]),
                credits,
                expected_records=count,
                estimate=Decimal(estimate["estimated_usd"]),
                license_evidence=evidence["license_evidence"],
            )
            print(
                json.dumps(
                    {
                        "state": "complete",
                        "index": index,
                        "total": len(items),
                        "metadata_cost": estimate["estimated_usd"],
                        "records": count,
                    }
                ),
                flush=True,
            )
    print(json.dumps({"state": "all_complete", "total": len(items)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "plan", "pilot-plan", "credentials", "credit-evidence"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--submit-approved", action="store_true")
    run(parser.parse_args())
