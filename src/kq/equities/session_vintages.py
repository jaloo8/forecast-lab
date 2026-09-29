"""Pure, finite compatibility review for the 2026-09-28 daily price vintage."""

from __future__ import annotations

import copy
from datetime import date, datetime, timedelta
from typing import Any

from kq.equities.research import _results, _timestamp
from kq.equities.session_data import _digest
from kq.equities.session_vintage_evidence import (
    _DAY,
    _PRICES,
    _accepted_fingerprint,
    _history,
    _instant,
    _provider_error,
    _repairs,
)

_POLICY = "finite_2026_09_28_source_vintage"
_VOLUME_ONLY = frozenset({"AMST", "EONR", "LGCY", "LITS", "PTN", "SCHL", "SNX"})
_NOTICE = (
    "Reviewed September 28 source vintage: legacy paper history retains its accepted "
    "prices; later primary daily prices are preserved separately. This compatibility "
    "view does not establish execution accuracy."
)


def _target(now: datetime) -> date:
    day = now.date() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _fresh(snapshot: dict[str, Any], now: datetime) -> date:
    captured = _timestamp(snapshot.get("captured_at"), "captured_at")
    price = _timestamp(snapshot.get("price_as_of"), "price_as_of")
    if price > captured:
        raise ValueError("price_as_of cannot follow captured_at")
    if any(stamp > now or now - stamp > timedelta(hours=24) for stamp in (captured, price)):
        raise ValueError("Daily capture and price evidence must be fresh")
    if snapshot.get("adjustment_type") != "split":
        raise ValueError("split-adjusted daily history required")
    _provider_error(snapshot)
    target = _target(now)
    if captured.date() <= target:
        raise ValueError("Daily capture must follow the target completed UTC session")
    return target


def _review_entries(prior: dict[str, Any], published: dict[str, Any]) -> list[dict[str, Any]]:
    old, new = _history(prior), _history(published)
    repaired = _repairs(prior, old)
    if old.keys() - new.keys():
        raise ValueError("published history missing prior bars")
    latest_old: dict[str, str] = {}
    for symbol, day in old:
        latest_old[symbol] = max(day, latest_old.get(symbol, day))
    for symbol, day in new.keys() - old.keys():
        if symbol in latest_old and day <= latest_old[symbol]:
            raise ValueError(f"unseen historical bar in published history for {symbol} {day}")
    entries: list[dict[str, Any]] = []
    for key, (_, accepted) in old.items():
        incoming = new[key][1]
        if accepted == incoming:
            continue
        symbol, day = key
        if accepted["synthetic"] and not incoming["synthetic"] and day == _DAY.isoformat():
            continue
        if day != _DAY.isoformat() or incoming["synthetic"]:
            raise ValueError(f"unreviewed history revision for {symbol} {day}")
        if key in repaired:
            kind = "supplement"
        elif (
            symbol in _VOLUME_ONLY
            and all(accepted[f] == incoming[f] for f in _PRICES)
            and incoming["volume"] > accepted["volume"]
        ):
            kind = "volume_correction"
        else:
            raise ValueError(f"unreviewed history revision for {symbol} {day}")
        entries.append(
            dict(
                symbol=symbol,
                session_date=day,
                kind=kind,
                accepted_bar=accepted,
                published_bar=incoming,
            )
        )
    return sorted(entries, key=lambda item: (item["symbol"], item["session_date"]))


def create_review(
    prior: dict[str, Any], published: dict[str, Any], *, now: datetime, note: str
) -> dict[str, Any]:
    """Bind an exact finite source transition to its original accepted capture."""
    instant = _instant(now, "now")
    if not isinstance(note, str) or not note.strip():
        raise ValueError("a review rationale is required")
    _fresh(published, instant)
    if _timestamp(prior.get("captured_at"), "prior captured_at") > instant:
        raise ValueError("prior capture is in the future")
    if "source_reconciliation" in prior:
        raise ValueError("cannot reanchor an inherited source review")
    entries = _review_entries(prior, published)
    if not entries:
        raise ValueError("no supported source transition to review")
    original = _history(prior)
    original_symbols = sorted({symbol for symbol, _ in original})
    unaccepted_keys = [
        list(key) for key in sorted(key for key, (_, bar) in original.items() if bar["synthetic"])
    ]
    review = dict(
        schema_version=1,
        policy=_POLICY,
        reviewed_at=instant.isoformat(),
        note=note.strip(),
        prior_sha256=_digest(prior),
        primary_snapshot_sha256=_digest(published),
        original_symbols=original_symbols,
        unaccepted_keys=unaccepted_keys,
        accepted_history_sha256=_accepted_fingerprint(
            original, set(original_symbols), {(key[0], key[1]) for key in unaccepted_keys}
        ),
        entries=entries,
    )
    review["review_sha256"] = _digest(review)
    return review


