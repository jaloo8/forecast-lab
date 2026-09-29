"""Finite review of the September 28 stock price source transition."""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

import pytest

from kq.equities.research import _results
from kq.equities.session_data import _digest
from kq.equities.session_vintages import create_review, primary_daily, reconcile_daily
from tests.equity_vintage_fixtures import snapshots

NOW = datetime(2026, 9, 29, 14, tzinfo=UTC)
PRIOR = "prior"
PUBLISHED = "published"


def _read(which: str) -> dict[str, Any]:
    prior, published = snapshots()
    return prior if which == PRIOR else published


def _bars(snapshot: dict[str, Any], symbol: str) -> list[dict[str, Any]]:
    return next(s["bars"] for s in _results(snapshot["bars"], "bars") if s["symbol"] == symbol)


def test_exact_review_preserves_accepted_vintage_and_primary_capture() -> None:
    prior, published = _read(PRIOR), _read(PUBLISHED)
    before = copy.deepcopy(published)
    review = create_review(prior, published, now=NOW, note="Reviewed historical source transition")
    assert len(review["entries"]) == 3
    assert sum(e["kind"] == "supplement" for e in review["entries"]) == 2
    assert sum(e["kind"] == "volume_correction" for e in review["entries"]) == 1
    legacy = reconcile_daily(published, prior, review, required={"SPY"}, now=NOW)
    assert _bars(legacy, "AAPL")[-1] == _bars(prior, "AAPL")[-1]
    assert _bars(legacy, "AMST")[-1] == _bars(prior, "AMST")[-1]
    assert _bars(legacy, "MPU")[-1] == _bars(published, "MPU")[-1]
    assert legacy["completed_session"] == "2026-09-28"
    assert legacy["source_reconciliation"]["review_sha256"] == review["review_sha256"]
    assert published == before


def test_review_rejects_tampered_old_evidence_and_saved_bar() -> None:
    prior, published = _read(PRIOR), _read(PUBLISHED)
    prior["session_evidence"]["fundamentals"][0]["open"] = "1"
    with pytest.raises(ValueError, match="evidence"):
        create_review(prior, published, now=NOW, note="review")
    prior = _read(PRIOR)
    _bars(prior, "AAPL")[-1]["open_price"] = "102"
    with pytest.raises(ValueError, match=r"accepted|saved|evidence"):
        create_review(prior, published, now=NOW, note="review")


def test_review_rejects_unlisted_or_earlier_changes_and_missing_history() -> None:
    prior, published = _read(PRIOR), _read(PUBLISHED)
    _bars(published, "AAPL")[-2]["close_price"] = "100.5"
    with pytest.raises(ValueError, match="revision"):
        create_review(prior, published, now=NOW, note="review")
    published = _read(PUBLISHED)
    _bars(published, "AAPL").pop(0)
    with pytest.raises(ValueError, match=r"missing|history"):
        create_review(prior, published, now=NOW, note="review")


def test_reconcile_rejects_replayed_review_for_new_pair_or_duplicate_entry() -> None:
    prior, published = _read(PRIOR), _read(PUBLISHED)
    review = create_review(prior, published, now=NOW, note="review")
    changed = copy.deepcopy(published)
    _bars(changed, "AAPL")[-1]["open_price"] = "100.6"
    with pytest.raises(ValueError, match=r"review|snapshot|pair"):
        reconcile_daily(changed, prior, review, required={"SPY"}, now=NOW)
    review["entries"].append(copy.deepcopy(review["entries"][0]))
    with pytest.raises(ValueError, match=r"review|duplicate|hash"):
        reconcile_daily(published, prior, review, required={"SPY"}, now=NOW)


def test_primary_requires_fresh_complete_regular_daily_bars() -> None:
    published = _read(PUBLISHED)
    primary = primary_daily(published, required={"AAPL", "SPY"}, now=NOW)
    assert primary["completed_session"] == "2026-09-28"
    assert _bars(primary, "AAPL")[-1] == _bars(published, "AAPL")[-1]
    bad = copy.deepcopy(published)
    _bars(bad, "SPY")[-1]["interpolated"] = True
    with pytest.raises(ValueError, match="SPY"):
        primary_daily(bad, required={"SPY"}, now=NOW)
    with pytest.raises(ValueError, match="fresh"):
        primary_daily(published, required={"SPY"}, now=NOW.replace(day=30, hour=16))


def test_primary_excludes_current_utc_day_and_rejects_duplicate() -> None:
    published = _read(PUBLISHED)
    current = copy.deepcopy(_bars(published, "AAPL")[-1])
    current["begins_at"] = "2026-09-29T00:00:00Z"
    _bars(published, "AAPL").append(current)
    primary = primary_daily(published, required={"SPY"}, now=NOW)
    assert current not in _bars(primary, "AAPL")
    _bars(published, "AAPL").append(copy.deepcopy(_bars(published, "AAPL")[-2]))
    with pytest.raises(ValueError, match="duplicate"):
        primary_daily(published, required={"SPY"}, now=NOW)


