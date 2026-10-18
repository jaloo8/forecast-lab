"""Verified historical comparisons remain complete and separate from paper accounts."""

import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest


def _report() -> dict[str, Any]:
    rows = []
    for family, lookback, size, hold, cost in itertools.product(
        [
            "momentum",
            "risk_momentum",
            "reversal",
            "low_volatility",
            "breakout",
        ],
        [10, 20, 40, 60],
        [1, 3, 5, 10, 20],
        [5, 20],
        [10, 25, 50],
    ):
        rows.append(
            dict(
                selection_id=f"{family}-{lookback}-{size}",
                family=family,
                lookback=lookback,
                size=size,
                hold_sessions=hold,
                cost_bps=cost,
                cohort_count=2,
                unavailable_count=0,
                mean_exposure=0.5,
                mean_net_return=-0.02,
                median_net_return=-0.01,
                mean_excess_vs_spy=-0.03,
                worst_cohort_return=-0.04,
                status="complete",
            )
        )
    rows[0].update(status="unavailable", mean_net_return=None)
    return dict(
        schema_version=1,
        status="success",
        run_id="fixture",
        captured_at="2026-09-29T00:00:00Z",
        source=dict(
            captured_at="2026-09-28T00:00:00Z",
            first_session="2026-03-02",
            last_session="2026-09-25",
            stock_count=4447,
            candidate_count=4999,
            limitations=["Fixture coverage limitation"],
        ),
        results=rows,
        cohorts=[],
        controls=[],
        limitations=["Exploratory sample"],
    )


def _publish(folder: Path, report: dict[str, Any]) -> Path:
    root = folder / "strategy-lab"
    run = root / "runs" / "fixture"
    run.mkdir(parents=True)
    payload = json.dumps(report).encode()
    (run / "report.json").write_bytes(payload)
    (root / "latest.json").write_text(
        json.dumps(
            dict(
                run_id="fixture",
                report_file="runs/fixture/report.json",
                report_sha256=hashlib.sha256(payload).hexdigest(),
            )
        ),
        encoding="utf-8",
    )
    return root


def _app(folder: Path, *, main: bool = False) -> AppTest:
    module, function = (
        ("dashboard", "main") if main else ("strategy_lab_panel", "render_strategy_lab")
    )
    return AppTest.from_string(
        f"from pathlib import Path\nfrom kq.equities.{module} import {function}\n"
        f"{function}(Path({str(folder)!r}))"
    ).run(timeout=30)


def test_missing_report_is_honest_and_read_only(tmp_path: Path) -> None:
    app = _app(tmp_path)
    assert not app.exception
    assert any("No strategy comparison" in item.value for item in app.info)
    assert not list(tmp_path.iterdir())


def test_all_outcomes_filters_and_downloads(tmp_path: Path) -> None:
    _publish(tmp_path, _report())
    app = _app(tmp_path)
    assert not app.exception
    assert len(app.dataframe[0].value) == 600
    assert app.dataframe[0].value["mean_net_return"].isna().sum() == 1
    assert len(app.get("download_button")) == 2
    app.selectbox(key="lab_family").select("reversal").run()
    app.selectbox(key="lab_hold_sessions").select(20).run()
    app.selectbox(key="lab_cost_bps").select(25).run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 20
    assert (app.dataframe[0].value["mean_net_return"] < 0).all()
    assert any("600" in item.value and "independent" in item.value for item in app.caption)
    assert any("Fixture coverage limitation" in item.value for item in app.warning)


@pytest.mark.parametrize(
    "fault", ["hash", "traversal", "schema", "rows", "shape", "nonfinite", "counts", "missing_file"]
)
def test_invalid_reports_withhold_comparisons(tmp_path: Path, fault: str) -> None:
    report = _report()
    if fault == "schema":
        report["schema_version"] = 99
    elif fault == "rows":
        report["results"].pop()
    elif fault == "shape":
        report["results"][0].pop("worst_cohort_return")
    elif fault == "nonfinite":
        report["results"][0]["mean_exposure"] = float("inf")
    elif fault == "counts":
        report["source"]["stock_count"] = "many"
    root = _publish(tmp_path, report)
    if fault == "missing_file":
        (root / "runs" / "fixture" / "report.json").unlink()
    if fault in ("hash", "traversal"):
        pointer = json.loads((root / "latest.json").read_text())
        pointer.update(
            {"report_sha256": "0" * 64}
            if fault == "hash"
            else {
                "report_file": "../outside.json",
            }
        )
        (root / "latest.json").write_text(json.dumps(pointer))
    app = _app(tmp_path)
    assert not app.exception
    assert app.error
    assert not app.dataframe


def test_navigation_keeps_existing_sections_reachable(tmp_path: Path) -> None:
    app = _app(tmp_path, main=True)
    assert not app.exception
    assert [tab.label for tab in app.tabs][:4] == [
        "Paper accounts",
        "Strategy comparisons",
        "Scanner",
        "Data health",
    ]
    text = " ".join(item.value for item in app.subheader)
    assert "Original pilot" in text
    assert "Nine parallel paper portfolios" in text
    assert "Adaptive stock research" in text
    assert any("Historical" in expander.label for expander in app.expander)
    assert any("recurring" in item.value for item in app.caption)
