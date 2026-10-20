"""Causal SPY-underlying diagnostic, never an options-profitability substitute."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _session(group: pd.DataFrame) -> dict[str, object]:
    expected = pd.date_range(
        group.index[0].normalize() + pd.Timedelta(hours=9, minutes=30), periods=390, freq="min"
    )
    result: dict[str, object] = {
        "session": str(group.index[0].date()),
        "as_of": (group.index[-1] + pd.Timedelta(minutes=1)).tz_convert("UTC"),
        "status": "incomplete_session",
    }
    group = group.between_time("09:30", "15:59")
    if not group.index.equals(expected):
        return result
    values = group[["open", "high", "low", "close"]].to_numpy(dtype=float)
    if (
        not np.isfinite(values).all()
        or (values <= 0).any()
        or group.low.gt(group[["open", "close"]].min(axis=1)).any()
        or group.high.lt(group[["open", "close"]].max(axis=1)).any()
    ):
        result["status"] = "invalid_prices"
        return result
    high, low = float(group.high.iloc[:15].max()), float(group.low.iloc[:15].min())
    signals = np.flatnonzero(group.close.iloc[15:90].to_numpy() > high)
    if not len(signals):
        result["status"] = "no_signal"
        return result
    signal = int(signals[0]) + 15
    entry = signal + 2
    stops = np.flatnonzero(group.close.iloc[entry:359].to_numpy() < low)
    exit_index = min(entry + int(stops[0]) + 2, 360) if len(stops) else 360
    entry_price, exit_price = float(group.open.iloc[entry]), float(group.open.iloc[exit_index])
    result.update(
        status="underlying_only",
        signal_at=(group.index[signal] + pd.Timedelta(minutes=1)).tz_convert("UTC"),
        entry_at=group.index[entry].tz_convert("UTC"),
        exit_at=group.index[exit_index].tz_convert("UTC"),
        entry_price=entry_price,
        exit_price=exit_price,
        exit_reason="range_failure" if exit_index < 360 else "time_exit",
        raw_return=exit_price / entry_price - 1,
    )
    for bp in (1, 5, 10):
        result[f"net_{bp}bp"] = exit_price * (1 - bp / 10000) / (entry_price * (1 + bp / 10000)) - 1
    return result


def underlying_diagnostic(bars: pd.DataFrame) -> pd.DataFrame:
    """Minute-start OHLC -> daily status, UTC as_of/signal/fill times and returns.

    Full 390-minute sessions only; partial/early-close days remain unscored.
    The output is conditional share returns, not option returns or a portfolio.
    Calendar coverage outside supplied dates must be verified by the caller.
    """
    if (
        not isinstance(bars.index, pd.DatetimeIndex)
        or bars.index.tz is None
        or not bars.index.is_unique
        or not bars.index.is_monotonic_increasing
        or bars.empty
    ):
        raise ValueError("Invalid timestamp index")
    local = bars.copy()
    local.index = local.index.tz_convert("America/New_York")
    return pd.DataFrame([_session(g) for _, g in local.groupby(local.index.date)])
