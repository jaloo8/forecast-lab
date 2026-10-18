"""Verified completed-session statistics supplement delayed daily history."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from kq.equities.research import _number, _results, _timestamp, daily_bars

_METHOD = "robinhood_session_statistics_official_close_v1"
_FIELDS = ("open_price", "high_price", "low_price", "close_price", "volume")


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _synthetic(bar: dict[str, Any]) -> bool:
    return any(bar.get(flag) is True for flag in ("interpolated", "synthetic", "is_synthetic"))


def _index(rows: list[dict[str, Any]], *, quotes: bool = False) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = (row.get("quote") or {}).get("symbol") if quotes else row.get("symbol")
        if not isinstance(symbol, str) or not symbol or symbol != symbol.upper():
            raise ValueError("Missing symbol identity in session evidence")
        if symbol in result:
            raise ValueError(f"duplicate session evidence for {symbol}")
        result[symbol] = row
    return result


def _target(now: datetime) -> date:
    day = now.date() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _observed(raw: Any, day: date, now: datetime) -> datetime:
    observed = _timestamp(raw, "session evidence timestamp")
    local = observed.astimezone(ZoneInfo("America/New_York"))
    if (
        observed > now
        or now - observed > timedelta(hours=24)
        or local.date() < day
        or (local.date() == day and local.time() < time(16))
        or (local.date() > day and local.weekday() < 5 and local.time() >= time(9, 30))
    ):
        raise ValueError("Session evidence must be fresh, after close and before next open")
    return observed


def _official_bar(
    fundamental: dict[str, Any], quote: dict[str, Any], symbol: str, day: date
) -> dict[str, Any]:
    close = quote.get("close") or {}
    if (
        fundamental.get("symbol") != symbol
        or fundamental.get("bounds") != "regular"
        or fundamental.get("market_date") != day.isoformat()
        or (quote.get("quote") or {}).get("symbol") != symbol
        or close.get("symbol") != symbol
        or close.get("date") != day.isoformat()
        or close.get("interpolated") is not False
        or close.get("source") != "sip-list-exchange-close"
    ):
        raise ValueError("matching regular-session statistics and official SIP close required")
    values = {k: _number(fundamental.get(k), k) for k in ("open", "high", "low", "volume")}
    price = _number(close.get("price"), "official close")
    if (
        not values["low"]
        <= min(values["open"], price)
        <= max(values["open"], price)
        <= values["high"]
    ):
        raise ValueError("session OHLC is inconsistent")
    if not values["volume"].is_integer():
        raise ValueError("session volume must be an integer")
    return dict(
        begins_at=day.isoformat() + "T00:00:00Z",
        session="reg",
        interpolated=False,
        open_price=fundamental["open"],
        high_price=fundamental["high"],
        low_price=fundamental["low"],
        close_price=close["price"],
        volume=int(values["volume"]),
    )


def _carry_prior(series: dict[str, dict[str, Any]], prior: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = copy.deepcopy(prior.get("session_repairs", []))
    original = _index(_results(prior.get("bars", []), "prior bars"))
    seen: set[tuple[str, str]] = set()
    for record in records:
        symbol, day = record["symbol"], record["session_date"]
        key = (symbol, day)
        if key in seen or record["method"] != _METHOD:
            raise ValueError("Invalid prior session repair provenance")
        seen.add(key)
        if symbol not in series:
            raise ValueError(f"Missing previously repaired symbol {symbol}")
        saved = [b for b in original[symbol]["bars"] if b["begins_at"][:10] == day]
        current = [b for b in series[symbol]["bars"] if b["begins_at"][:10] == day]
        if len(saved) != 1 or len(current) > 1 or _synthetic(saved[0]):
            raise ValueError("Invalid prior session repair bars")
        if current and not _synthetic(current[0]):
            if any(float(current[0][k]) != float(saved[0][k]) for k in _FIELDS):
                raise ValueError(f"history revision for repaired {symbol} {day}")
        else:
            series[symbol]["bars"] = [
                b for b in series[symbol]["bars"] if b["begins_at"][:10] != day
            ] + [copy.deepcopy(saved[0])]
    return records


def complete_session(  # noqa: PLR0912
    snapshot: dict[str, Any],
    evidence: dict[str, Any],
    *,
    required: set[str],
    now: datetime,
    prior: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a provenance-labelled capture; never mutate input or a paper ledger."""
    now = _timestamp(now.isoformat(), "now")
    source_time = _timestamp(snapshot["captured_at"], "captured_at")
    if source_time > now or now - source_time > timedelta(hours=24):
        raise ValueError("Daily history capture must be fresh")
    if snapshot.get("adjustment_type") != "split":
        raise ValueError("Session repair requires split-adjusted history")
    day = _target(now)
    if source_time.date() <= day:
        raise ValueError("Daily capture must follow the completed session's UTC date")
    observed = [_observed(evidence[k], day, now) for k in ("fundamentals_as_of", "quotes_as_of")]
    observed.extend(
        _observed(evidence[k], day, now)
        for k in ("fundamentals_latest_as_of", "quotes_latest_as_of")
        if k in evidence
    )
    if evidence.get("source_errors"):
        raise ValueError("Session evidence contains source errors")
    fundamentals = _index(_results(evidence["fundamentals"], "fundamentals"))
    quotes = _index(_results(evidence["quotes"], "quotes"), quotes=True)
    result = copy.deepcopy(snapshot)
    result["bars"] = _results(result.get("bars", []), "bars")
    series = _index(result["bars"])
    required = required | {str(snapshot["benchmark"])}
    if required - series.keys():
        raise ValueError(f"Missing required history: {sorted(required - series.keys())}")
    if prior and _timestamp(prior["captured_at"], "prior captured_at") > now:
        raise ValueError("Prior repair capture is in the future")
    repairs = _carry_prior(series, prior) if prior else []
    errors = list(result.get("source_errors", []))
    for symbol, row in series.items():
        current = [b for b in row["bars"] if b["begins_at"][:10] == day.isoformat()]
        if len(current) > 1:
            raise ValueError(f"duplicate daily bar for {symbol}")
        if (
            current
            and not _synthetic(current[0])
            and _number(current[0]["volume"], "volume", positive=False) > 0
        ):
            continue
        try:
            if current and not _synthetic(current[0]):
                raise ValueError("existing nonsynthetic daily bar has no volume")
            bar = _official_bar(fundamentals.get(symbol, {}), quotes.get(symbol, {}), symbol, day)
        except (ValueError, KeyError, TypeError) as exc:
            if symbol in required:
                raise ValueError(f"Required {symbol} session unavailable: {exc}") from exc
            errors.append(f"Session fallback unavailable for {symbol}: {exc}")
            continue
        row["bars"] = [b for b in row["bars"] if b["begins_at"][:10] != day.isoformat()] + [bar]
        repairs.append(
            dict(
                symbol=symbol,
                session_date=day.isoformat(),
                method=_METHOD,
                fundamentals_as_of=observed[0].isoformat(),
                quotes_as_of=observed[1].isoformat(),
                evidence_hash=_digest(evidence),
            )
        )
    for row in series.values():
        row["bars"].sort(key=lambda b: b["begins_at"])
    result.update(
        captured_at=now.isoformat(),
        parent_captured_at=snapshot["captured_at"],
        parent_hash=_digest(snapshot),
        session_repairs=repairs,
        source_errors=errors,
        price_as_of=max(source_time, *observed).isoformat(),
    )
    completed = daily_bars(result)
    covered = set(completed.loc[(completed.session_date == day) & (completed.volume > 0), "symbol"])
    if required - covered:
        raise ValueError(
            f"Required completed regular session missing: {sorted(required - covered)}"
        )
    return result
