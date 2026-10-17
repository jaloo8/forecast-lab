"""Unavailable, unselected history stays dated and cannot become fresh evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import runpy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from kq.equities.research import _results, daily_bars
from kq.equities.session_vintages import create_review, reconcile_daily
from tests.equity_vintage_fixtures import snapshots

NOW = datetime(2026, 9, 30, 2, tzinfo=UTC)


def _case(symbol: str = "UXIN") -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], bytes]:
    original, primary = snapshots()
    review = create_review(
        original, primary, now=NOW.replace(day=29, hour=14), note="finite review"
    )
    prior = reconcile_daily(
        primary, original, review, required={"SPY"}, now=NOW.replace(day=29, hour=14)
    )
    fresh = copy.deepcopy(primary)
    fresh.update(captured_at="2026-09-30T01:30:00Z", price_as_of="2026-09-30T01:00:00Z")
    fresh["universe"] = ["SPY"]
    fresh["bars"] = [s for s in fresh["bars"] if s["symbol"] != symbol]
    for series in fresh["bars"]:
        bar = copy.deepcopy(series["bars"][-1])
        bar["begins_at"] = "2026-09-29T00:00:00Z"
        series["bars"].append(bar)
    wrapper = dict(
        request=dict(
            symbols=[symbol],
            start_time="2026-06-01T00:00:00Z",
            end_time="2026-09-30T00:00:00Z",
            interval="day",
            bounds="regular",
            adjustment_type="split",
        ),
        retrieved_at=fresh["price_as_of"],
        response={"structuredContent": {"data": {"results": [], "not_found": [symbol]}}},
    )
    raw = json.dumps(wrapper).encode()
    fresh["raw_sha256"] = {"missing.json": hashlib.sha256(raw).hexdigest()}
    return fresh, prior, review, raw


def _run(
    fresh: dict[str, Any],
    prior: dict[str, Any],
    review: dict[str, Any],
    raw: bytes,
    required: set[str] | None = None,
) -> dict[str, Any]:
    return reconcile_daily(
        fresh,
        prior,
        review,
        required=required or {"SPY"},
        now=NOW,
        unavailable_sources={"missing.json": raw},
    )


@pytest.mark.parametrize("symbol", ["UXIN"])
def test_preserves_exact_retired_series_without_retiming_or_mutating_inputs(symbol: str) -> None:
    fresh, prior, review, raw = _case(symbol)
    before = copy.deepcopy((fresh, prior, review))
    result = _run(fresh, prior, review, raw)
    old = next(s for s in prior["bars"] if s["symbol"] == symbol)
    retained = next(s for s in result["bars"] if s["symbol"] == symbol)
    assert retained["bars"] == old["bars"]
    assert retained["as_of"] == prior["captured_at"]
    assert retained["retrieved_at"] == prior["price_as_of"]
    assert (
        result["historical_retention"][symbol]["reason"]
        == "provider_not_found_not_current_candidate"
    )
    assert result["historical_retention"][symbol]["raw_sha256"] == fresh["raw_sha256"]
    frame = daily_bars(result)
    assert set(frame[frame.symbol == symbol].as_of) == {
        datetime.fromisoformat(prior["captured_at"])
    }
    assert (fresh, prior, review) == before
    assert symbol not in result["universe"]


@pytest.mark.parametrize(
    "defect",
    [
        "no_proof",
        "hash",
        "not_found",
        "requested",
        "required",
        "candidate",
        "returned",
        "review",
        "prior",
    ],
)
def test_refuses_unproven_or_unsafe_retention(defect: str) -> None:
    fresh, prior, review, raw = _case()
    required = {"SPY"}
    if defect == "no_proof":
        with pytest.raises(ValueError, match="missing prior"):
            reconcile_daily(fresh, prior, review, required=required, now=NOW)
        return
    if defect == "hash":
        fresh["raw_sha256"]["missing.json"] = "0" * 64
    if defect in {"not_found", "requested"}:
        wrapper = json.loads(raw)
        if defect == "not_found":
            wrapper["response"]["structuredContent"]["data"]["not_found"] = []
        else:
            wrapper["request"]["symbols"] = ["OTHER"]
        raw = json.dumps(wrapper).encode()
        fresh["raw_sha256"]["missing.json"] = hashlib.sha256(raw).hexdigest()
    if defect == "required":
        required.add("UXIN")
    if defect == "candidate":
        fresh["universe"].append("UXIN")
    if defect == "returned":
        fresh["bars"].append(copy.deepcopy(next(s for s in prior["bars"] if s["symbol"] == "UXIN")))
    if defect == "review":
        review["entries"][0]["kind"] = "fake"
    if defect == "prior":
        next(s for s in prior["bars"] if s["symbol"] == "UXIN")["bars"][0]["close_price"] = "1.36"
    with pytest.raises(ValueError):
        _run(fresh, prior, review, raw, required)


def test_repeated_retention_keeps_original_observation_time_and_checks_returned_history() -> None:
    fresh, prior, review, raw = _case("UXIN")
    first = _run(fresh, prior, review, raw)
    second = _run(fresh, first, review, raw)
    old = next(s for s in second["bars"] if s["symbol"] == "UXIN")
    assert old["as_of"] == prior["captured_at"]
    returning = copy.deepcopy(fresh)
    _, primary = snapshots()
    series = copy.deepcopy(
        next(s for s in _results(primary["bars"], "bars") if s["symbol"] == "UXIN")
    )
    series["bars"][0]["close_price"] = "1.36"
    returning["bars"].append(series)
    with pytest.raises(ValueError, match="revision"):
        reconcile_daily(returning, second, review, required={"SPY"}, now=NOW)


def test_reviewed_missing_symbol_cannot_be_retained() -> None:
    with pytest.raises(ValueError, match="reviewed"):
        _run(*_case("AAPL"))


@pytest.mark.parametrize("field", ["request", "response"])
def test_malformed_raw_wrapper_is_a_validation_failure(field: str) -> None:
    fresh, prior, review, raw = _case()
    wrapper = json.loads(raw)
    wrapper[field] = []
    raw = json.dumps(wrapper).encode()
    fresh["raw_sha256"]["missing.json"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="object"):
        _run(fresh, prior, review, raw)


def test_retained_series_metadata_cannot_be_retimed_on_retry() -> None:
    fresh, prior, review, raw = _case()
    retained = _run(fresh, prior, review, raw)
    next(s for s in retained["bars"] if s["symbol"] == "UXIN")["as_of"] = fresh["captured_at"]
    with pytest.raises(ValueError, match="retained series hash"):
        _run(fresh, retained, review, raw)


@pytest.mark.parametrize("defect", ["future", "stale", "range", "tool_error", "contradiction"])
def test_rejects_invalid_not_found_wrapper(defect: str) -> None:
    fresh, prior, review, raw = _case()
    wrapper = json.loads(raw)
    if defect == "future":
        wrapper["retrieved_at"] = "2026-10-01T00:00:00Z"
    elif defect == "stale":
        wrapper["retrieved_at"] = "2026-09-28T00:00:00Z"
    elif defect == "range":
        wrapper["request"]["start_time"] = "2026-09-29T00:00:00Z"
    elif defect == "tool_error":
        wrapper["response"]["isError"] = True
    else:
        wrapper["response"]["structuredContent"]["data"]["results"] = [{"symbol": "UXIN"}]
    raw = json.dumps(wrapper).encode()
    fresh["raw_sha256"]["missing.json"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):
        _run(fresh, prior, review, raw)


def test_cli_binds_raw_retention_source_in_immutable_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh, prior, review, raw = _case()
    for name, value in (("fresh", fresh), ("prior", prior), ("review", review)):
        (tmp_path / f"{name}.json").write_text(json.dumps(value))
    (tmp_path / "missing.json").write_bytes(raw)
    main = runpy.run_path(str(Path(__file__).parents[1] / "scripts/reconcile_stock_daily.py"))[
        "main"
    ]

    class Clock(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return NOW.astimezone(tz)

    monkeypatch.setitem(main.__globals__, "datetime", Clock)
    args = [
        "--snapshot",
        str(tmp_path / "fresh.json"),
        "--prior",
        str(tmp_path / "prior.json"),
        "--review",
        str(tmp_path / "review.json"),
        "--output",
        str(tmp_path / "out.json"),
        "--required",
        "SPY",
        "--unavailable-source",
        str(tmp_path / "missing.json"),
    ]
    assert main(args) == 0
    receipt = json.loads((tmp_path / "out.json.sources.json").read_bytes())
    assert receipt["inputs_sha256"]["unavailable:missing.json"] == hashlib.sha256(raw).hexdigest()
    assert main(args) == 2
