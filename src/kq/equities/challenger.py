"""Fixed prospective earnings/momentum screen; no trading or probabilities.

``screen`` returns one row per captured catalogue/calendar intersection:
symbol, as_of (aware UTC), price_as_of (aware UTC or null), session_date,
close, median_dollar_volume_20d, excess_momentum_20d, report_date,
eps_estimate, eps_actual, earnings_beat, eligible, reason, reasons,
momentum_reason, earnings_reason, challenger_rank,
challenger_selected, momentum_eligible, momentum_rank, momentum_selected.
"""

from __future__ import annotations

import json
import statistics
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd

from kq.equities.research import _number, _results, _timestamp, daily_bars

COLUMNS = [
    "symbol", "as_of", "price_as_of", "session_date", "close",
    "median_dollar_volume_20d", "excess_momentum_20d", "report_date",
    "eps_estimate", "eps_actual", "earnings_beat", "eligible", "reason",
    "reasons", "momentum_reason", "earnings_reason",
    "challenger_rank", "challenger_selected", "momentum_eligible",
    "momentum_rank", "momentum_selected",
]


def _calendar(snapshot: dict[str, Any], captured: datetime) -> dict[str, dict[str, Any]]:
    chosen: dict[str, dict[str, Any]] = {}
    quarters: dict[tuple[str, int, int], str] = {}
    for item in _results(snapshot.get("earnings", []), "earnings"):
        symbol = item.get("symbol")
        if not isinstance(symbol, str) or not symbol or symbol != symbol.upper():
            raise ValueError("earnings symbol must be uppercase")
        year, quarter = item.get("year"), item.get("quarter")
        if type(year) is not int or type(quarter) is not int or quarter not in (1, 2, 3, 4):
            raise ValueError("earnings require year and quarter")
        key = (symbol, year, quarter)
        canonical = json.dumps(item, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if key in quarters and quarters[key] != canonical:
            raise ValueError(f"conflicting earnings quarter: {symbol} {year} Q{quarter}")
        quarters[key] = canonical
        report = item.get("report") or {}
        if not isinstance(report, dict):
            raise ValueError("earnings report must be an object")
        reported = report.get("date")
        if not isinstance(reported, str):
            continue
        try:
            report_date = date.fromisoformat(reported)
        except ValueError as exc:
            raise ValueError("invalid earnings report.date") from exc
        eps = item.get("eps") or {}
        if not isinstance(eps, dict):
            raise ValueError("earnings eps must be an object")
        if report_date > captured.date() and eps.get("actual") is not None:
            raise ValueError("future earnings actual")
        prior = chosen.get(symbol)
        prior_date: date | None = None if prior is None else prior["report_date"]
        is_past = report_date <= captured.date()
        if (prior_date is None
            or (is_past and (prior_date > captured.date() or report_date > prior_date))
            or (not is_past and prior_date > captured.date() and report_date < prior_date)):
            chosen[symbol] = {"report_date": report_date, "report": report,
                              "eps": eps}
    return chosen


EpsContext = tuple[str | None, float | None, float | None, float | None, str | None]


def _eps_reason(  # noqa: PLR0911
    event: dict[str, Any] | None, captured: datetime
) -> EpsContext:
    if event is None:
        return None, None, None, None, "report_not_yet_available"
    reported: date = event["report_date"]
    report: dict[str, Any] = event["report"]
    eps = event["eps"]
    if not isinstance(eps, dict):
        raise ValueError("earnings eps must be an object")
    date_text = reported.isoformat()
    if captured < datetime.combine(reported + timedelta(days=1), datetime.min.time(), UTC):
        return date_text, None, None, None, "report_not_yet_available"
    if (captured.date() - reported).days > 7:
        return date_text, None, None, None, "stale_report"
    if report.get("verified") is not True:
        return date_text, None, None, None, "unverified_report"
    estimate = eps.get("estimate")
    actual = eps.get("actual")
    if actual is None:
        return date_text, None, None, None, "unreported_eps"
    actual_value = _number(actual, "eps.actual", positive=False)
    if estimate is None:
        return date_text, None, actual_value, None, "missing_estimate"
    estimate_value = _number(estimate, "eps.estimate", positive=False)
    if estimate_value <= 0:
        return date_text, estimate_value, actual_value, None, "nonpositive_estimate"
    beat = actual_value / estimate_value - 1
    return (date_text, estimate_value, actual_value, beat,
            None if beat >= 0.05 else "insufficient_earnings_beat")


def screen(snapshot: dict[str, Any]) -> pd.DataFrame:  # noqa: PLR0912, PLR0915
    """Apply frozen 21-session/20-day liquidity and reported-EPS rules.

    The ablation ranks the identical event-conditioned universe using only
    the common price/liquidity/positive-excess rules. No future bars are read.
    """
    captured = _timestamp(snapshot.get("captured_at"), "captured_at")
    if captured > datetime.now(UTC):
        raise ValueError("captured_at cannot be future")
    if snapshot.get("benchmark") != "SPY":
        raise ValueError("benchmark must be SPY")
    if snapshot.get("adjustment_type") != "split":
        raise ValueError("adjustment_type must be split")
    universe = snapshot.get("universe")
    if (not isinstance(universe, list) or any(
        not isinstance(s, str) or not s or s != s.upper() or s == "SPY" for s in universe
    ) or len(set(universe)) != len(universe)):
        raise ValueError("universe must be unique uppercase stock symbols")
    events = _calendar(snapshot, captured)
    for name in ("earnings_as_of", "price_as_of"):
        value = snapshot.get(name)
        if value is not None and _timestamp(value, name) > captured:
            raise ValueError(f"{name} cannot follow captured_at")
    for series in _results(snapshot.get("bars", []), "bars"):
        for bar in series.get("bars", []):
            if not isinstance(bar, dict) or any(
                flag in bar and type(bar[flag]) is not bool
                for flag in ("interpolated", "synthetic", "is_synthetic")
            ):
                raise ValueError("invalid synthetic flag")
    frame = daily_bars(snapshot)
    base = frame.loc[frame.symbol == "SPY"].sort_values("session_date")
    if len(base) < 21 or (captured.date() - base.iloc[-1].session_date).days > 4:
        raise ValueError("SPY requires 21 fresh completed sessions")
    dates = base.tail(21)["session_date"].tolist()
    spy_return = float(base.iloc[-1]["close"] / base.iloc[-21]["close"] - 1)
    price_as_of = snapshot.get("price_as_of")
    price_time = _timestamp(price_as_of, "price_as_of") if price_as_of is not None else None
    rows: list[dict[str, Any]] = []
    for symbol in sorted(set(universe) & set(events)):
        stock = frame.loc[frame.symbol == symbol].sort_values("session_date")
        last = stock.iloc[-1] if not stock.empty else None
        reason: str | None = None
        median: float | None = None
        excess: float | None = None
        close = float(last["close"]) if last is not None else None
        if len(stock) < 21 or stock.tail(21)["session_date"].tolist() != dates:
            reason = "missing_history"
        elif close is not None and close < 5:
            reason = "low_price"
        else:
            dollar_values = (stock.tail(20)["close"] * stock.tail(20)["volume"]).tolist()
            median = float(statistics.median(dollar_values))
            if median < 20_000_000:
                reason = "illiquid"
            else:
                excess = float(stock.iloc[-1]["close"] / stock.iloc[-21]["close"] - 1
                               - spy_return)
                if excess <= 0:
                    reason = "nonpositive_excess"
        report_date, estimate, actual, beat, eps_reason = _eps_reason(events[symbol], captured)
        momentum_eligible = reason is None
        challenge_reason = reason or eps_reason
        rows.append({
            "symbol": symbol, "as_of": captured, "price_as_of": price_time,
            "session_date": None if last is None else last["session_date"].isoformat(),
            "close": close, "median_dollar_volume_20d": median,
            "excess_momentum_20d": excess, "report_date": report_date,
            "eps_estimate": estimate, "eps_actual": actual, "earnings_beat": beat,
            "eligible": challenge_reason is None, "reason": challenge_reason,
            "reasons": ";".join(filter(None, (reason, eps_reason))) or None,
            "momentum_reason": reason, "earnings_reason": eps_reason,
            "challenger_rank": None, "challenger_selected": False,
            "momentum_eligible": momentum_eligible, "momentum_rank": None,
            "momentum_selected": False,
        })
    result = pd.DataFrame(rows, columns=COLUMNS)
    result["as_of"] = pd.to_datetime(result["as_of"], utc=True)
    result["price_as_of"] = pd.to_datetime(result["price_as_of"], utc=True)
    for lane, eligible in (("challenger", "eligible"), ("momentum", "momentum_eligible")):
        ranked = sorted(
            (row for row in rows if row[eligible]),
            key=lambda row: (-row["excess_momentum_20d"], row["symbol"]),
        )
        ranks = {row["symbol"]: index for index, row in enumerate(ranked, 1)}
        result[f"{lane}_rank"] = result["symbol"].map(ranks)
        result[f"{lane}_selected"] = result[f"{lane}_rank"].le(3).fillna(False)
    return result
