"""Stale, malformed, and failed advisory evidence must not look current."""

import sqlite3
from pathlib import Path

import pytest

from tests.test_equity_adaptive_panel import _app, _journal, _text


@pytest.mark.parametrize("condition", ["stale", "failed"])
def test_stale_or_failed_attempt_withholds_current_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, condition: str
) -> None:
    _journal(
        tmp_path,
        captured="2026-09-27T02:00:00+00:00"
        if condition == "stale"
        else "2026-09-29T02:00:00+00:00",
        failure=condition == "failed",
    )
    app = _app(tmp_path, monkeypatch)
    assert not app.exception
    assert "withheld" in _text(app).lower()
    assert not any(
        "Action" in table.value and "BUY" in set(table.value["Action"]) for table in app.dataframe
    )


def test_older_price_evidence_withholds_buy_despite_recent_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _journal(tmp_path, price_as_of="2026-09-28T02:00:00+00:00")
    app = _app(tmp_path, monkeypatch)
    assert not app.exception
    assert "price" in _text(app).lower()
    assert "withheld" in _text(app).lower()
    assert any("Historical suggestions" in item.label for item in app.expander)
    assert not any("Action" in table.value for table in app.dataframe)


def test_older_reference_evidence_withholds_buy_despite_recent_price(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _journal(tmp_path, reference_source_as_of="2026-09-28T02:00:00+00:00")
    app = _app(tmp_path, monkeypatch)
    assert not app.exception
    assert "reference" in _text(app).lower()
    assert "withheld" in _text(app).lower()
    assert not any("Action" in table.value for table in app.dataframe)


def test_reference_observation_after_decision_cannot_show_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _journal(tmp_path, reference_observed_at="2026-09-29T04:00:00+00:00")
    app = _app(tmp_path, monkeypatch)
    assert not app.exception
    assert "cannot be verified" in _text(app).lower()
    assert not any("Action" in table.value for table in app.dataframe)


def test_missing_price_timestamp_cannot_show_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _journal(tmp_path, omit_price=True)
    app = _app(tmp_path, monkeypatch)
    assert not app.exception
    assert "cannot be verified" in _text(app).lower()
    assert not any("Action" in table.value for table in app.dataframe)


@pytest.mark.parametrize(
    ("price_as_of", "created_at"),
    [
        ("invalid", "2026-09-29T03:00:00+00:00"),
        ("2026-09-29T02:00:00+00:00", "2026-09-30T03:00:00+00:00"),
        ("2026-09-29T02:00:00+00:00", "2026-09-29T01:00:00+00:00"),
    ],
)
def test_invalid_evidence_chronology_never_shows_current_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, price_as_of: str, created_at: str
) -> None:
    _journal(tmp_path, price_as_of=price_as_of, created_at=created_at)
    app = _app(tmp_path, monkeypatch)
    assert not app.exception
    assert "cannot be verified" in _text(app).lower()
    assert not any("Action" in table.value for table in app.dataframe)


@pytest.mark.parametrize("invalid", ["{}", "[]"])
def test_corrupt_journal_is_not_displayed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    path = _journal(tmp_path)
    with sqlite3.connect(path) as con:
        con.execute("UPDATE decisions SET artifact=?", (invalid,))
    before = path.read_bytes()
    app = _app(tmp_path, monkeypatch)
    assert not app.exception
    assert "cannot be verified" in _text(app).lower()
    assert not app.dataframe
    assert path.read_bytes() == before
