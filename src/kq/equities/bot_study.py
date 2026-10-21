"""Frozen daily bot hypotheses and fractional wealth-unit research accounting."""

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

RULES = ("C00", "C01", "C02", *(f"B{i:02d}" for i in range(1, 13)))
COLUMNS = (
    "open_before",
    "open_after",
    "cash_open",
    "units_open",
    "nav_close",
    "cash_close",
    "units_close",
    "notional_open",
    "fee_open",
    "notional_close",
    "fee_close",
    "close_before_fee",
)


@dataclass(frozen=True)
class PathResult:
    """Every monetary field uses dollars or fractional adjusted wealth units."""

    values: NDArray[np.float64]
    skipped_tickets: int


def adjusted_prices(raw: pd.DataFrame) -> pd.DataFrame:
    """Validate current-vintage inputs; no inference of nominal share feasibility."""
    fields = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
    index = raw.index
    if (
        not isinstance(index, pd.DatetimeIndex)
        or index.empty
        or index.has_duplicates
        or index.hasnans
        or index.tz is not None
        or not index.is_monotonic_increasing
        or not index.equals(index.normalize())
        or not set(fields) <= set(raw)
    ):
        raise ValueError("Invalid source schema/dates")
    array = raw[fields].to_numpy(float)
    if (
        not np.isfinite(array).all()
        or (array[:, :5] <= 0).any()
        or (array[:, 5] < 0).any()
        or (raw.High + 1e-7 < raw[["Open", "Low", "Close"]].max(axis=1)).any()
        or (raw.Low - 1e-7 > raw[["Open", "High", "Close"]].min(axis=1)).any()
    ):
        raise ValueError("Invalid source prices/volume")
    factor = raw["Adj Close"] / raw.Close
    frame = raw[["Open", "High", "Low", "Close"]].mul(factor, axis=0)
    frame["Volume"] = raw.Volume
    return frame


def _state(
    enter: pd.Series, leave: pd.Series, ready: pd.Series, limit: int | None = None
) -> NDArray[np.bool_]:
    active = False
    age = 0
    result = np.zeros(len(enter), dtype=bool)
    for i, (go, stop, valid) in enumerate(
        zip(enter.fillna(False), leave.fillna(False), ready, strict=True)
    ):
        if not valid:
            continue
        if active:
            age += 1
            if stop or (limit is not None and age >= limit):
                active = False
        elif go:
            active, age = True, 0
        result[i] = active
    return result


def build_signals(prices: pd.DataFrame) -> pd.DataFrame:
    """Completed-close decisions only; the caller applies execution lag."""
    c, o, h, low, v = (prices[k] for k in ("Close", "Open", "High", "Low", "Volume"))
    ready = pd.Series(np.arange(len(c)) >= 251, index=c.index)
    ma20, ma200 = c.rolling(20).mean(), c.rolling(200).mean()
    sd20 = c.rolling(20).std(ddof=0)
    upper, lower = ma20 + 2 * sd20, ma20 - 2 * sd20
    ema20 = c.ewm(span=20, adjust=False).mean()
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    macd_up = macd > macd.ewm(span=9, adjust=False).mean()
    true_range = pd.concat([h - low, (h - c.shift()).abs(), (low - c.shift()).abs()], axis=1).max(
        axis=1
    )
    atr = true_range.rolling(20).mean()
    low14, high14 = low.rolling(14).min(), h.rolling(14).max()
    slow_k = (100 * (c - low14) / (high14 - low14).replace(0, np.nan)).rolling(3).mean()
    inside = (lower > ema20 - 1.5 * atr) & (upper < ema20 + 1.5 * atr)
    prior_volume = v.shift().rolling(20).mean()
    relative_volume = v >= 1.5 * prior_volume
    gap = o / c.shift() - 1
    ret = c.pct_change(fill_method=None)
    never = pd.Series(False, index=c.index)
    states = {
        "C00": ready.to_numpy(),
        "C01": ((c > ma200) & ready).to_numpy(),
        "C02": _state(c > c.shift().rolling(55).max(), c < c.shift().rolling(20).min(), ready),
        "B01": (macd_up & ready).to_numpy(),
        "B02": _state(c > upper, c < ma20, ready),
        "B03": _state((c.shift() < lower.shift()) & (c >= lower), c >= ma20, ready, 5),
        "B04": _state((slow_k.shift() <= 20) & (slow_k > 20), slow_k >= 80, ready, 10),
        "B05": _state(c > ema20 + 2 * atr, c < ema20, ready),
        "B06": _state(inside.shift(fill_value=False) & ~inside & (c > ma20), c < ma20, ready, 10),
        "B07": _state(
            (c > c.shift().rolling(20).max()) & (v > 1.5 * prior_volume),
            c < c.rolling(10).mean(),
            ready,
            10,
        ),
        "B08": _state(gap.between(0.02, 0.15) & (c > o) & relative_volume, never, ready, 1),
        "B09": _state(gap.between(-0.15, -0.02) & (c > o) & relative_volume, never, ready, 1),
        "B10": _state(
            (ret <= -2 * ret.shift().rolling(20).std(ddof=1)) & (c > ma200), never, ready, 5
        ),
        "B11": _state(
            (true_range > 2 * true_range.shift().rolling(20).mean())
            & ((c - low) / (h - low).replace(0, np.nan) >= 0.8),
            never,
            ready,
            3,
        ),
        "B12": (
            (
                macd_up.astype(int)
                + (c > c.rolling(50).mean()).astype(int)
                + (c / c.shift(20) > 1).astype(int)
                >= 2
            )
            & ready
        ).to_numpy(),
    }
    result = pd.DataFrame(states, index=c.index)
    result["warmup_ready"] = ready
    result["as_of"] = (
        (c.index + pd.Timedelta(hours=16))
        .tz_localize("America/New_York")
        .tz_convert("UTC")
        .astype(str)
    )
    return result


