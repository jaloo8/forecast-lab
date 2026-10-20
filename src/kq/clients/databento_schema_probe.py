"""Bounded CBBO schema inspection only; no strategy or profit calculation.

The fixed plan has its own durable $0.50 catalog. A reservation is a local
spending guard, not a vendor-side maximum-charge guarantee. Keep this catalog
when resuming; a new empty directory is not recovery of an old acquisition.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Any

from kq.clients.databento_batch import BatchClient
from kq.clients.databento_metadata import MetadataClient
from kq.equities.options_cache import CreditSnapshot, Job, OptionsCache, Request

PLAN_SHA256 = "8eafd4ea0cd550eb77fef1b9626e194d87ceecdb34affde27ef04fb3534dd054"
CEILING = Decimal("0.50")
DEFAULT_PLAN = (
    Path(__file__).resolve().parents[3] / "docs/research/cbbo-schema-probe-requests-2026-10-19.json"
)
_PROTOCOL = "cbbo-schema-probe-20261019-v1"
_SENSITIVE = {
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


def load_plan(path: Path = DEFAULT_PLAN) -> tuple[tuple[str, Request], ...]:
    """Accept only the exact registered bytes, including order and all bounds."""
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != PLAN_SHA256:
        raise ValueError("Schema-probe plan hash differs from registration")
    result = []
    for item in json.loads(payload):
        result.append(
            (
                item["name"],
                Request(
                    item["dataset"],
                    item["schema"],
                    tuple(item["symbols"]),
                    datetime.fromisoformat(item["start"]),
                    datetime.fromisoformat(item["end"]),
                    item["stype_in"],
                    "instrument_id",
                    "csv",
                    _PROTOCOL,
                    "raw",
                    "original",
                ),
            )
        )
    if len(result) != 9 or len({request.key for _, request in result}) != 9:
        raise ValueError("Expected nine distinct registered schema requests")
    return tuple(result)


def _approved(request: Request) -> None:
    if request not in [item for _, item in load_plan()]:
        raise ValueError("Request is outside the pinned schema-probe plan")


def request_params(request: Request) -> dict[str, str]:
    _approved(request)
    return {
        "dataset": request.dataset,
        "schema": request.schema,
        "symbols": ",".join(request.symbols),
        "stype_in": request.stype_in,
        "start": request.start.isoformat(),
        "end": request.end.isoformat(),
    }


def reserved_cost(value: Decimal) -> Decimal:
    if not value.is_finite() or value < 0:
        raise ValueError("Expected a finite nonnegative estimate")
    return max(value * Decimal("1.20"), Decimal("0.0001")).quantize(
        Decimal("0.0001"), rounding=ROUND_CEILING
    )


def validate_estimate(request: Request, receipt: dict[str, Any]) -> Decimal:
    """A current quote must refer to this request, not another cheaper job."""
    params = request_params(request)
    digest = hashlib.sha256(
        json.dumps(params, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    # Every registered bound already falls on the metadata rounding grid.
    if (
        receipt.get("params") != params
        or receipt.get("requested_start") != params["start"]
        or receipt.get("requested_end") != params["end"]
        or receipt.get("request_sha256") != digest
    ):
        raise ValueError("Estimate identity does not match registered request")
    observed = datetime.fromisoformat(receipt["as_of"])
    if observed.tzinfo is None or not timedelta(0) <= datetime.now(UTC) - observed <= timedelta(
        minutes=5
    ):
        raise ValueError("Fresh estimate required")
    return reserved_cost(Decimal(receipt["estimated_usd"]))


def quote_plan(metadata: MetadataClient) -> dict[str, Any]:
    """Free GET metadata only. No cache creation, reservation or submission."""
    rows: list[dict[str, Any]] = []
    for name, request in load_plan():
        params = request_params(request)
        params.pop("symbols")
        receipt = metadata.estimate(symbols=list(request.symbols), **params)
        rows.append(
            {
                "name": name,
                "request_key": request.key,
                "reserved_usd": str(validate_estimate(request, receipt)),
                "estimate": receipt,
            }
        )
    total = sum((Decimal(row["reserved_usd"]) for row in rows), Decimal("0"))
    return {
        "plan_sha256": PLAN_SHA256,
        "mode": "free_metadata_only",
        "requests": rows,
        "reservation_total_usd": str(total),
        "reservation_ceiling_usd": str(CEILING),
        "within_ceiling": total <= CEILING,
        "new_billable_jobs": 0,
    }


def read_credits(path: Path) -> tuple[CreditSnapshot, str]:
    evidence = json.loads(path.read_text(encoding="utf-8-sig"))
    license_evidence = evidence.get("license_evidence")
    if (
        evidence.get("cash_budget_usd") != "0"
        or not isinstance(license_evidence, str)
        or not license_evidence.strip()
        or evidence.get("outstanding_usage_reconciled") is not True
    ):
        raise ValueError("Zero-cash, license and reconciled-usage evidence required")
    credits = CreditSnapshot(
        Decimal(evidence["available"]),
        datetime.fromisoformat(evidence["observed_at"]),
        datetime.fromisoformat(evidence["expires_at"]),
        evidence.get("verified") is True,
        evidence.get("deduct_imports") is True,
    )
    credits.validate(Decimal("0"), datetime.now(UTC))
    return credits, license_evidence


def sanitized(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            name: sanitized(item) for name, item in value.items() if name.lower() not in _SENSITIVE
        }
    if isinstance(value, list):
        return [sanitized(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"db-[A-Za-z0-9]{29}", "[REDACTED]", value)
    return value


def save_receipt(path: Path, value: object) -> None:
    """Never overwrite a receipt; flush evidence before the next side effect."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(sanitized(value), indent=2, allow_nan=False).encode()
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def validate_job(request: Request, details: dict[str, Any]) -> None:
    expected: dict[str, Any] = {
        **request_params(request),
        "encoding": "csv",
        "stype_out": "instrument_id",
        "pretty_px": True,
        "pretty_ts": True,
        "map_symbols": True,
        "limit": None,
    }
    for name in ("start", "end"):
        expected.pop(name)
    if (
        any(name not in details or details[name] != value for name, value in expected.items())
        or details.get("compression") not in {None, "none"}
        or datetime.fromisoformat(details["start"]) != request.start
        or datetime.fromisoformat(details["end"]) != request.end
    ):
        raise ValueError("Vendor job differs from the registered request")


