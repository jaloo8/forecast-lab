"""Small captured-price vintages for portable reconciliation tests."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

_DAY = "2026-09-28"
_FUNDAMENTALS_AT = "2026-09-29T01:20:31+00:00"
_QUOTES_AT = "2026-09-29T01:20:32+00:00"
_ACCEPTED = {
    "AAPL": ("101", "104", "99", "103", 500000),
    "SPY": ("200", "205", "198", "202", 1000000),
    "UXIN": ("1.39", "1.39", "1.30", "1.35", 237108),
    "AMST": ("1.04", "1.05", "1.01", "1.01", 59479),
    "MPU": ("2.78", "2.78", "2.78", "2.78", 100),
}


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _bar(
    day: str, values: tuple[str, str, str, str, int], *, interpolated: bool = False
) -> dict[str, Any]:
    opening, high, low, close, volume = values
    return dict(
        begins_at=f"{day}T00:00:00Z",
        session="reg",
        interpolated=interpolated,
        open_price=opening,
        high_price=high,
        low_price=low,
        close_price=close,
        volume=volume,
    )


def snapshots() -> tuple[dict[str, Any], dict[str, Any]]:
    """Return independent accepted and later primary captures of the same history."""
    fundamentals = []
    quotes = []
    for symbol in ("AAPL", "SPY", "UXIN"):
        opening, high, low, close, volume = _ACCEPTED[symbol]
        fundamentals.append(
            dict(
                symbol=symbol,
                bounds="regular",
                market_date=_DAY,
                open=opening,
                high=high,
                low=low,
                volume=str(volume),
            )
        )
        quotes.append(
            dict(
                quote=dict(symbol=symbol),
                close=dict(
                    symbol=symbol,
                    date=_DAY,
                    price=close,
                    interpolated=False,
                    source="sip-list-exchange-close",
                ),
            )
        )
    evidence = dict(
        fundamentals=fundamentals,
        quotes=quotes,
        fundamentals_as_of=_FUNDAMENTALS_AT,
        quotes_as_of=_QUOTES_AT,
    )
    repairs = [
        dict(
            symbol=symbol,
            session_date=_DAY,
            method="robinhood_session_statistics_official_close_v1",
            fundamentals_as_of=_FUNDAMENTALS_AT,
            quotes_as_of=_QUOTES_AT,
            evidence_hash=_digest(evidence),
        )
        for symbol in ("AAPL", "SPY", "UXIN")
    ]
    bars: list[dict[str, Any]] = [
        dict(
            symbol=symbol,
            interval="day",
            bounds="regular",
            bars=[
                _bar("2026-09-25", _ACCEPTED[symbol]),
                _bar(_DAY, _ACCEPTED[symbol], interpolated=symbol == "MPU"),
            ],
        )
        for symbol in _ACCEPTED
    ]
    next(series for series in bars if series["symbol"] == "MPU")["bars"][-1]["volume"] = 0
    prior: dict[str, Any] = dict(
        captured_at="2026-09-29T01:27:23+00:00",
        price_as_of="2026-09-29T01:20:32+00:00",
        adjustment_type="split",
        benchmark="SPY",
        bars=bars,
        session_repairs=repairs,
        session_evidence=evidence,
        source_errors=[],
    )
    published: dict[str, Any] = copy.deepcopy(prior)
    published["captured_at"] = "2026-09-29T13:02:56+00:00"
    published["price_as_of"] = "2026-09-29T13:02:18+00:00"
    del published["session_repairs"]
    del published["session_evidence"]
    rows = {series["symbol"]: series["bars"][-1] for series in published["bars"]}
    rows["AAPL"].update(open_price="100.5", volume=500001)
    rows["SPY"].update(open_price="199.5", volume=1000001)
    rows["AMST"]["volume"] = 60009
    rows["MPU"].update(
        open_price="2.815",
        high_price="2.815",
        low_price="2.77",
        close_price="2.77",
        volume=3621,
        interpolated=False,
    )
    return prior, published
