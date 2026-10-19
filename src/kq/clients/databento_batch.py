"""Explicit credit-approved pilot batches; no retries or streaming fallback."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import TracebackType
from typing import Any

import httpx

from kq.equities.options_cache import CreditSnapshot, OptionsCache, RawFile, Request


def _pilot(request: Request, *, extension: bool = False) -> dict[str, str]:
    duration = request.end - request.start
    quotes = (
        request.dataset == "OPRA.PILLAR"
        and request.schema == "cmbp-1"
        and request.stype_in == "raw_symbol"
        and len(request.symbols) <= 2
        and all(re.fullmatch(r"SPY   \d{6}C\d{8}", s) for s in request.symbols)
        and duration <= (timedelta(seconds=11) if extension else timedelta(days=1))
    )
    definitions = (
        request.dataset == "OPRA.PILLAR"
        and request.schema == "definition"
        and request.stype_in == "parent"
        and request.symbols == ("SPY.OPT",)
        and duration <= timedelta(days=4 if extension else 1)
    )
    bars = (
        request.dataset == "EQUS.MINI"
        and request.schema == "ohlcv-1m"
        and request.stype_in == "raw_symbol"
        and request.symbols == ("SPY",)
        and duration <= timedelta(days=1461)
    )
    if (
        not (quotes or definitions or bars)
        or (
            extension
            and (
                bars
                or request.start < datetime(2023, 3, 28, tzinfo=UTC)
                or request.end > datetime(2026, 10, 17, tzinfo=UTC)
            )
        )
        or request.encoding != "csv"
        or request.stype_out != "instrument_id"
    ):
        raise ValueError("Request outside the approved pilot scope")
    return {
        "dataset": request.dataset,
        "schema": request.schema,
        "symbols": ",".join(request.symbols),
        "start": request.start.isoformat(),
        "end": request.end.isoformat(),
        "stype_in": request.stype_in,
        "stype_out": request.stype_out,
        "encoding": "csv",
        "compression": "none",
        "pretty_px": "true",
        "pretty_ts": "true",
        "map_symbols": "true",
        "split_duration": "none",
        "delivery": "download",
    }


class BatchClient:
    """Small bounded jobs, durable uncertainty and vendor-verified file hashes."""

    def __init__(self, key: str, *, transport: httpx.BaseTransport | None = None) -> None:
        self._http = httpx.Client(
            base_url="https://hist.databento.com/v0/",
            auth=(key, ""),
            timeout=60,
            follow_redirects=False,
            transport=transport,
        )

    def __enter__(self) -> BatchClient:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._http.close()

    def _json(self, method: str, endpoint: str, params: dict[str, str]) -> Any:
        try:
            response = (
                self._http.post(endpoint, data=params)
                if method == "POST"
                else self._http.get(endpoint, params=params)
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"Databento batch HTTP {response.status_code}; reconcile before retry"
                )
            return response.json()
        except (httpx.HTTPError, ValueError):
            raise RuntimeError("Databento response uncertain; reconcile before retry") from None

    def submit(
        self,
        cache: OptionsCache,
        request: Request,
        reservation: Decimal,
        credits: CreditSnapshot,
        *,
        extension: bool = False,
    ) -> dict[str, Any]:
        params = _pilot(request, extension=extension)
        # Extension authorization: existing $7 reservations plus $10 additional credits.
        key = cache.reserve(
            request, reservation, credits, ceiling=Decimal("17") if extension else Decimal("9.99")
        )
        cache.mark_submission_unknown(key)
        result = self._json("POST", "batch.submit_job", params)
        if not isinstance(result, dict) or not isinstance(result.get("id"), str):
            raise RuntimeError("Databento submission uncertain; reconcile before retry")
        cache.mark_submitted(key, result["id"])
        return result

    def details(self, job_id: str) -> dict[str, Any]:
        result = self._json("GET", "batch.get_job_details", {"job_id": job_id})
        if not isinstance(result, dict) or result.get("id") != job_id:
            raise ValueError("Invalid job identity")
        return result

    def list_jobs(self, since: datetime) -> list[dict[str, Any]]:
        """Inspect existing jobs without submitting or reserving a new request."""
        if since.tzinfo is None:
            raise ValueError("An explicit timezone is required")
        result = self._json(
            "GET",
            "batch.list_jobs",
            {"since": since.isoformat(), "states": "queued,processing,done,expired"},
        )
        if not isinstance(result, list) or not all(
            isinstance(job, dict)
            and isinstance(job.get("id"), str)
            and re.fullmatch(r"[A-Za-z0-9-]+", job["id"])
            for job in result
        ):
            raise ValueError("Invalid existing-job inventory")
        return result

    def files(self, job_id: str) -> list[dict[str, Any]]:
        result = self._json("GET", "batch.list_files", {"job_id": job_id})
        if (
            not isinstance(result, list)
            or not result
            or not all(isinstance(f, dict) for f in result)
        ):
            raise ValueError("Incomplete vendor file manifest")
        for file in result:
            parts = httpx.URL(file["urls"]["https"]).path.split("/")
            if len(parts) != 7 or parts[5] != job_id or parts[6] != file.get("filename"):
                raise ValueError("Download manifest names a different job/file")
        return result

    def download(self, meta: dict[str, Any], directory: Path) -> RawFile:
        url = httpx.URL(meta["urls"]["https"])
        if (
            url.scheme != "https"
            or url.host not in {"hist.databento.com", "api.databento.com"}
            or not url.path.startswith("/v0/batch/download/")
            or url.username
            or url.password
        ):
            raise ValueError("Unexpected download host/path")
        name = str(meta["filename"])
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in {".", ".."}:
            raise ValueError("Invalid vendor filename")
        checksum = str(meta["hash"])
        if not checksum.startswith("sha256:"):
            raise ValueError("Missing vendor hash")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        expected = RawFile(path, int(meta["size"]), checksum[7:])
        if path.exists():
            expected.verify()
            return expected
        partial = directory / (name + ".part")
        created = False
        try:
            with self._http.stream("GET", url) as response:
                if response.status_code != 200:
                    raise RuntimeError(f"Databento download HTTP {response.status_code}")
                with partial.open("xb") as stream:
                    created = True
                    count = 0
                    for chunk in response.iter_bytes():
                        count += len(chunk)
                        if count > expected.size:
                            raise ValueError("Downloaded size exceeds vendor manifest")
                        stream.write(chunk)
                    stream.flush()
                    os.fsync(stream.fileno())
            RawFile(partial, expected.size, expected.sha256).verify()
            os.replace(partial, path)
        except httpx.HTTPError:
            raise RuntimeError("Databento download interrupted; reuse the same job") from None
        finally:
            if created:
                partial.unlink(missing_ok=True)
        return expected
