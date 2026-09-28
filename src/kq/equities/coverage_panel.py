"""Read-only listing and event evidence, separate from the fixed paper book."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from kq.equities.events import events_as_of
from kq.equities.universe import load_universe


def _broad_study(data_dir: Path) -> None:
    path = data_dir / "broad-historical-study.json"
    if not path.exists():
        return
    st.subheader("Broad stock simulation: all outcomes")
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        coverage = result["coverage"]
        st.caption(
            f"{coverage['study_stock_count']:,} stocks · {coverage['first_session']} "
            f"through {coverage['last_session']} · fixed momentum rule"
        )
        groups = [group for group in result["groups"] if group["cohort_count"] > 0]
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Sessions": group["horizon_sessions"],
                        "Test periods": group["cohort_count"],
                        "Mean net return": f"{group['mean_net_return']:.2%}",
                        "Mean excess vs SPY": f"{100 * group['mean_excess_vs_matched_spy']:.2f} pp",
                    }
                    for group in groups
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        ready = {group["horizon_sessions"] for group in groups}
        for horizon in (5, 20, 126):
            if horizon not in ready:
                st.info(f"{horizon}-session: no mature test periods; more history is needed.")
        st.warning(
            "These are separate historical test periods, not the $100 paper account or "
            "annualized returns. Current survivors only; dividends and realistic liquidity "
            "are missing. Assumed costs may understate trading costs. No news signal is tested."
        )
        st.download_button(
            "Download every broad simulation outcome",
            path.read_bytes(),
            file_name=path.name,
            mime="application/json",
        )
    except (ValueError, KeyError, TypeError, OSError) as exc:
        st.error(f"Broad simulation could not be loaded: {exc}")


def _price_coverage(data_dir: Path) -> None:
    path = data_dir / "broad-coverage.csv"
    if not path.exists():
        st.info("Broad price-history validation has not produced a coverage report yet.")
        return
    try:
        coverage = pd.read_csv(path, keep_default_na=False)
        if coverage["symbol"].duplicated().any():
            raise ValueError("duplicate coverage symbols")
        dates = pd.to_datetime(coverage["as_of"], utc=True, errors="raise")
        if dates.isna().any() or (dates > pd.Timestamp.now(tz="UTC")).any():
            raise ValueError("invalid coverage observation time")
        ranked = int((coverage["coverage_status"] == "ranked").sum())
        st.caption(f"{ranked:,} of {len(coverage):,} stock candidates have ranked price history.")
        st.caption(f"History observed: {dates.max()}. Rankings describe past price strength.")
        st.dataframe(
            coverage.groupby("coverage_status").size().rename("Stocks").reset_index(),
            hide_index=True,
            width="stretch",
        )
        ranks = data_dir / "broad-rankings.csv"
        if ranks.exists():
            st.download_button(
                "Download broad historical-strength rankings",
                ranks.read_bytes(),
                file_name="broad-rankings.csv",
                mime="text/csv",
            )
        st.warning("Current survivors only. Broad rankings are not backtests or profit forecasts.")
    except (ValueError, KeyError, TypeError, OSError) as exc:
        st.error(f"Price-history coverage could not be verified: {exc}")


def render_coverage(data_dir: Path) -> None:
    """Display verified directory rows and events known by the current UTC time."""
    st.subheader("How broad is our research?")
    manifest = data_dir / "universe" / "manifest.json"
    if not manifest.exists():
        st.info("No broad stock catalogue captured yet.")
    else:
        try:
            frame = load_universe(manifest)
            st.metric("Listed securities captured", str(len(frame)))
            st.caption(f"Catalogue observed: {frame['as_of'].iloc[0]}")
            st.warning(
                "Current US exchange listings include funds and other securities. "
                "This is not historical membership, global coverage or verified price history. "
                "The six-stock paper baseline stays separate."
            )
            category = st.selectbox(
                "Security classification", ["All", *sorted(frame["category"].unique().tolist())]
            )
            shown = frame if category == "All" else frame.loc[frame["category"] == category]
            st.caption(f"Showing the first {min(250, len(shown)):,} of {len(shown):,} rows.")
            st.dataframe(
                shown[["symbol", "name", "exchange", "category", "reason"]].head(250),
                hide_index=True,
                width="stretch",
            )
            st.download_button(
                "Download full catalogue",
                frame.to_csv(index=False),
                file_name="stock-research-catalogue.csv",
                mime="text/csv",
            )
        except (ValueError, KeyError, TypeError, OSError) as exc:
            st.error(f"Catalogue could not be verified: {exc}")
    _price_coverage(data_dir)
    _broad_study(data_dir)
    st.subheader("News and filing evidence")
    database = data_dir / "events.sqlite"
    if not database.exists():
        st.info("No archived events yet. Missing coverage does not mean no news occurred.")
        return
    try:
        events = events_as_of(database, datetime.now(UTC))
        st.caption(
            f"{len(events):,} latest observed source versions. News coverage is incomplete; "
            "events are evidence, not forecast probabilities or buy signals."
        )
        st.dataframe(
            events[["symbol", "title", "kind", "published_at", "first_seen", "url"]],
            hide_index=True,
            width="stretch",
        )
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as exc:
        st.error(f"Event history could not be verified: {exc}")
