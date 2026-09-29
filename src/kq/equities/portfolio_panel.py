"""Read-only view of nine prospective, independently funded stock paper books."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from kq.equities.portfolios import portfolio_specs


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Invalid portfolio timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Portfolio timestamp lacks a timezone")
    return parsed.astimezone(UTC)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _report(root: Path) -> dict[str, Any] | None:
    path = root / "latest.json"
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Portfolio report must be an object")
    expected = {spec.portfolio_id for spec in portfolio_specs()}
    rows = raw.get("accounts")
    if (
        not isinstance(rows, list)
        or len(rows) != len(expected)
        or any(not isinstance(row, dict) for row in rows)
        or {row.get("portfolio_id") for row in rows} != expected
        or raw.get("status") not in ("ok", "partial_failure")
        or not isinstance(raw.get("benchmark"), dict)
        or not isinstance(raw.get("session_date"), str)
        or not isinstance(raw.get("snapshot_hash"), str)
        or not isinstance(raw.get("source_errors", []), list)
        or any(not isinstance(error, str) for error in raw.get("source_errors", []))
        or not isinstance(raw.get("recovery", False), bool)
    ):
        raise ValueError("Unknown portfolio report schema or account set")
    _timestamp(raw.get("as_of"))
    _timestamp(raw.get("source_as_of"))
    _timestamp(raw.get("launched_at"))
    specifications = {spec.portfolio_id: spec for spec in portfolio_specs()}
    for row in rows:
        spec = specifications[row["portfolio_id"]]
        if (
            row.get("protocol_id") != spec.protocol_id
            or row.get("family") != spec.family
            or row.get("lookback") != spec.lookback
            or row.get("holding_sessions") != spec.holding_sessions
        ):
            raise ValueError("Portfolio report method differs from frozen protocol")
        if row.get("status") not in ("ok", "error"):
            raise ValueError("Unknown portfolio account status")
        if row["status"] == "ok" and (
            not isinstance(row.get("summary"), dict) or not isinstance(row.get("metrics"), dict)
        ):
            raise ValueError("Incomplete portfolio account result")
    return raw


def _account_row(account: dict[str, Any], *, stale: bool) -> dict[str, Any]:
    spec = next(spec for spec in portfolio_specs() if spec.portfolio_id == account["portfolio_id"])
    summary = account.get("summary") or {}
    metrics = account.get("metrics") or {}
    valid = (
        account["status"] == "ok"
        and not stale
        and summary.get("equity_valid") is True
        and metrics.get("valid") is True
        and not summary.get("stale_symbols")
        and _number(summary.get("equity")) is not None
    )
    equity = _number(summary.get("equity")) if valid else None
    return {
        "Portfolio": account["portfolio_id"],
        "Family": spec.family,
        "Lookback sessions": spec.lookback,
        "Hold sessions": spec.holding_sessions,
        "Method hash": spec.protocol_id[:12],
        "Status": (
            "Failed"
            if account["status"] == "error"
            else "Stale"
            if stale
            else "Invalid marks"
            if not valid
            else "Paused"
            if summary.get("paused")
            else "Current"
        ),
        "Equity ($)": equity,
        "Profit ($)": equity - 100 if equity is not None else None,
        "Cash ($)": _number(summary.get("cash")) if valid else None,
        "Reserved ($)": _number(summary.get("reserved_cash")) if valid else None,
        "Realized P&L ($)": _number(metrics.get("realized_pnl")) if valid else None,
        "Unrealized P&L ($)": _number(metrics.get("unrealized_pnl")) if valid else None,
        "Max drawdown": _number(metrics.get("max_drawdown")) if valid else None,
        "Exposure": _number(metrics.get("exposure")) if valid else None,
        "Pending": summary.get("pending_count") if valid else None,
        "Open": summary.get("open_count") if valid else None,
        "Closed": summary.get("closed_count") if valid else None,
        "Matched closed-trade SPY P&L ($)": (
            _number(metrics.get("matched_spy_pnl")) if valid else None
        ),
        "Launched (UTC)": account.get("launched_at"),
    }


def _source_warnings(report: dict[str, Any]) -> None:
    if report.get("recovery"):
        st.warning(
            "Recovered prior committed results; source timestamp unchanged; "
            "no new trades from stale data."
        )
    for source_error in report.get("source_errors", []):
        st.warning(f"Source error: {escape(source_error, quote=False)}")


def render_portfolios(data_dir: Path) -> None:
    """Display the latest shared capture without writing or repairing local evidence."""
    st.subheader("Parallel stock paper portfolios")
    st.caption("Nine independent $100 virtual accounts · $900 simulated total · paper only")
    st.caption(
        "Nine frozen tests share one event-conditioned capture; overlapping positions make "
        "their observations correlated. Results are not a validated winner. "
        "The original $100 pilot is shown separately."
    )
    try:
        report = _report(data_dir / "parallel-books")
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        st.error(f"Parallel portfolio report cannot be verified: {exc}")
        return
    if report is None:
        st.warning("Parallel books have not started. No verified results are available.")
        return

    captured = _timestamp(report["source_as_of"])
    evaluated = _timestamp(report["as_of"])
    launched = _timestamp(report["launched_at"])
    stale = datetime.now(UTC) - min(captured, evaluated) > timedelta(hours=30)
    st.caption(
        f"Launch: {launched.isoformat()} · source capture: {captured.isoformat()} · "
        f"evaluated: {evaluated.isoformat()} · session: {report['session_date']} · "
        f"source hash: {report['snapshot_hash'][:12]}"
    )
    if stale:
        st.warning("Portfolio capture or evaluation is over 30 hours old; results are stale.")
    _source_warnings(report)
    if report["status"] == "partial_failure":
        st.error("Partial failure: one or more account updates failed.")
    accounts = report["accounts"]
    launches = {row.get("launched_at") for row in accounts if row["status"] == "ok"}
    if len(launches) > 1 or (launches and launches != {report["launched_at"]}):
        st.warning("Account launch times differ; comparison windows are not identical.")
    for account in accounts:
        if account["status"] == "error":
            st.error(f"{account['portfolio_id']}: {account.get('error') or 'update failed'}")
        elif account["summary"].get("paused"):
            st.warning(
                f"{account['portfolio_id']} paused: "
                f"{account['summary'].get('pause_reason') or 'review required'}"
            )
        elif account["summary"].get("stale_symbols"):
            st.warning(f"{account['portfolio_id']} has stale position marks.")
    st.dataframe(
        pd.DataFrame([_account_row(row, stale=stale) for row in accounts]), hide_index=True
    )
    if all(row["summary"].get("closed_count") == 0 for row in accounts if row["status"] == "ok"):
        st.info("Not yet measured: no completed paper trades in the current accounts.")
    reference = report["benchmark"]
    st.caption("Passive SPY reference: $100 fully invested with costs; it is not risk matched.")
    if not stale and reference.get("status") == "marked" and _number(reference.get("equity")):
        st.metric("Passive SPY marked equity", f"${float(reference['equity']):,.2f}")
    else:
        st.info("Passive SPY reference is pending or unverified.")
    st.caption(
        "Matched closed-trade SPY P&L uses only the same entry and exit dates as closed "
        "positions; it is not whole-account alpha. Cash exposure and fees differ."
    )
