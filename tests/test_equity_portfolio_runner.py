"""Shared evidence and independent account behavior through real SQLite."""

from __future__ import annotations

import copy
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from kq.equities import portfolio_runner as runner


class Clock(datetime):
    current = datetime(2026, 8, 4, 3, tzinfo=UTC)

    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        return cls.current.astimezone(tz)


def capture(last: int = 60) -> dict[str, Any]:
    days = pd.bdate_range("2026-04-01", periods=90)
    as_of = days[last].to_pydatetime().replace(tzinfo=UTC) + timedelta(days=1, hours=3)
    rows = []
    for symbol in ("AAA", "SPY"):
        bars = []
        for i, day in enumerate(days[: last + 1]):
            price = 100 if symbol == "SPY" else 100 + i if i <= 60 else 160 - (i - 60)
            bars.append(
                dict(
                    begins_at=day.isoformat() + "Z",
                    open_price=str(price),
                    close_price=str(price),
                    high_price=str(price),
                    low_price=str(price),
                    volume=1_000_000,
                    session="reg",
                )
            )
        rows.append(dict(symbol=symbol, interval="day", bounds="regular", bars=bars))
    return dict(
        captured_at=as_of.isoformat(),
        benchmark="SPY",
        adjustment_type="split",
        universe=["AAA"],
        bars=rows,
        earnings=[
            dict(
                symbol="AAA",
                year=2026,
                quarter=2,
                report=dict(date=days[60].date().isoformat(), verified=True),
                eps=dict(actual="1.10", estimate="1.00"),
            )
        ],
    )


def invoke(folder: Path, monkeypatch: pytest.MonkeyPatch, last: int = 60) -> dict[str, Any]:
    snapshot = capture(last)
    Clock.current = datetime.fromisoformat(snapshot["captured_at"]) + timedelta(minutes=1)
    monkeypatch.setattr(runner, "datetime", Clock)
    source = folder / f"source-{last}.json"
    source.write_text(json.dumps(snapshot), encoding="utf-8")
    return runner.run_portfolios(source, folder / "parallel-books")


def test_nine_accounts_start_without_fills_and_replay_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = invoke(tmp_path, monkeypatch)
    assert len(report["accounts"]) == 9
    assert report["status"] == "ok"
    assert all(row["summary"]["equity"] == 100 for row in report["accounts"])
    assert all(row["summary"]["open_count"] == 0 for row in report["accounts"])
    assert all(row["summary"]["pending_count"] == 1 for row in report["accounts"])
    assert invoke(tmp_path, monkeypatch) == report
    assert len(list((tmp_path / "parallel-books" / "runs").glob("*.json"))) == 1
    assert not (tmp_path / "paper.sqlite").exists()


def test_daily_losing_path_has_independent_horizons_and_open_losses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoke(tmp_path, monkeypatch)
    for last in range(61, 81):
        report = invoke(tmp_path, monkeypatch, last)
        assert report["status"] == "ok"
        rows = {r["portfolio_id"]: r for r in report["accounts"]}
        if last == 65:
            assert rows["momentum5_20"]["summary"]["closed_count"] == 1
            assert rows["momentum20_20"]["summary"]["closed_count"] == 0
            assert rows["momentum20_20"]["metrics"]["unrealized_pnl"] < 0
    assert rows["momentum20_20"]["summary"]["closed_count"] == 1
    assert rows["momentum20_20"]["metrics"]["realized_pnl"] < 0
    assert rows["momentum20_20"]["metrics"]["max_drawdown"] > 0
    assert report["benchmark"]["status"] == "marked"


def test_one_bad_account_is_visible_without_resetting_other_accounts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoke(tmp_path, monkeypatch)
    db = tmp_path / "parallel-books" / "momentum5_10" / "paper.sqlite"
    with sqlite3.connect(db) as con:
        con.execute("UPDATE state SET value='tampered' WHERE key='protocol_id'")
    result = invoke(tmp_path, monkeypatch, 61)
    assert result["status"] == "partial_failure"
    failed = [r for r in result["accounts"] if r["status"] == "error"]
    assert len(failed) == 1 and failed[0]["portfolio_id"] == "momentum5_10"
    assert "summary" not in failed[0]
    assert all(r["summary"]["open_count"] == 1 for r in result["accounts"] if r["status"] == "ok")


def test_bad_capture_and_unsafe_root_cannot_create_ledgers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = copy.deepcopy(capture())
    snapshot["adjustment_type"] = "none"
    source = tmp_path / "invalid.json"
    source.write_text(json.dumps(snapshot), encoding="utf-8")
    Clock.current = datetime.fromisoformat(snapshot["captured_at"]) + timedelta(minutes=1)
    monkeypatch.setattr(runner, "datetime", Clock)
    with pytest.raises(ValueError):
        runner.run_portfolios(source, tmp_path / "parallel-books")
    assert not (tmp_path / "parallel-books").exists()
    with pytest.raises(ValueError, match="parallel-books"):
        runner.run_portfolios(source, tmp_path)


def test_revised_benchmark_stays_invalid_on_later_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoke(tmp_path, monkeypatch)
    invoke(tmp_path, monkeypatch, 61)
    for last in (62, 63):
        snapshot = capture(last)
        for field in ("open_price", "close_price", "high_price", "low_price"):
            snapshot["bars"][1]["bars"][61][field] = "105"
        Clock.current = datetime.fromisoformat(snapshot["captured_at"]) + timedelta(minutes=1)
        source = tmp_path / f"revision-{last}.json"
        source.write_text(json.dumps(snapshot), encoding="utf-8")
        result = runner.run_portfolios(source, tmp_path / "parallel-books")
        assert result["status"] == "partial_failure"
        assert result["benchmark"]["status"] == "invalid"
        assert all("benchmark revision" in r["error"] for r in result["accounts"])


