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

import pytest

# AppTest ships with streamlit (>=1.28); skip cleanly if unavailable.
AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

_APP = "src/kq/dashboard/streamlit_app.py"
_EXPECTED_TABS = ["Router", "Backtest", "Reliability", "Paper trades", "NBA CLV", "Data health"]


def _run() -> AppTest:
    return AppTest.from_file(_APP, default_timeout=90).run()


def test_dashboard_renders_without_exception() -> None:
    """The whole script runs through the Streamlit runtime with no uncaught
    exception in any tab body."""
    at = _run()
    assert not at.exception, f"dashboard raised: {list(at.exception)}"


def test_dashboard_has_all_six_tabs_in_order() -> None:
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
