"""End-to-end synthetic captures through the offline equity paper workflow.

These paths test accounting and point-in-time behavior, not investment performance.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from kq.equities import __main__ as cli
from kq.equities.dashboard_data import load_dashboard
from kq.equities.research import scan


class _Clock(datetime):
    current: datetime

    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)


def _sessions() -> list[datetime]:
    days = pd.bdate_range("2026-03-02", periods=147)
    return [day.to_pydatetime().replace(tzinfo=UTC) for day in days]


def _prices(shape: str, count: int) -> dict[str, list[tuple[float, float]]]:
    spy = [(100.0, 100.0) for _ in range(count)]
    bbb = [(100.0, 100.0) for _ in range(count)]
    aaa: list[tuple[float, float]] = []
    previous = 100.0
    for index in range(count):
        if index < 127:
            close = 100.0 + 0.1 * index
        else:
            future = index - 126
            close = {
                "rising": 112.6 + 0.4 * future,
                "falling": 112.6 - 0.4 * future,
                "volatile": 112.6 + (3.0 if future % 2 else -2.0) + 0.05 * future,
            }[shape]
        aaa.append((previous, close))
        previous = close
    return {"AAA": aaa, "BBB": bbb, "SPY": spy}


def _snapshot(
    sessions: list[datetime], prices: dict[str, list[tuple[float, float]]],
    last: int, news: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    captured = sessions[last] + timedelta(days=1, hours=3)
    results = []
    for symbol in ("AAA", "BBB", "SPY"):
        bars = []
        for day, (open_price, close_price) in zip(
            sessions[: last + 1], prices[symbol][: last + 1], strict=True
        ):
            bars.append({
                "begins_at": day.isoformat().replace("+00:00", "Z"),
                "open_price": str(open_price), "close_price": str(close_price),
                "high_price": str(max(open_price, close_price) + 1),
                "low_price": str(min(open_price, close_price) - 1),
                "volume": 1_000_000, "session": "reg",
            })
        results.append({"symbol": symbol, "interval": "day", "bounds": "regular", "bars": bars})
    return {
        "captured_at": captured.isoformat(), "benchmark": "SPY",
        "universe": ["AAA", "BBB"],
        "bars": {"data": {"results": results}},
        "fundamentals": {"data": {"results": []}},
        "earnings": {"data": {"results": []}},
        "news": news or [], "source_errors": [],
    }


def _import(
    tmp_path: Path, snapshot: dict[str, Any], name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[int, Path]:
    path = tmp_path / f"snapshot-{name}.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    _Clock.current = datetime.fromisoformat(snapshot["captured_at"]) + timedelta(minutes=10)
    monkeypatch.setattr(cli, "datetime", _Clock)
    result = cli.main([
        "--snapshot", str(path), "--ledger", str(tmp_path / "paper.sqlite"),
        "--report", str(tmp_path / "report.html"),
    ])
    return result, path


@pytest.mark.parametrize("shape", ["rising", "falling", "volatile"])
def test_daily_workflow_settles_next_open_and_20_session_horizon(
    shape: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = _sessions()
    prices = _prices(shape, len(sessions))
    initial = _snapshot(sessions, prices, 126)
    assert _import(tmp_path, initial, "initial", monkeypatch)[0] == 0
    first = load_dashboard(tmp_path)
    assert first["summary"]["pending_count"] == 1
    assert first["summary"]["open_count"] == 0
    assert first["summary"]["cash"] == pytest.approx(100)
    assert first["summary"]["reserved_cash"] == pytest.approx(10)
    assert first["source"]["news"] == []
    assert first["forecasts"]["exit_date"].isna().all()

    for index in range(127, 147):
        snapshot = _snapshot(sessions, prices, index)
        assert _import(tmp_path, snapshot, str(index), monkeypatch)[0] == 0
        view = load_dashboard(tmp_path)
        if index == 127:
            opened = view["trades"].iloc[0]
            assert opened["entry_date"] == sessions[127].date().isoformat()
            assert opened["entry_open"] == pytest.approx(prices["AAA"][127][0])
            assert opened["entry_cost"] == pytest.approx(10)
            assert view["summary"]["cash"] == pytest.approx(90)
            assert view["summary"]["open_count"] == 1
        if index == 130:
            assert view["summary"]["forecast_settled_count"] == 0

    view = load_dashboard(tmp_path)
    trade = view["trades"].iloc[0]
    entry_open = prices["AAA"][127][0]
    exit_close = prices["AAA"][146][1]
    expected_shares = 10 / (entry_open * 1.001)
    expected_proceeds = expected_shares * exit_close * 0.999
    assert trade["exit_date"] == sessions[146].date().isoformat()
    assert trade["shares"] == pytest.approx(expected_shares)
    assert trade["proceeds"] == pytest.approx(expected_proceeds)
    assert trade["net_pnl"] == pytest.approx(expected_proceeds - 10)
    assert view["summary"]["closed_count"] == 1
    assert view["summary"]["cash"] == pytest.approx(100 + expected_proceeds - 10)
    assert view["summary"]["pnl"] == pytest.approx(expected_proceeds - 10, abs=1e-6)
    assert view["summary"]["equity_valid"] is True
    initial_forecasts = view["forecasts"].loc[
        (view["forecasts"]["symbol"] == "AAA")
        & (view["forecasts"]["source_as_of"] == initial["captured_at"])
    ]
    for horizon in (5, 20):
        forecast = initial_forecasts.loc[initial_forecasts["horizon"] == horizon].iloc[0]
        assert forecast["entry_date"] == sessions[127].date().isoformat()
        assert forecast["exit_date"] == sessions[126 + horizon].date().isoformat()
        assert forecast["stock_return"] == pytest.approx(
            prices["AAA"][126 + horizon][1] / entry_open - 1
        )
        assert forecast["benchmark_return"] == pytest.approx(0)
    assert len(initial_forecasts.loc[initial_forecasts["horizon"] == 126]) == 1
    assert pd.isna(initial_forecasts.loc[initial_forecasts["horizon"] == 126].iloc[0]["exit_date"])


def test_news_is_context_only_and_invalid_capture_is_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = _sessions()
    prices = _prices("rising", len(sessions))
    initial = _snapshot(sessions, prices, 126)
    assert _import(tmp_path, initial, "initial", monkeypatch)[0] == 0
    report = tmp_path / "report.html"
    ledger = tmp_path / "paper.sqlite"
    title = "Future filing available after day three"
    news = [{
        "symbol": "AAA", "title": title, "url": "https://example.org/filing",
        "kind": "filing",
        "published_at": (sessions[129] + timedelta(hours=17)).isoformat(),
        "retrieved_at": (sessions[129] + timedelta(hours=22)).isoformat(),
    }]
    invalid = copy.deepcopy(initial)
    invalid["news"] = news
    before_db = hashlib.sha256(ledger.read_bytes()).digest()
    before_report = report.read_bytes()
    assert _import(tmp_path, invalid, "invalid", monkeypatch)[0] == 2
    assert hashlib.sha256(ledger.read_bytes()).digest() == before_db
    assert report.read_bytes() == before_report
    assert title not in report.read_text(encoding="utf-8")
    assert load_dashboard(tmp_path)["source"]["news"] == []

    assert _import(tmp_path, initial, "initial", monkeypatch)[0] == 0
    assert hashlib.sha256(ledger.read_bytes()).digest() == before_db
    for index in range(127, 130):
        capture = _snapshot(sessions, prices, index, news if index == 129 else None)
        assert _import(tmp_path, capture, str(index), monkeypatch)[0] == 0
        if index < 129:
            assert title not in report.read_text(encoding="utf-8")
    with_news = _snapshot(sessions, prices, 129, news)
    without_news = _snapshot(sessions, prices, 129)
    ranked_news = scan(with_news).set_index(["symbol", "horizon_sessions"])
    ranked_plain = scan(without_news).set_index(["symbol", "horizon_sessions"])
    assert ranked_news.loc[("AAA", 20), "news_count"] == 1
    assert ranked_plain.loc[("AAA", 20), "news_count"] == 0
    pd.testing.assert_series_equal(
        ranked_news["excess_momentum"], ranked_plain["excess_momentum"]
    )
    assert title in report.read_text(encoding="utf-8")
    assert load_dashboard(tmp_path)["source"]["news"] == news
