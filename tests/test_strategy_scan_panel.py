"""Dated scanner matches must expose provenance and withhold invalid evidence."""

import hashlib
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from kq.equities.strategy_lab.scanner import publish_scan


def _report() -> dict[str, Any]:
    rows = [
        dict(
            symbol=symbol,
            family=family,
            lookback=lookback,
            score=0.1 if eligible else None,
            eligible=eligible,
            reason="" if eligible else "missing_latest_session",
            as_of="2020-01-03T21:00:00Z",
            rank=1 if eligible else None,
        )
        for symbol, eligible in [("AAA", True), ("BBB", False)]
        for family in ["momentum", "reversal"]
        for lookback in [10, 20]
    ]
    return dict(
        schema_version=1,
        status="success",
        run_id="fixture",
        captured_at="2020-01-04T00:00:00Z",
        completed_session="2020-01-03",
        target_session="2020-01-03",
        rows=rows,
        coverage=dict(
            requested_count=3,
            candidate_count=2,
            not_found_count=0,
            invalid_count=0,
            missing_latest_count=1,
            excluded_bar_count=0,
            rows=[],
        ),
    )


def _publish(folder: Path, report: dict[str, Any]) -> Path:
    root = folder / "strategy-lab"
    run = root / "scanner-runs" / "fixture"
    run.mkdir(parents=True)
    raw = json.dumps(report).encode()
    (run / "report.json").write_bytes(raw)
    pointer = dict(
        run_id="fixture",
        report_file="scanner-runs/fixture/report.json",
        report_sha256=hashlib.sha256(raw).hexdigest(),
    )
    (root / "scanner-latest.json").write_text(json.dumps(pointer))
    _attempt(root)
    return root


def _attempt(root: Path, *, failed: bool = False) -> None:
    run_id = "failed" if failed else "fixture"
    run = root / "scanner-runs" / run_id
    run.mkdir(exist_ok=True)
    raw = json.dumps(
        dict(
            schema_version=1,
            status="failure" if failed else "success",
            run_id=run_id,
            attempted_at="2020-01-04T01:00:00Z",
            completed_session="2020-01-03",
            error="Missing target SPY session" if failed else None,
        )
    ).encode()
    (run / "scanner-attempt.json").write_bytes(raw)
    (root / "scanner-attempt.json").write_text(
        json.dumps(
            dict(
                run_id=run_id,
                attempt_file=f"scanner-runs/{run_id}/scanner-attempt.json",
                attempt_sha256=hashlib.sha256(raw).hexdigest(),
            )
        )
    )


def _app(folder: Path) -> AppTest:
    return AppTest.from_string(
        "from pathlib import Path\n"
        "from kq.equities.strategy_scan_panel import render_strategy_scan\n"
        f"render_strategy_scan(Path({str(folder)!r}))"
    ).run()


def test_missing_scan_is_read_only(tmp_path: Path) -> None:
    app = _app(tmp_path)
    assert not app.exception
    assert any("No strategy scan" in item.value for item in app.info)
    assert not list(tmp_path.iterdir())


def test_matches_filters_exclusions_and_stale_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    downloads = []
    original = st.download_button

    def download(label: str, data: str, **kwargs: Any) -> bool:
        downloads.append(data)
        return original(label, data, **kwargs)

    monkeypatch.setattr(st, "download_button", download)
    _publish(tmp_path, _report())
    app = _app(tmp_path)
    assert not app.exception
    assert len(app.dataframe[0].value) == 4
    assert set(app.dataframe[0].value.symbol) == {"AAA"}
    assert any("30 hours" in item.value for item in app.warning)
    assert any("2020-01-03" in item.value for item in app.caption)
    assert len(app.get("download_button")) == 1
    app.selectbox(key="scan_family").select("momentum").run()
    app.selectbox(key="scan_lookback").select(10).run()
    assert len(app.dataframe[0].value) == 1
    assert app.dataframe[1].value.iloc[0]["Rows"] == 1
    assert any("8" in item.proto.label for item in app.get("download_button"))
    full = pd.read_csv(io.StringIO(downloads[-1]))
    assert len(full) == 8
    assert full.eligible.sum() == 4
    assert full.score.isna().sum() == 4


