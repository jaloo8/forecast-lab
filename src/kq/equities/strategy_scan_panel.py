"""Read-only scanner matches from a verified, dated research artifact."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from kq.equities.strategy_lab.registry import FAMILIES, LOOKBACKS


def _time(value: Any) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("scanner timestamp has no timezone")
    return parsed.astimezone(UTC)


def _rows(report: dict[str, Any], captured: datetime, session: date) -> pd.DataFrame:
    raw = report["rows"]
    if not isinstance(raw, list) or not all(isinstance(row, dict) for row in raw):
        raise ValueError("invalid scanner rows")
    for row in raw:
        if (
            not isinstance(row["symbol"], str)
            or not row["symbol"]
            or row["family"] not in FAMILIES
            or row["lookback"] not in LOOKBACKS
            or type(row["eligible"]) is not bool
            or not isinstance(row["reason"], str)
        ):
            raise ValueError("invalid scanner identity or eligibility")
        observed = _time(row["as_of"])
        if observed > captured or observed.date() != session:
            raise ValueError("scanner row does not match the completed session")
        if row["reason"] == "unavailable_benchmark":
            raise ValueError("SPY evidence is unavailable; matches withheld")
        score, rank = row["score"], row["rank"]
        if row["eligible"] and (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
            or row["reason"]
        ):
            raise ValueError("invalid eligible score")
        if rank is not None and (type(rank) is not int or not 1 <= rank <= 20):
            raise ValueError("invalid scanner rank")
        if not row["eligible"] and (score is not None or rank is not None or not row["reason"]):
            raise ValueError("unavailable scanner measurement must be null")
    frame = pd.DataFrame(
        raw,
        columns=[
            "symbol",
            "family",
            "lookback",
            "score",
            "eligible",
            "reason",
            "as_of",
            "rank",
        ],
    )
    if frame.duplicated(["symbol", "family", "lookback"]).any():
        raise ValueError("duplicate scanner rows")
    return frame


def _artifact(root: Path, filename: str, kind: str) -> dict[str, Any]:
    pointer = json.loads((root / filename).read_text(encoding="utf-8"))
    relative = Path(pointer[f"{kind}_file"])
    path = (root / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError("scanner artifact leaves the research directory")
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("published scanner artifact is missing") from exc
    if hashlib.sha256(raw).hexdigest() != pointer[f"{kind}_sha256"]:
        raise ValueError("scanner artifact digest mismatch")
    report = json.loads(raw)
    if report["schema_version"] != 1 or report["run_id"] != pointer["run_id"]:
        raise ValueError("unsupported scanner artifact")
    return dict(report)


def _load(root: Path) -> tuple[dict[str, Any], pd.DataFrame, datetime]:
    report = _artifact(root, "scanner-latest.json", "report")
    if report["status"] != "success":
        raise ValueError("unsuccessful scanner report")
    captured = _time(report["captured_at"])
    session = date.fromisoformat(report["completed_session"])
    if (
        captured > datetime.now(UTC)
        or session >= captured.date()
        or session.weekday() >= 5
        or report["target_session"] != report["completed_session"]
    ):
        raise ValueError("invalid source or completed-session chronology")
    for key in (
        "requested_count",
        "candidate_count",
        "not_found_count",
        "invalid_count",
        "missing_latest_count",
        "excluded_bar_count",
    ):
        if type(report["coverage"][key]) is not int or report["coverage"][key] < 0:
            raise ValueError("invalid scanner coverage count")
    return report, _rows(report, captured, session), captured


def _attempt(root: Path) -> dict[str, Any]:
    attempt = _artifact(root, "scanner-attempt.json", "attempt")
    if attempt["status"] not in ("success", "failure") or _time(
        attempt["attempted_at"]
    ) > datetime.now(UTC):
        raise ValueError("invalid latest scanner attempt")
    if attempt["status"] == "failure" and not isinstance(attempt["error"], str):
        raise ValueError("failed scanner attempt has no reason")
    return attempt


def render_strategy_scan(folder: Path) -> None:
    """Show dated research candidates; never fetch prices or write orders."""
    st.subheader("Dated strategy matches")
    st.caption(
        "Research candidates, not orders or profit forecasts. Scores use completed daily "
        "sessions, not live intraday prices. Coverage is the captured stock sample, "
        "not all global stocks."
    )
    root = folder / "strategy-lab"
    try:
        attempt = _attempt(root)
        if attempt["status"] == "failure":
            st.error(
                f"Latest scan failed at {attempt['attempted_at']}: {attempt['error']}. "
                "Current matches are withheld."
            )
            if not (root / "scanner-latest.json").exists():
                return
        report, rows, captured = _load(root)
        if attempt["status"] == "failure":
            st.caption(
                f"Previous report is historical only: session {report['completed_session']} "
                f"· source captured {captured.isoformat()}."
            )
            return
        if (
            attempt["run_id"] != report["run_id"]
            or attempt["completed_session"] != report["completed_session"]
        ):
            raise ValueError("latest successful attempt does not match the published report")
    except FileNotFoundError:
        if (root / "scanner-latest.json").exists() or (root / "scanner-attempt.json").exists():
            st.error("Latest scanner attempt or report is missing; current matches are withheld.")
        else:
            st.info("No strategy scan is available yet.")
        return
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
        st.error(f"Strategy scan cannot be verified: {exc}")
        return
    _show(report, rows, captured)


def _show(report: dict[str, Any], rows: pd.DataFrame, captured: datetime) -> None:
    coverage = report["coverage"]
    st.caption(
        f"Completed session: {report['completed_session']} "
        f"· source captured {captured.isoformat()} "
        f"· {coverage['candidate_count']:,} candidates / "
        f"{coverage['requested_count']:,} requested symbols"
    )
    if datetime.now(UTC) - captured > timedelta(hours=30):
        st.warning(
            "Source capture is over 30 hours old. These are dated matches; "
            "refresh collection before use."
        )
    st.caption(
        f"Coverage: {coverage['not_found_count']} not found "
        f"· {coverage['invalid_count']} invalid · "
        f"{coverage['missing_latest_count']} missing the latest session · "
        f"{coverage['excluded_bar_count']} excluded bars."
    )
    selected = rows
    for column, label in (
        ("family", "Scanner family"),
        ("lookback", "Scanner lookback (sessions)"),
    ):
        chosen = st.selectbox(
            label, ["All", *sorted(rows[column].unique().tolist())], key=f"scan_{column}"
        )
        if chosen != "All":
            selected = selected.loc[selected[column] == chosen]
    matches = selected.loc[selected.eligible.eq(True) & selected["rank"].notna()]
    st.caption(
        f"Showing {len(matches):,} ranked matches: at most 20 per family/lookback. "
        "Ranks compare the same rule only; the download retains all matches and exclusions."
    )
    if matches.empty:
        st.info("No ranked matches for these filters.")
    else:
        st.dataframe(matches, hide_index=True, width="stretch")
    excluded = selected.loc[selected.eligible.eq(False)]
    with st.expander("Why candidate rows were excluded"):
        if excluded.empty:
            st.info("No exclusions for these filters.")
        else:
            st.dataframe(
                excluded.groupby("reason").size().rename("Rows").reset_index(), hide_index=True
            )
    st.download_button(
        f"Download all {len(rows):,} scanner rows",
        rows.to_csv(index=False),
        file_name="strategy-scanner.csv",
        mime="text/csv",
    )