def test_later_primary_session_inherits_original_review_without_reanchoring() -> None:
    prior, published = _read(PRIOR), _read(PUBLISHED)
    review = create_review(prior, published, now=NOW, note="review")
    legacy = reconcile_daily(published, prior, review, required={"SPY"}, now=NOW)
    later = copy.deepcopy(published)
    later["captured_at"] = "2026-09-30T01:00:00+00:00"
    later["price_as_of"] = "2026-09-30T00:50:00+00:00"
    for series in _results(later["bars"], "bars"):
        bar = copy.deepcopy(series["bars"][-1])
        bar["begins_at"] = "2026-09-29T00:00:00Z"
        series["bars"].append(bar)
    at = datetime(2026, 9, 30, 1, 30, tzinfo=UTC)
    next_legacy = reconcile_daily(later, legacy, review, required={"SPY"}, now=at)
    assert next_legacy["completed_session"] == "2026-09-29"
    assert next_legacy["source_reconciliation"]["primary_snapshot_sha256"] == _digest(later)
    assert (
        next_legacy["source_reconciliation"]["reviewed_primary_snapshot_sha256"]
        == review["primary_snapshot_sha256"]
    )
    assert _bars(next_legacy, "AAPL")[-2] == _bars(prior, "AAPL")[-1]
    assert _bars(next_legacy, "AAPL")[-1] == _bars(later, "AAPL")[-1]
    tampered = copy.deepcopy(legacy)
    tampered["source_reconciliation"]["reviewed_primary_snapshot_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="binding"):
        reconcile_daily(later, tampered, review, required={"SPY"}, now=at)
    tampered = copy.deepcopy(legacy)
    _bars(tampered, "AAPL")[-2]["close_price"] = "100.5"
    also_changed = copy.deepcopy(later)
    _bars(also_changed, "AAPL")[-3]["close_price"] = "100.5"
    with pytest.raises(ValueError, match="accepted history"):
        reconcile_daily(also_changed, tampered, review, required={"SPY"}, now=at)
    with pytest.raises(ValueError, match="reanchor"):
        create_review(legacy, later, now=at, note="new review")


def test_later_unknown_historical_revision_is_rejected() -> None:
    prior, published = _read(PRIOR), _read(PUBLISHED)
    review = create_review(prior, published, now=NOW, note="review")
    legacy = reconcile_daily(published, prior, review, required={"SPY"}, now=NOW)
    later = copy.deepcopy(published)
    _bars(later, "AAPL")[-2]["close_price"] = "100.5"
    with pytest.raises(ValueError, match="revision"):
        reconcile_daily(later, legacy, review, required={"SPY"}, now=NOW)


def test_primary_rejects_fake_regular_flags_and_incomplete_bar() -> None:
    published = _read(PUBLISHED)
    _bars(published, "AAPL")[-1]["interpolated"] = "false"
    with pytest.raises(ValueError, match="flag"):
        primary_daily(published, required={"SPY"}, now=NOW)
    published = _read(PUBLISHED)
    del _bars(published, "AAPL")[-1]["low_price"]
    with pytest.raises(ValueError, match="low_price"):
        primary_daily(published, required={"SPY"}, now=NOW)


def test_review_rejects_unseen_old_date_added_to_existing_symbol() -> None:
    prior, published = _read(PRIOR), _read(PUBLISHED)
    extra = copy.deepcopy(_bars(published, "AAPL")[0])
    extra["begins_at"] = "2026-01-01T00:00:00Z"
    _bars(published, "AAPL").append(extra)
    with pytest.raises(ValueError, match="history"):
        create_review(prior, published, now=NOW, note="review")


def test_primary_rejects_future_bar_even_when_optional() -> None:
    published = _read(PUBLISHED)
    future = copy.deepcopy(_bars(published, "AAPL")[-1])
    future["begins_at"] = "2026-09-30T00:00:00Z"
    _bars(published, "AAPL").append(future)
    with pytest.raises(ValueError, match="future"):
        primary_daily(published, required={"SPY"}, now=NOW)


@pytest.mark.parametrize("level", ["snapshot", "series", "bar"])
def test_primary_rejects_provider_error_markers(level: str) -> None:
    published = _read(PUBLISHED)
    if level == "snapshot":
        published["error"] = "price service failed"
    elif level == "series":
        next(s for s in _results(published["bars"], "bars") if s["symbol"] == "SPY")["error"] = (
            "price service failed"
        )
    else:
        _bars(published, "SPY")[-1]["error"] = "price service failed"
    with pytest.raises(ValueError, match="provider error"):
        primary_daily(published, required={"SPY"}, now=NOW)


def test_primary_rejects_contradictory_series_adjustment_and_price_time() -> None:
    published = _read(PUBLISHED)
    next(s for s in _results(published["bars"], "bars") if s["symbol"] == "SPY")[
        "adjustment_type"
    ] = "none"
    with pytest.raises(ValueError, match="split"):
        primary_daily(published, required={"SPY"}, now=NOW)
    published = _read(PUBLISHED)
    published["price_as_of"] = "2026-09-29T13:10:00Z"
    with pytest.raises(ValueError, match="price_as_of"):
        primary_daily(published, required={"SPY"}, now=NOW)


def test_empty_inherited_marker_cannot_reanchor_review() -> None:
    prior, published = _read(PRIOR), _read(PUBLISHED)
    prior["source_reconciliation"] = {}
    with pytest.raises(ValueError, match="reanchor"):
        create_review(prior, published, now=NOW, note="review")


def test_primary_rejects_weekend_regular_daily_bar() -> None:
    published = _read(PUBLISHED)
    extra = copy.deepcopy(_bars(published, "AAPL")[-1])
    extra["begins_at"] = "2026-09-27T00:00:00Z"
    _bars(published, "AAPL").append(extra)
    with pytest.raises(ValueError, match="weekend"):
        primary_daily(published, required={"SPY"}, now=NOW)
