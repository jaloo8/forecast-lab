"""Finite offline ETF research; adjusted wealth units are not broker shares."""

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

SYMBOLS = ("SPY", "QQQ", "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY")
SECTORS = SYMBOLS[2:]
INITIAL_CAPITAL = 1000.0
RISK_BUDGET = 0.98
POLICIES = tuple(
    f"{family}{number:02d}"
    for family, count in (("C", 5), ("T", 6), ("B", 3), ("M", 4), ("V", 4), ("R", 3), ("E", 3))
    for number in range(1, count + 1)
)
ACTIVE_POLICIES = tuple(p for p in POLICIES if not p.startswith("C"))


@dataclass(frozen=True)
class Prices:
    """Dense observed-session adjusted prices; missing rows fail closed."""

    opened: pd.DataFrame
    closed: pd.DataFrame


def prepare_prices(bars: pd.DataFrame) -> Prices:
    required = {"session_date", "symbol", "open", "close"}
    if not required <= set(bars):
        raise ValueError("Missing price columns")
    frame = bars.copy()
    frame["session_date"] = pd.to_datetime(frame.session_date, errors="raise")
    if (
        set(frame.symbol) != set(SYMBOLS)
        or frame.session_date.isna().any()
        or frame.duplicated(["session_date", "symbol"]).any()
    ):
        raise ValueError("Invalid symbol/date coverage")
    outputs = []
    for column in ("open", "close"):
        value = frame.pivot(index="session_date", columns="symbol", values=column)
        value = value.sort_index().reindex(columns=SYMBOLS)
        array = value.to_numpy(float)
        if not np.isfinite(array).all() or (array <= 0).any():
            raise ValueError("Missing, nonfinite or nonpositive prices")
        outputs.append(value)
    if outputs[0].index.tz is not None:
        raise ValueError("Session labels must be timezone-naive dates")
    return Prices(*outputs)


def rebalance(
    units: NDArray[np.float64],
    cash: float,
    price: NDArray[np.float64],
    weights: NDArray[np.float64],
    rate: float,
) -> tuple[NDArray[np.float64], float, float, float]:
    """Solve N_after + costs(target(N_after) - current) = N_before."""
    if (
        not np.isfinite(weights).all()
        or (weights < 0).any()
        or weights.sum() > 1 + 1e-12
        or not 0 <= rate < 1
    ):
        raise ValueError("Invalid long-only weights or cost")
    current = units * price
    before = float(cash + current.sum())
    low, high = 0.0, before
    for _ in range(52):
        after = (low + high) / 2
        needed = after + rate * float(np.abs(weights * after - current).sum())
        if needed > before:
            high = after
        else:
            low = after
    new_units = weights * low / price
    turnover = float(np.abs((new_units - units) * price).sum())
    fee = turnover * rate
    new_cash = before - float((new_units * price).sum()) - fee
    if new_cash < -1e-8:
        raise ValueError("Unfunded rebalance")
    return new_units, max(0.0, new_cash), turnover, fee


def _as_of(date: pd.Timestamp) -> pd.Timestamp:
    return (date + pd.Timedelta(hours=16)).tz_localize("America/New_York").tz_convert("UTC")


def _rank(values: pd.Series, count: int, *, largest: bool = True) -> list[str]:
    if not np.isfinite(values.to_numpy(float)).all():
        raise ValueError("Insufficient signal history")
    return sorted(values.index, key=lambda s: (-values[s] if largest else values[s], s))[:count]


def _sleeves(symbols: list[str] | tuple[str, ...], scale: float = 1.0) -> NDArray[np.float64]:
    weights = np.zeros(len(SYMBOLS))
    for symbol in symbols:
        weights[SYMBOLS.index(symbol)] = scale / len(symbols)
    return weights


