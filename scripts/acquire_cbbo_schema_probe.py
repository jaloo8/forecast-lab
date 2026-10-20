"""Inspect/quote the fixed CBBO schema plan; submission requires explicit flags.

Default: nine free estimates only. --offline needs no key or network.
--resume only reuses a recorded job/cache. --submit-approved submits ONE index,
after fresh full-plan quotes and exact verified/reconciled zero-cash evidence.
Use the same private --root on every invocation; never replace its catalog.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from kq.clients.databento_metadata import MetadataClient, load_key
from kq.clients.databento_schema_probe import (
    CEILING,
    PLAN_SHA256,
    SchemaProbeClient,
    load_plan,
    quote_plan,
    read_credits,
    sanitized,
    save_receipt,
)
from kq.equities.options_cache import OptionsCache


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Local --credit-evidence JSON: available (exact USD string), observed_at "
            "(original UTC timestamp, <=5 minutes old), expires_at (exact UTC timestamp), "
            "verified:true, cash_budget_usd:'0', outstanding_usage_reconciled:true, "
            "license_evidence (nonempty string), optional deduct_imports:true. "
            "Do not convert approximate reports into verified evidence or refresh timestamps. "
            "The $0.50 guard limits local reservations; it is not a vendor charge guarantee."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true")
    mode.add_argument("--status", action="store_true", help="Read local catalog without a key")
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--submit-approved", action="store_true")
    mode.add_argument(
        "--lookup", action="store_true", help="GET retained vendor job inventory only"
    )
    parser.add_argument("--index", type=int, choices=range(9))
    parser.add_argument("--root", type=Path, help="Dedicated persistent private $0.50 cache")
    parser.add_argument("--credentials", type=Path)
    parser.add_argument("--credit-evidence", type=Path)
    parser.add_argument("--license-evidence", default="")
    parser.add_argument("--reconcile-job-id", help="With --resume: validate an existing vendor ID")
    parser.add_argument(
        "--output", type=Path, help="New JSON receipt; existing files are preserved"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:  # noqa: PLR0912
    args = arguments(argv)
    plan = load_plan()
    if args.output and args.output.exists():
        raise FileExistsError("Choose a new output receipt; existing evidence is preserved")
    if args.status:
        if args.root is None:
            raise ValueError("--root required for local status")
        database = args.root.resolve() / "catalog.sqlite"
        if not database.exists():
            result = {"mode": "local_status", "state": "no_catalog", "new_billable_jobs": 0}
        else:
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    "SELECT key,state,job_id,reserved,actual FROM jobs ORDER BY created"
                ).fetchall()
                budget = connection.execute("SELECT budget FROM policy WHERE id=1").fetchone()
            result = {
                "mode": "local_status",
                "persistent_budget_usd": budget["budget"],
                "jobs": [dict(row) for row in rows],
                "new_billable_jobs": 0,
            }
    elif args.offline:
        result = {
            "mode": "offline_inspection",
            "plan_sha256": PLAN_SHA256,
            "ceiling_usd": str(CEILING),
            "requests": [
                {"index": index, "name": name, "request": json.loads(request.canonical)}
                for index, (name, request) in enumerate(plan)
            ],
            "new_billable_jobs": 0,
        }
    else:
        if args.credentials is None:
            raise ValueError("--credentials is required for authenticated metadata or GET calls")
        key = load_key(args.credentials)
        if args.lookup:
            with SchemaProbeClient(key) as client:
                result = {
                    "mode": "lookup_only",
                    "jobs": client.list_jobs(datetime.now(UTC) - timedelta(days=30)),
                    "new_billable_jobs": 0,
                }
        elif not (args.resume or args.submit_approved):
            with MetadataClient(key) as metadata:
                result = quote_plan(metadata)
        else:
            if args.root is None or args.index is None:
                raise ValueError("--root and --index required for resume/submission")
            if args.reconcile_job_id and not args.resume:
                raise ValueError("--reconcile-job-id is only valid with --resume")
            request = plan[args.index][1]
            with OptionsCache(args.root, budget=CEILING) as cache, SchemaProbeClient(key) as client:
                if args.resume:
                    if args.reconcile_job_id:
                        client.reconcile(cache, request, args.reconcile_job_id)
                    result = client.resume(cache, request, license_evidence=args.license_evidence)
                else:
                    if args.credit_evidence is None:
                        raise ValueError("--credit-evidence required before a new submission")
                    credits, _ = read_credits(args.credit_evidence)
                    with MetadataClient(key) as metadata:
                        quotes = quote_plan(metadata)
                    result = client.submit_probe(cache, request, quotes, credits)
    if args.output:
        save_receipt(args.output, result)
    print(json.dumps(sanitized(result), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
