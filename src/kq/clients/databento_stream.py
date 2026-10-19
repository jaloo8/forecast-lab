"""Explicit small historical streams; durable uncertainty and no automatic retries."""

import csv
import hashlib
import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx

from kq.clients.databento_batch import BatchClient, _pilot
from kq.equities.options_cache import CreditSnapshot, OptionsCache, RawFile, Request


def stream_params(request: Request) -> dict[str, str]:
    """Aligned bounds allow independent metadata record-count verification."""
    interval = 86400 if request.schema == "definition" else 600
    if request.end > datetime(2026, 10, 17, tzinfo=UTC):
        raise ValueError("Stream outside approved dates")
    if any(t.timestamp() % interval for t in (request.start, request.end)):
        raise ValueError("Aligned stream bounds required")
    check = request
    if request.schema == "cmbp-1":
        if request.end - request.start > timedelta(minutes=40):
            raise ValueError("Stream quote scope exceeds 40 minutes")
        check = replace(request, end=request.start + timedelta(seconds=11))
    params = _pilot(check, extension=True)
    params["end"] = request.end.isoformat()
    for key in ("delivery", "split_duration"):
        del params[key]
    return params


def verify_csv(path: Path, expected_records: int) -> RawFile:
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.reader(source, strict=True)
        header = next(reader, [])
        if not {"ts_recv", "ts_event", "instrument_id"} <= set(header):
            raise ValueError("Unexpected CSV header")
        count = 0
        for row in reader:
            if len(row) != len(header):
                raise ValueError("Truncated or malformed CSV record")
            count += 1
    if count != expected_records:
        raise ValueError("Delivered records differ from independent metadata count")
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return RawFile(path, path.stat().st_size, digest)


class StreamClient(BatchClient):
    """Opt-in transport, never an automatic fallback for an uncertain batch."""

    def acquire(
        self,
        cache: OptionsCache,
        request: Request,
        reservation: Decimal,
        credits: CreditSnapshot,
        *,
        expected_records: int,
        estimate: Decimal,
        license_evidence: str,
    ) -> None:
        params = stream_params(request)
        if (
            type(expected_records) is not int
            or expected_records < 0
            or not estimate.is_finite()
            or not 0 <= estimate <= reservation
        ):
            raise ValueError("Independent count and bounded cost estimate required")
        cache.reserve(request, reservation, credits, ceiling=Decimal("17"))
        cache.mark_submission_unknown(request.key)
        directory = cache.root / "runs" / request.key
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "stream.csv"
        try:
            with self._http.stream("POST", "timeseries.get_range", data=params) as response:
                (directory / "response.json").write_text(
                    json.dumps(
                        {
                            "status": response.status_code,
                            "warnings": response.headers.get("warnings"),
                            "content_type": response.headers.get("content-type"),
                        },
                        indent=2,
                    )
                )
                if response.status_code not in {200, 206}:
                    raise RuntimeError(
                        f"Stream HTTP {response.status_code}; reconcile, do not retry"
                    )
                with path.open("xb") as target:
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > 256_000_000:
                            raise ValueError("Stream exceeded local size bound")
                        target.write(chunk)
                    target.flush()
                    os.fsync(target.fileno())
        except httpx.HTTPError:
            raise RuntimeError("Stream outcome uncertain; no retry") from None
        raw = verify_csv(path, expected_records)
        receipt = {
            "transport": "timeseries.get_range",
            "status": response.status_code,
            "warnings": response.headers.get("warnings"),
            "params": params,
            "records": expected_records,
            "sha256": raw.sha256,
            "size": raw.size,
            "cost_basis": "conservative reservation, NOT vendor-reported actual charge",
            "metadata_cost": str(estimate),
            "accounted_cost": str(reservation),
            "integrity_basis": "HTTP completion + independent aligned metadata count + local hash",
        }
        (directory / "stream-receipt.json").write_text(json.dumps(receipt, indent=2))
        cache.mark_submitted(request.key, "local-stream-" + request.key)
        # Ledger deliberately overstates stream usage until billing reconciliation.
        cache.import_files(
            request.key,
            (raw,),
            complete=True,
            actual_cost=reservation,
            license_evidence=license_evidence,
            conditions=json.dumps(receipt),
        )
