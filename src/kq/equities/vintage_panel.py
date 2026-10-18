"""Read-only display of a verified manual stock price-source review."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import streamlit as st


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} is missing")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None or parsed.astimezone(UTC) > datetime.now(UTC):
        raise ValueError(f"{label} is timezone-free or future-dated")
    return parsed.astimezone(UTC)


def _verified_json(root: Path, relative: Any, digest: Any, section: str) -> dict[str, Any]:
    if not isinstance(relative, str) or not isinstance(digest, str):
        raise ValueError("source-review artifact reference is missing")
    parts = Path(relative).parts
    if (
        len(parts) < (4 if section == "runs" else 3)
        or parts[:2] != ("source-reconciliation", section)
        or any(part in ("", ".", "..") for part in parts)
        or Path(relative).suffix != ".json"
    ):
        raise ValueError("source-review artifact path is invalid")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("source-review artifact leaves the data directory")
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("published source-review artifact is missing") from exc
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("source-review artifact hash does not match")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("source-review artifact is invalid")
    return value


def _complete_bar(value: Any, session: str) -> bool:
    if not isinstance(value, dict):
        return False
    prices = ("open_price", "high_price", "low_price", "close_price")
    return (
        value.get("session_date") == session
        and value.get("session") == "reg"
        and type(value.get("synthetic")) is bool
        and all(isinstance(value.get(field), str) and value[field] for field in prices)
        and type(value.get("volume")) is int
    )


def _verify_review(root: Path, row: dict[str, Any], captured: datetime) -> None:
    lane = row["lane"]
    review = _verified_json(root, row.get("review_file"), row.get("review_sha256"), "reviews")
    if (
        review.get("schema_version") != 1
        or review.get("policy") != "finite_2026_09_28_source_vintage"
    ):
        raise ValueError("source-review evidence has an unsupported policy")
    if _time(review.get("reviewed_at"), f"{lane} review time") > captured:
        raise ValueError("source review follows the report capture")
    entries = review.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("source-review entries are missing")
    counts = {"supplement": 0, "volume_correction": 0}
    identities: set[tuple[str, str]] = set()
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("kind") not in counts:
            raise ValueError("source-review entry kind is invalid")
        symbol = entry.get("symbol")
        session = entry.get("session_date")
        if (
            not isinstance(symbol, str)
            or not symbol
            or session != "2026-09-28"
            or (symbol, session) in identities
            or not _complete_bar(entry.get("accepted_bar"), session)
            or not _complete_bar(entry.get("published_bar"), session)
        ):
            raise ValueError("source-review entry does not identify a unique September 28 bar")
        identities.add((symbol, session))
        counts[entry["kind"]] += 1
    claims = (
        ("entry_count", len(entries)),
        ("supplement_count", counts["supplement"]),
        ("volume_correction_count", counts["volume_correction"]),
    )
    if any(type(row.get(key)) is not int or row[key] != actual for key, actual in claims):
        raise ValueError(f"{lane} source-review counts do not match the evidence")


def _load(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    pointer = json.loads((root / "source-reconciliation.json").read_text(encoding="utf-8"))
    if not isinstance(pointer, dict):
        raise ValueError("source-review pointer is invalid")
    report = _verified_json(root, pointer.get("report_file"), pointer.get("report_sha256"), "runs")
    if (
        report.get("schema_version") != 1
        or report.get("status") != "validated"
        or report.get("kind") != "manual_source_review"
    ):
        raise ValueError("source-review report has not been validated")
    captured = _time(report.get("captured_at"), "source-review capture time")
    reviews = report.get("reviews")
    if not isinstance(reviews, list) or len(reviews) != 3:
        raise ValueError("source-review report does not cover all three lanes")
    seen: set[str] = set()
    for row in reviews:
        if not isinstance(row, dict) or row.get("lane") not in {"baseline", "parallel", "forward"}:
            raise ValueError("source-review lane is invalid")
        lane = row["lane"]
        if lane in seen:
            raise ValueError("source-review lane is duplicated")
        seen.add(lane)
        _verify_review(root, row, captured)
    return report, reviews


def render_source_reconciliation(folder: Path) -> None:
    """Show manual review only when its report and every lane's evidence verify."""
    if not (folder / "source-reconciliation.json").exists():
        return
    try:
        report, reviews = _load(folder)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        st.error(f"Price-source review could not be verified: {exc}")
        return
    counts = {row["lane"]: row for row in reviews}
    st.caption(
        "September 28 price-source review: preserved as-recorded legacy observations "
        "for existing paper results. Full newer primary daily bars are retained separately. "
        "New completed sessions and scans use primary daily-bar prices, "
        "not official settled closes."
    )
    with st.expander("What the manual source review covers"):
        st.caption(
            "Reviewed differences by book (parallel and forward can overlap): "
            + " · ".join(
                f"{lane}: {counts[lane]['entry_count']} "
                f"({counts[lane]['supplement_count']} supplemented, "
                f"{counts[lane]['volume_correction_count']} volume-only)"
                for lane in ("baseline", "parallel", "forward")
            )
        )
        st.caption(
            "This manual source check does not prove the price sources equivalent, "
            "scheduled checks ran, fills were accurate, or the strategy is profitable. "
            "Earlier audit failures remain recorded. "
            f"Review report captured {report['captured_at']}."
        )