def _job(cache: OptionsCache, request: Request) -> Job | None:
    try:
        return cache.job(request.key)
    except ValueError as exc:
        if str(exc) != "unknown reservation":
            raise
        return None


class SchemaProbeClient(BatchClient):
    """Reuse GET/download integrity primitives without broadening legacy submit."""

    def __enter__(self) -> SchemaProbeClient:
        return self

    def submit(
        self,
        cache: OptionsCache,
        request: Request,
        reservation: Decimal,
        credits: CreditSnapshot,
        *,
        extension: bool = False,
    ) -> dict[str, Any]:
        raise ValueError("Legacy submission is disabled; use the pinned submit_probe path")

    def _save(self, cache: OptionsCache, request: Request, name: str, value: object) -> None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        save_receipt(cache.root / "runs" / request.key / f"{stamp}-{name}.json", value)

    @staticmethod
    def _reservations(cache: OptionsCache, quotes: dict[str, Any]) -> dict[str, Decimal]:
        plan = load_plan()
        if quotes.get("plan_sha256") != PLAN_SHA256 or len(quotes["requests"]) != len(plan):
            raise ValueError("Quote plan identity mismatch")
        amounts = {}
        total = Decimal("0")
        for (name, request), row in zip(plan, quotes["requests"], strict=True):
            if row["name"] != name or row["request_key"] != request.key:
                raise ValueError("Quote order or request identity mismatch")
            amount = validate_estimate(request, row["estimate"])
            if amount != Decimal(row["reserved_usd"]):
                raise ValueError("Per-job rounded reservation differs from estimate")
            amounts[request.key] = amount
            job = _job(cache, request)
            total += (
                max(job.reserved_cost, job.actual_cost or Decimal("0"))
                if job is not None
                else amount
            )
        if total > CEILING:
            raise ValueError("Whole-plan cumulative reservation exceeds $0.50")
        return amounts

    def submit_probe(
        self,
        cache: OptionsCache,
        request: Request,
        quotes: dict[str, Any],
        credits: CreditSnapshot,
    ) -> dict[str, Any]:
        """At most one POST; repeats or lost responses must use GET-only resume."""
        _approved(request)
        amounts = self._reservations(cache, quotes)
        if _job(cache, request) is not None:
            raise ValueError("Existing reservation: resume or reconcile, never resubmit")
        # The vendor inventory includes retained completed and unresolved work.
        # Refuse to buy a matching existing request even if its local DB is absent.
        for listed in self.list_jobs(datetime.now(UTC) - timedelta(days=30)):
            details = self.details(listed["id"])
            symbols = details.get("symbols")
            if isinstance(symbols, str):
                symbols = symbols.split(",")
            if (
                details.get("dataset") == request.dataset
                and details.get("schema") == request.schema
                and isinstance(symbols, list)
                and tuple(sorted(symbols)) == request.symbols
                and details.get("stype_in") == request.stype_in
                and datetime.fromisoformat(details["start"]) == request.start
                and datetime.fromisoformat(details["end"]) == request.end
            ):
                raise ValueError("Matching vendor job exists: recover it without repurchase")
        # Inventory GETs can take minutes. Recheck quote age and persisted totals
        # immediately before reserving rather than treating the earlier check as current.
        amounts = self._reservations(cache, quotes)
        self._save(cache, request, "pre-submit-quotes", quotes)
        params = {
            **request_params(request),
            "stype_out": "instrument_id",
            "encoding": "csv",
            "compression": "none",
            "pretty_px": "true",
            "pretty_ts": "true",
            "map_symbols": "true",
            "split_duration": "none",
            "delivery": "download",
        }
        reservation_key = cache.reserve(request, amounts[request.key], credits, ceiling=CEILING)
        cache.mark_submission_unknown(reservation_key)
        result = self._json("POST", "batch.submit_job", params)
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("id"), str)
            or not re.fullmatch(r"[A-Za-z0-9-]+", result["id"])
        ):
            raise RuntimeError("Submission uncertain: GET-only reconciliation required")
        self._save(cache, request, "submission", result)
        cache.mark_submitted(request.key, result["id"])
        return {"state": "submitted", "job_id": result["id"], "request_key": request.key}

    def reconcile(self, cache: OptionsCache, request: Request, job_id: str) -> None:
        """Validate an operator-supplied existing ID; never create a replacement."""
        _approved(request)
        job = cache.job(request.key)
        if job.state not in {"reserved", "uncertain"} or job.job_id is not None:
            raise ValueError("Only an unresolved local submission may be reconciled")
        if not re.fullmatch(r"[A-Za-z0-9-]+", job_id):
            raise ValueError("Invalid vendor job ID")
        details = self.details(job_id)
        validate_job(request, details)
        self._save(cache, request, "reconciled-details", details)
        cache.mark_submitted(request.key, job_id)

    def resume(
        self, cache: OptionsCache, request: Request, *, license_evidence: str
    ) -> dict[str, Any]:
        """Reuse completed files or the same vendor job using GET requests only."""
        _approved(request)
        job = _job(cache, request)
        if job is None:
            return {"state": "not_acquired", "request_key": request.key, "new_billable_jobs": 0}
        if job.state == "complete":
            return {
                "state": "cached",
                "job_id": job.job_id,
                "files": len(cache.local_files(request)),
                "cost_usd": str(job.actual_cost),
            }
        if job.job_id is None:
            return {
                "state": job.state,
                "request_key": request.key,
                "next_action": "Look up the existing vendor job and reconcile its ID; no POST.",
            }
        if not license_evidence.strip():
            raise ValueError("License evidence required before downloading")
        details = self.details(job.job_id)
        validate_job(request, details)
        self._save(cache, request, "details", details)
        if details["state"] != "done":
            return {"state": details["state"], "job_id": job.job_id}
        manifest = self.files(job.job_id)
        self._save(cache, request, "vendor-manifest", manifest)
        directory = cache.root / "runs" / request.key / "delivery"
        files = tuple(self.download(item, directory) for item in manifest)
        cache.import_files(
            request.key,
            files,
            complete=True,
            actual_cost=Decimal(str(details["cost_usd"])),
            license_evidence=license_evidence,
            conditions=json.dumps(
                {
                    "job_id": job.job_id,
                    "record_count": details["record_count"],
                    "manifest": manifest,
                }
            ),
        )
        return {
            "state": "complete",
            "job_id": job.job_id,
            "cost_usd": str(details["cost_usd"]),
            "files": len(files),
            "delivery_directory": str(directory),
            "new_billable_jobs": 0,
        }
