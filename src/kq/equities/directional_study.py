"""Frozen directional study of adjusted historical stock prices."""

import re

import numpy as np
import pandas as pd
from numpy.typing import NDArray


def _validated(bars: pd.DataFrame, cost_bps: float) -> pd.DataFrame:
    if (
        isinstance(cost_bps, (bool, np.bool_))
        or not np.isfinite(cost_bps)
        or not 0 <= cost_bps < 10000
    ):
        raise ValueError("cost_bps must be finite in [0, 10000)")
    required = ["symbol", "session_date", "open", "close"]
    if bars.empty or not set(required) <= set(bars.columns) or bars.columns.duplicated().any():
        raise ValueError("nonempty symbol/session_date/open/close data required")
    frame = bars[required].copy()
    if frame[["open", "close"]].map(lambda value: isinstance(value, (bool, np.bool_))).any().any():
        raise ValueError("boolean prices are malformed")
    if not frame.symbol.map(
        lambda value: isinstance(value, str) and bool(re.fullmatch(r"[A-Z0-9.\-]{1,20}", value))
    ).all():
        raise ValueError("invalid symbol")
    try:
        frame["session_date"] = pd.to_datetime(frame.session_date, errors="raise")
        for column in ["open", "close"]:
            frame[column] = pd.to_numeric(frame[column], errors="raise")
    except (ValueError, TypeError) as exc:
        raise ValueError("malformed dates or prices") from exc
    if (
        frame.session_date.isna().any()
        or frame.session_date.dt.tz is not None
        or (frame.session_date != frame.session_date.dt.normalize()).any()
        or (frame.session_date > pd.Timestamp("2025-12-31")).any()
    ):
        raise ValueError("session_date must be a date through 2025-12-31")
    prices = frame[["open", "close"]].to_numpy(dtype=float)
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError("prices must be finite and positive")
    if frame.duplicated(["symbol", "session_date"]).any():
        raise ValueError("duplicate symbol/session_date")
    if "SPY" not in set(frame.symbol) or not set(frame.symbol) - {"SPY"}:
        raise ValueError("SPY and at least one stock required")
    if not set(frame.session_date) <= set(frame.loc[frame.symbol == "SPY", "session_date"]):
        raise ValueError("stock sessions must belong to SPY calendar")
    return frame


def _feature(closes: NDArray[np.float64], index: int, rule: str) -> float | None:
    lookback = 252 if rule == "L12-1" else 20 if rule == "S20" else 5
    if index < lookback or np.isnan(closes[index - lookback : index + 1]).any():
        return None
    end = index - 21 if rule == "L12-1" else index
    return float(
        (closes[end, 1] / closes[index - lookback, 1])
        / (closes[end, 0] / closes[index - lookback, 0])
        - 1
    )


def _outcome(
    dates: pd.DatetimeIndex,
    opens: NDArray[np.float64],
    index: int,
    horizon: str,
    signal: int,
    cost: float,
) -> dict[str, object]:
    result: dict[str, object] = {
        "entry_date": pd.NaT,
        "exit_date": pd.NaT,
        "status": "pending",
        "reason": "endpoint_beyond_data",
    }
    entry = index + 1
    if entry >= len(dates):
        return result
    result["entry_date"] = dates[entry]
    end = (
        entry + int(horizon[:-1])
        if horizon.endswith("s")
        else int(dates.searchsorted(dates[entry] + pd.DateOffset(months=int(horizon[:-1]))))
    )
    if end >= len(dates):
        return result
    result["exit_date"] = dates[end]
    benchmark = float(opens[end, 0] / opens[entry, 0])
    benchmark_net = benchmark * (1 - cost) / (1 + cost) - 1
    result.update(spy_gross_return=benchmark - 1, spy_net_return=benchmark_net)
    if np.isnan(opens[[entry, end], 1]).any():
        result.update(status="unavailable", reason="missing_entry_or_exit")
        return result
    stock = float(opens[end, 1] / opens[entry, 1])
    net = stock * (1 - cost) / (1 + cost) - 1
    result.update(
        status="complete",
        reason="",
        gross_return=stock - 1,
        net_return=net,
        excess_vs_spy=net - benchmark_net,
        absolute_hit=signal * (stock - 1) > 0,
        relative_hit=signal * (stock - benchmark) > 0,
    )
    return result


