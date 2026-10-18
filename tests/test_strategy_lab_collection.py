import copy
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from kq.equities.strategy_lab import collection
from kq.equities.strategy_lab.collection import begin_capture, progress, record_batch


def plan(tmp_path: Path, symbols: list[str] | None = None) -> tuple[Path, dict[str, Any]]:
    catalogue = tmp_path / "source.json"
    catalogue.write_text('{"catalogue":"dated"}', encoding="utf-8")
    root = tmp_path / "capture"
    manifest = begin_capture(
        root, symbols or ["AAA", "SPY"], catalogue, "2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z"
    )
    return root, manifest


def wrapper(manifest: dict[str, Any], index: int = 0) -> dict[str, Any]:
    request = copy.deepcopy(manifest["batches"][index])
    results = [
        {"symbol": symbol, "interval": "day", "bounds": "regular", "bars": []}
        for symbol in request["symbols"]
    ]
    return {
        "retrieved_at": datetime.now(UTC).isoformat(),
        "request": request,
        "response": {"structuredContent": {"data": {"results": results, "not_found": []}}},
    }


def test_plan_batches_sorted_unique_and_resume(tmp_path: Path) -> None:
    symbols = [f"S{i:02}" for i in range(23)]
    root, manifest = plan(tmp_path, [*reversed(symbols), "S00"])
    assert [len(batch["symbols"]) for batch in manifest["batches"]] == [10, 10, 3]
    assert manifest["batches"][0]["symbols"] == symbols[:10]
    assert progress(root)["pending_batches"] == [0, 1, 2]
    assert progress(root)["snapshot_path"] is None
    first = wrapper(manifest)
    record_batch(root, 0, first)
    assert record_batch(root, 0, first)["pending_batches"] == [1, 2]
    assert len(list((root / "attempts").glob("*.json"))) == 1
    record_batch(root, 2, wrapper(manifest, 2))
    assert not progress(root)["complete"]
    status = record_batch(root, 1, wrapper(manifest, 1))
    assert status["complete"]
    assert Path(status["snapshot_path"]).is_file()
    assert not status["coverage_complete"]  # Empty histories are transport successes only.


