"""Read-only collection checks and prospective research outcomes."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from kq.equities.forward_study import evaluate
from kq.equities.health import collection_health
from kq.equities.observations import observation_folder, prior_observation


def _evidence(data_dir: Path) -> None:
    path = data_dir / "forward-coverage.json"
    if not path.exists():
        return
    coverage = json.loads(path.read_text(encoding="utf-8"))
    st.caption(
        f"Observed {coverage['as_of']}: {coverage['calendar_reports']} earnings reports, "
        f"{coverage['stock_candidates']} catalogue candidates, quarterly financials for "
        f"{coverage['financial_symbols']}."
    )
    with st.expander("Evidence gaps"):
        for detail in coverage["limitations"]:
            st.write(detail)
        st.write("Outside stock-candidate classification:", coverage["outside_candidates"])


def _decisions(data_dir: Path) -> None:
    paths = sorted((data_dir / "forward-decisions").glob("*.json"))
    if not paths:
        st.info("No prospective research decision recorded yet. Profitability is unmeasured.")
        return
    snapshot = json.loads((data_dir / "forward-snapshot.json").read_text(encoding="utf-8"))
    selected = st.selectbox("Research decision", paths, format_func=lambda path: path.stem)
    decision = json.loads(selected.read_text(encoding="utf-8"))
    journal = observation_folder(data_dir / "forward-observations", decision)
    previous = prior_observation(journal, snapshot)
    outcomes = evaluate(decision, snapshot, previous_snapshot=previous)
    st.caption(f"Created {decision['created_at']} · fixed 20-session holding period")
    if outcomes.empty:
        st.info("No selections for this decision. No investment return is inferred.")
    else:
        returns = {column: "{:.2%}" for column in (
            "gross_return", "net_return", "spy_net_return", "excess_vs_spy"
        )}
        st.dataframe(outcomes.style.format(returns, na_rep="Unmeasured"),
                     hide_index=True, width="stretch")
        if (~outcomes["status"].isin(["pending", "mature"])).any():
            st.error("Research evidence is invalid or the session calendar is unverified. "
                     "Review the source history before interpreting returns.")
        elif outcomes["status"].eq("pending").any():
            st.info("No mature outcomes yet. Future completed sessions are needed.")
    st.download_button("Download immutable research decision", selected.read_bytes(),
                       file_name=selected.name, mime="application/json")
    with st.expander("Screened stocks and exclusion reasons"):
        if decision["screen"]:
            st.dataframe(pd.DataFrame(decision["screen"])[[
                "symbol", "close", "median_dollar_volume_20d", "excess_momentum_20d",
                "reason", "challenger_selected", "momentum_selected",
            ]], hide_index=True, width="stretch")
    st.warning(
        "Research cohorts are separate from the $100 paper account. Returns include assumed "
        "costs; daily cohorts can overlap. Captured EPS estimates may be revised and their "
        "accounting basis is unverified. This is not a proven earnings-surprise strategy."
    )


def render_forward(data_dir: Path) -> None:
    """Inspect existing records; do not collect, create decisions or trade."""
    st.subheader("Collection health")
    health = collection_health(data_dir, datetime.now(UTC))
    st.dataframe(health[["check", "status", "detail"]], hide_index=True, width="stretch")
    for row in health.to_dict("records"):
        if row["status"] == "failure":
            st.error(str(row["detail"]))
        elif row["status"] in {"stale", "never_run", "configured_unverified", "unverified"}:
            st.warning(str(row["detail"]))
    st.caption("A configured schedule does not prove a successful refresh or independent A8 feed.")
    st.subheader("Forward earnings experiment")
    try:
        _evidence(data_dir)
        _decisions(data_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        st.error(f"Forward research could not be verified: {exc}")
