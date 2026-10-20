"""Separate funded allocation research; no broker or provider calls."""

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from kq.equities.stock_family_study import rebalance, summarize

SYMBOLS = ("SPY", "EFA", "IEF", "VNQ", "GLD", "BIL")
RISK_SYMBOLS = SYMBOLS[:-1]
POLICIES = ("C01", "C02", "C03", "C04", "A01", "A02", "I01", "I02", "I03", "I04", "O01", "O02")
INSURANCE_POLICIES = ("I01", "I02", "I03", "I04")
INITIAL_CAPITAL = 1000.0
TARGET_BUDGET = 0.98
__all__ = [
    "INITIAL_CAPITAL",
    "INSURANCE_POLICIES",
    "POLICIES",
    "RISK_SYMBOLS",
    "SYMBOLS",
    "TARGET_BUDGET",
    "Prices",
    "insurance_target",
    "simulate",
    "summarize",
    "validate_prices",
]


@dataclass(frozen=True)
class Prices:
    """Aligned adjusted opening and closing wealth prices."""

    opened: pd.DataFrame
    closed: pd.DataFrame


def validate_prices(prices: Prices) -> None:
    opened, closed = prices.opened, prices.closed
    if (
        opened.empty
        or not opened.index.equals(closed.index)
        or not opened.columns.equals(closed.columns)
        or opened.columns.has_duplicates
        or not all(isinstance(symbol, str) for symbol in opened.columns)
        or not isinstance(opened.index, pd.DatetimeIndex)
        or opened.index.tz is not None
        or opened.index.hasnans
        or opened.index.has_duplicates
        or not opened.index.is_monotonic_increasing
        or not opened.index.equals(opened.index.normalize())
    ):
        raise ValueError("Invalid or misaligned price panel")
    for frame in (opened, closed):
        values = frame.to_numpy(float)
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError("Prices must be finite and positive")


def as_of(date: pd.Timestamp) -> pd.Timestamp:
    """Synthetic conservative close timestamp; not original receipt time."""
    return (date + pd.Timedelta(hours=16)).tz_localize("America/New_York").tz_convert("UTC")


def insurance_target(
    policy: str, reference_nav: float, reference_peak: float
) -> tuple[NDArray[np.float64], float, float]:
    """Unscaled target from this account's preceding completed closing state."""
    if (
        policy not in INSURANCE_POLICIES
        or not np.isfinite([reference_nav, reference_peak]).all()
        or reference_nav <= 0
        or reference_peak < max(INITIAL_CAPITAL, reference_nav) - 1e-8
    ):
        raise ValueError("Invalid insurance policy or account reference")
    floor = 0.8 * (reference_peak if policy in {"I03", "I04"} else INITIAL_CAPITAL)
    exposure = float(np.clip(3 * (reference_nav - floor) / reference_nav, 0, 1))
    weights = np.zeros(len(SYMBOLS))
    if policy in {"I01", "I03"}:
        weights[0] = exposure
    else:
        weights[:-1] = exposure / len(RISK_SYMBOLS)
    weights[-1] = 1 - exposure
    return weights, floor, exposure


def _validate_signals(prices: Prices, signals: pd.DataFrame) -> None:
    required = {*prices.closed.columns, "rebalance", "warmup_ready", "decision_date", "as_of"}
    if not signals.index.equals(prices.closed.index) or not required <= set(signals):
        raise ValueError("Missing signal fields or misaligned dates")
    weights = signals[list(prices.closed.columns)].to_numpy(float)
    if (
        not np.isfinite(weights).all()
        or (weights < 0).any()
        or (weights.sum(axis=1) > 1 + 1e-12).any()
        or signals[["rebalance", "warmup_ready"]].isna().any().any()
        or not all(
            value in (True, False)
            for value in signals[["rebalance", "warmup_ready"]].to_numpy().flat
        )
    ):
        raise ValueError("Invalid unscaled long-only targets or scheduling flags")
    if (weights[~signals.warmup_ready.to_numpy(bool)] != 0).any():
        raise ValueError("Nonzero target before warmup")


def _static_decision(
    signals: pd.DataFrame, dates: pd.DatetimeIndex, i: int
) -> tuple[pd.Timestamp, pd.Timestamp]:
    decision = pd.Timestamp(signals.decision_date.iloc[i])
    timestamp = pd.Timestamp(signals.as_of.iloc[i])
    if pd.isna(decision) and not bool(signals.warmup_ready.iloc[i]):
        return dates[i - 1], as_of(dates[i - 1])
    if (
        pd.isna(decision)
        or decision not in dates[:i]
        or timestamp != as_of(decision)
        or timestamp
        >= (dates[i] + pd.Timedelta(hours=9, minutes=30)).tz_localize("America/New_York")
    ):
        raise ValueError("Noncausal signal decision or synthetic timestamp")
    return decision, timestamp


