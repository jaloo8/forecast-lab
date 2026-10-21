"""Artificial input-boundary tests; no market data or real paper accounts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts import local_paper as cli


@pytest.mark.parametrize("asset_type", ["stock", "option"])
def test_printed_template_cannot_launch_a_book(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], asset_type: str
) -> None:
    assert cli.main(["template", "--asset-type", asset_type]) == 0
    template = json.loads(capsys.readouterr().out)
    assert template["initial_cash"] == "1000.00"
    assert template["strategy_sha256"] is None
    if asset_type == "option":
        assert template["instruments"][0]["standard_deliverable"] is None
    registration = tmp_path / "incomplete.json"
    registration.write_text(json.dumps(template), encoding="utf-8")
    assert cli.main(["create", "--root", str(tmp_path), "--registration", str(registration)]) == 2
    assert not (tmp_path / template["book_id"]).exists()
    assert not list(tmp_path.rglob("*.sqlite"))


@pytest.mark.parametrize(
    "payload",
    [
        '{"quantity": 1, "quantity": 2}',
        '{"bid": NaN}',
        '{"ask": Infinity}',
        '{"nested": [{"api_key": "SYNTHETIC_SENSITIVE_MARKER"}]}',
        "[]",
        '{"broken": "SYNTHETIC_SENSITIVE_MARKER"',
    ],
)
def test_unsafe_json_cannot_reach_storage_and_is_not_echoed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], payload: str
) -> None:
    source = tmp_path / "input.json"
    source.write_text(payload, encoding="utf-8")
    assert cli.main(["intent", "--book", str(tmp_path / "absent"), "--input", str(source)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "SYNTHETIC_SENSITIVE_MARKER" not in captured.err
    assert not (tmp_path / "absent").exists()


def test_file_size_limit_does_not_truncate_into_valid_input(tmp_path: Path) -> None:
    path = tmp_path / "oversized.json"
    path.write_bytes(b"{}" + b" " * cli._MAX_INPUT_BYTES)
    with pytest.raises(ValueError, match="limit"):
        cli.read_input(path)


def test_clock_override_is_not_a_cli_option(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(["status", "--book", "unused", "--now", "2000-01-01T00:00:00Z"])
    assert error.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err


def test_recorded_quote_refusal_is_visible_to_the_shell(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The process must not report success when the engine persisted a rejection."""
    source = tmp_path / "quote.json"
    source.write_text('{"quote_id":"fixture"}', encoding="utf-8")
    monkeypatch.setattr(cli.local_paper, "observe_quote", lambda *_: {"accepted": False})
    assert cli.main(["quote", "--book", str(tmp_path), "--input", str(source)]) == 2
    assert json.loads(capsys.readouterr().out) == {"accepted": False}
