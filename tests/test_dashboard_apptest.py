"""Render-path smoke for the Streamlit dashboard via the official AppTest.

`panels.py` is unit-tested and the module imports clean, but neither proves
the *app actually renders* — a Streamlit API misuse, a None-handling slip in
a tab body, or a bad `st.tabs` unpacking only surfaces when the script runs
through Streamlit's runtime. `streamlit.testing.v1.AppTest` runs the script
in-process (no server, no socket — so the network guard is untripped) and
exposes the rendered element tree, so we can assert the whole app renders
without raising and the wired-in tabs (#85: Conformal coverage + NBA CLV)
are present.

Robust to environment: the DB-touching tabs (Paper, Data health) wrap their
DuckDB access in try/except and render an error string rather than crashing,
and the manifest-reading tabs use defensive `.get(...)`, so this passes with a
missing/empty DB and whatever manifests are committed — it asserts structure,
not data.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# AppTest ships with streamlit (>=1.28); skip cleanly if unavailable.
AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

_APP = "src/kq/dashboard/streamlit_app.py"
_EXPECTED_TABS = [
    "Router",
    "Backtest",
    "Reliability",
    "Paper trades",
    "Nowcast edge",
    "NBA CLV",
    "Data health",
]


def _run() -> AppTest:
    return AppTest.from_file(_APP, default_timeout=90).run()


def test_dashboard_renders_without_exception() -> None:
    """The whole script runs through the Streamlit runtime with no uncaught
    exception in any tab body."""
    at = _run()
    assert not at.exception, f"dashboard raised: {list(at.exception)}"


def test_dashboard_has_all_tabs_in_order() -> None:
    """Pins the tab set + order — catches a botched `st.tabs(...)` unpacking
    (the exact failure mode #85's wiring could have introduced)."""
    at = _run()
    assert [t.label for t in at.tabs] == _EXPECTED_TABS


def test_dashboard_renders_conformal_and_nba_clv_sections() -> None:
    """The two #85 additions actually render. Both are unconditional: the
    Reliability tab always emits the 'Conformal coverage' subheader, and the
    NBA CLV tab always emits its header + a summary markdown (real data or the
    'no manifest' fallback — both are markdown)."""
    at = _run()
    subheaders = " ".join(s.value for s in at.subheader)
    headers = " ".join(h.value for h in at.header)
    assert "Conformal coverage" in subheaders
    assert "NBA closing-line value" in headers


def test_dashboard_opens_with_what_am_i_looking_at_expander() -> None:
    """The plain-language pass (UX audit): the app opens with a
    'What am I looking at?' expander that gives the 10-second read and points
    at the docs/GETTING-STARTED.md glossary."""
    at = _run()
    labels = " ".join(e.label for e in at.expander)
    assert "What am I looking at?" in labels
    all_markdown = " ".join(m.value for m in at.markdown)
    assert "pretend money only" in all_markdown
    assert "GETTING-STARTED.md" in all_markdown


def test_dashboard_every_tab_has_plain_language_header() -> None:
    """Each tab opens with a plain-English 'what question does this page
    answer?' header/caption. Every asserted string is emitted unconditionally
    (before any data lookup), so this passes on a fresh DB with no manifests."""
    at = _run()
    headers = " ".join(h.value for h in at.header)
    captions = " ".join(c.value for c in at.caption)
    text = headers + " " + captions
    assert "which forecast recipe is in charge" in text  # Router
    assert "report card on past data" in text  # Backtest
    assert "does it happen about 70% of the time" in text  # Reliability
    assert "pretend money" in text  # Paper trades
    assert "beat the market's price" in text  # Nowcast edge
    assert "better prices than the market's final (closing) price" in text  # NBA CLV
    assert "are the downloads running on schedule" in text.lower()  # Data health


def test_dashboard_glosses_jargon_with_real_gate_numbers() -> None:
    """Headline metrics carry plain-language interpretations with the real
    gate numbers from the code (not invented ones): Brier coin-flip anchor,
    the +0.01 NBA CLV go-live gate, and the 0.90/0.85 conformal-coverage
    target. All emitted unconditionally via captions."""
    at = _run()
    captions = " ".join(c.value for c in at.caption)
    assert "coin flip" in captions  # Brier gloss (Backtest tab)
    assert "+0.01" in captions  # NBA CLV gate (Phase 5 #5 bar in panels.py)
    assert "0.90" in captions and "0.85" in captions  # conformal target + warn line
    assert "overconfident" in captions  # what a miss means
    assert "uv run kq doctor" in captions  # Data health: what to DO


def test_dashboard_db_connections_are_read_only_and_context_managed() -> None:
    """2026-07-01 audit: a raw `duckdb.connect(...)` + manual close leaked an
    open handle (and the DuckDB file lock, starving cron writers) whenever a
    tab body raised. Pin the fix at the source level: every DB read goes
    through the shared read-only factory inside a `with` block, and no raw
    duckdb.connect remains."""
    src = (Path(__file__).resolve().parents[1] / _APP).read_text(encoding="utf-8")
    assert "duckdb.connect(" not in src, "raw duckdb.connect leaks the file lock on exception"
    assert src.count("with connect(db_path, read_only=True) as con:") == 2
