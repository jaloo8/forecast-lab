"""Free historical metadata only; deliberately no market-data retrieval interface."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import TracebackType
from typing import Any

import httpx
from dotenv import dotenv_values

_FREE_ENDPOINTS = frozenset(
    {
        "metadata.list_datasets",
        "metadata.list_schemas",
        "metadata.get_dataset_range",
        "metadata.get_dataset_condition",
        "metadata.get_cost",
        "metadata.get_billable_size",
        "metadata.get_record_count",
        "symbology.resolve",
    }
)


def load_key(path: Path) -> str:
    """Read a local credential without exposing its contents in errors."""
    key = dotenv_values(path, interpolate=False).get("DATABENTO_API_KEY", "") or ""
    if not key.startswith("db-") or len(key) != 32 or any(c.isspace() for c in key):
        raise ValueError("Databento credential missing or invalid; check the private key file")
    return key


def _instant(value: str) -> datetime:
    instant = datetime.fromisoformat(value)
    if instant.tzinfo is None:
        raise ValueError("An explicit UTC offset is required")
    return instant.astimezone(UTC)


def _bounded(params: dict[str, str]) -> None:
    symbols = params.get("symbols", "").split(",")
    if any(not symbol.strip() or symbol.strip().upper() == "ALL_SYMBOLS" for symbol in symbols):
        raise ValueError("Explicit bounded symbols required")
    if len(symbols) > 2000 or _instant(params["start"]) >= _instant(params["end"]):
        raise ValueError("Invalid estimate bounds")


class MetadataClient:
    """GET-only allowlist; redirects/retries and response-body errors are disabled."""

    def __init__(self, key: str, *, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(
            base_url="https://hist.databento.com/v0/",
            auth=(key, ""),
            timeout=60,
            follow_redirects=False,
            transport=transport,
        )

    def __enter__(self) -> MetadataClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._client.close()

    def get(self, endpoint: str, params: dict[str, str] | None = None) -> Any:
        if endpoint not in _FREE_ENDPOINTS:
            raise ValueError("Not an allowed free endpoint")
        params = dict(params or {})
        if endpoint in {
            "metadata.get_cost",
            "metadata.get_billable_size",
            "metadata.get_record_count",
        }:
            try:
                _bounded(params)
            except KeyError:
                raise ValueError("Explicit time bounds required") from None
        try:
            response = self._client.get(endpoint, params=params)
        except httpx.HTTPError:
            raise RuntimeError("Databento metadata transport failed; no automatic retry") from None
        if response.status_code != 200:
            raise RuntimeError(f"Databento metadata HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError:
            raise RuntimeError("Databento metadata returned invalid JSON") from None

    def estimate(
        self, *, dataset: str, schema: str, symbols: list[str], stype_in: str, start: str, end: str
    ) -> dict[str, Any]:
        if (
            not isinstance(symbols, list)
            or not symbols
            or any(
                not isinstance(symbol, str)
                or not symbol.strip()
                or symbol != symbol.strip()
                or any(char in symbol for char in ",*?[]\n\r\x00")
                for symbol in symbols
            )
        ):
            raise ValueError("Explicit symbols must be a nonempty list of bounded strings")
        params = {
            "dataset": dataset,
            "schema": schema,
            "symbols": ",".join(sorted(set(symbols))),
            "stype_in": stype_in,
            "start": start,
            "end": end,
        }
        _bounded(params)
        seconds = 86400 if schema == "definition" else 600
        params["start"] = datetime.fromtimestamp(
            math.floor(_instant(start).timestamp() / seconds) * seconds, UTC
        ).isoformat()
        params["end"] = datetime.fromtimestamp(
            math.ceil(_instant(end).timestamp() / seconds) * seconds, UTC
        ).isoformat()
        value = self.get("metadata.get_cost", params)
        try:
            cost = Decimal(str(value))
        except InvalidOperation:
            raise RuntimeError("Databento returned invalid cost") from None
        if not cost.is_finite() or cost < 0:
            raise RuntimeError("Databento returned invalid cost")
        return {
            "as_of": datetime.now(UTC).isoformat(),
            "params": params,
            "requested_start": start,
            "requested_end": end,
            "estimated_usd": str(cost),
            "request_sha256": hashlib.sha256(
                json.dumps(params, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "note": "Free estimate only; rounded bounds; no data job submitted",
        }
