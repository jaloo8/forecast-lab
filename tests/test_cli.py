"""Smoke test: CLI starts up and reports version."""

from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from kq.__main__ import app


def test_version_command() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip()


def test_help_includes_phase_reference() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "CLAUDE.md" in result.stdout


def test_log_json_pretty_is_a_real_tri_state() -> None:
    """--log-json forces JSON, --log-pretty forces pretty, neither = auto
    (None). Pre-audit the bool collapsed --log-pretty into auto-detect."""
    runner = CliRunner()
    calls: list[object] = []

    def _capture(**kwargs: object) -> None:
        calls.append(kwargs.get("json_output"))

    with patch("kq.__main__.setup_logging", side_effect=_capture):
        assert runner.invoke(app, ["version"]).exit_code == 0
        assert runner.invoke(app, ["--log-json", "version"]).exit_code == 0
        assert runner.invoke(app, ["--log-pretty", "version"]).exit_code == 0
    assert calls == [None, True, False]


def test_paper_summary_malformed_date_exits_2() -> None:
    """Exit 1 is the documented 'still accumulating, no alert' code — a
    malformed --start/--end must exit 2 (fundamental error), not 1."""
    runner = CliRunner()
    result = runner.invoke(app, ["paper-summary", "--start", "not-a-date"])
    assert result.exit_code == 2
    output = result.output + str(result.stderr or "")
    assert "YYYY-MM-DD" in output
