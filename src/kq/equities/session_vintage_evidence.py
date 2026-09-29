"""Canonical daily bars and retained supplement evidence for vintage reviews."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from kq.equities.research import _results, _timestamp
from kq.equities.session_data import _digest, _official_bar

_DAY = date(2026, 9, 28)
_METHOD = "robinhood_session_statistics_official_close_v1"
_PRICES = ("open_price", "high_price", "low_price", "close_price")


def _instant(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field} must be timezone-aware")
        return value
    return _timestamp(value, field)


def _decimal(value: Any, field: str, *, positive: bool = True) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be finite")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be finite") from exc
    if not number.is_finite() or (positive and number <= 0):
        raise ValueError(f"{field} must be finite and positive")
    return number


def _provider_error(record: dict[str, Any]) -> None:
    if any(record.get(field) for field in ("error", "errors", "source_error", "has_error")):
        raise ValueError("daily history contains provider error")


def _bar(bar: dict[str, Any], symbol: str) -> dict[str, Any]:
    _provider_error(bar)
    starts = _timestamp(bar.get("begins_at"), "begins_at")
    if starts.date().weekday() >= 5:
        raise ValueError(f"weekend daily bar for {symbol}")
    if starts.hour or starts.minute or starts.second or starts.microsecond:
        raise ValueError(f"daily bar timestamp is not UTC midnight for {symbol}")
    if starts.utcoffset() != timedelta(0) or bar.get("session") != "reg":
        raise ValueError(f"regular UTC daily bar required for {symbol}")
    for flag in ("interpolated", "synthetic", "is_synthetic"):
        if flag in bar and not isinstance(bar[flag], bool):
            raise ValueError(f"invalid {flag} flag for {symbol}")
    values = {field: _decimal(bar.get(field), field) for field in _PRICES}
    volume = _decimal(bar.get("volume"), "volume", positive=False)
    if volume < 0 or volume != volume.to_integral_value():
        raise ValueError(f"invalid volume for {symbol}")
    if values["low_price"] > min(values["open_price"], values["close_price"]):
        raise ValueError(f"invalid OHLCV for {symbol}")
    if values["high_price"] < max(values["open_price"], values["close_price"]):
        raise ValueError(f"invalid OHLCV for {symbol}")
    synthetic = any(bar.get(flag) is True for flag in ("interpolated", "synthetic", "is_synthetic"))
    if not synthetic and volume == 0:
        raise ValueError(f"real daily bar requires positive volume for {symbol}")
    return {
        "session_date": starts.date().isoformat(),
        "session": "reg",
        "synthetic": synthetic,
        **{field: str(values[field].normalize()) for field in _PRICES},
        "volume": int(volume),
    }


def _history(
    snapshot: dict[str, Any],
) -> dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]]:
    indexed: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]] = {}
    symbols: set[str] = set()
    captured = _timestamp(snapshot.get("captured_at"), "captured_at")
    for series in _results(snapshot.get("bars", []), "bars"):
        symbol = series.get("symbol")
        if not isinstance(symbol, str) or not symbol or symbol != symbol.upper():
            raise ValueError("daily bars require uppercase symbols")
        if symbol in symbols:
            raise ValueError(f"duplicate symbol {symbol}")
        symbols.add(symbol)
        _provider_error(series)
        if "adjustment_type" in series and series["adjustment_type"] != "split":
            raise ValueError(f"split-adjusted daily series required for {symbol}")
        if series.get("interval") != "day" or series.get("bounds") != "regular":
            raise ValueError(f"day/regular series required for {symbol}")
        if not isinstance(series.get("bars"), list):
            raise ValueError(f"bar list required for {symbol}")
        for raw in series["bars"]:
            if not isinstance(raw, dict):
                raise ValueError(f"invalid bar for {symbol}")
            bar = _bar(raw, symbol)
            if bar["session_date"] > captured.date().isoformat():
                raise ValueError(f"future daily bar for {symbol}")
            key = symbol, bar["session_date"]
            if key in indexed:
                raise ValueError(f"duplicate daily bar for {symbol} {key[1]}")
            indexed[key] = raw, bar
    return indexed


def _repairs(  # noqa: PLR0912
    prior: dict[str, Any], history: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]]
) -> set[tuple[str, str]]:
    records = prior.get("session_repairs", [])
    if not isinstance(records, list):
        raise ValueError("invalid prior session repairs")
    evidence = prior.get("session_evidence")
    if records and not isinstance(evidence, dict):
        raise ValueError("prior supplement evidence missing")
    if not records:
        return set()
    assert isinstance(evidence, dict)
    evidence_hash = _digest(evidence)
    fundamentals = {
        row["symbol"]: row for row in _results(evidence.get("fundamentals"), "fundamentals")
    }
    quotes = {row["quote"]["symbol"]: row for row in _results(evidence.get("quotes"), "quotes")}
    if len(fundamentals) != len(_results(evidence.get("fundamentals"), "fundamentals")):
        raise ValueError("duplicate prior fundamental evidence")
    if len(quotes) != len(_results(evidence.get("quotes"), "quotes")):
        raise ValueError("duplicate prior quote evidence")
    seen: set[tuple[str, str]] = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("invalid prior repair record")
        symbol, day = record.get("symbol"), record.get("session_date")
        if not isinstance(symbol, str) or not isinstance(day, str):
            raise ValueError("invalid prior repair identity")
        key = symbol, day
        if (
            key in seen
            or record.get("method") != _METHOD
            or record.get("evidence_hash") != evidence_hash
        ):
            raise ValueError("prior supplement evidence hash or method mismatch")
        if day != _DAY.isoformat() or key not in history:
            raise ValueError("prior supplement saved bar missing")
        for field, evidence_field in (
            ("fundamentals_as_of", "fundamentals_as_of"),
            ("quotes_as_of", "quotes_as_of"),
        ):
            if _instant(record.get(field), field) != _instant(
                evidence.get(evidence_field), evidence_field
            ):
                raise ValueError("prior supplement evidence timestamp mismatch")
        try:
            expected = _official_bar(fundamentals[symbol], quotes[symbol], symbol, _DAY)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"prior supplement evidence invalid for {symbol}") from exc
        if _bar(expected, symbol) != history[key][1]:
            raise ValueError(f"prior accepted saved bar disagrees with evidence for {symbol}")
        seen.add(key)
    return seen


def _accepted_fingerprint(
    history: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]],
    symbols: set[str],
    excluded: set[tuple[str, str]],
) -> str:
    bars = [
        {"symbol": symbol, **normalized}
        for (symbol, day), (_, normalized) in sorted(history.items())
        if symbol in symbols and day <= _DAY.isoformat() and (symbol, day) not in excluded
    ]
    return _digest({"bars": bars})
