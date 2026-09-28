"""User-facing safety and offline import behavior."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from kq.equities import __main__ as cli
from kq.equities.__main__ import main
from kq.equities.report import render_report


def test_invalid_snapshot_does_not_create_ledger(tmp_path: Path) -> None:
    source = tmp_path / "snapshot.json"
    source.write_text(json.dumps({"captured_at": "not-a-time"}), encoding="utf-8")
    ledger = tmp_path / "paper.sqlite"
    assert (
        main(
            [
                "--snapshot",
                str(source),
                "--ledger",
                str(ledger),
                "--report",
                str(tmp_path / "report.html"),
            ]
        )
        == 2
    )
    assert not ledger.exists()


def test_output_cannot_overwrite_input(tmp_path: Path) -> None:
    source = tmp_path / "snapshot.json"
    source.write_text("{}", encoding="utf-8")
    assert (
        main(
            [
                "--snapshot",
                str(source),
                "--ledger",
                str(tmp_path / "paper.sqlite"),
                "--report",
                str(source),
            ]
        )
        == 2
    )
    assert source.read_text() == "{}"


def test_report_escapes_external_text_and_has_no_fake_probability() -> None:
    rows = pd.DataFrame(
        [
            {
                "symbol": "TEST",
                "horizon_sessions": 20,
                "session_date": "2026-09-25",
                "excess_momentum": 0.02,
                "momentum": 0.03,
                "volatility_20d": 0.2,
                "pe_ratio": None,
                "market_cap": 1e9,
                "sector": "<script>bad()</script>",
                "latest_eps_actual": 2.0,
                "latest_eps_estimate": 1.0,
                "news_count": 1,
                "status": "ranked",
            }
        ]
    )
    snapshot = {
        "captured_at": "2026-09-28T00:00:00Z",
        "benchmark": "SPY",
        "news": [
            {
                "symbol": "TEST",
                "title": "<script>bad()</script>",
                "url": "javascript:bad()",
                "published_at": "2026-09-24",
                "retrieved_at": "2026-09-28",
            }
        ],
        "source_errors": [],
    }
    html = render_report(snapshot, rows, {"equity": 100, "cash": 100}, "abc123")
    assert "<script>" not in html
    assert "javascript:" not in html
    assert "&lt;script&gt;" in html
    assert "abc123" in html
    assert "$100.00" in html
    assert "not a probability" in html
    assert "No live orders" in html
    assert "2.00%" in html


def test_missing_news_is_visible() -> None:
    html = render_report(
        {"captured_at": "now", "news": [], "source_errors": ["News feed unavailable"]},
        pd.DataFrame(),
        {},
        "hash",
    )
    assert "News feed unavailable" in html
    assert "No verified news" in html
    assert "No eligible stocks" in html


def test_report_distinguishes_unmeasured_and_invalid_outcomes() -> None:
    html = render_report(
        {},
        pd.DataFrame(),
        {
            "equity_valid": False,
            "forecast_valid": False,
            "forecast_by_horizon": [
                {
                    "horizon_sessions": 20,
                    "count": 0,
                    "mean_stock_return": None,
                    "mean_benchmark_return": None,
                    "mean_excess_return": None,
                }
            ],
        },
        "hash",
    )
    assert "Not yet measured" in html
    assert "Historical prices changed" in html
    assert "overlap" in html


def test_dropped_stock_is_visible_in_report() -> None:
    html = render_report({"universe": ["AAA", "BBB"], "news": []}, pd.DataFrame(), {}, "hash")
    assert "Excluded from rankings" in html
    assert "AAA, BBB" in html


def test_import_uses_creation_time_and_unique_report_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = datetime.now(UTC) - timedelta(hours=3)
    source = tmp_path / "report.html.tmp"
    original = json.dumps({"captured_at": captured.isoformat(), "benchmark": "SPY"})
    source.write_text(original, encoding="utf-8")
    observed: dict[str, Any] = {}

    def ledger(*args: Any, **kwargs: Any) -> dict[str, Any]:
        observed.update(kwargs)
        return {}

    monkeypatch.setattr(cli, "scan", lambda _: pd.DataFrame())
    monkeypatch.setattr(cli, "daily_bars", lambda _: pd.DataFrame())
    monkeypatch.setattr(cli, "update_ledger", ledger)
    assert (
        main(
            [
                "--snapshot",
                str(source),
                "--ledger",
                str(tmp_path / "paper.sqlite"),
                "--report",
                str(tmp_path / "report.html"),
            ]
        )
        == 0
    )
    assert observed["as_of"] > captured + timedelta(hours=2)
    assert source.read_text(encoding="utf-8") == original
