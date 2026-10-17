"""Public import routes preserve honest outage recognition and replay."""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from kq.equities import __main__ as cli
from kq.equities import portfolio_runner as runner
from kq.equities.portfolio_metrics import account_metrics
from tests.test_equity_portfolio_runner import Clock, capture, invoke


def test_recovered_drawdown_includes_missed_marks_without_moving_past_peaks() -> None:
    summary = dict(
        equity_valid=True,
        stale_symbols=[],
        equity=102,
        cash=80,
        closed_trades=[],
        delayed_recovery=dict(
            run_count=1, peak_equity=105, minimum_equity=95, max_drawdown_recovered=0.10
        ),
    )
    metrics = account_metrics(
        summary,
        dict(peak_equity=110, max_drawdown=0.04),
        pd.DataFrame(columns=["symbol", "session_date"]),
    )
    assert metrics["max_drawdown"] == pytest.approx(1 - 95 / 110)
    summary["equity"] = 120
    later = account_metrics(summary, metrics, pd.DataFrame(columns=["symbol", "session_date"]))
    assert later["max_drawdown"] == metrics["max_drawdown"]


def test_parallel_explicit_recovery_and_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invoke(tmp_path, monkeypatch)
    source = tmp_path / "recovery.json"
    snapshot = capture(66)
    source.write_text(json.dumps(snapshot))
    Clock.current = datetime.fromisoformat(snapshot["captured_at"]) + timedelta(minutes=1)
    report = runner.run_portfolios(
        source, tmp_path / "parallel-books", recover_missed_sessions=True
    )
    assert report["status"] == "ok"
    accounts = {a["portfolio_id"]: a for a in report["accounts"]}
    assert accounts["momentum5_20"]["summary"]["closed_count"] == 1
    assert accounts["momentum20_20"]["summary"]["open_count"] == 1
    assert report["delayed_recognition"] is True
    before = (tmp_path / "parallel-books" / "latest.json").read_bytes()
    assert (
        runner.run_portfolios(source, tmp_path / "parallel-books", recover_missed_sessions=True)
        == report
    )
    assert (tmp_path / "parallel-books" / "latest.json").read_bytes() == before
    Clock.current += timedelta(minutes=1)
    snapshot["captured_at"] = Clock.current.isoformat()
    source.write_text(json.dumps(snapshot))
    assert (
        runner.run_portfolios(source, tmp_path / "parallel-books", recover_missed_sessions=True)
        == report
    )
    assert (tmp_path / "parallel-books" / "latest.json").read_bytes() == before


def test_pilot_explicit_recovery_keeps_actual_decision_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "datetime", Clock)
    source = tmp_path / "snapshot.json"
    ledger = tmp_path / "paper.sqlite"
    report = tmp_path / "report.html"
    args = ["--snapshot", str(source), "--ledger", str(ledger), "--report", str(report)]
    for index in [60, 66]:
        snapshot = capture(index)
        for series in snapshot["bars"]:
            first = pd.Timestamp(series["bars"][0]["begins_at"])
            earlier = pd.bdate_range(end=first - timedelta(days=1), periods=90)
            series["bars"] = [
                dict(
                    begins_at=d.isoformat(),
                    open_price="100",
                    close_price="100",
                    high_price="100",
                    low_price="100",
                    volume=1000000,
                    session="reg",
                )
                for d in earlier
            ] + series["bars"]
        Clock.current = datetime.fromisoformat(snapshot["captured_at"]) + timedelta(minutes=1)
        source.write_text(json.dumps(snapshot))
        assert cli.main(args + (["--recover-missed-sessions"] if index == 66 else [])) == 0
    with sqlite3.connect(ledger) as con:
        assert con.execute("select count(*) from paper_trades").fetchone()[0] == 1
        assert con.execute("select count(distinct created_at) from forecasts").fetchone()[0] == 2
    assert "recognized late" in report.read_text(encoding="utf-8")
    original_report = report.read_bytes()
    Clock.current += timedelta(minutes=1)
    snapshot["captured_at"] = Clock.current.isoformat()
    source.write_text(json.dumps(snapshot))
    assert cli.main([*args, "--recover-missed-sessions"]) == 0
    assert report.read_bytes() == original_report


def test_public_writers_refuse_local_mirror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "READ_ONLY_MIRROR.txt").write_text("A8 is sole writer")
    source = tmp_path / "source.json"
    source.write_text(json.dumps(capture()))
    with pytest.raises(ValueError, match="read-only"):
        runner.run_portfolios(source, tmp_path / "parallel-books", recover_missed_sessions=True)
    assert (
        cli.main(
            [
                "--snapshot",
                str(source),
                "--ledger",
                str(tmp_path / "paper.sqlite"),
                "--report",
                str(tmp_path / "report.html"),
                "--recover-missed-sessions",
            ]
        )
        == 2
    )
    assert not (tmp_path / "paper.sqlite").exists()