def _monthly_targets(
    history: pd.DataFrame, closes: pd.DataFrame, decision_i: int
) -> dict[str, NDArray[np.float64]]:
    if len(history) < 13 or decision_i < 200:
        raise ValueError("At least13 month ends and201 daily closes required")
    latest = history.iloc[-1]
    absolute = latest / history.iloc[-13] - 1
    momentum = history.iloc[-2] / history.iloc[-13] - 1
    average = sum(latest / history.iloc[-n - 1] - 1 for n in (1, 3, 6, 12)) / 4
    daily = closes.iloc[: decision_i + 1]
    returns = daily.pct_change(fill_method=None).iloc[-63:]
    vols = returns.std(ddof=1) * np.sqrt(252)
    sector_vol = float(returns[list(SECTORS)].mean(axis=1).std(ddof=1) * np.sqrt(252))
    result = {
        "C01": np.zeros(len(SYMBOLS)),
        "C02": _sleeves(["SPY"]),
        "C03": _sleeves(["QQQ"]),
        "C04": _sleeves(SECTORS),
        "C05": _sleeves(["SPY", "QQQ"]),
    }
    for number, universe in enumerate((["SPY"], ["QQQ"], list(SECTORS)), 1):
        trend = latest > history.iloc[-10:].mean()
        for offset, enabled in ((0, trend), (3, absolute > 0)):
            weights = _sleeves(universe)
            weights *= np.array([bool(enabled[s]) for s in SYMBOLS])
            result[f"T{number + offset:02d}"] = weights
    result["M01"] = _sleeves(_rank(momentum[list(SECTORS)], 3))
    result["M02"] = _sleeves(_rank(average[list(SECTORS)], 3))
    result["M03"] = _sleeves(_rank(momentum[["SPY", "QQQ"]], 1))
    result["M04"] = result["M01"] * (absolute.to_numpy(float) > 0)
    for number, universe, vol in (
        (1, ["SPY"], float(vols.SPY)),
        (2, ["QQQ"], float(vols.QQQ)),
        (3, list(SECTORS), sector_vol),
    ):
        scale = min(1.0, 0.10 / vol) if np.isfinite(vol) and vol > 0 else 0.0
        result[f"V{number:02d}"] = _sleeves(universe, scale)
    sector_vols = vols[list(SECTORS)]
    result["V04"] = (
        _sleeves(_rank(sector_vols, 3, largest=False))
        if np.isfinite(sector_vols).all() and (sector_vols > 0).all()
        else np.zeros(len(SYMBOLS))
    )
    reversal = daily.iloc[-1] / daily.iloc[-22] - 1
    result["R02"] = _sleeves(_rank(reversal[list(SECTORS)], 3, largest=False))
    result["E01"] = (result["T01"] + result["M01"]) / 2
    result["E02"] = (result["M01"] + result["R02"]) / 2
    result["E03"] = (result["T01"] + result["M01"] + result["V04"]) / 3
    return result


