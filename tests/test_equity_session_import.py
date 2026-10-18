"""Session-source fallback flows through the unchanged paper execution accounting."""

from __future__ import annotations

import json
import runpy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from kq.equities import __main__ as cli
from kq.equities.dashboard_data import load_dashboard
from kq.equities.session_data import complete_session


def test_actual_cli_fills_prior_order_once_after_verified_completed_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Clock(datetime):
        current = datetime(2026, 9, 27, 3, tzinfo=UTC)

        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return cls.current.astimezone(tz)

    monkeypatch.setattr(cli, "datetime", Clock)
    bars = []
    for symbol in ("AAA", "SPY"):
        series = []
        for i, day in enumerate(pd.bdate_range(end="2026-09-25", periods=140)):
            price = 100 + i / 10 if symbol == "AAA" else 100
            series.append(
                dict(
                    begins_at=day.isoformat() + "Z",
                    session="reg",
                    open_price=str(price),
                    high_price=str(price),
                    low_price=str(price),
                    close_price=str(price),
                    volume=1_000_000,
                )
            )
        bars.append(dict(symbol=symbol, interval="day", bounds="regular", bars=series))
    source = dict(
        captured_at="2026-09-27T02:00:00+00:00",
        adjustment_type="split",
        universe=["AAA"],
        benchmark="SPY",
        bars=bars,
    )
    path = tmp_path / "snapshot-seed.json"
    path.write_text(json.dumps(source))
    args = [
        "--snapshot",
        str(path),
        "--ledger",
        str(tmp_path / "paper.sqlite"),
        "--report",
        str(tmp_path / "report.html"),
    ]
    assert cli.main(args) == 0
    assert load_dashboard(tmp_path)["summary"]["pending_count"] == 1
    source["captured_at"] = "2026-09-29T01:00:00+00:00"
    evidence = dict(
        fundamentals_as_of="2026-09-29T01:10:00+00:00",
        quotes_as_of="2026-09-29T01:11:00+00:00",
        fundamentals=[
            dict(
                symbol=s,
                bounds="regular",
                market_date="2026-09-28",
                open="120",
                high="124",
                low="119",
                volume="1000000",
            )
            for s in ("AAA", "SPY")
        ],
        quotes=[
            dict(
                quote=dict(symbol=s),
                close=dict(
                    symbol=s,
                    date="2026-09-28",
                    price="123",
                    interpolated=False,
                    source="sip-list-exchange-close",
                ),
            )
            for s in ("AAA", "SPY")
        ],
    )
    Clock.current = datetime(2026, 9, 29, 1, 30, tzinfo=UTC)
    result = complete_session(source, evidence, required={"AAA", "SPY"}, now=Clock.current)
    path = tmp_path / "snapshot-complete.json"
    path.write_text(json.dumps(result))
    args[1] = str(path)
    assert cli.main(args) == 0
    loaded = load_dashboard(tmp_path)
    assert loaded["summary"]["open_count"] == 1
    assert loaded["summary"]["cash"] == 90
    assert loaded["summary"]["closed_count"] == 0
    trade = loaded["trades"].iloc[0]
    assert trade["entry_date"] == "2026-09-28"
    assert trade["entry_open"] == 120
    assert trade["shares"] == pytest.approx(10 / (120 * 1.001))
    assert cli.main(args) == 0
    assert len(load_dashboard(tmp_path)["trades"]) == 1


@pytest.mark.parametrize("failure", ["tool", "closes", "not_found", "future", "naive"])
def test_raw_source_errors_cannot_be_hidden_by_assembly(tmp_path: Path, failure: str) -> None:
    capture: dict[str, Any] = {
        "retrieved_at": datetime.now(UTC).isoformat(),
        "response": {"structuredContent": {"data": {"results": [{"symbol": "AAA"}]}}},
    }
    response = capture["response"]
    if failure == "tool":
        response["isError"] = True
    elif failure == "closes":
        response["structuredContent"]["data"]["closes_error"] = "timeout"
    elif failure == "not_found":
        response["structuredContent"]["data"]["not_found"] = ["AAA"]
    elif failure == "future":
        capture["retrieved_at"] = "2099-01-01T00:00:00+00:00"
    else:
        capture["retrieved_at"] = "2026-09-29T01:00:00"
    path = tmp_path / "raw.json"
    path.write_text(json.dumps(capture))
    reader = runpy.run_path(str(Path(__file__).parents[1] / "scripts/complete_stock_session.py"))[
        "read_sources"
    ]
    with pytest.raises(ValueError):
        reader([path], "fundamentals")