def test_missing_weekday_remains_unverified_on_later_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoke(tmp_path, monkeypatch)
    for last in (62, 63):
        snapshot = capture(last)
        for series in snapshot["bars"]:
            del series["bars"][61]
        Clock.current = datetime.fromisoformat(snapshot["captured_at"]) + timedelta(minutes=1)
        source = tmp_path / f"gap-{last}.json"
        source.write_text(json.dumps(snapshot), encoding="utf-8")
        result = runner.run_portfolios(source, tmp_path / "parallel-books")
        assert result["status"] == "partial_failure"
        assert result["benchmark"]["status"] == "invalid"


def test_interrupted_report_requires_same_capture_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = runner._write

    def fail_latest(path: Path, value: dict[str, Any], *, immutable: bool = False) -> None:
        if path.name == "latest.json":
            raise OSError("interrupted publication")
        original(path, value, immutable=immutable)

    monkeypatch.setattr(runner, "_write", fail_latest)
    with pytest.raises(OSError, match="interrupted"):
        invoke(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, "_write", original)
    with pytest.raises(ValueError, match="unfinished capture"):
        invoke(tmp_path, monkeypatch, 61)
    assert invoke(tmp_path, monkeypatch)["status"] == "ok"
    result = invoke(tmp_path, monkeypatch, 61)
    assert result["status"] == "ok"
    assert all(r["summary"]["open_count"] == 1 for r in result["accounts"])


def test_fresh_timestamp_does_not_hide_missing_latest_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = capture()
    snapshot["captured_at"] = capture(61)["captured_at"]
    Clock.current = datetime.fromisoformat(snapshot["captured_at"]) + timedelta(minutes=1)
    monkeypatch.setattr(runner, "datetime", Clock)
    source = tmp_path / "stale-bars.json"
    source.write_text(json.dumps(snapshot), encoding="utf-8")
    result = runner.run_portfolios(source, tmp_path / "parallel-books")
    assert result["status"] == "partial_failure"
    assert all("unverified_calendar" in r["error"] for r in result["accounts"])
    assert not list((tmp_path / "parallel-books").glob("*/paper.sqlite"))


@pytest.mark.parametrize("missing", [61, 62])
def test_missing_pending_or_open_stock_session_never_silently_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing: int,
) -> None:
    invoke(tmp_path, monkeypatch)
    if missing == 62:
        invoke(tmp_path, monkeypatch, 61)
    for last in range(missing, 67):
        snapshot = capture(last)
        del snapshot["bars"][0]["bars"][missing]
        Clock.current = datetime.fromisoformat(snapshot["captured_at"]) + timedelta(minutes=1)
        source = tmp_path / f"stock-gap-{last}.json"
        source.write_text(json.dumps(snapshot), encoding="utf-8")
        result = runner.run_portfolios(source, tmp_path / "parallel-books")
        assert result["status"] == "partial_failure"
        row = next(r for r in result["accounts"] if r["portfolio_id"] == "momentum5_10")
        assert row["status"] == "error" and "missing stock session" in row["error"]


def test_old_interrupted_capture_republishes_only_committed_accounts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = runner.update_ledger
    calls = 0

    def interrupt(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("process died")
        return original(*args, **kwargs)

    monkeypatch.setattr(runner, "update_ledger", interrupt)
    with pytest.raises(RuntimeError, match="process died"):
        invoke(tmp_path, monkeypatch)
    root = tmp_path / "parallel-books"
    before = {p: p.read_bytes() for p in root.glob("*/paper.sqlite")}
    Clock.current += timedelta(hours=25)
    result = runner.run_portfolios(tmp_path / "source-60.json", root)
    assert result["recovery"] is True
    assert result["status"] == "partial_failure"
    assert sum(row["status"] == "ok" for row in result["accounts"]) == 1
    assert {p: p.read_bytes() for p in root.glob("*/paper.sqlite")} == before
    assert calls == 2
    assert not (root / "in-progress.json").exists()


def test_zero_volume_benchmark_session_cannot_fill_orders(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoke(tmp_path, monkeypatch)
    snapshot = capture(61)
    snapshot["bars"][1]["bars"][-1]["volume"] = 0
    Clock.current = datetime.fromisoformat(snapshot["captured_at"]) + timedelta(minutes=1)
    source = tmp_path / "zero-volume.json"
    source.write_text(json.dumps(snapshot), encoding="utf-8")
    result = runner.run_portfolios(source, tmp_path / "parallel-books")
    assert result["status"] == "partial_failure"
    assert result["benchmark"]["status"] == "invalid"
    with sqlite3.connect(tmp_path / "parallel-books/momentum5_10/paper.sqlite") as con:
        assert con.execute("SELECT count(*) FROM paper_trades").fetchone()[0] == 0


def test_late_first_success_uses_actual_account_start_for_benchmark(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = capture()
    snapshot["captured_at"] = capture(61)["captured_at"]
    Clock.current = datetime.fromisoformat(snapshot["captured_at"]) + timedelta(minutes=1)
    monkeypatch.setattr(runner, "datetime", Clock)
    source = tmp_path / "blocked-start.json"
    source.write_text(json.dumps(snapshot), encoding="utf-8")
    failed = runner.run_portfolios(source, tmp_path / "parallel-books")
    assert failed["status"] == "partial_failure"
    successful = invoke(tmp_path, monkeypatch, 63)
    assert successful["status"] == "ok"
    assert successful["launched_at"] == successful["accounts"][0]["launched_at"]
    assert successful["benchmark"]["status"] == "pending"
