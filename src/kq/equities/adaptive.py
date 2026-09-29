"""Frozen, pure daily adaptive equity research signals.

``signals`` returns symbol, as_of (UTC), session_date (ISO), source_hash,
method_hash, price_as_of (UTC or null), excess20, excess60, volatility20,
score, state, action, reason, candidate_eligible. Missing features are null.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd

from kq.equities.research import _results, _timestamp, daily_bars

# NYSE's published 2026 full-day closures. Early closes remain sessions.
_CLOSED_2026 = frozenset(
    date(2026, month, day)
    for month, day in (
        (1, 1),
        (1, 19),
        (2, 16),
        (4, 3),
        (5, 25),
        (6, 19),
        (7, 3),
        (9, 7),
        (11, 26),
        (12, 25),
    )
)
PROTOCOL = (
    "adaptive-stock-v1|NYSE-2026-closures=2026-01-01,01-19,02-16,04-03,"
    "05-25,06-19,07-03,09-07,11-26,12-25|61-real-aligned-sessions|"
    "split-adjusted-regular-positive-volume|log-excess=20,60-SPY|"
    "sample-stock-log-return-volatility=20|score=0.5*(E20/v/sqrt20+E60/v/sqrt60)|"
    "buy>=0.5|held-sell<=0|price>=5|median20-dollar-volume>=20000000|"
    "source-age<=24h|captured-and-price-as-of<=now"
)
METHOD_HASH = hashlib.sha256(PROTOCOL.encode()).hexdigest()
COLUMNS = [
    "symbol",
    "as_of",
    "session_date",
    "source_hash",
    "method_hash",
    "price_as_of",
    "excess20",
    "excess60",
    "volatility20",
    "score",
    "state",
    "action",
    "reason",
    "candidate_eligible",
]
_STATES = frozenset(("flat", "held", "pending_entry", "pending_exit"))


def _session_days(end: date, count: int) -> list[date] | None:
    days: list[date] = []
    cursor = end
    while len(days) < count:
        if cursor.year != 2026:
            return None
        if cursor.weekday() < 5 and cursor not in _CLOSED_2026:
            days.append(cursor)
        cursor -= timedelta(days=1)
    days.reverse()
    return days


def _symbol(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.upper() and value != "SPY"


def _evidence(  # noqa: PLR0911
    snapshot: dict[str, Any], now: datetime
) -> tuple[datetime | None, datetime | None, str | None]:
    try:
        captured = _timestamp(snapshot.get("captured_at"), "captured_at")
        price = _timestamp(snapshot.get("price_as_of"), "price_as_of")
    except ValueError:
        return None, None, "missing_or_invalid_source_time"
    if captured > now or price > now or price > captured:
        return captured, price, "future_source_time"
    for field in ("earnings_as_of", "news_as_of"):
        value = snapshot.get(field)
        if value is not None:
            try:
                observed = _timestamp(value, field)
            except ValueError:
                return captured, price, f"invalid_{field}"
            if observed > now or observed > captured:
                return captured, price, f"future_{field}"
    if now - captured > timedelta(hours=24) or now - price > timedelta(hours=24):
        return captured, price, "stale_source_time"
    if snapshot.get("benchmark") != "SPY" or snapshot.get("adjustment_type") != "split":
        return captured, price, "unverified_price_basis"
    return captured, price, None


def _features(
    stock: pd.DataFrame, spy: pd.DataFrame, days: list[date]
) -> tuple[float, float, float, float] | None:
    selected = stock.set_index("session_date").reindex(days)
    benchmark = spy.set_index("session_date").reindex(days)
    if selected["close"].isna().any() or benchmark["close"].isna().any():
        return None
    if (selected["volume"] <= 0).any() or (benchmark["volume"] <= 0).any():
        return None
    prices = selected["close"].astype(float).tolist()
    base = benchmark["close"].astype(float).tolist()
    returns = [math.log(prices[i] / prices[i - 1]) for i in range(41, 61)]
    volatility = statistics.stdev(returns)
    if not math.isfinite(volatility) or volatility <= 0:
        return None
    e20 = math.log(prices[-1] / prices[-21]) - math.log(base[-1] / base[-21])
    e60 = math.log(prices[-1] / prices[0]) - math.log(base[-1] / base[0])
    score = 0.5 * (e20 / (volatility * math.sqrt(20)) + e60 / (volatility * math.sqrt(60)))
    return e20, e60, volatility, score


def _action(state: str, score: float | None, eligible: bool, reason: str | None) -> tuple[str, str]:
    if state.startswith("pending_"):
        return "PENDING", reason or "pending_order"
    if score is None:
        return "WAIT_DATA", reason or "invalid_price_evidence"
    if state == "held":
        return ("SELL", "nonpositive_exit") if score <= 0 else ("HOLD", "positive_hold_band")
    if not eligible:
        return "WAIT_DATA", reason or "entry_ineligible"
    return ("BUY", "buy_threshold_met") if score >= 0.5 else ("WATCH", "below_buy_threshold")


def _unexpected_session(frame: pd.DataFrame, days: list[date]) -> bool:
    if frame.empty:
        return False
    expected = set(days)
    return any(day >= days[0] and day not in expected for day in frame.session_date)


def signals(  # noqa: PLR0912, PLR0915
    snapshot: dict[str, Any], states: dict[str, str], *, now: datetime
) -> pd.DataFrame:
    """Score a captured price snapshot without I/O, orders, or mutable state."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be aware")
    now = now.astimezone(UTC)
    if any(not _symbol(s) or state not in _STATES for s, state in states.items()):
        raise ValueError("invalid symbol or state")
    universe = snapshot.get("universe")
    if (
        not isinstance(universe, list)
        or any(not _symbol(s) for s in universe)
        or len(universe) != len(set(universe))
    ):
        raise ValueError("universe requires unique uppercase stock symbols")
    quarantined = snapshot.get("quarantined_symbols", [])
    if not isinstance(quarantined, list) or any(not _symbol(s) for s in quarantined):
        raise ValueError("quarantined_symbols requires stock symbols")
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)
    source_hash = hashlib.sha256(canonical.encode()).hexdigest()
    captured, price_time, global_reason = _evidence(snapshot, now)
    as_of = captured or now
    raw_series = _results(snapshot.get("bars", []), "bars")
    for series in raw_series:
        raw_bars = series.get("bars", [])
        if not isinstance(raw_bars, list):
            raise ValueError("bars require a list")
        for bar in raw_bars:
            if not isinstance(bar, dict) or any(
                flag in bar and type(bar[flag]) is not bool
                for flag in ("synthetic", "is_synthetic", "interpolated")
            ):
                raise ValueError("invalid synthetic flag")
    try:
        frame = daily_bars(snapshot) if captured is not None else pd.DataFrame()
    except ValueError as exc:
        frame = pd.DataFrame()
        global_reason = f"invalid_price_bars:{exc}"
    end = (captured or now).date() - timedelta(days=1)
    days = _session_days(end, 61)
    if days is None:
        global_reason = global_reason or "unsupported_exchange_calendar_year"
    spy = frame.loc[frame.symbol == "SPY"] if not frame.empty else pd.DataFrame()
    if days is not None and global_reason is None:
        spy_dates = set(spy.session_date) if not spy.empty else set()
        if _unexpected_session(spy, days):
            global_reason = "unexpected_SPY_session"
        elif not set(days).issubset(spy_dates):
            global_reason = "missing_SPY_session"
    rows: list[dict[str, Any]] = []
    for symbol in sorted(set(universe) | set(states)):
        state = states.get(symbol, "flat")
        stock = frame.loc[frame.symbol == symbol] if not frame.empty else pd.DataFrame()
        last_day = None if days is None else days[-1].isoformat()
        reason = global_reason
        values: tuple[float, float, float, float] | None = None
        if reason is None and days is not None:
            if _unexpected_session(stock, days):
                reason = "unexpected_stock_session"
            elif stock.empty or not set(days).issubset(set(stock.session_date)):
                reason = "missing_stock_session"
            else:
                values = _features(stock, spy, days)
                if values is None:
                    reason = "invalid_or_zero_volume_or_volatility"
        eligible = symbol in universe and symbol not in quarantined and values is not None
        if eligible and days is not None:
            selected = stock.set_index("session_date").reindex(days)
            latest = float(selected.iloc[-1]["close"])
            median_dollars = statistics.median(
                (selected["close"].tail(20) * selected["volume"].tail(20)).tolist()
            )
            if latest < 5:
                eligible, reason = False, "low_price"
            elif median_dollars < 20_000_000:
                eligible, reason = False, "illiquid"
        elif values is not None and symbol in quarantined:
            reason = "quarantined"
        elif values is not None and symbol not in universe:
            reason = "outside_candidate_universe"
        action, reason = _action(state, None if values is None else values[3], eligible, reason)
        rows.append(
            {
                "symbol": symbol,
                "as_of": as_of,
                "session_date": last_day,
                "source_hash": source_hash,
                "method_hash": METHOD_HASH,
                "price_as_of": price_time,
                "excess20": None if values is None else values[0],
                "excess60": None if values is None else values[1],
                "volatility20": None if values is None else values[2],
                "score": None if values is None else values[3],
                "state": state,
                "action": action,
                "reason": reason,
                "candidate_eligible": eligible,
            }
        )
    result = pd.DataFrame(rows, columns=COLUMNS)
    result["as_of"] = pd.to_datetime(result["as_of"], utc=True)
    result["price_as_of"] = pd.to_datetime(result["price_as_of"], utc=True)
    return result