def build_signals(prices: Prices) -> dict[str, pd.DataFrame]:  # noqa: PLR0915
    """Execution-date targets depend only on completed prior-session prices.

    Monthly/weekly calendars use observed date labels. The synthetic as_of is
    the preceding close, not a claim about original receipt-time availability.
    """
    closes, dates = prices.closed, prices.closed.index
    count = len(dates)
    arrays = {p: np.zeros((count, len(SYMBOLS))) for p in POLICIES}
    schedules = {p: np.zeros(count, dtype=bool) for p in POLICIES}
    ready = {p: np.zeros(count, dtype=bool) for p in POLICIES}
    decision_dates = {p: pd.Series(pd.NaT, index=dates, dtype="datetime64[ns]") for p in POLICIES}
    monthly = closes.resample("ME").last()
    monthly_periods = monthly.index.to_period("M")
    months, weeks = dates.to_period("M"), dates.to_period("W-SUN")
    values = closes.to_numpy(float)
    state = np.zeros(len(SYMBOLS), dtype=bool)
    current: dict[str, NDArray[np.float64]] = {}
    weekly: dict[str, NDArray[np.float64]] = {}
    monthly_decision, weekly_decision = pd.NaT, pd.NaT
    for i in range(1, count):
        decision = i - 1
        new_month = months[i] != months[i - 1]
        if new_month:
            history = monthly.loc[monthly_periods < months[i]]
            if len(history) >= 13 and decision >= 200:
                current = _monthly_targets(history, closes, decision)
                monthly_decision = dates[decision]
        for policy, target in current.items():
            arrays[policy][i] = target * RISK_BUDGET
            schedules[policy][i] = new_month and policy not in {"C01", "C02", "C03"}
            ready[policy][i] = True
            decision_dates[policy].iloc[i] = monthly_decision
        if decision >= 63:
            old = state.copy()
            high = values[decision - 63 : decision].max(axis=0)
            low = values[decision - 21 : decision].min(axis=0)
            state = np.where(state, ~(values[decision] < low), values[decision] > high)
            for number, universe in enumerate((["SPY"], ["QQQ"], list(SECTORS)), 1):
                policy = f"B{number:02d}"
                mask = _sleeves(universe)
                arrays[policy][i] = mask * state * RISK_BUDGET
                schedules[policy][i] = bool(((old != state) & (mask > 0)).any())
                ready[policy][i] = True
                decision_dates[policy].iloc[i] = dates[decision]
        if decision >= 200 and weeks[i] != weeks[i - 1]:
            reversal = closes.iloc[decision] / closes.iloc[decision - 5] - 1
            selected = _sleeves(_rank(reversal[list(SECTORS)], 3, largest=False))
            gate = values[decision, 0] > values[decision - 199 : decision + 1, 0].mean()
            weekly = {"R01": selected, "R03": selected * gate}
            weekly_decision = dates[decision]
        for policy, target in weekly.items():
            arrays[policy][i] = target * RISK_BUDGET
            schedules[policy][i] = weeks[i] != weeks[i - 1]
            ready[policy][i] = True
            decision_dates[policy].iloc[i] = weekly_decision
    result = {}
    for policy in POLICIES:
        frame = pd.DataFrame(arrays[policy], index=dates, columns=SYMBOLS)
        frame["rebalance"] = schedules[policy]
        frame["warmup_ready"] = ready[policy]
        frame["decision_date"] = decision_dates[policy]
        frame["as_of"] = decision_dates[policy].map(
            lambda date: _as_of(date) if pd.notna(date) else pd.NaT
        )
        result[policy] = frame
    return result