def simulate(
    opened: NDArray[np.float64],
    closed: NDArray[np.float64],
    target: NDArray[np.bool_],
    cost_bps: int,
    *,
    initial: float = 1000.0,
) -> PathResult:
    """Single-asset, self-financed next-open ledger; terminal close is liquidated."""
    if (
        len(opened) == 0
        or len(opened) != len(closed)
        or len(opened) != len(target)
        or target.dtype != np.dtype(bool)
        or cost_bps not in {10, 25, 50}
        or not np.isfinite(initial)
        or initial != 1000.0
        or not np.isfinite(opened).all()
        or not np.isfinite(closed).all()
        or (opened <= 0).any()
        or (closed <= 0).any()
    ):
        raise ValueError("Invalid simulation inputs")
    return _simulate(opened, closed, target, cost_bps, initial)


def _simulate(
    opened: NDArray[np.float64],
    closed: NDArray[np.float64],
    target: NDArray[np.bool_],
    cost_bps: int,
    initial: float = 1000.0,
) -> PathResult:
    cash, units = initial, 0.0
    cost = cost_bps / 10000
    skipped = 0
    rows = np.empty((len(opened), len(COLUMNS)), dtype=float)
    for i, (op, cl, desired) in enumerate(zip(opened, closed, target, strict=True)):
        before = cash + units * op
        notional = fee = 0.0
        if desired and units == 0:
            notional = 0.98 * cash / (1 + cost)
            if notional >= 1:
                fee = notional * cost
                units = notional / op
                cash -= notional + fee
            else:
                notional = 0.0
                skipped += 1
        elif not desired and units > 0:
            notional = -units * op
            if -notional >= 1:
                fee = -notional * cost
                cash += -notional - fee
                units = 0.0
            else:
                notional = 0.0
                skipped += 1
        after = cash + units * op
        cash_open, units_open = cash, units
        close_before_fee = cash + units * cl
        close_notional = close_fee = 0.0
        if i == len(opened) - 1 and units > 0:
            close_notional = -units * cl
            close_fee = -close_notional * cost
            cash += -close_notional - close_fee
            units = 0.0
        rows[i] = (
            before,
            after,
            cash_open,
            units_open,
            cash + units * cl,
            cash,
            units,
            notional,
            fee,
            close_notional,
            close_fee,
            close_before_fee,
        )
    return PathResult(rows, skipped)


def metrics(dates: pd.DatetimeIndex, path: PathResult) -> dict[str, Any]:
    """Calendar duration CAGR and discrete open/close drawdown, not intraday risk."""
    a = path.values
    marks = np.concatenate(([1000.0], a[:, [0, 1, 11, 4]].ravel()))
    peak = np.maximum.accumulate(marks)
    final = float(a[-1, 4])
    years = ((dates[-1] - dates[0]).days + 1) / 365.25
    return {
        "start": str(dates[0].date()),
        "end": str(dates[-1].date()),
        "sessions": len(dates),
        "ending_cash": final,
        "return": final / 1000 - 1,
        "cagr": (final / 1000) ** (1 / years) - 1,
        "drawdown": float(np.min(marks / peak - 1)),
        "trades": int(np.count_nonzero(a[:, 7]) + np.count_nonzero(a[:, 9])),
        "fees": float(a[:, 8].sum() + a[:, 10].sum()),
        "turnover_dollars": float(np.abs(a[:, 7]).sum() + np.abs(a[:, 9]).sum()),
        "exposed_sessions": int(np.count_nonzero(a[:, 3])),
        "skipped_tickets": path.skipped_tickets,
    }


def annual_returns(
    dates: pd.DatetimeIndex, path: PathResult, calendar: pd.DatetimeIndex
) -> list[dict[str, Any]]:
    nav = pd.Series(path.values[:, 4], index=dates)
    previous = 1000.0
    rows = []
    for year, group in nav.groupby(nav.index.year):
        end = float(group.iloc[-1])
        expected = calendar[calendar.year == year]
        rows.append(
            {
                "year": int(year),
                "return": end / previous - 1,
                "ending_nav": end,
                "complete_calendar_year": bool(group.index.equals(expected)),
            }
        )
        previous = end
    return rows
