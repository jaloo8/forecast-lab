"""Streamlit dashboard entrypoint. Phase 4 deliverable.

Run with `make dashboard` or `uv run streamlit run src/kq/dashboard/streamlit_app.py`.
"""

from __future__ import annotations

import streamlit as st

from kq import __version__

st.set_page_config(page_title="forecast-lab", layout="wide")
st.title("forecast-lab")
st.caption(f"v{__version__} - paper trading only. See CLAUDE.md §5 for the live gate.")

st.info(
    "Dashboard is a Phase 4 deliverable. "
    "Until then, look at the DuckDB file directly or use notebooks/."
)