def simulate(
    prices: Prices,
    signals: pd.DataFrame,
    cost_bps: int,
    start: str,
    end: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fresh cash; signal rows contain prior-close weights for each execution date."""
    if not 0 <= cost_bps < 10000 or not signals.index.equals(prices.closed.index):
        raise ValueError("Invalid costs or signal dates")
    chosen = np.flatnonzero(prices.closed.index.to_series().between(start, end).to_numpy())
    if not len(chosen) or chosen[0] == 0:
        raise ValueError("Evaluation needs prior-close warmup and nonempty sessions")
    opened, closed = prices.opened.to_numpy(float), prices.closed.to_numpy(float)
    weight_array = signals[list(SYMBOLS)].to_numpy(float)
    schedule = signals.rebalance.to_numpy(bool)
    signal_dates = signals.decision_date
    dates = prices.closed.index
    units = np.zeros(len(SYMBOLS))
    cash, rate = INITIAL_CAPITAL, cost_bps / 10000
    daily, ledger = [], []
    for i in chosen:
        open_before = float(cash + units @ opened[i])
        day_cost = 0.0
        if i == chosen[0] or schedule[i]:
            old_units = units.copy()
            units, cash, turnover, fee = rebalance(units, cash, opened[i], weight_array[i], rate)
            day_cost += fee
            ledger.append(
                {
                    "decision_date": signal_dates.iloc[i],
                    "as_of": signals.as_of.iloc[i],
                    "execution_date": dates[i],
                    "reason": "initial" if i == chosen[0] else "rebalance",
                    "pre_nav": open_before,
                    "post_nav": float(cash + units @ opened[i]),
                    "cash": cash,
                    "turnover": turnover,
                    "cost": fee,
                    **{f"units_{s}": units[j] for j, s in enumerate(SYMBOLS)},
                    **{f"delta_{s}": units[j] - old_units[j] for j, s in enumerate(SYMBOLS)},
                    **{f"price_{s}": opened[i, j] for j, s in enumerate(SYMBOLS)},
                    **{f"weight_{s}": weight_array[i, j] for j, s in enumerate(SYMBOLS)},
                }
            )
        open_after = float(cash + units @ opened[i])
        close_before = float(cash + units @ closed[i])
        if i == chosen[-1]:
            old_units = units.copy()
            units, cash, turnover, fee = rebalance(
                units, cash, closed[i], np.zeros(len(SYMBOLS)), rate
            )
            day_cost += fee
            ledger.append(
                {
                    "decision_date": dates[i - 1],
                    "as_of": _as_of(dates[i - 1]),
                    "execution_date": dates[i],
                    "reason": "terminal_prescheduled_close",
                    "pre_nav": close_before,
                    "post_nav": cash,
                    "cash": cash,
                    "turnover": turnover,
                    "cost": fee,
                    **{f"units_{s}": 0.0 for s in SYMBOLS},
                    **{f"delta_{s}": -old_units[j] for j, s in enumerate(SYMBOLS)},
                    **{f"price_{s}": closed[i, j] for j, s in enumerate(SYMBOLS)},
                    **{f"weight_{s}": 0.0 for s in SYMBOLS},
                }
            )
        daily.append(
            {
                "session_date": dates[i],
                "open_before": open_before,
                "open_after": open_after,
                "close_before": close_before,
                "nav": float(cash + units @ closed[i]),
                "cash": cash,
                "cost": day_cost,
            }
        )
    return pd.DataFrame(daily), pd.DataFrame(ledger)


def summarize(daily: pd.DataFrame) -> dict[str, Any]:
    """Calendar returns include all zero/loss years and final liquidation costs."""
    nav = pd.Series(daily.nav.to_numpy(float), index=pd.DatetimeIndex(daily.session_date))
    endings = nav.groupby(nav.index.year).last()
    annual = endings / endings.shift(1, fill_value=INITIAL_CAPITAL) - 1
    marks = np.r_[
        INITIAL_CAPITAL,
        daily[["open_before", "open_after", "close_before", "nav"]].to_numpy(float).ravel(),
    ]
    drawdowns = marks / np.maximum.accumulate(marks) - 1
    close_marks = np.r_[INITIAL_CAPITAL, nav.to_numpy(float)]
    beginnings = endings.shift(1, fill_value=INITIAL_CAPITAL)
    gaps = endings - 1.10 * beginnings
    return {
        "ending_nav": float(nav.iloc[-1]),
        "total_cost": float(daily.cost.sum()),
        "cagr": float((nav.iloc[-1] / INITIAL_CAPITAL) ** (1 / len(annual)) - 1),
        "max_drawdown": float(drawdowns.min()),
        "worst_year": float(annual.min()),
        "close_max_drawdown": float((close_marks / np.maximum.accumulate(close_marks) - 1).min()),
        "years_ge_10pct": int((annual >= 0.1).sum()),
        "years_ge_20pct": int((annual >= 0.2).sum()),
        "years_10_to_20_inclusive": int(((annual >= 0.1) & (annual <= 0.2)).sum()),
        "years_above_20pct": int((annual > 0.2).sum()),
        "years_below_10pct": int((annual < 0.1).sum()),
        "losing_years": int((annual < 0).sum()),
        "mean_cash_fraction": float((daily.cash / daily.nav).mean()),
        "all_years_ge_10pct": bool((annual >= 0.1).all()),
        "annual": {str(year): float(value) for year, value in annual.items()},
        "annual_additional_expense_capacity": {str(y): max(0.0, float(v)) for y, v in gaps.items()},
        "annual_10pct_dollar_gap": {str(y): float(v) for y, v in gaps.items()},
    }


def simulate_integer_spy(
    raw: pd.DataFrame, signals: pd.DataFrame, cost_bps: int, start: str, end: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Nominal integer SPY with permanently locked dividend receivables.

    A dividend belongs to prior-close holders, even if they sell at the ex-date
    open. Receivables enter NAV but never sizing capital or spendable cash.
    """
    required = {"Open", "Close", "Dividends", "Stock Splits"}
    if not required <= set(raw) or not raw.index.equals(signals.index):
        raise ValueError("Missing or misaligned nominal inputs")
    if not 0 <= cost_bps < 10000:
        raise ValueError("Invalid cost")
    array = raw[list(required)].to_numpy(float)
    if (
        not np.isfinite(array).all()
        or (raw[["Open", "Close"]] <= 0).any().any()
        or (raw.Dividends < 0).any()
        or (raw["Stock Splits"] != 0).any()
        or ("Capital Gains" in raw and (raw["Capital Gains"] != 0).any())
    ):
        raise ValueError("Invalid nominal prices or unsupported corporate action")
    chosen = np.flatnonzero(raw.index.to_series().between(start, end).to_numpy())
    if not len(chosen) or chosen[0] == 0:
        raise ValueError("Evaluation needs prior-close warmup")
    opened, closed = raw.Open.to_numpy(float), raw.Close.to_numpy(float)
    dividends, weights = raw.Dividends.to_numpy(float), signals.SPY.to_numpy(float)
    schedule = signals.rebalance.to_numpy(bool)
    cash, locked, shares, rate = INITIAL_CAPITAL, 0.0, 0, cost_bps / 10000
    daily, ledger = [], []
    for i in chosen:
        credited = shares * dividends[i]
        locked += credited
        open_before = cash + shares * opened[i] + locked
        fee = 0.0
        if i == chosen[0] or schedule[i]:
            desired, _, _, _ = rebalance(
                np.array([float(shares)]),
                cash,
                np.array([opened[i]]),
                np.array([weights[i]]),
                rate,
            )
            target = int(np.floor(desired[0] + 1e-12))
            delta = target - shares
            fee = abs(delta) * opened[i] * rate
            cash -= delta * opened[i] + fee
            if cash < -1e-8:
                raise ValueError("Unfunded integer trade")
            shares = target
            ledger.append(
                {
                    "decision_date": signals.decision_date.iloc[i],
                    "as_of": signals.as_of.iloc[i],
                    "execution_date": raw.index[i],
                    "reason": "initial" if i == chosen[0] else "rebalance",
                    "shares": shares,
                    "delta": delta,
                    "price": opened[i],
                    "cost": fee,
                    "cash": cash,
                    "locked_receivable": locked,
                    "target_weight": weights[i],
                }
            )
        open_after = cash + shares * opened[i] + locked
        close_before = cash + shares * closed[i] + locked
        if i == chosen[-1]:
            terminal_fee = shares * closed[i] * rate
            cash += shares * closed[i] - terminal_fee
            fee += terminal_fee
            ledger.append(
                {
                    "decision_date": raw.index[i - 1],
                    "as_of": _as_of(raw.index[i - 1]),
                    "execution_date": raw.index[i],
                    "reason": "terminal_prescheduled_close",
                    "shares": 0,
                    "delta": -shares,
                    "price": closed[i],
                    "cost": terminal_fee,
                    "cash": cash,
                    "locked_receivable": locked,
                    "target_weight": 0.0,
                }
            )
            shares = 0
        daily.append(
            {
                "session_date": raw.index[i],
                "open_before": open_before,
                "open_after": open_after,
                "close_before": close_before,
                "nav": cash + shares * closed[i] + locked,
                "cash": cash,
                "cost": fee,
                "shares": shares,
                "locked_receivable": locked,
                "dividend_receivable_added": credited,
            }
        )
    return pd.DataFrame(daily), pd.DataFrame(ledger)
