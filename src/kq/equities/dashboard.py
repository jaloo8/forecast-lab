"""Read-only paper dashboard using Forecast Lab's existing Streamlit stack."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from kq.equities.adaptive_panel import render_adaptive
from kq.equities.coverage_panel import render_coverage
from kq.equities.dashboard_data import load_dashboard
from kq.equities.forward_panel import render_forward
from kq.equities.portfolio_panel import render_portfolios
from kq.equities.strategy_lab_panel import render_strategy_lab
from kq.equities.strategy_scan_panel import render_strategy_scan
from kq.equities.study_panel import render_study


def _overview(data: dict[str, Any]) -> None:
    summary = data["summary"]
    st.subheader("How is the practice account doing?")
    if summary.get("equity_valid") is False:
        st.error("Portfolio valuation needs review. Balance and profit are withheld.")
    else:
        balance, profit = st.columns(2)
        balance.metric("Virtual balance", f"${summary['equity']:,.2f}")
        profit.metric("Paper profit / loss", f"${summary['pnl']:+,.2f}")
    cash, reserved, closed = st.columns(3)
    cash.metric("Cash", "Unavailable" if summary["cash"] is None else f"${summary['cash']:,.2f}")
    reserved.metric("Reserved cash", f"${summary['reserved_cash']:,.2f}")
    closed.metric("Closed trades", str(summary["closed_count"]))
    st.caption("Reserved money is part of cash, not an additional balance.")
    st.write(
        f"{summary['pending_count']} queued · {summary['open_count']} open · "
        f"{summary['forecast_settled_count']} scored forecasts"
    )
    repairs = (data.get("source") or {}).get("session_repairs", [])
    if repairs:
        st.caption(
            "Daily-history feed fallback: verified regular-session statistics and official "
            "exchange closes. Raw sources and retrieval times are retained."
        )
    if data["win_rate"] is None:
        st.info("Not yet measured: no completed trades. There is no accuracy record yet.")
    elif summary.get("equity_valid") is not False:
        st.metric("Profitable completed trades", f"{data['win_rate']:.1%}")
        st.caption("A trade win rate is not a measure of forecast accuracy.")
    st.subheader("Are recorded forecasts beating SPY?")
    outcomes = pd.DataFrame(summary.get("forecast_by_horizon", []))
    if summary.get("forecast_valid") is False:
        st.error("Forecast history needs review. Comparisons are withheld.")
    elif outcomes.empty or not outcomes["count"].sum():
        st.info("Not yet measured: forecasts need 5, 20 or 126 trading sessions to mature.")
    else:
        outcomes = outcomes.rename(
            columns={
                "horizon_sessions": "Sessions",
                "count": "Scored",
                "mean_stock_return": "Stock return %",
                "mean_benchmark_return": "SPY return %",
                "mean_excess_return": "Difference (percentage points)",
            }
        )
        outcomes.iloc[:, 2:] = outcomes.iloc[:, 2:] * 100
        st.dataframe(outcomes, hide_index=True)
    st.caption(
        "Matched entry and exit dates; all recorded stocks, not just paper holdings. "
        "These price returns exclude fees and dividends. Daily forecasts overlap."
    )


def _trades(data: dict[str, Any]) -> None:
    st.subheader("What is queued, held or finished?")
    status = st.radio("Show trades", ["Queued", "Open", "Closed"], horizontal=True)
    if status == "Queued":
        rows = data["orders"]
        rows = rows[rows["status"] == "pending"] if not rows.empty else rows
        columns = ["symbol", "created_at", "reserved"]
    else:
        rows = data["trades"]
        if not rows.empty:
            rows = rows[rows["exit_date"].isna() == (status == "Open")]
        columns = ["symbol", "entry_date", "entry_cost", "shares", "exit_date", "net_pnl"]
        if data["summary"].get("equity_valid") is False:
            columns.remove("net_pnl")
            st.warning("Trade records need valuation review; profit amounts are withheld.")
    if rows.empty:
        st.info(f"No {status.lower()} paper trades.")
    else:
        st.dataframe(
            rows[[key for key in columns if key in rows]].rename(
                columns={
                    "symbol": "Stock",
                    "created_at": "Queued at (UTC)",
                    "reserved": "Reserved ($)",
                    "entry_date": "Entry date",
                    "entry_cost": "Cost ($)",
                    "shares": "Shares",
                    "exit_date": "Exit date",
                    "net_pnl": "Net profit ($)",
                }
            ),
            hide_index=True,
        )
    st.caption(
        "$10 per position · maximum five positions · 20-session holding period · "
        "0.10% simulated friction each way. All timestamps are UTC."
    )


def _research(data: dict[str, Any]) -> None:
    st.subheader("Which stocks have shown the strongest past returns?")
    horizon = st.selectbox(
        "Time horizon",
        [5, 20, 126],
        format_func=lambda n: {
            5: "Short · 5 sessions",
            20: "Medium · 20 sessions",
            126: "Long · 126 sessions",
        }[n],
    )
    forecasts = data["forecasts"]
    if not forecasts.empty:
        latest = data["state"]["last_source_as_of"]
        selected = forecasts[
            (forecasts["source_as_of"] == latest) & (forecasts["horizon"] == horizon)
        ]
        rows = pd.DataFrame([json.loads(payload) for payload in selected["payload"]])
        if not rows.empty:
            columns = [
                "symbol",
                "excess_momentum",
                "momentum",
                "pe_ratio",
                "market_cap",
                "latest_eps_actual",
                "latest_eps_estimate",
            ]
            display = rows.sort_values("excess_momentum", ascending=False)[columns].copy()
            display[["excess_momentum", "momentum"]] *= 100
            st.dataframe(
                display.rename(
                    columns={
                        "symbol": "Stock",
                        "excess_momentum": "Ahead of SPY (pp)",
                        "momentum": "Past return (%)",
                        "pe_ratio": "P/E",
                        "market_cap": "Market cap ($)",
                        "latest_eps_actual": "Reported EPS",
                        "latest_eps_estimate": "Estimated EPS",
                    }
                ),
                hide_index=True,
            )
        else:
            st.info("No eligible rankings in the latest capture.")
    st.caption(
        "Rankings describe history, not "
        "predicted returns. Current earnings and financial metrics are context only."
    )
    source = data.get("source") or {}
    st.subheader("Public news and filings")
    news = pd.DataFrame(source.get("news", []))
    if news.empty:
        st.info("No verified source capture available for news.")
    else:
        columns = ["symbol", "title", "url", "published_at", "retrieved_at"]
        st.dataframe(
            news[[key for key in columns if key in news]].rename(
                columns={
                    "symbol": "Stock",
                    "title": "Headline",
                    "url": "Source",
                    "published_at": "Available at (UTC)",
                    "retrieved_at": "First retrieved (UTC)",
                }
            ),
            hide_index=True,
        )
    with st.expander("What we reuse from Forecast Lab"):
        st.write(
            "Already reused: Streamlit, timestamped evidence, prospective paper records, "
            "benchmark comparisons and the completed-trade win-rate calculation."
        )
        st.write(
            "Research to test next: SEC filings, earnings changes, executive events and "
            "customer/supplier links from Research Pass 2. These remain hypotheses."
        )
        st.write(
            "Weather and NBA models do not directly predict stocks. Probability calibration "
            "can be reused once we define stock outcomes and collect enough independent results."
        )


def render_dashboard(data: dict[str, Any]) -> None:
    """Display an already-loaded, consistent read-only view."""
    summary = data["summary"]
    if summary.get("paused"):
        st.error(f"New paper entries paused: {summary.get('pause_reason', 'review required')}")
    captured = data["state"].get("last_source_as_of", "")
    st.caption(f"Last imported source: {captured} · daily data, not live prices")
    if captured:
        age = (datetime.now(UTC) - datetime.fromisoformat(captured)).total_seconds() / 3600
        if age > 30:
            st.warning(
                f"Capture is {age:.0f} hours old. Check Data health before trusting freshness."
            )
    overview, trades, research, health = st.tabs(["Overview", "Trades", "Research", "Data health"])
    with overview:
        _overview(data)
    with trades:
        _trades(data)
    with research:
        _research(data)
    with health:
        st.subheader("Is the evidence current and complete?")
        st.write(f"Last import: {data['state'].get('last_as_of', 'Unavailable')}")
        st.write(
            f"Last processed session: {data['state'].get('last_processed_session', 'Unavailable')}"
        )
        if data.get("source_warning"):
            st.warning(data["source_warning"])
        for warning in (data.get("source") or {}).get("source_errors", []):
            st.warning(str(warning))
        if summary.get("stale_symbols"):
            st.warning(f"Stale position marks: {summary['stale_symbols']}")
        st.info(
            "Checks are scheduled for weekdays at 6 AM, 6 PM and 9 PM Pacific. "
            "Pending orders fill at the next regular open after creation, recognized when "
            "completed-session data arrives. This page cannot verify "
            "scheduler uptime. Refresh reloads local records; it does not fetch market data."
        )
        st.caption("Six-stock pilot. News coverage is incomplete. No real trading is enabled.")


def main(data_dir: Path | None = None) -> None:
    """Start the local dashboard; never create or update trading records."""
    st.set_page_config(
        page_title="Forecast Lab · Stocks", layout="wide", initial_sidebar_state="collapsed"
    )
    st.title("Stock Paper Lab")
    st.caption("$100 virtual experiment · real evidence · no real money")
    st.sidebar.button("Refresh local results")
    st.sidebar.link_button("Kalshi dashboard (if running)", "http://127.0.0.1:8501")
    st.sidebar.caption("Stock and Kalshi performance are measured separately.")
    folder = data_dir or Path(__file__).resolve().parents[3] / "data" / "equities"
    accounts, comparisons, scanner, health = st.tabs(
        ["Paper accounts", "Strategy comparisons", "Scanner", "Data health"]
    )
    with accounts:
        st.subheader("Original pilot")
        try:
            render_dashboard(load_dashboard(folder))
        except FileNotFoundError:
            st.warning("No paper ledger yet. Import a market snapshot to start the experiment.")
        except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as exc:
            st.error(f"Paper records could not be verified: {exc}")
        st.subheader("Nine parallel paper portfolios")
        render_portfolios(folder)
    with comparisons:
        render_strategy_lab(folder)
        with st.expander("Historical tests: original fixed baseline"):
            render_study(folder)
        with st.expander("Adaptive stock research"):
            render_adaptive(folder)
    with scanner:
        render_strategy_scan(folder)
        st.caption(
            "Dated catalogue, historical rankings and captured news. A recurring marketwide "
            "scanner is not enabled; scheduled collection follows the earnings subset."
        )
        render_coverage(folder)
    with health:
        render_forward(folder)


if __name__ == "__main__":
    main()
