"""Tests for the scheduled observed-truth ingest flow (PR-G, audit #7)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from kq.__main__ import app
from kq.flows import ingest_observed as mod


def _capture_backfill(
    monkeypatch: pytest.MonkeyPatch, captured: dict[str, Any], rows: int = 18
) -> None:
    async def fake_backfill(
        *, start_date: date, end_date: date, db_path: Path | None = None
    ) -> int:
        captured["start"] = start_date
        captured["end"] = end_date
        captured["db_path"] = db_path
        return rows

    monkeypatch.setattr(mod, "backfill", fake_backfill)


async def test_default_window_is_trailing_3_days(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, Any] = {}
    _capture_backfill(monkeypatch, captured)
    n = await mod.ingest_once(db_path=tmp_path / "x.duckdb")
    assert n == 18
    start, end = captured["start"], captured["end"]
    assert (end - start).days == mod.DEFAULT_LOOKBACK_DAYS == 3
    # end is "today" in UTC; tolerate a midnight crossing during the test.
    assert abs((end - datetime.now(tz=UTC).date()).days) <= 1
    assert captured["db_path"] == tmp_path / "x.duckdb"


async def test_custom_lookback_widens_the_window(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _capture_backfill(monkeypatch, captured)
    await mod.ingest_once(lookback_days=10)
    assert (captured["end"] - captured["start"]).days == 10


async def test_lookback_days_must_be_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _capture_backfill(monkeypatch, captured)
    with pytest.raises(ValueError, match="lookback_days"):
        await mod.ingest_once(lookback_days=0)
    assert not captured  # backfill never reached


def test_main_prints_summary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def fake_ingest_once(*, lookback_days: int = 3, db_path: Path | None = None) -> int:
        return 24

    monkeypatch.setattr(mod, "ingest_once", fake_ingest_once)
    mod.main()
    out = capsys.readouterr().out
    assert "24 observed daily rows" in out


def test_cli_command_registered() -> None:
    """`kq ingest-observed` exists so the cron entry in SCHEDULED-RUNS.md works."""
    result = CliRunner().invoke(app, ["ingest-observed", "--help"])
    assert result.exit_code == 0
    assert "lookback-days" in result.stdout
