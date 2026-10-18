"""Pure current-universe research; deliberately disconnected from paper accounts."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pandas as pd

Array = npt.NDArray[np.float64]


def require_sessions(actual: pd.DatetimeIndex, expected: pd.DatetimeIndex) -> None:
    """Reject shortened, duplicate or reordered benchmark evaluation windows."""
    if not len(expected) or not expected.is_unique or not expected.is_monotonic_increasing:
        raise ValueError("Invalid expected session coverage")
    if not actual.equals(expected):
        raise ValueError(
            f"Benchmark coverage mismatch: missing={len(expected.difference(actual))}, "
            f"unexpected={len(actual.difference(expected))}"
        )


def monthly_targets(
    close: pd.DataFrame, raw_close: pd.DataFrame, volume: pd.DataFrame
) -> dict[str, dict[int, Array]]:
    """Return next-session target weights using only completed month-end data.

    Inputs are aligned date-by-symbol matrices, including SPY. Price-history
    availability is simulated; original data vintages/membership are not implied.
    """
    if not close.index.equals(raw_close.index) or not close.columns.equals(raw_close.columns):
        raise ValueError("Unaligned raw prices")
    if not close.index.equals(volume.index) or not close.columns.equals(volume.columns):
        raise ValueError("Unaligned volume")
    if not close.index.is_unique or not close.index.is_monotonic_increasing:
        raise ValueError("Invalid dates")
    arms = ("M", "R", "V", "MR", "MV", "RV", "MRV", "M_trend", "MRV_trend")
    output: dict[str, dict[int, Array]] = {arm: {} for arm in arms}
    dates = pd.DatetimeIndex(close.index)
    for i in range(len(dates) - 1):
        if dates[i].month == dates[i + 1].month:
            continue
        choices: dict[str, Array] = {arm: np.zeros(len(close.columns)) for arm in arms}
        if i >= 252:
            window = close.iloc[i - 252 : i + 1]
            valid = np.isfinite(window).all() & window.gt(0).all()
            recent_volume = volume.iloc[i - 19 : i + 1]
            valid &= np.isfinite(recent_volume).all() & recent_volume.gt(0).all()
            liquid = (raw_close.iloc[i - 19 : i + 1] * recent_volume).median().ge(20_000_000)
            valid &= liquid
            valid.loc["SPY"] = False
            score = pd.DataFrame(
                {
                    "M": window.iloc[-22] / window.iloc[0] - 1,
                    "R": -(window.iloc[-1] / window.iloc[-6] - 1),
                    "V": -np.log(window / window.shift(1)).iloc[-60:].std(ddof=1),
                }
            ).loc[valid]
            ranks = score.rank(pct=True, method="average")
            if len(ranks) >= 5:
                for arm in arms:
                    gated = arm.endswith("_trend")
                    component = arm.removesuffix("_trend")
                    spy = close.SPY.iloc[i - 199 : i + 1]
                    if gated and (not np.isfinite(spy).all() or spy.iloc[-1] <= spy.mean()):
                        continue
                    combined = ranks[list(component)].mean(axis=1).sort_index()
                    selected = combined.sort_values(ascending=False, kind="stable").head(5).index
                    choices[arm][close.columns.get_indexer(selected)] = 0.98 / 5
        for arm in arms:
            output[arm][i + 1] = choices[arm]
    return output


def replay_path(
    dates: pd.DatetimeIndex,
    opens: Array,
    closes: Array,
    targets: dict[int, Array],
    cost_bps: float,
) -> pd.DataFrame:
    """Self-financing next-open trades and terminal liquidation, starting at $1,000.

    Unheld missing prices are permitted. A missing held or desired execution
    price invalidates the entire path rather than dropping a losing position.
    """
    if opens.shape != closes.shape or len(dates) != len(opens) or not 0 <= cost_bps < 10000:
        raise ValueError("Invalid shape or cost")
    cash = 1000.0
    units = np.zeros(opens.shape[1])
    fee = cost_bps / 10000
    rows = []
    for i, day in enumerate(dates):
        held = units > 0
        target = targets.get(i)
        cost, traded = 0.0, 0.0
        if target is not None:
            if (
                not np.isfinite(target).all()
                or (target < 0).any()
                or target.shape != units.shape
                or target.sum() > 1.00000001
            ):
                raise ValueError("Invalid target weights")
            needed = held | (target > 0)
            if not np.isfinite(opens[i, needed]).all() or (opens[i, needed] <= 0).any():
                raise ValueError(f"Missing held/target opening price on {day}")
            old = np.zeros_like(units)
            old[held] = units[held] * opens[i, held]
            before = cash + old.sum()
            low, high = 0.0, float(before)
            for _ in range(50):
                wealth = (low + high) / 2
                if wealth + fee * np.abs(target * wealth - old).sum() > before:
                    high = wealth
                else:
                    low = wealth
            dollars = target * low
            traded = float(np.abs(dollars - old).sum())
            cost = fee * traded
            cash = float(before - dollars.sum() - cost)
            units[:] = 0
            units[needed] = dollars[needed] / opens[i, needed]
            held = units > 0
            if not np.isclose(cash + dollars.sum() + cost, before, atol=1e-7):
                raise ValueError("Rebalance accounting identity failed")
        if not np.isfinite(closes[i, held]).all() or (closes[i, held] <= 0).any():
            raise ValueError(f"Missing held closing price on {day}")
        marked = float((units[held] * closes[i, held]).sum())
        if i == len(dates) - 1:
            cost += marked * fee
            traded += marked
            cash += marked * (1 - fee)
            marked = 0.0
        nav = cash + marked
        if cash < -1e-7 or nav <= 0:
            raise ValueError("Nonpositive equity or negative cash")
        rows.append((day, nav, cash, cost, traded))
    return pd.DataFrame(rows, columns=["date", "nav", "cash", "cost", "traded"]).set_index("date")
