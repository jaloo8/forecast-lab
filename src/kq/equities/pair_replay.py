"""Offline, fixed-pair research with explicit short liability and lagged fills."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt
import pandas as pd


def _prices(frame: pd.DataFrame) -> npt.NDArray[np.float64]:
    values = np.asarray(frame.to_numpy(), dtype=np.float64)
    if (
        values.ndim != 2
        or values.shape[1] != 2
        or not len(values)
        or not np.isfinite(values).all()
        or (values <= 0).any()
        or not frame.index.is_unique
        or not frame.index.is_monotonic_increasing
    ):
        raise ValueError("Invalid pair prices or dates")
    return values


@dataclass
class _PairRule:
    spread: npt.NDArray[np.float64]
    start: int
    lookback: int
    max_hold: int
    entry_index: int = 0
    frozen_mean: float = 0.0

    def __post_init__(self) -> None:
        if (
            self.lookback < 2
            or self.start < self.lookback
            or self.start >= len(self.spread)
            or self.max_hold < 1
        ):
            raise ValueError("Invalid formation/evaluation window")

    def decide(self, i: int, held_side: int) -> int | None:
        if i < self.start or i == len(self.spread) - 1:
            return None
        if held_side:
            crossed = held_side * (self.spread[i] - self.frozen_mean) >= 0
            return 0 if crossed or i - self.entry_index + 1 >= self.max_hold else None
        formation = self.spread[i - self.lookback : i]
        mean, sigma = float(formation.mean()), float(formation.std(ddof=1))
        if sigma <= 1e-12 or abs((self.spread[i] - mean) / sigma) < 2:
            return None
        self.frozen_mean, self.entry_index = mean, i + 1
        return -1 if self.spread[i] > mean else 1


@dataclass
class _Account:
    cash: float = 1000.0
    units: npt.NDArray[np.float64] = field(default_factory=lambda: np.zeros(2))
    entry: dict[str, object] = field(default_factory=dict)
    entry_equity: float = 0.0
    entry_cost: float = 0.0
    borrow_total: float = 0.0
    trades: list[dict[str, object]] = field(default_factory=list)

    def equity(self, price: npt.NDArray[np.float64]) -> float:
        return self.cash + float(self.units @ price)

    def enter(
        self, price: npt.NDArray[np.float64], side: int, fee: float, day: object, signal: object
    ) -> float:
        if self.entry:
            raise ValueError("Cannot pyramid an open pair")
        self.entry_equity = self.equity(price)
        self.units = np.array([side, -side]) * self.entry_equity * 0.25 / price
        self.entry_cost = float(np.abs(self.units * price).sum()) * fee
        self.cash -= float(self.units @ price) + self.entry_cost
        self.borrow_total = 0.0
        self.entry = {"entry_date": day, "signal_date": signal, "side": side}
        return self.entry_cost

    def exit(self, price: npt.NDArray[np.float64], fee: float, day: object, reason: str) -> float:
        if not self.entry:
            return 0.0
        cost = float(np.abs(self.units * price).sum()) * fee
        self.cash += float(self.units @ price) - cost
        self.units[:] = 0
        self.trades.append(
            dict(
                self.entry,
                exit_date=day,
                reason=reason,
                net_pnl=self.cash - self.entry_equity,
                cost=self.entry_cost + cost,
                borrow=self.borrow_total,
            )
        )
        self.entry = {}
        return cost


def replay_pair(
    opens: pd.DataFrame,
    closes: pd.DataFrame,
    orders: dict[int, int] | None,
    cost_bps: float,
    borrow_rate: float,
    *,
    start: int = 252,
    lookback: int = 252,
    max_hold: int = 63,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Replay manual accounting fixtures, or causal strategy when orders is None."""
    if not opens.index.equals(closes.index) or not opens.columns.equals(closes.columns):
        raise ValueError("Prices must align")
    op, cl = _prices(opens), _prices(closes)
    if not 0 <= cost_bps < 10000 or not 0 <= borrow_rate <= 1:
        raise ValueError("Invalid friction")
    rule = None
    if orders is None:
        rule = _PairRule(np.log(cl[:, 0] / cl[:, 1]), start, lookback, max_hold)
        orders = {}
    elif any(i < 0 or i >= len(op) or side not in {-1, 0, 1} for i, side in orders.items()):
        raise ValueError("Invalid order")
    dates = pd.DatetimeIndex(closes.index)
    account, risk_exit = _Account(), False
    rows = []
    for i, day in enumerate(dates):
        borrow, cost = 0.0, 0.0
        if i and account.entry:
            short_value = -float(np.minimum(account.units, 0) @ cl[i - 1])
            borrow = short_value * borrow_rate * (day - dates[i - 1]).days / 365
            account.cash -= borrow
            account.borrow_total += borrow
        order = orders.get(i)
        if risk_exit or order == 0:
            cost += account.exit(op[i], cost_bps / 10000, day, "risk" if risk_exit else "signal")
            risk_exit = False
        elif order in {-1, 1}:
            cost += account.enter(op[i], order, cost_bps / 10000, day, dates[i - 1] if i else None)
        if i == len(dates) - 1:
            cost += account.exit(cl[i], cost_bps / 10000, day, "terminal")
        nav = account.equity(cl[i])
        gross = float(np.abs(account.units * cl[i]).sum())
        if nav <= 0 or account.cash < 0:
            raise ValueError("Insolvent research path; cannot continue sizing")
        risk_exit = gross > nav
        rows.append((day, nav, account.cash, gross, cost, borrow))
        if rule:
            decision = rule.decide(i, int(np.sign(account.units[0])))
            if decision is not None:
                orders[i + 1] = decision
    daily = pd.DataFrame(rows, columns=["date", "nav", "cash", "gross", "cost", "borrow"])
    daily.attrs["orders"] = dict(orders)
    return daily.set_index("date"), pd.DataFrame(account.trades)
