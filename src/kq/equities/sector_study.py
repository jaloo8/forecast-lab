"""Pure portfolio accounting for the frozen October 2026 sector study."""

from itertools import pairwise

import numpy as np
import pandas as pd
from numpy.typing import NDArray

SECTORS = ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY")
SYMBOLS = ("SPY", *SECTORS)
STRATEGIES = ("spy_hold", "equal_sectors", "sector_momentum", "spy_trend", "sector_momentum_trend")
INVVOL_STRATEGIES = (
    "equal_sectors_invvol",
    "sector_momentum_invvol",
    "sector_momentum_trend_invvol",
)


def _prices(bars: pd.DataFrame, end: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {"symbol", "session_date", "open", "close"}
    if not required.issubset(bars.columns):
        raise ValueError("Missing required price columns")
    frame = bars.loc[:, sorted(required)].copy()
    frame["session_date"] = pd.to_datetime(frame.session_date, errors="raise")
    dates = frame.session_date
    if dates.isna().any() or dates.dt.tz is not None or (dates != dates.dt.normalize()).any():
        raise ValueError("Session dates must be non-null, timezone-naive calendar dates")
    frame = frame.loc[(dates <= end) & (dates >= "1998-01-01")]
    if set(frame.symbol) != set(SYMBOLS):
        raise ValueError("Expected exactly the ten registered funds")
    if frame.duplicated(["session_date", "symbol"]).any():
        raise ValueError("Duplicate fund/session prices")
    values = frame[["open", "close"]].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("Prices must be finite and positive")
    # SPY predates the sectors; only their shared inception boundary is discarded.
    common_start = frame.groupby("symbol").session_date.min().max()
    frame = frame.loc[frame.session_date >= common_start]
    opened = frame.pivot(index="session_date", columns="symbol", values="open").reindex(
        columns=SYMBOLS
    )
    closed = frame.pivot(index="session_date", columns="symbol", values="close").reindex(
        columns=SYMBOLS
    )
    if opened.empty or opened.isna().any().any() or closed.isna().any().any():
        raise ValueError("Missing fund/session prices inside common history")
    return opened.astype(float), closed.astype(float)


def _target(history: pd.DataFrame, strategy: str) -> NDArray[np.float64]:
    if strategy in INVVOL_STRATEGIES:
        if len(history) < 13:
            raise ValueError("Insufficient monthly warmup: need 13 closes")
        weights = _target(history, strategy.removesuffix("_invvol"))
        selected = weights > 0
        if not selected.any():
            return weights
        closes = history.loc[:, list(SYMBOLS)].iloc[-13:].to_numpy(float)[:, selected]
        if not np.isfinite(closes).all() or (closes <= 0).any():
            raise ValueError("Invalid prices for volatility")
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            volatility = np.std(closes[1:] / closes[:-1] - 1, axis=0, ddof=1)
        if not np.isfinite(volatility).all() or (volatility <= 0).any():
            raise ValueError("Selected volatility must be finite and positive")
        inverse = volatility.min() / volatility
        weights[selected] = inverse / inverse.sum()
        return weights
    needed = 13 if "momentum" in strategy else 10 if "trend" in strategy else 1
    if len(history) < needed:
        raise ValueError(f"Insufficient monthly warmup: need {needed} closes")
    weights = np.zeros(len(SYMBOLS), dtype=float)
    if "trend" in strategy and not history.SPY.iloc[-1] > history.SPY.iloc[-10:].mean():
        return weights
    if strategy in ("spy_hold", "spy_trend"):
        weights[0] = 1
    elif strategy == "equal_sectors":
        weights[1:] = 1 / len(SECTORS)
    else:
        scores = history.iloc[-2] / history.iloc[-13] - 1
        chosen = sorted(SECTORS, key=lambda symbol: (-float(scores[symbol]), symbol))[:3]
        for symbol in chosen:
            weights[SYMBOLS.index(symbol)] = 1 / 3
    return weights


def _trade(
    units: NDArray[np.float64],
    cash: float,
    prices: NDArray[np.float64],
    weights: NDArray[np.float64],
    cost_rate: float,
) -> tuple[NDArray[np.float64], float, float, float, float]:
    assets = units * prices
    before = float(cash + assets.sum())
    low, high = 0.0, before
    for _ in range(64):
        after = (low + high) / 2
        residual = after + cost_rate * float(np.abs(weights * after - assets).sum()) - before
        if residual > 0:
            high = after
        else:
            low = after
    after = (low + high) / 2
    target_assets = weights * after
    turnover = float(np.abs(target_assets - assets).sum())
    return target_assets / prices, float(after * (1 - weights.sum())), before, after, turnover


def simulate_portfolio(
    bars: pd.DataFrame,
    strategy: str,
    cost_bps: float,
    start: str = "2006-01-01",
    end: str = "2025-12-31",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Simulate adjusted-price portfolios without I/O or orders.

    Input: symbol/string, session_date/naive date, open/positive float,
    close/positive float; prices already distribution adjusted. Daily output:
    session_date/datetime64[ns], nav/float, cash/float (terminal liquidation included).
    Ledger: decision_date/datetime64, as_of/UTC timestamp, execution_date/datetime64,
    reason/string, pre_nav/post_nav/cost/turnover/float; weight_, units_, price_
    float columns for every symbol. Turnover is dollar notional, counting both sides.
    Terminal decision_date/as_of are null: liquidation is an endpoint convention.
    """
    start_date, end_date = pd.Timestamp(start), pd.Timestamp(end)
    if start_date > end_date or start_date.tz is not None or end_date.tz is not None:
        raise ValueError("Invalid study endpoints")
    if (
        strategy not in STRATEGIES + INVVOL_STRATEGIES
        or not np.isfinite(cost_bps)
        or not 0 <= cost_bps < 10000
    ):
        raise ValueError("Invalid strategy or proportional cost")
    opened, closed = _prices(bars, end_date)
    sessions = closed.index[closed.index >= start_date]
    if sessions.empty:
        raise ValueError("No study sessions")
    monthly = closed.groupby(closed.index.to_period("M")).tail(1)
    periods = monthly.index.to_period("M")
    if any(right.ordinal - left.ordinal != 1 for left, right in pairwise(periods)):
        raise ValueError("Missing complete month of history")
    units = np.zeros(len(SYMBOLS), dtype=float)
    cash = 10000.0
    cost_rate = cost_bps / 10000
    daily_rows: list[dict[str, object]] = []
    ledger_rows: list[dict[str, object]] = []
    last_month = None
    for date in sessions:
        month = date.to_period("M")
        if last_month is None or (month != last_month and strategy != "spy_hold"):
            history = monthly.loc[monthly.index.to_period("M") < month]
            if history.empty or history.index[-1].to_period("M") != month - 1:
                raise ValueError("Missing prior month decision close")
            weights = _target(history, strategy)
            decision = history.index[-1]
            as_of = (
                (decision + pd.Timedelta(hours=16))
                .tz_localize("America/New_York")
                .tz_convert("UTC")
            )
            prices = opened.loc[date].to_numpy(dtype=float)
            units, cash, before, after, turnover = _trade(units, cash, prices, weights, cost_rate)
            ledger_rows.append(
                {
                    "decision_date": decision,
                    "as_of": as_of,
                    "execution_date": date,
                    "reason": "initial" if last_month is None else "rebalance",
                    "pre_nav": before,
                    "post_nav": after,
                    "cost": cost_rate * turnover,
                    "turnover": turnover,
                    **{f"weight_{s}": weights[i] for i, s in enumerate(SYMBOLS)},
                    **{f"units_{s}": units[i] for i, s in enumerate(SYMBOLS)},
                    **{f"price_{s}": prices[i] for i, s in enumerate(SYMBOLS)},
                }
            )
        prices = closed.loc[date].to_numpy(dtype=float)
        if date == sessions[-1]:
            units, cash, before, after, turnover = _trade(
                units, cash, prices, np.zeros(len(SYMBOLS)), cost_rate
            )
            ledger_rows.append(
                {
                    "decision_date": pd.NaT,
                    "as_of": pd.NaT,
                    "execution_date": date,
                    "reason": "terminal",
                    "pre_nav": before,
                    "post_nav": after,
                    "cost": cost_rate * turnover,
                    "turnover": turnover,
                    **{f"weight_{s}": 0.0 for s in SYMBOLS},
                    **{f"units_{s}": units[i] for i, s in enumerate(SYMBOLS)},
                    **{f"price_{s}": prices[i] for i, s in enumerate(SYMBOLS)},
                }
            )
        daily_rows.append({"session_date": date, "nav": float(cash + units @ prices), "cash": cash})
        last_month = month
    daily, ledger = pd.DataFrame(daily_rows), pd.DataFrame(ledger_rows)
    ledger["as_of"] = pd.to_datetime(ledger.as_of, utc=True)
    return daily, ledger
