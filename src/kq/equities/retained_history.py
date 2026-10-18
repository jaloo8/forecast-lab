"""Explicit, hash-bound retention of unavailable, unselected historical series."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import timedelta
from typing import Any

from kq.equities.research import _results, _timestamp
from kq.equities.session_data import _digest
from kq.equities.session_vintage_evidence import _history, _provider_error


def _object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("unavailable source requires JSON objects")
    return value


def retain_unavailable(  # noqa: PLR0912, PLR0915
    snapshot: dict[str, Any],
    prior: dict[str, Any],
    review: dict[str, Any],
    *,
    required: set[str],
    sources: dict[str, bytes],
) -> dict[str, Any]:
    """Copy exact prior history only with explicit fresh provider not-found evidence.

    This creates a capture derivative, never a fresh price for a missing symbol.
    Required symbols, current candidates and finite reviewed pairs are ineligible.
    """
    captured = _timestamp(snapshot.get("captured_at"), "captured_at")
    old = {s["symbol"]: s for s in _results(prior.get("bars"), "bars")}
    incoming = {s["symbol"] for s in _results(snapshot.get("bars"), "bars")}
    universe = snapshot.get("universe")
    if not isinstance(universe, list) or not all(isinstance(s, str) for s in universe):
        raise ValueError("retention requires an explicit candidate universe")
    forbidden = required | set(universe) | {str(snapshot.get("benchmark", "SPY"))}
    forbidden |= {e["symbol"] for e in review["entries"]}
    evidence: dict[str, dict[str, Any]] = {}
    for name, raw in sources.items():
        digest = hashlib.sha256(raw).hexdigest()
        if _object(snapshot.get("raw_sha256", {})).get(name) != digest:
            raise ValueError("unavailable raw source hash mismatch")
        wrapper = _object(json.loads(raw))
        request = _object(wrapper.get("request"))
        response = _object(wrapper.get("response"))
        structured = _object(response.get("structuredContent"))
        data = _object(structured.get("data"))
        for record in (wrapper, response, structured, data):
            _provider_error(record)
        if response.get("isError"):
            raise ValueError("unavailable source contains tool error")
        retrieved = _timestamp(wrapper.get("retrieved_at"), "retrieved_at")
        if retrieved > captured or captured - retrieved > timedelta(hours=24):
            raise ValueError("unavailable source observation must be fresh")
        if any(
            request.get(k) != v
            for k, v in {"interval": "day", "bounds": "regular", "adjustment_type": "split"}.items()
        ):
            raise ValueError("unavailable source must request split daily regular history")
        missing = data.get("not_found")
        requested = request.get("symbols")
        if (
            not isinstance(missing, list)
            or not missing
            or not all(isinstance(s, str) for s in missing)
            or not isinstance(requested, list)
            or not set(missing) <= set(requested)
        ):
            raise ValueError("explicit requested provider not_found symbols required")
        returned = {s.get("symbol") for s in _results(data, "unavailable results")}
        if set(missing) & (incoming | returned):
            raise ValueError("provider not_found contradicts returned series")
        for symbol in set(missing) & old.keys():
            if symbol in forbidden:
                raise ValueError(f"required, current or reviewed {symbol} cannot be retained")
            if symbol in evidence:
                raise ValueError("duplicate unavailable source evidence")
            dates = [_timestamp(b["begins_at"], "begins_at") for b in old[symbol]["bars"]]
            if (
                not dates
                or _timestamp(request.get("start_time"), "start_time") > min(dates)
                or _timestamp(request.get("end_time"), "end_time") <= max(dates)
            ):
                raise ValueError("unavailable request does not cover prior history")
            evidence[symbol] = dict(
                raw_sha256={name: digest},
                not_found_observed_at=wrapper["retrieved_at"],
                raw_wrapper=wrapper,
            )
    if not evidence:
        raise ValueError("no eligible prior history has provider not_found evidence")
    result = copy.deepcopy(snapshot)
    rows = _results(result.get("bars"), "bars")
    retention: dict[str, Any] = {}
    for symbol, proof in evidence.items():
        series = copy.deepcopy(old[symbol])
        previous = prior.get("historical_retention", {}).get(symbol)
        if previous and previous.get("retained_series_sha256") != _digest(series):
            raise ValueError("prior retained series hash mismatch")
        series["as_of"] = series.get("as_of", prior["captured_at"])
        series["retrieved_at"] = series.get("retrieved_at", prior["price_as_of"])
        observed = _timestamp(series["as_of"], "retained as_of")
        retrieved = _timestamp(series["retrieved_at"], "retained retrieved_at")
        if retrieved > observed or observed > _timestamp(prior["captured_at"], "prior capture"):
            raise ValueError("retained observation timestamps invalid")
        series["historical_only"] = True
        rows.append(series)
        retention[symbol] = dict(
            reason="provider_not_found_not_current_candidate",
            prior_snapshot_sha256=_digest(prior),
            prior_series_sha256=_digest(old[symbol]),
            retained_series_sha256=_digest(series),
            as_of=series["as_of"],
            retrieved_at=series["retrieved_at"],
            **proof,
        )
    result["historical_retention"] = retention
    result["source_errors"] = [
        *result.get("source_errors", []),
        *[
            f"{symbol}: prior history retained only; "
            "provider not_found, no current price or selection"
            for symbol in sorted(retention)
        ],
    ]
    _history(result)
    return result