def simulate_directional(bars: pd.DataFrame, cost_bps: float = 10.0) -> pd.DataFrame:
    """Simulate registered S20/S5/L12-1 rules; no portfolio or short-sale returns.
    Input: symbol (uppercase), session_date (naive midnight), open/close (finite,
    positive distribution-adjusted prices). SPY defines all observed sessions.
    Output: rule/horizon/symbol strings; decision/entry/exit naive dates (NaT beyond data);
    signal int {-1,0,1}; feature_value float (NaN when excluded);
    as_of aware UTC, as_of_kind='simulated_session_close' (16:00 New York);
    status complete/excluded/pending/unavailable and reason string; gross_return,
    net_return, spy_gross_return, spy_net_return, excess_vs_spy decimal long returns;
    absolute_hit/relative_hit nullable booleans based on gross outcomes. Missing
    labels are NaN/NA; excluded signal=0 is a placeholder, not a neutral forecast.
    Labels are exact next-open to future-open, with identical two-sided costs.
    """
    frame = _validated(bars, cost_bps)
    dates = pd.DatetimeIndex(frame.loc[frame.symbol == "SPY", "session_date"].sort_values())
    anchor = int(dates.searchsorted(pd.Timestamp("2006-01-01")))
    schema = (
        "rule horizon symbol decision_date entry_date exit_date signal feature_value "
        "as_of as_of_kind status reason gross_return net_return spy_gross_return spy_net_return "
        "excess_vs_spy absolute_hit relative_hit"
    )
    columns = schema.split()
    rows: list[dict[str, object]] = []
    for symbol in sorted(set(frame.symbol) - {"SPY"}):
        aligned = frame[frame.symbol.isin(["SPY", symbol])]
        opens = (
            aligned.pivot(index="session_date", columns="symbol", values="open")
            .reindex(index=dates, columns=["SPY", symbol])
            .to_numpy(dtype=float)
        )
        closes = (
            aligned.pivot(index="session_date", columns="symbol", values="close")
            .reindex(index=dates, columns=["SPY", symbol])
            .to_numpy(dtype=float)
        )
        for rule, stride, horizons in [
            ("S20", 5, ["5s", "20s"]),
            ("S5", 5, ["5s", "20s"]),
            ("L12-1", 21, ["6m", "12m", "18m"]),
        ]:
            for index in range(anchor, len(dates), stride):
                feature = _feature(closes, index, rule)
                signal = (
                    int(np.sign(feature)) * (-1 if rule == "S5" else 1)
                    if feature is not None
                    else 0
                )
                stamp = (
                    (dates[index] + pd.Timedelta(hours=16))
                    .tz_localize("America/New_York")
                    .tz_convert("UTC")
                )
                for horizon in horizons:
                    row: dict[str, object] = dict.fromkeys(columns, float("nan"))
                    row.update(
                        rule=rule,
                        horizon=horizon,
                        symbol=symbol,
                        decision_date=dates[index],
                        signal=signal,
                        feature_value=feature if feature is not None else float("nan"),
                        as_of=stamp,
                        as_of_kind="simulated_session_close",
                        absolute_hit=pd.NA,
                        relative_hit=pd.NA,
                    )
                    row.update(_outcome(dates, opens, index, horizon, signal, cost_bps / 10000))
                    if feature is None:
                        row.update(status="excluded", reason="insufficient_history")
                        for name in columns[12:]:
                            row[name] = pd.NA if name.endswith("hit") else float("nan")
                    rows.append(row)
    result = pd.DataFrame(rows, columns=columns)
    for name in ["absolute_hit", "relative_hit"]:
        result[name] = result[name].astype("boolean")
    return result
