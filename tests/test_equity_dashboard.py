"""The dashboard must show honest empty states and never initiate imports."""

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest


def test_missing_paper_data_is_not_a_fake_account(tmp_path: Path) -> None:
    app = AppTest.from_string(
        "from pathlib import Path\n"
        "from kq.equities.dashboard import main\n"
        f"main(Path({str(tmp_path)!r}))"
    ).run()
    assert not app.exception
    assert app.warning
    assert not app.metric
    assert not (tmp_path / "paper.sqlite").exists()


def test_dashboard_shows_pending_without_claiming_wins() -> None:
    data = {
        "summary": {
            "equity": 100,
            "cash": 100,
            "reserved_cash": 30,
            "pnl": 0,
            "pending_count": 3,
            "open_count": 0,
            "closed_count": 0,
            "forecast_settled_count": 0,
            "equity_valid": True,
            "forecast_valid": True,
            "forecast_by_horizon": [],
        },
        "state": {"last_source_as_of": "2026-09-28T03:15:19+00:00"},
        "orders": pd.DataFrame([{"symbol": "AAPL", "status": "pending", "reserved": 10}]),
        "trades": pd.DataFrame(),
        "forecasts": pd.DataFrame(),
        "source": None,
        "source_warning": "Matching capture unavailable",
        "win_rate": None,
    }
    app = AppTest.from_string(
        "from kq.equities.dashboard import render_dashboard\n"
        "import streamlit as st\nrender_dashboard(st.session_state['data'])"
    )
    app.session_state["data"] = data
    app.run()
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Overview", "Trades", "Research", "Data health"]
    assert any(metric.value == "$100.00" for metric in app.metric)
    assert "Not yet measured" in " ".join(item.value for item in app.info)
    data["summary"]["equity_valid"] = False
    data["summary"]["forecast_valid"] = False
    data["summary"]["cash"] = None
    app.session_state["data"] = data
    app.run()
    assert not app.exception
    assert all(metric.label != "Virtual balance" for metric in app.metric)
    assert app.error
    data["trades"] = pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "entry_date": "2026-09-28",
                "exit_date": "2026-10-23",
                "entry_cost": 10,
                "shares": 0.1,
                "net_pnl": 2,
            }
        ]
    )
    app.session_state["data"] = data
    app.radio[0].set_value("Closed").run()
    assert not app.exception
    assert "Net profit ($)" not in app.dataframe[0].value.columns
    assert any("withheld" in item.value for item in app.warning)
