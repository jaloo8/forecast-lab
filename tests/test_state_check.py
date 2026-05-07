"""Tests for `kq state-check` — Kalshi sports geofence verification."""

from __future__ import annotations

import json

import pytest

from kq.flows.state_check import (
    SNAPSHOT_DATE,
    look_up,
    main,
    render_human,
)

# ----------------------------------------------------------- look_up


def test_look_up_returns_blocked_for_az() -> None:
    """AZ has criminal charges as of March 17 2026."""
    row = look_up("AZ")
    assert row.status == "criminal"
    assert "criminal" in row.notes.lower()


def test_look_up_returns_blocked_for_ma() -> None:
    """MA: Suffolk County preliminary injunction Jan 20 2026."""
    row = look_up("MA")
    assert row.status == "blocked"
    assert "Suffolk" in row.notes


def test_look_up_returns_contested_for_ny() -> None:
    """NY is in the contested-but-not-yet-adjudicated bucket."""
    row = look_up("NY")
    assert row.status == "contested"


def test_look_up_returns_green_for_nj() -> None:
    """NJ is explicitly green after the 3rd Circuit ruling."""
    row = look_up("NJ")
    assert row.status == "green"
    assert "3rd Circuit" in row.notes


def test_look_up_returns_green_for_tn() -> None:
    """TN is explicitly green after Feb 19 2026 prelim injunction."""
    row = look_up("TN")
    assert row.status == "green"
    assert "Tenn" in row.notes


def test_look_up_returns_green_default_for_listed_quiet_state() -> None:
    """Pick a state with no known challenge — should default-green."""
    row = look_up("CA")
    assert row.status == "green"
    assert "No active Kalshi-sports challenge" in row.notes


def test_look_up_is_case_insensitive() -> None:
    a = look_up("ca")
    b = look_up("CA")
    c = look_up("Ca")
    assert a == b == c


def test_look_up_strips_whitespace() -> None:
    assert look_up("  CA  ") == look_up("CA")


def test_look_up_rejects_unknown_state() -> None:
    with pytest.raises(ValueError, match="unknown state code"):
        look_up("XX")


def test_look_up_rejects_lowercase_unknown() -> None:
    with pytest.raises(ValueError, match="unknown state code"):
        look_up("zz")


# ----------------------------------------------------------- render_human


def test_render_human_includes_status_glyph_and_state() -> None:
    row = look_up("AZ")
    out = render_human(row)
    assert "AZ" in out
    assert "CRIMINAL" in out
    assert "[ERR]" in out


def test_render_human_includes_weather_note_by_default() -> None:
    """All 50 states have weather; the summary should always say so."""
    row = look_up("CA")
    out = render_human(row)
    assert "Weather contracts" in out
    assert "all 50 states" in out


def test_render_human_includes_recommendation_for_blocked() -> None:
    out = render_human(look_up("MA"))
    assert "Recommendation" in out
    assert "do NOT enable `--live`" in out


def test_render_human_includes_recommendation_for_contested() -> None:
    out = render_human(look_up("OH"))
    assert "Recommendation" in out
    assert "legally risky" in out


def test_render_human_no_recommendation_for_green() -> None:
    out = render_human(look_up("CA"))
    assert "Recommendation" not in out


# ----------------------------------------------------------- main entrypoint


def test_main_returns_2_when_state_unset(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No --state and no env var → exit 2 with explanation."""
    monkeypatch.setenv("OPERATOR_STATE", "")
    # Clear cached settings.
    from kq import config as _cfg  # noqa: PLC0415

    _cfg.get_settings.cache_clear()

    code = main(state=None, json_output=False)
    assert code == 2
    captured = capsys.readouterr()
    assert "OPERATOR_STATE" in captured.out


def test_main_returns_0_for_green(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit green state → exit 0."""
    monkeypatch.setenv("OPERATOR_STATE", "")
    from kq import config as _cfg  # noqa: PLC0415

    _cfg.get_settings.cache_clear()

    code = main(state="CA")
    assert code == 0
    captured = capsys.readouterr()
    assert "CA" in captured.out


def test_main_returns_1_for_contested(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPERATOR_STATE", "")
    from kq import config as _cfg  # noqa: PLC0415

    _cfg.get_settings.cache_clear()

    code = main(state="OH")
    assert code == 1


def test_main_returns_2_for_blocked(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPERATOR_STATE", "")
    from kq import config as _cfg  # noqa: PLC0415

    _cfg.get_settings.cache_clear()

    code = main(state="MA")
    assert code == 2


def test_main_returns_2_for_criminal(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criminal-risk states (AZ) exit with same code as blocked."""
    monkeypatch.setenv("OPERATOR_STATE", "")
    from kq import config as _cfg  # noqa: PLC0415

    _cfg.get_settings.cache_clear()

    code = main(state="AZ")
    assert code == 2


def test_main_reads_env_var_when_no_flag(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPERATOR_STATE", "TX")
    from kq import config as _cfg  # noqa: PLC0415

    _cfg.get_settings.cache_clear()

    code = main(state=None)
    assert code == 0  # TX is green
    captured = capsys.readouterr()
    assert "TX" in captured.out


def test_main_flag_overrides_env(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPERATOR_STATE", "TX")
    from kq import config as _cfg  # noqa: PLC0415

    _cfg.get_settings.cache_clear()

    # Pass --state explicitly; should beat env.
    code = main(state="MA")
    assert code == 2
    captured = capsys.readouterr()
    assert "MA" in captured.out
    assert "TX" not in captured.out


def test_main_invalid_state_returns_2(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPERATOR_STATE", "")
    from kq import config as _cfg  # noqa: PLC0415

    _cfg.get_settings.cache_clear()

    code = main(state="ZZ")
    assert code == 2
    captured = capsys.readouterr()
    assert "unknown state code" in captured.out


# ----------------------------------------------------------- json output


def test_main_json_output_round_trips(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The --json output must be parseable + carry the snapshot date.

    structlog may also write to stdout in unconfigured test environments,
    so we extract the first line (the print()-emitted JSON object) rather
    than parsing the whole capture.
    """
    monkeypatch.setenv("OPERATOR_STATE", "")
    from kq import config as _cfg  # noqa: PLC0415

    _cfg.get_settings.cache_clear()

    code = main(state="CA", json_output=True)
    assert code == 0
    captured = capsys.readouterr()
    # The first line is our print()'d JSON. Subsequent lines may be log output.
    json_line = captured.out.splitlines()[0]
    parsed = json.loads(json_line)
    assert parsed["state"] == "CA"
    assert parsed["status"] == "green"
    assert parsed["snapshot_date"] == SNAPSHOT_DATE.isoformat()


def test_state_row_dataclass_immutable() -> None:
    """StateRow is frozen — attempting to mutate must raise."""
    row = look_up("CA")
    with pytest.raises((AttributeError, TypeError)):
        row.status = "criminal"  # type: ignore[misc]
