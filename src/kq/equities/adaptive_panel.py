"""Read-only display of verified adaptive stock research observations."""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from kq.equities.adaptive_journal import load_latest


def _now() -> datetime:
    return datetime.now(UTC)


def _time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("missing adaptive evidence timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("adaptive evidence timestamp has no timezone")
    return parsed.astimezone(UTC)


def _table(rows: list[dict[str, Any]], *, historical: bool) -> pd.DataFrame:
    columns = {
        "symbol": "Stock",
        "state": "Reference state",
        "action": "Recorded suggestion" if historical else "Action",
        "reason": "Reason",
        "score": "Score",
        "excess20": "Excess 20",
        "excess60": "Excess 60",
        "volatility20": "Volatility 20",
        "candidate_eligible": "Candidate eligible",
        "as_of": "As of",
        "price_as_of": "Price as of",
        "source_hash": "Source hash",
        "method_hash": "Method hash",
        "event_refs": "News refs",
    }
    selected = [{label: row.get(key) for key, label in columns.items()} for row in rows]
    for row in selected:
        row["News refs"] = len(row["News refs"] or [])
    return pd.DataFrame(selected, columns=list(columns.values()))


def _contents(
    decision: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], datetime, datetime]:
    if (
        decision["reference_kind"] != "original_pilot_read_only"
        or decision["mode"] != "advisory_only"
    ):
        raise ValueError("unexpected adaptive research mode or reference")
    rows, news, errors = decision["rows"], decision["news"], decision["source_errors"]
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("invalid adaptive research rows")
    if not isinstance(news, list) or not all(isinstance(row, dict) for row in news):
        raise ValueError("invalid adaptive news evidence")
    if not isinstance(errors, list) or not all(isinstance(error, str) for error in errors):
        raise ValueError("invalid adaptive source errors")
    return rows, news, errors, _time(decision["input_captured_at"]), _time(decision["created_at"])


def _stale_evidence(
    decision: dict[str, Any],
    rows: list[dict[str, Any]],
    captured: datetime,
    created: datetime,
    now: datetime,
) -> bool:
    if not captured <= created <= now:
        raise ValueError("adaptive capture, decision, or clock chronology is invalid")
    reference = decision.get("reference")
    if not isinstance(reference, dict) or reference.get("kind") != "original_pilot_read_only":
        raise ValueError("adaptive reference evidence is missing")
    reference_source = _time(reference.get("source_as_of"))
    reference_observed = _time(reference.get("observed_at"))
    if not reference_source <= reference_observed <= created:
        raise ValueError("adaptive reference chronology is invalid")
    times = [captured, reference_source]
    for row in rows:
        price = _time(row.get("price_as_of"))
        as_of = _time(row.get("as_of"))
        if price > as_of or as_of > captured:
            raise ValueError("adaptive row price chronology is invalid")
        times.append(price)
    return any(now - observed > timedelta(hours=24) for observed in times)


def _news(news: list[dict[str, Any]]) -> None:
    st.caption(
        f"News metadata: {len(news)} records. Coverage may be incomplete; news has no "
        "numerical influence on scores or actions. Published and retrieved times are shown below."
    )
    if news:
        labels = {
            "symbol": "Stock",
            "title": "Headline",
            "url": "Source",
            "published_at": "Published at",
            "retrieved_at": "Retrieved at",
        }
        st.dataframe(
            pd.DataFrame(
                [{label: item.get(key) for key, label in labels.items()} for item in news]
            ),
            hide_index=True,
            width="stretch",
        )


def _rows(rows: list[dict[str, Any]], *, current: bool) -> None:
    if not rows:
        st.info("No stocks were scored in this decision.")
    elif current:
        st.dataframe(_table(rows, historical=False), hide_index=True, width="stretch")
    else:
        with st.expander("Historical suggestions (current actions withheld)"):
            st.dataframe(_table(rows, historical=True), hide_index=True, width="stretch")


def render_adaptive(folder: Path) -> None:
    """Show latest immutable advice; never write a journal or place an order."""
    st.subheader("Adaptive stock research")
    st.caption(
        "Advisory suggestions use read-only positions from the original pilot. "
        "No orders or new account are created. Profit has not been validated. "
        "The nine parallel paper portfolios remain separate."
    )
    try:
        latest = load_latest(folder / "adaptive-research")
    except FileNotFoundError:
        st.info("No adaptive research journal is available yet.")
        return
    except (
        OSError,
        sqlite3.Error,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        IndexError,
    ) as exc:
        st.error(f"Adaptive research journal cannot be verified: {exc}")
        return
    decision = latest["decision"]
    attempt = latest["last_attempt"]
    if decision is None:
        st.info("No accepted adaptive research decision is available yet.")
        if attempt and attempt["status"] == "failure":
            st.warning(f"Last attempt failed at {attempt['attempted_at']}: {attempt['error']}")
        return

    try:
        rows, news, errors, captured, created = _contents(decision)
        now = _now()
        stale = _stale_evidence(decision, rows, captured, created, now)
        failed = bool(attempt and attempt["status"] != "success")
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        st.error(f"Adaptive research decision cannot be verified: {exc}")
        return

    st.caption(
        "Original pilot reference: held / flat / pending states "
        f"· session {decision['session_date']} "
        f"· captured {captured.isoformat()} · recorded {created.isoformat()} "
        f"· method {decision['method_hash'][:12]}"
    )
    if stale:
        st.warning(
            "Input capture, price, or reference evidence is over 24 hours old. "
            "Current BUY/SELL suggestions are withheld."
        )
    if failed and attempt:
        st.warning(
            f"Latest attempt failed at {attempt['attempted_at']}: {attempt['error']}. "
            "Current BUY/SELL suggestions are withheld."
        )
    counts = Counter(str(row.get("action", "UNKNOWN")) for row in rows)
    current = not stale and not failed
    summary = st.columns(5)
    for column, action in zip(
        summary, ("BUY", "HOLD", "SELL", "PENDING", "WAIT_DATA"), strict=True
    ):
        column.metric(f"{'Advisory' if current else 'Recorded'} {action}", str(counts[action]))
    st.caption(
        f"WATCH: {counts['WATCH']} · pending means an existing pilot intent, not a new order. "
        "Score combines 20 and 60 session excess return over SPY with 20 session volatility; "
        "the reason column explains each state and threshold."
    )
    _rows(rows, current=current)
    for error in errors:
        st.warning(f"Source limitation: {error}")
    _news(news)
