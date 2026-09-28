"""Operational warnings and unmeasured research outcomes stay visible."""

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


def _app(folder: Path) -> AppTest:
    return AppTest.from_string(
        "from pathlib import Path\nfrom kq.equities.forward_panel import render_forward\n"
        f"render_forward(Path({str(folder)!r}))"
    ).run()


def test_empty_panel_never_creates_research_or_trading_records(tmp_path: Path) -> None:
    app = _app(tmp_path)
    assert not app.exception
    assert any("No prospective" in item.value for item in app.info)
    assert any("not prove" in item.value for item in app.caption)
    assert not list(tmp_path.iterdir())


def test_failed_automation_is_visible_and_not_a_success(tmp_path: Path) -> None:
    (tmp_path / "scheduler-audit.json").write_text(json.dumps({
        "captured_at": "2026-09-28T05:00:00Z", "configured": True,
        "last_run_at": "2026-09-28T04:59:00Z", "last_result": "failure",
    }), encoding="utf-8")
    app = _app(tmp_path)
    assert not app.exception
    assert any("failed run" in item.value for item in app.error)
    assert not (tmp_path / "paper.sqlite").exists()


@pytest.mark.parametrize("status", [None, "invalid_revision"])
def test_empty_or_invalid_outcome_never_promises_waiting_will_fix_it(
    tmp_path: Path, status: str | None,
) -> None:
    (tmp_path / "forward-decisions").mkdir()
    (tmp_path / "forward-decisions" / "test.json").write_text(json.dumps({
        "created_at": "2026-09-28T05:00:00Z", "screen": [],
    }), encoding="utf-8")
    (tmp_path / "forward-snapshot.json").write_text(json.dumps({
        "captured_at": "2026-09-28T04:59:00Z",
    }), encoding="utf-8")
    rows = [] if status is None else [{"status": status}]
    app = AppTest.from_string(
        "from pathlib import Path\nimport pandas as pd\n"
        "import kq.equities.forward_panel as panel\n"
        "from unittest.mock import patch\n"
        f"with patch.object(panel, 'evaluate', return_value=pd.DataFrame({rows!r})):\n"
        f"    panel.render_forward(Path({str(tmp_path)!r}))"
    ).run()
    assert not app.exception
    assert not any("Future completed" in item.value for item in app.info)
    if status is None:
        assert not app.error
        assert any("No selections" in item.value for item in app.info)
    else:
        assert any("evidence is invalid" in item.value for item in app.error)
