import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from kq.equities.strategy_lab.scanner import publish_scan


def snapshot() -> dict[str, Any]:
    series = []
    for symbol, slope in (("SPY", 1), ("AAA", 2), ("HELD", 3)):
        bars = []
        for i, day in enumerate(pd.bdate_range("2026-01-02", periods=65)):
            close = 100 + slope * i
            bars.append(
                dict(
                    begins_at=day.strftime("%Y-%m-%dT00:00:00Z"),
                    session="reg",
                    open_price=close,
                    high_price=close + 1,
                    low_price=close - 1,
                    close_price=close,
                    volume=2_000_000,
                )
            )
        series.append(dict(symbol=symbol, interval="day", bounds="regular", bars=bars))
    return dict(
        captured_at="2026-05-01T12:00:00Z",
        benchmark="SPY",
        adjustment_type="split",
        universe=["AAA", "HELD"],
        requested_symbols=["SPY", "AAA", "HELD"],
        completed_session="2026-04-02",
        bars={"data": {"results": series}},
    )


def read(root: Path, pointer: dict[str, Any]) -> dict[str, Any]:
    path = root / pointer["report_file"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == pointer["report_sha256"]
    return dict(json.loads(path.read_bytes()))


def test_reports_all_rules_only_for_candidates_with_source_timestamps(tmp_path: Path) -> None:
    data = snapshot()
    pointer = publish_scan(data, {"universe": ["AAA"]}, tmp_path)
    report = read(tmp_path, pointer)
    assert len(report["rows"]) == 20
    assert {row["symbol"] for row in report["rows"]} == {"AAA"}
    assert {row["family"] for row in report["rows"]} == {
        "momentum",
        "risk_momentum",
        "reversal",
        "low_volatility",
        "breakout",
    }
    assert report["source_captured_at"] == data["captured_at"]
    assert report["completed_session"] == "2026-04-02"
    assert report["coverage"]["requested_count"] == 3
    assert report["coverage"]["candidate_count"] == 1
    assert all(row["rank"] == 1 for row in report["rows"] if row["eligible"])
    manifest = tmp_path / "runs" / pointer["run_id"] / "scanner-manifest.json"
    assert report["manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()


def test_placeholders_cannot_advance_benchmark_decision_date(tmp_path: Path) -> None:
    data = snapshot()
    spy = data["bars"]["data"]["results"][0]["bars"]
    spy[-1]["volume"] = 0
    spy[-2]["synthetic"] = True
    with pytest.raises(ValueError, match="intended"):
        publish_scan(data, {"universe": ["AAA"]}, tmp_path)


def test_invalid_missing_and_not_found_symbols_are_explicit(tmp_path: Path) -> None:
    data = snapshot()
    data["bars"]["data"]["results"][1]["bars"][-1]["high_price"] = 1
    data["bars"]["data"]["results"][2]["bars"].pop()
    data["bars"]["data"]["not_found"] = ["MISSING"]
    data["requested_symbols"].append("MISSING")
    report = read(tmp_path, publish_scan(data, {"universe": ["AAA", "HELD", "MISSING"]}, tmp_path))
    assert len(report["rows"]) == 60
    assert not any(row["eligible"] for row in report["rows"])
    coverage = report["coverage"]
    assert (
        coverage["invalid_count"]
        == coverage["missing_latest_count"]
        == coverage["not_found_count"]
        == 1
    )
    assert {row["reason"] for row in report["rows"]} == {
        "invalid_bar",
        "missing_latest",
        "not_found",
    }


@pytest.mark.parametrize("fault", ["spy", "future", "mirror"])
def test_failed_scan_does_not_replace_published_pointer(tmp_path: Path, fault: str) -> None:
    data = snapshot()
    pointer = publish_scan(data, {"universe": ["AAA"]}, tmp_path)
    if fault == "spy":
        data["bars"]["data"]["results"][0]["bars"] = []
    elif fault == "future":
        data["captured_at"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    else:
        (tmp_path / "READ_ONLY_MIRROR.txt").write_text("mirror", encoding="utf-8")
    with pytest.raises(ValueError):
        publish_scan(data, {"universe": ["AAA"]}, tmp_path)
    assert json.loads((tmp_path / "scanner-latest.json").read_bytes()) == pointer


def test_duplicate_candidate_response_isolated_without_hiding_other_stocks(tmp_path: Path) -> None:
    data = snapshot()
    data["bars"]["data"]["results"].append(copy.deepcopy(data["bars"]["data"]["results"][1]))
    report = read(tmp_path, publish_scan(data, {"universe": ["AAA", "HELD"]}, tmp_path))
    assert any(row["eligible"] for row in report["rows"] if row["symbol"] == "HELD")
    assert all(
        row["reason"] == "duplicate_symbol" for row in report["rows"] if row["symbol"] == "AAA"
    )
    assert all(type(row["rank"]) is int for row in report["rows"] if row["rank"] is not None)


@pytest.mark.parametrize("fault", ["adjustment", "weekend"])
def test_invalid_benchmark_metadata_is_not_a_genuine_session(tmp_path: Path, fault: str) -> None:
    data = snapshot()
    spy = data["bars"]["data"]["results"][0]
    if fault == "adjustment":
        spy["adjustment_type"] = "none"
    else:
        spy["bars"][-1]["begins_at"] = "2026-04-05T00:00:00Z"
    with pytest.raises(ValueError, match="benchmark"):
        publish_scan(data, {"universe": ["AAA"]}, tmp_path)


def test_requested_count_does_not_invent_requests_for_candidates(tmp_path: Path) -> None:
    data = snapshot()
    data["requested_symbols"] = ["SPY", "AAA"]
    report = read(tmp_path, publish_scan(data, {"universe": ["AAA", "HELD", "NEW"]}, tmp_path))
    assert report["coverage"]["requested_count"] == 2
    assert report["coverage"]["not_requested_count"] == 2
    assert all(row["reason"] == "not_requested" for row in report["rows"] if row["symbol"] != "AAA")


@pytest.mark.parametrize("metadata", ["completed_session", "requested_symbols"])
def test_missing_scan_intent_cannot_be_inferred_from_returned_data(
    tmp_path: Path, metadata: str
) -> None:
    data = snapshot()
    del data[metadata]
    with pytest.raises(ValueError):
        publish_scan(data, {"universe": ["AAA"]}, tmp_path)


@pytest.mark.parametrize("flag", ["error", "errors", "isError"])
@pytest.mark.parametrize("level", ["series", "bar"])
def test_provider_errors_cannot_be_scored(tmp_path: Path, flag: str, level: str) -> None:
    data = snapshot()
    series = data["bars"]["data"]["results"][1]
    target = series if level == "series" else series["bars"][-1]
    target[flag] = True
    report = read(tmp_path, publish_scan(data, {"universe": ["AAA"]}, tmp_path))
    assert all(row["reason"] == "invalid_bar" for row in report["rows"])


def test_latest_attempt_records_success_then_failure_without_hiding_history(tmp_path: Path) -> None:
    data = snapshot()
    success = publish_scan(data, {"universe": ["AAA"]}, tmp_path)
    pointer = json.loads((tmp_path / "scanner-attempt.json").read_bytes())
    raw = (tmp_path / pointer["attempt_file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == pointer["attempt_sha256"]
    assert json.loads(raw)["status"] == "success"
    assert pointer["run_id"] == success["run_id"]
    data["completed_session"] = "2026-04-03"
    with pytest.raises(ValueError, match="intended"):
        publish_scan(data, {"universe": ["AAA"]}, tmp_path)
    failed = json.loads((tmp_path / "scanner-attempt.json").read_bytes())
    attempt = json.loads((tmp_path / failed["attempt_file"]).read_bytes())
    assert attempt["status"] == "failure" and attempt["error"]
    assert failed["run_id"] != success["run_id"]
    assert attempt["completed_session"] == "2026-04-03"
    assert json.loads((tmp_path / "scanner-latest.json").read_bytes()) == success


def test_assembler_validation_errors_publish_failed_attempt_preserving_raw_source(
    tmp_path: Path,
) -> None:
    data = snapshot()
    success = publish_scan(data, {"universe": ["AAA"]}, tmp_path)
    data["validation_errors"] = ["Historical revisions detected for AAA; prior snapshot retained"]
    raw_hash = hashlib.sha256(
        json.dumps(data, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="Historical revisions detected for AAA"):
        publish_scan(data, {"universe": ["AAA"]}, tmp_path)
    pointer = json.loads((tmp_path / "scanner-attempt.json").read_bytes())
    attempt = json.loads((tmp_path / pointer["attempt_file"]).read_bytes())
    run = tmp_path / "runs" / pointer["run_id"]
    assert attempt["status"] == "failure"
    assert "Historical revisions detected for AAA" in attempt["error"]
    assert json.loads((run / "scanner-manifest.json").read_bytes())["snapshot_sha256"] == raw_hash
    assert not (run / "scanner-report.json").exists()
    assert json.loads((tmp_path / "scanner-latest.json").read_bytes()) == success
