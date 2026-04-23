"""Smoke test: CLI starts up and reports version."""

from __future__ import annotations

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
