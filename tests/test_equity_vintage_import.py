"""Reviewed source vintages preserve real paper-book chronology."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from kq.equities import __main__ as importer
from kq.equities.dashboard_data import load_dashboard
from kq.equities.session_data import complete_session
from kq.equities.session_vintages import create_review, reconcile_daily


def _seed() -> dict[str, Any]:
    rows = []
    for symbol in ("AAA", "BBB", "SPY"):
        bars = []
        for index, day in enumerate(pd.bdate_range(end="2026-09-25", periods=140)):
            price = 100 + index / 10 if symbol == "AAA" else 100
            bars.append(
                dict(
                    begins_at=day.isoformat() + "Z",
                    session="reg",
                    interpolated=False,
                    open_price=str(price),
                    high_price=str(price),
                    low_price=str(price),
                    close_price=str(price),
                    volume=1_000_000,
                )
            )
        rows.append(dict(symbol=symbol, interval="day", bounds="regular", bars=bars))
    return dict(
        captured_at="2026-09-27T02:00:00+00:00",
        price_as_of="2026-09-27T02:00:00+00:00",
        adjustment_type="split",
        universe=["AAA", "BBB"],
        benchmark="SPY",
        bars=rows,
    )


def _bar(day: str, open_price: int, close_price: int) -> dict[str, Any]:
    return dict(
        begins_at=day + "T00:00:00Z",
        session="reg",
        interpolated=False,
        open_price=str(open_price),
        high_price=str(max(open_price, close_price) + 2),
        low_price=str(min(open_price, close_price) - 2),
        close_price=str(close_price),
        volume=1_000_000,
    )


def _evidence() -> dict[str, Any]:
    prices = {"AAA": (120, 123), "BBB": (150, 153), "SPY": (100, 100)}
    return dict(
        fundamentals_as_of="2026-09-29T01:10:00+00:00",
        quotes_as_of="2026-09-29T01:11:00+00:00",
        fundamentals=[
            dict(
                symbol=symbol,
                bounds="regular",
                market_date="2026-09-28",
                open=str(opening),
                high=str(max(opening, close) + 2),
                low=str(min(opening, close) - 2),
                volume="1000000",
            )
            for symbol, (opening, close) in prices.items()
        ],
        quotes=[
            dict(
                quote=dict(symbol=symbol),
                close=dict(
                    symbol=symbol,
                    date="2026-09-28",
                    price=str(close),
                    interpolated=False,
                    source="sip-list-exchange-close",
                ),
            )
            for symbol, (_, close) in prices.items()
        ],
    )


def _clock(monkeypatch: pytest.MonkeyPatch, at: datetime) -> None:
    class Clock(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return at.astimezone(tz)

    monkeypatch.setattr(importer, "datetime", Clock)


def _import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    snapshot: dict[str, Any],
    at: datetime,
    name: str,
) -> int:
    _clock(monkeypatch, at)
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    return importer.main(
        [
            "--snapshot",
            str(path),
            "--ledger",
            str(tmp_path / "paper.sqlite"),
            "--report",
            str(tmp_path / "report.html"),
        ]
    )


def test_reviewed_history_preserves_fill_and_only_next_completed_open_fills_new_order(  # noqa: PLR0915
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = _seed()
    assert _import(tmp_path, monkeypatch, seed, datetime(2026, 9, 27, 3, tzinfo=UTC), "seed") == 0
    assert load_dashboard(tmp_path)["summary"]["pending_count"] == 1

    raw = copy.deepcopy(seed)
    raw["captured_at"] = "2026-09-29T01:00:00+00:00"
    raw["price_as_of"] = raw["captured_at"]
    evidence = _evidence()
    prior = complete_session(
        raw,
        evidence,
        required={"AAA", "BBB", "SPY"},
        now=datetime(2026, 9, 29, 1, 30, tzinfo=UTC),
    )
    prior["session_evidence"] = evidence
    assert (
        _import(tmp_path, monkeypatch, prior, datetime(2026, 9, 29, 1, 31, tzinfo=UTC), "prior")
        == 0
    )
    original = load_dashboard(tmp_path)["trades"].iloc[0]
    assert original["symbol"] == "AAA"
    assert original["entry_date"] == "2026-09-28"
    assert original["entry_open"] == 120

    published = copy.deepcopy(raw)
    published["captured_at"] = "2026-09-29T02:00:00+00:00"
    published["price_as_of"] = published["captured_at"]
    for series in published["bars"]:
        symbol = series["symbol"]
        opening, close = {"AAA": (121, 123), "BBB": (151, 153), "SPY": (101, 100)}[symbol]
        series["bars"].append(_bar("2026-09-28", opening, close))
    reviewed_at = datetime(2026, 9, 29, 2, 10, tzinfo=UTC)
    review = create_review(
        prior, published, now=reviewed_at, note="Exact September 28 source review"
    )
    legacy = reconcile_daily(
        published,
        prior,
        review,
        required={"AAA", "BBB", "SPY"},
        now=datetime(2026, 9, 29, 2, 11, tzinfo=UTC),
    )
    assert legacy["source_reconciliation"]["entry_count"] == 3
    assert (
        _import(tmp_path, monkeypatch, legacy, datetime(2026, 9, 29, 2, 12, tzinfo=UTC), "reviewed")
        == 0
    )
    same_day = load_dashboard(tmp_path)
    assert len(same_day["trades"]) == 1
    assert same_day["summary"]["pending_count"] == 1
    assert same_day["trades"].iloc[0]["entry_open"] == 120

    unknown = copy.deepcopy(published)
    unknown["bars"][0]["bars"][-1]["open_price"] = "122"
    with pytest.raises(ValueError):
        reconcile_daily(
            unknown,
            prior,
            review,
            required={"AAA", "BBB", "SPY"},
            now=datetime(2026, 9, 29, 2, 15, tzinfo=UTC),
        )
    assert len(load_dashboard(tmp_path)["trades"]) == 1

    next_snapshot = copy.deepcopy(published)
    next_snapshot["captured_at"] = "2026-09-30T01:00:00+00:00"
    next_snapshot["price_as_of"] = next_snapshot["captured_at"]
    for series in next_snapshot["bars"]:
        symbol = series["symbol"]
        opening = {"AAA": 124, "BBB": 152, "SPY": 101}[symbol]
        series["bars"].append(_bar("2026-09-29", opening, opening))
    next_legacy = reconcile_daily(
        next_snapshot,
        legacy,
        review,
        required={"AAA", "BBB", "SPY"},
        now=datetime(2026, 9, 30, 1, 30, tzinfo=UTC),
    )
    at = datetime(2026, 9, 30, 1, 31, tzinfo=UTC)
    assert _import(tmp_path, monkeypatch, next_legacy, at, "next") == 0
    next_day = load_dashboard(tmp_path)
    assert len(next_day["trades"]) == 2
    bbb = next_day["trades"].loc[next_day["trades"].symbol == "BBB"].iloc[0]
    assert bbb["entry_date"] == "2026-09-29"
    assert bbb["entry_open"] == 152
    assert next_day["summary"]["closed_count"] == 0
    assert _import(tmp_path, monkeypatch, next_legacy, at, "retry") == 0
    assert len(load_dashboard(tmp_path)["trades"]) == 2

    previous = next_legacy
    source = next_snapshot
    remaining = pd.bdate_range(start="2026-09-30", periods=18)
    for index, day in enumerate(remaining):
        source = copy.deepcopy(source)
        session = day.date().isoformat()
        captured = day.to_pydatetime().replace(tzinfo=UTC) + timedelta(days=1, hours=1)
        source["captured_at"] = captured.isoformat()
        source["price_as_of"] = captured.isoformat()
        for series in source["bars"]:
            price = {"AAA": 124, "BBB": 152, "SPY": 101}[series["symbol"]]
            series["bars"].append(_bar(session, price, price))
        previous = reconcile_daily(
            source,
            previous,
            review,
            required={"AAA", "BBB", "SPY"},
            now=captured.replace(minute=30),
        )
        assert (
            _import(tmp_path, monkeypatch, previous, captured.replace(minute=31), f"later-{index}")
            == 0
        )
        if index < len(remaining) - 1:
            assert load_dashboard(tmp_path)["summary"]["closed_count"] == 0

    final = load_dashboard(tmp_path)
    assert final["summary"]["closed_count"] == 1
    aaa = final["trades"].loc[final["trades"].symbol == "AAA"].iloc[0]
    assert aaa["exit_date"] == remaining[-1].date().isoformat()
    bbb = final["trades"].loc[final["trades"].symbol == "BBB"].iloc[0]
    assert pd.isna(bbb["exit_date"])
