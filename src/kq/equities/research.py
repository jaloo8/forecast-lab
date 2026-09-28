"""Completed-session Robinhood bars and prospective momentum research.

``daily_bars`` schema: symbol, session_date, open, close, volume, as_of (UTC).
``scan`` schema: symbol, horizon_sessions, as_of (UTC), session_date, close,
benchmark_close, momentum, benchmark_momentum, excess_momentum,
volatility_20d, pe_ratio, market_cap, sector, latest_eps_actual,
latest_eps_estimate, news_count, status. Missing context is null.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import pandas as pd

BAR_COLUMNS = ["symbol", "session_date", "open", "close", "volume", "as_of"]
RESEARCH_COLUMNS = [
    "symbol",
    "horizon_sessions",
    "as_of",
    "session_date",
    "close",
    "benchmark_close",
    "momentum",
    "benchmark_momentum",
    "excess_momentum",
    "volatility_20d",
    "pe_ratio",
    "market_cap",
    "sector",
    "latest_eps_actual",
    "latest_eps_estimate",
    "news_count",
    "status",
]
HORIZONS = (5, 20, 126)


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an aware ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def _number(value: Any, field: str, *, positive: bool = True) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be finite") from exc
    if not math.isfinite(number) or (positive and number <= 0):
        raise ValueError(f"{field} must be finite and positive")
    return number


def _results(value: Any, field: str) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get("data", value)
        if isinstance(value, dict):
            value = value.get("results", [])
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{field} must contain a results list")
    return value


def _capture(snapshot: dict[str, Any]) -> datetime:
    return _timestamp(snapshot.get("captured_at"), "captured_at")


def daily_bars(snapshot: dict[str, Any]) -> pd.DataFrame:
    """Return real, completed regular-session daily bars from a captured snapshot.

    A bar's UTC date must precede the capture UTC date; this conservative rule
    avoids accidentally treating a still-open session as complete.
    """
    captured = _capture(snapshot)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, object]] = set()
    for series in _results(snapshot.get("bars", []), "bars"):
        if series.get("interval") != "day" or series.get("bounds") != "regular":
            raise ValueError("bars require interval=day and bounds=regular")
        symbol = series.get("symbol")
        if not isinstance(symbol, str) or not symbol or symbol != symbol.upper():
            raise ValueError("bars require an uppercase symbol")
        raw_bars = series.get("bars")
        if not isinstance(raw_bars, list):
            raise ValueError("bars require a list")
        for bar in raw_bars:
            if not isinstance(bar, dict):
                raise ValueError("bar must be an object")
            if any(bar.get(flag) is True for flag in ("is_synthetic", "synthetic", "interpolated")):
                continue
            if bar.get("session") != "reg":
                continue
            starts = _timestamp(bar.get("begins_at"), "begins_at")
            if starts > captured:
                raise ValueError("future bar begins_at")
            if starts.date() >= captured.date():
                continue
            key = (symbol, starts.date())
            if key in seen:
                raise ValueError(f"duplicate bar {symbol} {starts.date()}")
            seen.add(key)
            opening = _number(bar.get("open_price"), "open_price")
            close = _number(bar.get("close_price"), "close_price")
            high = _number(bar.get("high_price"), "high_price")
            low = _number(bar.get("low_price"), "low_price")
            volume = _number(bar.get("volume"), "volume", positive=False)
            if volume < 0 or low > min(opening, close) or high < max(opening, close):
                raise ValueError(f"invalid OHLCV bar for {symbol}")
            rows.append(
                {
                    "symbol": symbol,
                    "session_date": starts.date(),
                    "open": opening,
                    "close": close,
                    "volume": volume,
                    "as_of": captured,
                }
            )
    return pd.DataFrame(rows, columns=BAR_COLUMNS).sort_values(
        ["symbol", "session_date"], ignore_index=True
    )


def _fundamentals(snapshot: dict[str, Any], captured: datetime) -> dict[str, dict[str, Any]]:
    fundamentals: dict[str, dict[str, Any]] = {}
    for item in _results(snapshot.get("fundamentals", []), "fundamentals"):
        symbol = item.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("fundamentals require symbol")
        market_date = item.get("market_date")
        if market_date is not None and pd.Timestamp(market_date).date() > captured.date():
            raise ValueError("future fundamentals market_date")
        fundamentals[symbol] = {
            "pe_ratio": _number(item["pe_ratio"], "pe_ratio", positive=False)
            if item.get("pe_ratio") is not None
            else None,
            "market_cap": _number(item["market_cap"], "market_cap")
            if item.get("market_cap") is not None
            else None,
            "sector": item.get("sector"),
        }
    return fundamentals


def _earnings(snapshot: dict[str, Any], captured: datetime) -> dict[str, dict[str, Any]]:
    earnings: dict[str, dict[str, Any]] = {}
    for item in _results(snapshot.get("earnings", []), "earnings"):
        symbol = item.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("earnings require symbol")
        eps = item.get("eps") or {}
        if not isinstance(eps, dict):
            raise ValueError("earnings eps must be an object")
        report = item.get("report") or {}
        if not isinstance(report, dict) or not report.get("date"):
            if eps.get("actual") is None:
                continue
            raise ValueError("reported earnings require report.date")
        report_date = pd.Timestamp(report["date"]).date()
        if report_date > captured.date():
            if eps.get("actual") is not None:
                raise ValueError("future earnings actual")
            continue
        if eps.get("actual") is None:
            continue
        context = {
            "date": report_date,
            "latest_eps_actual": _number(eps["actual"], "eps.actual", positive=False)
            if eps.get("actual") is not None
            else None,
            "latest_eps_estimate": _number(eps["estimate"], "eps.estimate", positive=False)
            if eps.get("estimate") is not None
            else None,
        }
        if symbol not in earnings or report_date > earnings[symbol]["date"]:
            earnings[symbol] = context
    return earnings


def _news_counts(
    snapshot: dict[str, Any], captured: datetime, covered_symbols: set[str]
) -> dict[str, int]:
    counts: dict[str, int] = {}
    news = snapshot.get("news", [])
    if not isinstance(news, list):
        raise ValueError("news must be a list")
    seen: set[tuple[str, str]] = set()
    for item in news:
        if not isinstance(item, dict) or item.get("symbol") not in covered_symbols:
            raise ValueError("news symbol must match snapshot coverage")
        if not isinstance(item.get("title"), str) or not item["title"].strip():
            raise ValueError("news title required")
        if item.get("kind") not in {"news", "filing"}:
            raise ValueError("news kind must be news or filing")
        url = item.get("url")
        parsed_url = urlparse(url) if isinstance(url, str) else None
        if (
            parsed_url is None
            or parsed_url.scheme != "https"
            or not parsed_url.netloc
            or parsed_url.username is not None
            or parsed_url.password is not None
        ):
            raise ValueError("news require HTTPS URL")
        published = _timestamp(item.get("published_at"), "published_at")
        retrieved = _timestamp(item.get("retrieved_at"), "retrieved_at")
        if published > captured or retrieved > captured:
            raise ValueError("future news observation")
        if retrieved < published:
            raise ValueError("news retrieved_at precedes published_at")
        symbol = item["symbol"]
        key = (str(symbol), str(url))
        if key not in seen:
            counts[symbol] = counts.get(symbol, 0) + 1
            seen.add(key)
    return counts


def scan(snapshot: dict[str, Any]) -> pd.DataFrame:
    """Rank complete shared-session history; scores are observed price returns.

    No forecast probability or estimated future return is produced. A stock
    needs the benchmark's latest session and 127 shared sessions. Benchmark
    history older than four UTC calendar days fails rather than ranking stale data.
    """
    benchmark = snapshot.get("benchmark")
    if benchmark != "SPY":
        raise ValueError("benchmark must be SPY for this release")
    captured = _capture(snapshot)
    bars = daily_bars(snapshot)
    context = _fundamentals(snapshot, captured)
    earnings = _earnings(snapshot, captured)
    counts = _news_counts(snapshot, captured, set(bars["symbol"]))
    base = bars.loc[bars["symbol"] == benchmark].set_index("session_date")
    if base.empty:
        raise ValueError("benchmark has no completed bars")
    latest = base.index.max()
    if (captured.date() - latest).days > 4:
        raise ValueError("stale benchmark history")
    rows: list[dict[str, Any]] = []
    for symbol in sorted(set(bars["symbol"]) - {benchmark}):
        stock = bars.loc[bars["symbol"] == symbol].set_index("session_date")
        if stock.empty or stock.index.max() != latest:
            continue
        if not set(base.tail(max(HORIZONS) + 1).index).issubset(set(stock.index)):
            continue
        shared = (
            stock[["close"]]
            .join(base[["close"]], how="inner", lsuffix="_stock", rsuffix="_benchmark")
            .sort_index()
        )
        if len(shared) < max(HORIZONS) + 1 or shared.index.max() != latest:
            continue
        stock_returns = shared["close_stock"].pct_change().tail(20)
        volatility = float(stock_returns.std(ddof=1))
        for horizon in HORIZONS:
            stock_return = float(
                shared["close_stock"].iloc[-1] / shared["close_stock"].iloc[-horizon - 1] - 1
            )
            base_return = float(
                shared["close_benchmark"].iloc[-1] / shared["close_benchmark"].iloc[-horizon - 1]
                - 1
            )
            fund = context.get(symbol, {})
            eps = earnings.get(symbol, {})
            rows.append(
                {
                    "symbol": symbol,
                    "horizon_sessions": horizon,
                    "as_of": captured,
                    "session_date": latest,
                    "close": float(shared["close_stock"].iloc[-1]),
                    "benchmark_close": float(shared["close_benchmark"].iloc[-1]),
                    "momentum": stock_return,
                    "benchmark_momentum": base_return,
                    "excess_momentum": stock_return - base_return,
                    "volatility_20d": volatility,
                    "pe_ratio": fund.get("pe_ratio"),
                    "market_cap": fund.get("market_cap"),
                    "sector": fund.get("sector"),
                    "latest_eps_actual": eps.get("latest_eps_actual"),
                    "latest_eps_estimate": eps.get("latest_eps_estimate"),
                    "news_count": counts.get(symbol, 0),
                    "status": "ranked",
                }
            )
    return pd.DataFrame(rows, columns=RESEARCH_COLUMNS).sort_values(
        ["horizon_sessions", "excess_momentum", "symbol"],
        ascending=[True, False, True],
        ignore_index=True,
    )