def primary_daily(snapshot: dict[str, Any], *, required: set[str], now: datetime) -> dict[str, Any]:
    """Return fresh genuine completed primary daily bars without retiming evidence."""
    instant = _instant(now, "now")
    target = _fresh(snapshot, instant)
    indexed = _history(snapshot)
    required_symbols = required | {str(snapshot.get("benchmark", "SPY"))}
    for symbol in required_symbols:
        if (symbol, target.isoformat()) not in indexed or indexed[symbol, target.isoformat()][1][
            "synthetic"
        ]:
            raise ValueError(f"required {symbol} primary daily bar missing for {target}")
    result = copy.deepcopy(snapshot)
    errors = list(result.get("source_errors", []))
    for series in _results(result.get("bars", []), "bars"):
        symbol = series["symbol"]
        kept = []
        for raw in series["bars"]:
            normalized = indexed[
                symbol, _timestamp(raw["begins_at"], "begins_at").date().isoformat()
            ][1]
            if normalized["synthetic"] or normalized["session_date"] >= instant.date().isoformat():
                errors.append(
                    "Primary daily bar excluded for "
                    f"{symbol} {normalized['session_date']}: synthetic or current UTC day"
                )
            else:
                kept.append(raw)
        series["bars"] = kept
        unavailable = (symbol, target.isoformat()) not in indexed or indexed[
            symbol, target.isoformat()
        ][1]["synthetic"]
        if unavailable and symbol not in required_symbols:
            errors.append(f"Optional {symbol} primary daily bar unavailable for {target}")
    result["source_errors"] = errors
    result["completed_session"] = target.isoformat()
    return result


def reconcile_daily(  # noqa: PLR0912
    snapshot: dict[str, Any],
    prior: dict[str, Any],
    review: dict[str, Any],
    *,
    required: set[str],
    now: datetime,
) -> dict[str, Any]:
    """Project accepted legacy prices only for exact reviewed source pairs."""
    if not isinstance(review, dict) or review.get("review_sha256") != _digest(
        {k: v for k, v in review.items() if k != "review_sha256"}
    ):
        raise ValueError("review hash mismatch")
    if review.get("schema_version") != 1 or review.get("policy") != _POLICY:
        raise ValueError("unknown source review policy")
    instant = _instant(now, "now")
    if _instant(review.get("reviewed_at"), "reviewed_at") > instant:
        raise ValueError("review is in the future")
    binding = prior.get("source_reconciliation")
    if "source_reconciliation" in prior:
        if (
            not isinstance(binding, dict)
            or binding.get("policy") != _POLICY
            or binding.get("review_sha256") != review["review_sha256"]
            or binding.get("prior_sha256") != review.get("prior_sha256")
            or binding.get("reviewed_primary_snapshot_sha256")
            != review.get("primary_snapshot_sha256")
            or binding.get("reviewed_at") != review.get("reviewed_at")
        ):
            raise ValueError("inherited review binding mismatch")
    elif _digest(prior) != review.get("prior_sha256"):
        raise ValueError("review prior snapshot hash mismatch")
    symbols = review.get("original_symbols")
    excluded = review.get("unaccepted_keys")
    if (
        not isinstance(symbols, list)
        or not all(isinstance(symbol, str) for symbol in symbols)
        or not isinstance(excluded, list)
        or not all(isinstance(key, list) and len(key) == 2 for key in excluded)
    ):
        raise ValueError("review accepted history identity invalid")
    ignored = {(str(key[0]), str(key[1])) for key in excluded}
    if _accepted_fingerprint(_history(prior), set(symbols), ignored) != review.get(
        "accepted_history_sha256"
    ):
        raise ValueError("review accepted history fingerprint mismatch")
    if not binding and _digest(snapshot) != review.get("primary_snapshot_sha256"):
        raise ValueError("review primary snapshot hash mismatch")
    primary = primary_daily(snapshot, required=required, now=instant)
    actual = _review_entries(prior, snapshot)
    entries = review.get("entries")
    if not isinstance(entries, list) or len(
        {(e.get("symbol"), e.get("session_date")) for e in entries if isinstance(e, dict)}
    ) != len(entries):
        raise ValueError("duplicate or malformed review entries")
    if actual != entries:
        raise ValueError("review pair mismatch or unreviewed history revision")
    result = copy.deepcopy(primary)
    rows = {s["symbol"]: s for s in _results(result["bars"], "bars")}
    old = _history(prior)
    for entry in entries:
        symbol, day = entry["symbol"], entry["session_date"]
        if (symbol, day) not in old:
            raise ValueError("review accepted bar missing")
        bars = rows[symbol]["bars"]
        for index, bar in enumerate(bars):
            if _timestamp(bar["begins_at"], "begins_at").date().isoformat() == day:
                bars[index] = copy.deepcopy(old[symbol, day][0])
                break
        else:
            raise ValueError("review published bar missing")
    result["session_repairs"] = copy.deepcopy(prior.get("session_repairs", []))
    result["session_evidence"] = copy.deepcopy(prior.get("session_evidence"))
    errors = list(result.get("source_errors", []))
    errors.append(_NOTICE)
    result["source_errors"] = errors
    result["source_reconciliation"] = dict(
        policy=_POLICY,
        review_sha256=review["review_sha256"],
        prior_sha256=review["prior_sha256"],
        primary_snapshot_sha256=_digest(snapshot),
        reviewed_primary_snapshot_sha256=review["primary_snapshot_sha256"],
        entry_count=len(entries),
        supplement_count=sum(e["kind"] == "supplement" for e in entries),
        volume_correction_count=sum(e["kind"] == "volume_correction" for e in entries),
        reviewed_at=review["reviewed_at"],
    )
    return result
