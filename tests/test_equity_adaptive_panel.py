"""The adaptive advisory view reads verified evidence without altering it."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from kq.equities import adaptive_journal as journal

NOW = datetime(2026, 9, 29, 3, tzinfo=UTC)


def _app(folder: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    monkeypatch.setattr("kq.equities.adaptive_panel._now", lambda: NOW)
    return AppTest.from_string(
        "from pathlib import Path\n"
        "from kq.equities.adaptive_panel import render_adaptive\n"
        f"render_adaptive(Path({str(folder)!r}))"
    ).run()


def _text(app: AppTest) -> str:
    return " ".join(
        str(item.value)
        for group in (app.warning, app.error, app.info, app.caption, app.markdown, app.metric)
        for item in group
    )


def _journal(
    folder: Path,
    *,
    captured: str = "2026-09-29T02:00:00+00:00",
    price_as_of: str | None = None,
    reference_source_as_of: str | None = None,
    reference_observed_at: str | None = None,
    created_at: str = "2026-09-29T03:00:00+00:00",
    omit_price: bool = False,
    failure: bool = False,
) -> Path:
    root = folder / "adaptive-research"
    root.mkdir()
    path = root / "journal.sqlite"
    evidence = {
        "snapshot": {"captured_at": captured},
        "reference": {
            "kind": "original_pilot_read_only",
            "source_as_of": reference_source_as_of or captured,
            "observed_at": reference_observed_at or created_at,
        },
    }
    rows = [
        dict(
            symbol=symbol,
            score=score,
            excess20=0.12,
            excess60=0.26,
            volatility20=0.02,
            state=state,
            action=action,
            reason=reason,
            candidate_eligible=True,
            source_hash=journal._digest(evidence["snapshot"]),
            method_hash=journal.METHOD_HASH,
            as_of=captured,
            price_as_of=price_as_of if price_as_of is not None else captured,
            event_refs=[],
        )
        for symbol, score, state, action, reason in (
            ("AAA", 0.8, "flat", "BUY", "buy_threshold_met"),
            ("BBB", 0.3, "held", "HOLD", "positive_hold_band"),
            ("CCC", -0.2, "held", "SELL", "nonpositive_exit"),
            ("DDD", 0.9, "pending_entry", "PENDING", "pending_order"),
            ("EEE", 0.1, "flat", "WATCH", "below_buy_threshold"),
            ("FFF", None, "flat", "WAIT_DATA", "missing_stock_session"),
        )
    ]
    if omit_price:
        rows[0].pop("price_as_of")
    artifact: dict[str, Any] = dict(
        created_at=created_at,
        input_captured_at=captured,
        session_date="2026-09-28",
        source_hash=journal._digest(evidence["snapshot"]),
        reference_hash=journal._digest(evidence["reference"]),
        method_hash=journal.METHOD_HASH,
        protocol=journal.PROTOCOL,
        reference_kind="original_pilot_read_only",
        reference=evidence["reference"],
        mode="advisory_only",
        rows=rows,
        source_errors=["price source incomplete"],
        news=[
            {
                "symbol": "AAA",
                "title": "Example event",
                "url": "https://example.com/event",
                "published_at": captured,
                "retrieved_at": captured,
            }
        ],
    )
    with sqlite3.connect(path) as con:
        journal._check(con, initialize=True)
        con.execute(
            "INSERT INTO decisions VALUES(?,?,?,?)",
            (
                artifact["session_date"],
                journal._encoded(artifact),
                journal._digest(artifact),
                journal._encoded(evidence),
            ),
        )
        con.execute(
            "INSERT INTO attempts(attempted_at,status,error,evidence) VALUES(?,?,?,?)",
            (
                "2026-09-29T03:00:00+00:00",
                "failure" if failure else "success",
                "source revised" if failure else "",
                journal._encoded(evidence),
            ),
        )
    return path


def test_missing_journal_is_clear_and_does_not_create_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _app(tmp_path, monkeypatch)
    assert not app.exception
    assert "No adaptive research" in _text(app)
    assert not (tmp_path / "adaptive-research").exists()


def test_verified_advice_shows_states_components_and_source_context_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _journal(tmp_path)
    before = path.read_bytes()
    app = _app(tmp_path, monkeypatch)
    assert not app.exception
    assert path.read_bytes() == before
    visible = _text(app)
    for phrase in (
        "original pilot",
        "advisory",
        "No orders",
        "profit",
        "News metadata",
        "incomplete",
        "2026-09-29",
        "price source incomplete",
    ):
        assert phrase.lower() in visible.lower()
    frames = [table.value for table in app.dataframe]
    assert any(
        {"BUY", "HOLD", "SELL", "PENDING", "WATCH", "WAIT_DATA"}.issubset(set(frame["Action"]))
        for frame in frames
        if "Action" in frame
    )
    assert any(
        {
            "Score",
            "Excess 20",
            "Excess 60",
            "Volatility 20",
            "Reason",
            "Reference state",
            "Price as of",
        }.issubset(frame.columns)
        for frame in frames
    )
    assert "pending" in visible.lower()
