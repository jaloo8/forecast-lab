"""Pure normalized-budget accounting for historical strategy cohorts."""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd


class Prices:
    """Aligned regular-session prices; no interpolation or missing-price substitution."""

    def __init__(self, bars: pd.DataFrame) -> None:
        self.dates: list[date] = sorted(bars.loc[bars.symbol == "SPY", "session_date"].unique())
        if not self.dates or not bars.session_date.isin(self.dates).all():
            raise ValueError("Missing benchmark or stock sessions outside benchmark calendar")
        numeric = bars[["open", "high", "low", "close", "volume"]].apply(
            pd.to_numeric, errors="coerce"
        )
        valid = np.isfinite(numeric).all(axis=1) & numeric.gt(0).all(axis=1)
        valid &= numeric.high.ge(numeric[["open", "close"]].max(axis=1))
        valid &= numeric.low.le(numeric[["open", "close"]].min(axis=1))
        valid &= numeric.high.ge(numeric.low)
        for column in numeric.columns:
            if bars[column].dtype == object or bars[column].dtype == bool:
                valid &= ~bars[column].map(lambda value: isinstance(value, (bool, np.bool_)))
        close_time = (
            pd.to_datetime(bars.session_date).dt.tz_localize("America/New_York")
            + pd.Timedelta(hours=16)
        ).dt.tz_convert("UTC")
        valid &= pd.to_datetime(bars.as_of, utc=True, errors="coerce").le(close_time)
        for flag in ("synthetic", "is_synthetic", "interpolated"):
            if flag in bars:
                valid &= ~bars[flag].fillna(True).astype(bool)
        if "session" in bars:
            valid &= bars.session.eq("reg")
        frame = bars.assign(valid=valid)
        self.opens = frame.pivot(index="session_date", columns="symbol", values="open")
        self.closes = frame.pivot(index="session_date", columns="symbol", values="close")
        self.valid = frame.pivot(index="session_date", columns="symbol", values="valid")

    def cohort(
        self,
        symbols: list[str],
        size: int,
        index: int,
        hold: int,
        cost: int,
        *,
        details: bool = True,
    ) -> dict[str, Any]:
        end = index + hold
        row: dict[str, Any] = {
            "decision_date": self.dates[index].isoformat(),
            "entry_date": self.dates[index + 1].isoformat()
            if index + 1 < len(self.dates)
            else None,
            "exit_date": self.dates[end].isoformat() if end < len(self.dates) else None,
            "hold_sessions": hold,
            "cost_bps": cost,
            "selected_symbols": symbols,
            "exposure": len(symbols) / size if size else 0.0,
            "gross_return": None,
            "entry_cost": None,
            "exit_cost": None,
            "net_return": None,
            "trades": [],
            "missing_symbols": [],
            "status": "pending",
        }
        if end >= len(self.dates):
            return row
        valid = self.valid.reindex(columns=symbols).iloc[index + 1 : end + 1]
        missing = valid.columns[~valid.eq(True).all()].tolist()
        if missing:
            row.update(status="unavailable", missing_symbols=missing)
            return row
        friction = cost / 10_000
        opening = self.opens.iloc[index + 1].reindex(symbols).to_numpy(dtype=float)
        closing = self.closes.iloc[end].reindex(symbols).to_numpy(dtype=float)
        shares = 1 / (size * opening * (1 + friction))
        gain = shares * (closing - opening)
        paid_entry = shares * opening * friction
        paid_exit = shares * closing * friction
        gross, entry_cost, exit_cost = (
            float(gain.sum()),
            float(paid_entry.sum()),
            float(paid_exit.sum()),
        )
        trades = [
            {
                "symbol": symbol,
                "slot_budget": 1 / size,
                "shares": float(shares[i]),
                "entry_open": float(opening[i]),
                "exit_close": float(closing[i]),
                "gross_return": float(gain[i]),
                "entry_cost": float(paid_entry[i]),
                "exit_cost": float(paid_exit[i]),
                "net_return": float(gain[i] - paid_entry[i] - paid_exit[i]),
            }
            for i, symbol in enumerate(symbols)
            if details
        ]
        row.update(
            status="complete",
            gross_return=gross,
            entry_cost=entry_cost,
            exit_cost=exit_cost,
            net_return=gross - entry_cost - exit_cost,
            trades=trades,
            invested_exposure=row["exposure"] / (1 + friction),
        )
        return row