@pytest.mark.parametrize(
    "malformation",
    [
        "request",
        "range",
        "error",
        "omission",
        "duplicate",
        "contradiction",
        "future",
        "naive",
        "foreign",
        "bounds",
    ],
)
def test_bad_attempts_preserved_and_retryable(tmp_path: Path, malformation: str) -> None:
    root, manifest = plan(tmp_path)
    bad = wrapper(manifest)
    data = bad["response"]["structuredContent"]["data"]
    if malformation == "request":
        bad["request"]["symbols"] = ["EVIL"]
    elif malformation == "range":
        bad["request"]["start_time"] = "2020-01-01T00:00:00Z"
    elif malformation == "error":
        bad["response"]["isError"] = True
    elif malformation == "omission":
        data["results"].pop()
    elif malformation == "duplicate":
        data["results"].append(data["results"][0])
    elif malformation == "contradiction":
        data["not_found"] = ["AAA"]
    elif malformation == "future":
        bad["retrieved_at"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    elif malformation == "naive":
        bad["retrieved_at"] = "2026-09-29T00:00:00"
    elif malformation == "foreign":
        data["results"][0]["symbol"] = "EVIL"
    else:
        data["results"][0]["bounds"] = "extended"
    with pytest.raises(ValueError):
        record_batch(root, 0, bad)
    assert list((root / "attempts").glob("*.json"))
    assert progress(root)["errors"]
    assert progress(root)["pending_batches"] == [0]
    assert record_batch(root, 0, wrapper(manifest))["complete"]


def test_not_found_accounts_for_response_but_not_coverage(tmp_path: Path) -> None:
    root, manifest = plan(tmp_path)
    response = wrapper(manifest)
    data = response["response"]["structuredContent"]["data"]
    data["results"] = []
    data["not_found"] = ["AAA", "SPY"]
    status = record_batch(root, 0, response)
    assert status["complete"] and not status["coverage_complete"]
    assert status["unavailable"] == {"AAA": "not_found", "SPY": "not_found"}


def test_accepted_capture_is_immutable_and_tampering_detected(tmp_path: Path) -> None:
    root, manifest = plan(tmp_path)
    accepted = wrapper(manifest)
    record_batch(root, 0, accepted)
    with pytest.raises(ValueError, match="immutable"):
        record_batch(root, 0, wrapper(manifest))
    digest = json.loads((root / "accepted" / "0000.json").read_text())["sha256"]
    attempt = root / "attempts" / f"0000-{digest}.json"
    attempt.write_text(json.dumps({"tampered": True}), encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        progress(root)


def test_plan_tampering_detected(tmp_path: Path) -> None:
    root, _ = plan(tmp_path)
    (root / "plan.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        progress(root)


@pytest.mark.parametrize("mode", ["outside", "duplicate", "adjustment", "bar_error"])
def test_bar_range_and_response_adjustment_cannot_contradict_request(
    tmp_path: Path, mode: str
) -> None:
    root, manifest = plan(tmp_path)
    response = wrapper(manifest)
    item = response["response"]["structuredContent"]["data"]["results"][0]
    bar = {"begins_at": "2026-01-05T00:00:00Z", "session": "reg"}
    item["bars"] = [bar]
    if mode == "outside":
        bar["begins_at"] = "2025-01-05T00:00:00Z"
    elif mode == "duplicate":
        item["bars"].append(bar)
    elif mode == "adjustment":
        item["adjustment_type"] = "none"
    else:
        bar["error"] = "provider failure"
    with pytest.raises(ValueError):
        record_batch(root, 0, response)


def test_resume_same_plan_and_reject_changed_catalogue(tmp_path: Path) -> None:
    root, manifest = plan(tmp_path)
    source = tmp_path / "source.json"
    args = (root, ["SPY", "AAA"], source, "2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z")
    assert begin_capture(*args) == manifest
    source.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="immutable"):
        begin_capture(*args)


def test_bulk_receipt_defers_full_progress_until_explicit_finalization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, manifest = plan(tmp_path)
    original = collection.progress
    calls = []

    def observed(path: Path) -> dict[str, Any]:
        calls.append(path)
        return original(path)

    monkeypatch.setattr(collection, "progress", observed)
    receipt = collection.record_batch(root, 0, wrapper(manifest), check_progress=False)
    assert calls == []
    assert receipt["accepted"] is True and receipt["complete"] is None
    assert receipt["index"] == 0 and len(receipt["sha256"]) == 64
    assert not (root / "snapshot.json").exists()
    assert collection.progress(root)["complete"]
    assert calls == [root]


def test_interrupted_plan_initialization_can_be_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = collection._write

    def interrupted(path: Path, raw: bytes) -> None:
        if path.name == "plan.sha256":
            raise OSError("simulated disk interruption")
        original(path, raw)

    monkeypatch.setattr(collection, "_write", interrupted)
    with pytest.raises(OSError, match="interruption"):
        plan(tmp_path)
    assert not (tmp_path / "capture").exists()
    monkeypatch.setattr(collection, "_write", original)
    root, _ = plan(tmp_path)
    assert progress(root)["pending_batches"] == [0]


def test_interrupted_file_flush_never_publishes_partial_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "capture.json"

    def interrupted(fd: int) -> None:
        raise OSError("simulated disk interruption")

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", interrupted)
        with pytest.raises(OSError, match="interruption"):
            collection._write(target, b'{"complete":true}')
    assert not target.exists()
    collection._write(target, b'{"complete":true}')
    assert target.read_bytes() == b'{"complete":true}'


@pytest.mark.parametrize(
    "location,flag", [("item", "isError"), ("bar", "isError"), ("bar", "errors")]
)
def test_provider_error_flags_on_results_and_bars_are_rejected(
    tmp_path: Path, location: str, flag: str
) -> None:
    root, manifest = plan(tmp_path)
    response = wrapper(manifest)
    item = response["response"]["structuredContent"]["data"]["results"][0]
    item["bars"] = [
        {
            "begins_at": "2026-01-05T00:00:00Z",
            "session": "reg",
            "open_price": "10",
            "high_price": "11",
            "low_price": "9",
            "close_price": "10",
            "volume": 1000,
        }
    ]
    target = item if location == "item" else item["bars"][0]
    target[flag] = True
    with pytest.raises(ValueError):
        record_batch(root, 0, response, check_progress=False)
    assert progress(root)["pending_batches"] == [0]
    assert len(progress(root)["errors"]) == 1