def test_failed_latest_attempt_withholds_previous_matches(tmp_path: Path) -> None:
    root = _publish(tmp_path, _report())
    _attempt(root, failed=True)
    app = _app(tmp_path)
    assert not app.exception
    assert any("Missing target SPY session" in item.value for item in app.error)
    assert any("historical only" in item.value for item in app.caption)
    assert not app.dataframe
    assert not app.get("download_button")


@pytest.mark.parametrize("fault", ["missing", "hash", "run_id", "target"])
def test_unverified_attempt_withholds_matches(tmp_path: Path, fault: str) -> None:
    report = _report()
    if fault == "target":
        report["target_session"] = "2020-01-02"
    root = _publish(tmp_path, report)
    if fault == "missing":
        (root / "scanner-attempt.json").unlink()
    elif fault in ("hash", "run_id"):
        pointer = json.loads((root / "scanner-attempt.json").read_text())
        pointer["attempt_sha256" if fault == "hash" else "run_id"] = "bad"
        (root / "scanner-attempt.json").write_text(json.dumps(pointer))
    app = _app(tmp_path)
    assert not app.exception
    assert app.error
    assert not app.dataframe


def test_real_failed_fresh_capture_keeps_prior_report_historical(tmp_path: Path) -> None:
    days = pd.bdate_range("2020-01-02", periods=65)
    data = dict(
        captured_at=datetime.now(UTC).isoformat(),
        benchmark="SPY",
        adjustment_type="split",
        completed_session=days[-1].date().isoformat(),
        requested_symbols=["SPY", "AAA"],
        universe=["AAA"],
        bars=[
            dict(
                symbol=symbol,
                interval="day",
                bounds="regular",
                bars=[
                    dict(
                        begins_at=day.strftime("%Y-%m-%dT00:00:00Z"),
                        session="reg",
                        volume=2_000_000,
                        open_price=100 + i,
                        high_price=101 + i,
                        low_price=99 + i,
                        close_price=100 + i,
                    )
                    for i, day in enumerate(days)
                ],
            )
            for symbol in ["SPY", "AAA"]
        ],
    )
    root = tmp_path / "strategy-lab"
    publish_scan(data, {"universe": ["AAA"]}, root)
    initial = _app(tmp_path)
    assert not initial.exception and not initial.error and initial.dataframe
    data["completed_session"] = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    with pytest.raises(ValueError):
        publish_scan(data, {"universe": ["AAA"]}, root)
    app = _app(tmp_path)
    assert not app.exception
    assert any("Latest scan failed" in item.value for item in app.error)
    assert any("historical only" in item.value for item in app.caption)
    assert not app.dataframe


@pytest.mark.parametrize(
    "fault", ["hash", "path", "date", "spy", "future", "nan", "rank", "coverage"]
)
def test_invalid_evidence_withholds_matches(tmp_path: Path, fault: str) -> None:
    report = _report()
    if fault == "date":
        report.pop("completed_session")
    elif fault == "spy":
        report["rows"][0].update(
            eligible=False, score=None, rank=None, reason="unavailable_benchmark"
        )
    elif fault == "future":
        report["captured_at"] = "2999-01-04T00:00:00Z"
    elif fault == "nan":
        report["rows"][0]["score"] = float("nan")
    elif fault == "rank":
        report["rows"][0]["rank"] = "best"
    elif fault == "coverage":
        report["coverage"]["candidate_count"] = "unknown"
    root = _publish(tmp_path, report)
    if fault in ("hash", "path"):
        pointer = json.loads((root / "scanner-latest.json").read_text())
        pointer.update(
            {"report_sha256": "0" * 64}
            if fault == "hash"
            else {
                "report_file": "../outside.json",
            }
        )
        (root / "scanner-latest.json").write_text(json.dumps(pointer))
    app = _app(tmp_path)
    assert not app.exception
    assert app.error
    assert not app.dataframe