def simulate(  # noqa: PLR0915
    prices: Prices,
    signals: dict[str, pd.DataFrame] | pd.DataFrame | None,
    policy: str,
    cost_bps: int,
    start: str,
    end: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fresh funded account; all submitted targets are based on completed closes."""
    validate_prices(prices)
    if isinstance(signals, dict):
        signals = signals.get(policy)
    if policy not in POLICIES or not 0 <= cost_bps < 10000:
        raise ValueError("Invalid policy or cost")
    symbols = tuple(prices.closed.columns)
    dynamic = policy in INSURANCE_POLICIES
    if dynamic:
        if symbols != SYMBOLS:
            raise ValueError("Insurance requires the registered six-symbol order")
    elif signals is None:
        raise ValueError("Static policy requires signals")
    else:
        _validate_signals(prices, signals)
    dates = prices.closed.index
    chosen = np.flatnonzero(dates.to_series().between(start, end).to_numpy())
    if not len(chosen) or chosen[0] == 0:
        raise ValueError("Evaluation requires a nonempty window and prior observed session")
    opened, closed = prices.opened.to_numpy(float), prices.closed.to_numpy(float)
    units = np.zeros(len(symbols))
    cash, rate = INITIAL_CAPITAL, cost_bps / 10000
    reference_nav = reference_peak = INITIAL_CAPITAL
    daily: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    for i in chosen:
        open_before = float(cash + units @ opened[i])
        day_cost = 0.0
        floor = exposure = None
        if dynamic:
            raw_weights, floor, exposure = insurance_target(policy, reference_nav, reference_peak)
            weights = raw_weights * TARGET_BUDGET
            decision, timestamp = dates[i - 1], as_of(dates[i - 1])
            scheduled = True
        else:
            assert signals is not None
            weights = signals.loc[dates[i], list(symbols)].to_numpy(float) * TARGET_BUDGET
            decision, timestamp = _static_decision(signals, dates, int(i))
            scheduled = bool(signals.rebalance.iloc[i]) and policy not in {"C01", "C02", "C03"}
        state = {
            "reference_nav": reference_nav if dynamic else None,
            "reference_peak": reference_peak if dynamic else None,
            "floor": floor,
            "risky_fraction": exposure,
        }
        if i == chosen[0] or scheduled:
            old_units = units.copy()
            units, cash, turnover, fee = rebalance(units, cash, opened[i], weights, rate)
            day_cost += fee
            ledger.append(
                {
                    "decision_date": decision,
                    "as_of": timestamp,
                    "execution_date": dates[i],
                    "reason": "initial" if i == chosen[0] else "rebalance",
                    "pre_nav": open_before,
                    "post_nav": float(cash + units @ opened[i]),
                    "cash": cash,
                    "turnover": turnover,
                    "cost": fee,
                    **{f"units_{s}": units[j] for j, s in enumerate(symbols)},
                    **{f"delta_{s}": units[j] - old_units[j] for j, s in enumerate(symbols)},
                    **{f"price_{s}": opened[i, j] for j, s in enumerate(symbols)},
                    **{f"weight_{s}": weights[j] for j, s in enumerate(symbols)},
                    **state,
                }
            )
        open_after = float(cash + units @ opened[i])
        close_before = float(cash + units @ closed[i])
        if i == chosen[-1]:
            old_units = units.copy()
            units, cash, turnover, fee = rebalance(
                units, cash, closed[i], np.zeros(len(symbols)), rate
            )
            day_cost += fee
            ledger.append(
                {
                    "decision_date": dates[i - 1],
                    "as_of": as_of(dates[i - 1]),
                    "execution_date": dates[i],
                    "reason": "terminal_prescheduled_close",
                    "pre_nav": close_before,
                    "post_nav": cash,
                    "cash": cash,
                    "turnover": turnover,
                    "cost": fee,
                    **{f"units_{s}": 0.0 for s in symbols},
                    **{f"delta_{s}": -old_units[j] for j, s in enumerate(symbols)},
                    **{f"price_{s}": closed[i, j] for j, s in enumerate(symbols)},
                    **{f"weight_{s}": 0.0 for s in symbols},
                    **state,
                }
            )
        nav = float(cash + units @ closed[i])
        daily.append(
            {
                "session_date": dates[i],
                "open_before": open_before,
                "open_after": open_after,
                "close_before": close_before,
                "nav": nav,
                "cash": cash,
                "cost": day_cost,
                **state,
                "floor_breached_open_before": floor is not None and open_before < floor,
                "floor_breached_open_after": floor is not None and open_after < floor,
                "floor_breached_close_before": floor is not None and close_before < floor,
                "floor_breached_nav": floor is not None and nav < floor,
            }
        )
        reference_nav = close_before
        reference_peak = max(reference_peak, close_before)
    return pd.DataFrame(daily), pd.DataFrame(ledger)
