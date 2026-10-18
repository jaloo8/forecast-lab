"""Point-in-time price scores on a verified SPY session calendar."""

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from kq.equities.strategy_lab.registry import FAMILIES, LOOKBACKS


def _invalid_rows(frame: pd.DataFrame) -> pd.Series:
    prices = frame[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors="coerce")
    invalid = (~np.isfinite(prices) | (prices <= 0)).any(axis=1)
    for column in prices.columns:
        if frame[column].dtype == object or frame[column].dtype == bool:
            invalid |= frame[column].map(lambda value: isinstance(value, (bool, np.bool_)))
    invalid |= prices.high < prices[["open", "close", "low"]].max(axis=1)
    invalid |= prices.low > prices[["open", "close", "high"]].min(axis=1)
    for flag in ("synthetic", "is_synthetic", "interpolated"):
        if flag in frame:
            invalid |= frame[flag].fillna(False).astype(bool)
    if "session" in frame:
        invalid |= frame.session != "reg"
    return invalid


def _scores(close: pd.DataFrame, family: str, lookback: int) -> pd.Series:
    window = close.iloc[-lookback - 1 :]
    returns = window.iloc[-1] / window.iloc[0] - 1
    daily = np.log(window / window.shift(1)).iloc[1:]
    volatility = daily.std(ddof=1)
    if family == "momentum":
        return returns - returns["SPY"]
    if family == "risk_momentum":
        relative = np.log1p(returns) - np.log1p(returns["SPY"])
        return relative / (volatility.replace(0, np.nan) * np.sqrt(lookback))
    if family == "reversal":
        return -returns
    if family == "low_volatility":
        return -volatility
    return window.iloc[-1] / window.iloc[:-1].max() - 1


def score_candidates(
    bars: pd.DataFrame, decision_date: date, family: str, lookback: int
) -> pd.DataFrame:
    """Return symbol:str, score:float, eligible:bool, reason:str, as_of:UTC.

    `as_of` is the simulated 16:00 New York decision timestamp, not collection
    time. Input bars are validated regular daily bars with simulated availability
    in as_of; preserve actual retrieval metadata separately at the source boundary.
    Invalid candidates remain explicit. Valid scores sort descending, with symbol
    ascending to break ties. Only sessions through the decision affect features.
    """
    if family not in FAMILIES or lookback not in LOOKBACKS:
        raise ValueError("unregistered scoring rule")
    cutoff = datetime.combine(decision_date, time(16), ZoneInfo("America/New_York")).astimezone(UTC)
    frame = bars.loc[bars.session_date <= decision_date].copy()
    symbols = sorted(set(frame.symbol) - {"SPY"})
    result = pd.DataFrame(
        {"symbol": symbols, "score": np.nan, "eligible": False, "reason": "", "as_of": cutoff}
    ).set_index("symbol")
    spy = frame.loc[frame.symbol == "SPY"].sort_values("session_date")
    count = max(20, lookback + 1)
    dates = spy.session_date.drop_duplicates().tail(count)
    if len(dates) != count or dates.iloc[-1] != decision_date:
        result["reason"] = "unavailable_benchmark"
        return result.reset_index()
    frame = frame.loc[frame.session_date.isin(dates)].copy()
    frame["invalid"] = _invalid_rows(frame)
    frame["late"] = pd.to_datetime(frame.as_of, utc=True, errors="coerce").isna() | (
        pd.to_datetime(frame.as_of, utc=True, errors="coerce") > cutoff
    )
    frame["duplicate"] = frame.duplicated(["symbol", "session_date"], keep=False)
    failures = frame.groupby("symbol")[["invalid", "late", "duplicate"]].any()
    if failures.loc["SPY"].any():
        result["reason"] = "unavailable_benchmark"
        return result.reset_index()
    unique = frame.drop_duplicates(["symbol", "session_date"])
    close = unique.pivot(index="session_date", columns="symbol", values="close").reindex(dates)
    close = close.apply(pd.to_numeric, errors="coerce")
    volume = unique.pivot(index="session_date", columns="symbol", values="volume").reindex(dates)
    volume = volume.apply(pd.to_numeric, errors="coerce")
    scores = _scores(close.where(close > 0), family, lookback).reindex(symbols)
    reasons = result.reason.copy()
    tests = (
        (close.notna().sum().reindex(symbols).fillna(0) != count, "insufficient_history"),
        (failures.invalid.reindex(symbols, fill_value=False), "invalid_bar"),
        (failures.late.reindex(symbols, fill_value=False), "unavailable_as_of"),
        (failures.duplicate.reindex(symbols, fill_value=False), "duplicate_session"),
        (close.iloc[-1].reindex(symbols) < 5, "below_minimum_price"),
        (
            (close * volume).iloc[-20:].median().reindex(symbols) < 20_000_000,
            "insufficient_liquidity",
        ),
        (~np.isfinite(scores), "zero_volatility" if family == "risk_momentum" else "invalid_score"),
    )
    for mask, reason in tests:
        reasons.loc[mask & reasons.eq("")] = reason
    if family != "low_volatility":
        reasons.loc[(scores <= 0) & reasons.eq("")] = "signal_not_positive"
    result["reason"] = reasons
    result["eligible"] = reasons.eq("")
    result["score"] = scores.where(result.eligible)
    return result.reset_index().sort_values(
        ["eligible", "score", "symbol"], ascending=[False, False, True], ignore_index=True
    )
