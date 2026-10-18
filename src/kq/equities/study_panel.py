"""Display historical evidence without mixing it into the forward paper account."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st


def render_study(data_dir: Path) -> None:
    """Read an optional completed study; never launch research or touch a ledger."""
    st.subheader("Historical experiments")
    path = data_dir / "historical-study.json"
    if not path.is_file():
        st.info("No historical study has been completed here yet.")
        return
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        rows = pd.DataFrame(result["groups"])
        if rows.empty:
            st.info("The historical study produced no eligible holding periods.")
            return
        st.warning(
            "Exploratory history using six present-day survivors. Dividends and delisted "
            "companies are missing. These are not paper-account results or proof of future profits."
        )
        horizon = st.selectbox("Historical holding period", [5, 20, 126], index=1)
        chosen = rows[rows["horizon_sessions"] == horizon].copy()
        chosen["worst_cohort"] = chosen["worst_cohort"].map(
            lambda cohort: cohort["net_return"] if isinstance(cohort, dict) else None
        )
        labels = {
            "block": "Years",
            "cohort_count": "Periods",
            "invested_count": "Invested periods",
            "mean_net_return": "Average period return (%)",
            "mean_excess_vs_matched_spy": "Ahead of matched SPY (pp)",
            "mean_spy_market_net_return": "SPY market period return (%)",
            "positive_fraction_invested": "Profitable invested periods (%)",
            "worst_cohort": "Worst period (%)",
        }
        for column in list(labels)[3:]:
            chosen[column] *= 100
        st.dataframe(chosen[list(labels)].rename(columns=labels), hide_index=True)
        st.caption(
            "Signal at one close, entry at the following open; top three positive-strength "
            "stocks; 0.10% cost each way. Nonoverlapping periods, fixed rules, "
            "no parameter search. Matched SPY uses the same invested dates; "
            "the market column also includes cash periods. "
            "These averages are not annual or compounded returns; holding periods differ."
        )
        st.caption(
            "Periods count provider-observed sessions. Missing days shared by all symbols "
            "are not detected against an independent exchange calendar."
        )
        st.download_button(
            "Download every historical gain and loss",
            path.read_bytes(),
            file_name="historical-study.json",
            mime="application/json",
        )
        st.caption(f"Source captured: {result['captured_at']} · Price history: 2010-2026")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        st.error(f"Historical results could not be read: {exc}")
