"""The parallel-books panel only presents verified local evidence."""

import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from streamlit.testing.v1 import AppTest

from kq.equities.portfolios import portfolio_specs


def _run(folder: Path) -> AppTest:
    app = AppTest.from_string(
        "from kq.equities.portfolio_panel import render_portfolios\n"
        "import streamlit as st\n"
        "render_portfolios(st.session_state['folder'])"
    )
    app.session_state["folder"] = folder
    return app.run()


def _account(portfolio_id: str) -> dict[str, object]:
    return {
        "portfolio_id": portfolio_id,
        "status": "ok",
        "launched_at": "2026-09-28T12:00:00+00:00",
        "summary": {
            "equity_valid": True,
            "equity": 100.0,
            "cash": 100.0,
            "reserved_cash": 10.0,
            "pending_count": 1,
            "open_count": 0,
            "closed_count": 0,
            "paused": False,
            "pause_reason": "",
            "stale_symbols": [],
        },
        "metrics": {
            "valid": True,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "max_drawdown": 0.0,
            "exposure": 0.0,
            "matched_spy_pnl": None,
        },
    }


def _report() -> dict[str, object]:
    at = datetime.now(UTC).isoformat()
    return {
        "status": "ok",
        "as_of": at,
        "source_as_of": at,
        "session_date": "2026-09-28",
        "snapshot_hash": "a" * 64,
        "launched_at": "2026-09-28T12:00:00+00:00",
        "benchmark": {"status": "pending", "equity": None, "return": None},
        "accounts": [{**asdict(spec), **_account(spec.portfolio_id)} for spec in portfolio_specs()],
    }


def _save(folder: Path, report: dict[str, object]) -> None:
    root = folder / "parallel-books"
    root.mkdir()
    (root / "latest.json").write_text(json.dumps(report), encoding="utf-8")


def test_missing_and_corrupt_report_are_safe_and_read_only(tmp_path: Path) -> None:
    app = _run(tmp_path)
    assert not app.exception
    assert app.warning
    assert not app.dataframe
    assert list(tmp_path.iterdir()) == []
    _save(tmp_path, _report())
    report_path = tmp_path / "parallel-books" / "latest.json"
    report_path.write_text("{broken", encoding="utf-8")
    before = report_path.read_bytes()
    app = _run(tmp_path)
    assert not app.exception
    assert app.error
    assert report_path.read_bytes() == before


def test_all_nine_pending_accounts_and_open_loss_are_visible(tmp_path: Path) -> None:
    report = _report()
    accounts = report["accounts"]
    assert isinstance(accounts, list)
    losing = accounts[0]
    losing["summary"].update(
        equity=94.0, cash=90.0, reserved_cash=0.0, pending_count=0, open_count=1
    )
    losing["metrics"].update(unrealized_pnl=-6.0, max_drawdown=0.06, exposure=4 / 94)
    _save(tmp_path, report)
    before = (tmp_path / "parallel-books" / "latest.json").read_bytes()
    app = _run(tmp_path)
    assert not app.exception
    table = app.dataframe[0].value
    assert len(table) == 9
    assert set(table["Portfolio"]) == {spec.portfolio_id for spec in portfolio_specs()}
    loss = table.loc[table["Portfolio"] == losing["portfolio_id"]].iloc[0]
    assert loss["Equity ($)"] == 94.0
    assert loss["Unrealized P&L ($)"] == -6.0
    assert loss["Open"] == 1
    assert "Not yet measured" in " ".join(item.value for item in app.info)
    assert "$900" in " ".join(item.value for item in app.caption)
    assert (tmp_path / "parallel-books" / "latest.json").read_bytes() == before


def test_partial_invalid_and_stale_values_are_withheld(tmp_path: Path) -> None:
    report = _report()
    report["status"] = "partial_failure"
    report["source_as_of"] = (datetime.now(UTC) - timedelta(hours=31)).isoformat()
    accounts = report["accounts"]
    assert isinstance(accounts, list)
    accounts[0].pop("summary")
    accounts[0].pop("metrics")
    accounts[0].update(status="error", error="capture gap")
    accounts[1]["summary"]["equity_valid"] = False
    accounts[1]["summary"]["equity"] = 300.0
    accounts[1]["metrics"]["valid"] = False
    accounts[2]["summary"]["stale_symbols"] = ["AAA"]
    _save(tmp_path, report)
    app = _run(tmp_path)
    assert not app.exception
    table = app.dataframe[0].value
    assert table["Equity ($)"].isna().all()
    assert table["Profit ($)"].isna().all()
    assert "capture gap" in " ".join(item.value for item in app.error)
    assert any("stale" in item.value.lower() for item in app.warning)


def test_unknown_schema_and_mismatched_launch_do_not_fabricate_results(tmp_path: Path) -> None:
    report = _report()
    accounts = report["accounts"]
    assert isinstance(accounts, list)
    accounts[0]["launched_at"] = "2026-09-29T12:00:00+00:00"
    _save(tmp_path, report)
    app = _run(tmp_path)
    assert not app.exception
    assert any("launch" in item.value.lower() for item in app.warning)
    report["accounts"] = [{"portfolio_id": "unrecognized", "status": "ok"}]
    (tmp_path / "parallel-books" / "latest.json").write_text(json.dumps(report), encoding="utf-8")
    app = _run(tmp_path)
    assert not app.exception
    assert app.error
    assert not app.dataframe


def test_recovered_report_discloses_quarantined_source_error(tmp_path: Path) -> None:
    report = _report()
    report["source_as_of"] = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
    report["source_errors"] = ["IXHL: conflicting quarterly values; ticker excluded"]
    report["recovery"] = True
    _save(tmp_path, report)
    app = _run(tmp_path)
    assert not app.exception
    warnings = " ".join(item.value for item in app.warning)
    assert "IXHL" in warnings
    assert "excluded" in warnings
    assert "Recovered prior committed results" in warnings
    assert "no new trades from stale data" in warnings


def test_old_method_report_is_rejected_before_display(tmp_path: Path) -> None:
    report = _report()
    accounts = report["accounts"]
    assert isinstance(accounts, list)
    accounts[0]["protocol_id"] = "superseded-method"
    _save(tmp_path, report)
    app = _run(tmp_path)
    assert not app.exception
    assert app.error
    assert not app.dataframe
