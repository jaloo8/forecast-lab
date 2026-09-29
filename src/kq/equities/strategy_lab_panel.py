"""Read-only, hash-verified exploratory stock strategy comparisons."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


def _load(root: Path) -> tuple[dict[str, Any], bytes, pd.DataFrame]:
    pointer = json.loads((root / "latest.json").read_text(encoding="utf-8"))
    if not isinstance(pointer, dict):
        raise ValueError("invalid report pointer")
    relative = Path(pointer["report_file"])
    path = (root / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError("report path leaves the research directory")
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("published report file is missing") from exc
    if hashlib.sha256(raw).hexdigest() != pointer["report_sha256"]:
        raise ValueError("report digest mismatch")
    report = json.loads(raw)
    if (
        not isinstance(report, dict)
        or report.get("schema_version") != 1
        or report.get("status") != "success"
        or report.get("run_id") != pointer["run_id"]
    ):
        raise ValueError("unsupported or unsuccessful report")
    _coverage(report)
    return report, raw, _results(report["results"])


def _coverage(report: dict[str, Any]) -> None:
    source = report["source"]
    for timestamp in (report["captured_at"], source["captured_at"]):
        if datetime.fromisoformat(timestamp).utcoffset() is None:
            raise ValueError("research retrieval time has no timezone")
    for key in ("first_session", "last_session"):
        if source.get(key) is None:
            raise ValueError(f"missing source coverage: {key}")
    for key in ("stock_count", "candidate_count"):
        if type(source.get(key)) is not int or source[key] < 0:
            raise ValueError(f"invalid source coverage: {key}")
    for container, key in ((report, "limitations"), (source, "limitations")):
        if not isinstance(container[key], list) or not all(
            isinstance(value, str) for value in container[key]
        ):
            raise ValueError("invalid research limitations")
    for key in ("results", "cohorts", "controls"):
        if not isinstance(report[key], list) or not all(
            isinstance(row, dict) for row in report[key]
        ):
            raise ValueError(f"invalid {key} rows")


def _results(rows: list[dict[str, Any]]) -> pd.DataFrame:
    numbers = (
        "lookback",
        "size",
        "hold_sessions",
        "cost_bps",
        "cohort_count",
        "unavailable_count",
        "mean_exposure",
        "mean_net_return",
        "median_net_return",
        "mean_excess_vs_spy",
        "worst_cohort_return",
    )
    for row in rows:
        for key in ("selection_id", "family", "status"):
            if not isinstance(row[key], str) or not row[key]:
                raise ValueError(f"missing result identity: {key}")
        for key in numbers:
            value = row[key]
            if value is None and key.startswith(("mean_", "median_", "worst_")):
                continue
            if (
                isinstance(value, bool)
                or not isinstance(value, (float, int))
                or not math.isfinite(value)
            ):
                raise ValueError(f"invalid result measurement: {key}")
    frame = pd.DataFrame(rows)
    if len(frame) != 600 or frame.duplicated(["selection_id", "hold_sessions", "cost_bps"]).any():
        raise ValueError("expected all 600 unique cost scenarios")
    return frame


def render_strategy_lab(folder: Path) -> None:
    """Display immutable research only; never write an account or choose a winner."""
    st.subheader("Strategy comparisons")
    st.caption(
        "Exploratory historical research · 100 selection configurations x 2 holding periods "
        "= 200 variants x 3 cost assumptions = 600 scenarios, not independent experiments."
    )
    try:
        report, raw, rows = _load(folder / "strategy-lab")
    except FileNotFoundError:
        st.info("No strategy comparison report is available yet.")
        return
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
        st.error(f"Strategy comparison report cannot be verified: {exc}")
        return
    source = report["source"]
    st.caption(
        f"{source['stock_count']:,} accepted stocks from {source['candidate_count']:,} candidates "
        f"· sessions {source['first_session']} through {source['last_session']} "
        f"· sources captured {source['captured_at']} · report created {report['captured_at']}"
    )
    st.warning(
        "Already inspected historical sample: exploratory, with current-listing and "
        "complete-history selection bias; delisted stocks and dividends are missing. "
        "Short history and hypothetical fills cannot establish future profitability. "
        "Historical returns never enter paper-account balances."
    )
    for limitation in dict.fromkeys([*source["limitations"], *report["limitations"]]):
        st.warning(limitation)
    with st.expander("Selection, entry and exit rules"):
        st.write(
            "Momentum selects positive stock returns above SPY; risk-adjusted momentum "
            "divides relative log returns by volatility. Reversal selects recent decliners. "
            "Low volatility selects the least variable returns. Breakout selects closes "
            "above the preceding lookback's highest close. Ties use symbol order."
        )
        st.write(
            "Each rule uses 10, 20, 40 or 60 sessions and at most 1, 3, 5, 10 or 20 stocks. "
            "Eligible stocks cost at least $5 and have trailing 20-session median dollar "
            "volume of at least $20 million. Signals use decision-close information; entry "
            "is the next verified session's open, exit the fifth or twentieth session's close."
        )
        st.write(
            "Each of K slots has 1/K of the budget; unused slots stay cash. Fractional shares "
            "and 10, 25 or 50 basis points per side are assumptions. Compare holding periods "
            "separately. Missing outcomes stay unavailable. Worst cohort return is not account "
            "maximum drawdown. No rule is selected automatically."
        )
    filtered = rows
    for column, label in (
        ("family", "Family"),
        ("hold_sessions", "Hold (sessions)"),
        ("cost_bps", "Cost per side (basis points)"),
    ):
        chosen = st.selectbox(
            label, ["All", *sorted(rows[column].unique().tolist())], key=f"lab_{column}"
        )
        if chosen != "All":
            filtered = filtered.loc[filtered[column] == chosen]
    st.caption(
        f"Showing {len(filtered)} of {len(rows)} scenarios, "
        "including losses and unavailable outcomes."
    )
    st.caption(
        "Returns and exposure are fractions: 0.01 = 1%. Blank measurements mean unavailable."
    )
    st.dataframe(filtered, hide_index=True, width="stretch")
    with st.expander("Same-date controls and exposure"):
        st.caption(
            "Cash, SPY and the equal-weight eligible universe use matched dates and cost "
            "assumptions. SPY's exposure can differ from partly invested strategies."
        )
        if report["controls"]:
            st.dataframe(pd.DataFrame(report["controls"]), hide_index=True, width="stretch")
        else:
            st.info("Control outcomes are unavailable.")
    st.download_button(
        "Download all 600 result rows",
        rows.to_csv(index=False),
        file_name="strategy-comparisons.csv",
        mime="text/csv",
    )
    st.download_button(
        "Download verified report and cohort evidence",
        raw,
        file_name="strategy-lab-report.json",
        mime="application/json",
    )
