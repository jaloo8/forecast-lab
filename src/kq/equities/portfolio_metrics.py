"""Daily account metrics and an explicitly fully invested SPY reference."""

from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd


def benchmark_revision(bars: pd.DataFrame, prior: pd.DataFrame, launched_at: str) -> bool:
    """Reject revised or omitted benchmark prices since prospective entry."""
    launched = datetime.fromisoformat(launched_at)
    current = bars.loc[bars.symbol == "SPY"].set_index("session_date")
    for row in prior.loc[prior.symbol == "SPY"].itertuples():
        opened = datetime.combine(row.session_date, time(9, 30), ZoneInfo("America/New_York"))
        if opened.astimezone(UTC) <= launched:
            continue
        if row.session_date not in current.index or any(
            float(current.loc[row.session_date, key]) != float(getattr(row, key))
            for key in ("open", "close")
        ):
            return True
    return False


def benchmark(bars: pd.DataFrame, launched_at: str) -> dict[str, Any]:
    """Return prospective $100 SPY liquidation value, with 10bp per side."""
    launched = datetime.fromisoformat(launched_at)
    spy = bars.loc[bars.symbol == "SPY"].sort_values("session_date")
    spy = spy.loc[
        spy.session_date.map(
            lambda d: (
                datetime.combine(d, time(9, 30), ZoneInfo("America/New_York")).astimezone(UTC)
                > launched
            )
        )
    ]
    if spy.empty:
        return {"status": "pending", "equity": None, "return": None}
    equity = 100 * float(spy.iloc[-1]["close"]) * 0.999 / (float(spy.iloc[0]["open"]) * 1.001)
    return dict(
        status="marked",
        equity=equity,
        **{"return": equity / 100 - 1},
        entry_date=spy.iloc[0].session_date.isoformat(),
        session_date=spy.iloc[-1].session_date.isoformat(),
    )


def account_metrics(
    summary: dict[str, Any],
    previous: dict[str, Any],
    bars: pd.DataFrame,
) -> dict[str, Any]:
    """Compute cash-aware equity/drawdown and matched closed-trade SPY P&L."""
    valid = bool(summary["equity_valid"]) and not summary["stale_symbols"]
    if not valid:
        return dict(
            valid=False,
            realized_pnl=None,
            unrealized_pnl=None,
            exposure=None,
            peak_equity=previous.get("peak_equity", 100.0),
            max_drawdown=previous.get("max_drawdown"),
            matched_spy_pnl=None,
        )
    equity = float(summary["equity"])
    realized = sum(float(row["net_pnl"]) for row in summary["closed_trades"])
    peak = max(100.0, float(previous.get("peak_equity") or 100), equity)
    drawdown = max(float(previous.get("max_drawdown") or 0), 1 - equity / peak)
    recovery = summary.get("delayed_recovery") or {}
    recovery_runs = int(recovery.get("run_count", 0))
    if recovery_runs > int(previous.get("recovery_runs_seen", 0)):
        minimum = float(recovery.get("last_run_minimum_equity", recovery["minimum_equity"]))
        drawdown = max(
            drawdown,
            float(recovery["max_drawdown_recovered"]),
            1 - minimum / max(100.0, float(previous.get("peak_equity") or 100)),
        )
        peak = max(peak, float(recovery["peak_equity"]))
        drawdown = max(drawdown, 1 - equity / peak)
    spy = bars.loc[bars.symbol == "SPY"].set_index("session_date")
    matched = 0.0
    for trade in summary["closed_trades"]:
        first = datetime.fromisoformat(trade["entry_date"]).date()
        last = datetime.fromisoformat(trade["exit_date"]).date()
        if first not in spy.index or last not in spy.index:
            return dict(
                valid=False,
                realized_pnl=None,
                unrealized_pnl=None,
                exposure=None,
                peak_equity=peak,
                max_drawdown=None,
                matched_spy_pnl=None,
            )
        matched += 10 * (
            float(spy.loc[last, "close"]) * 0.999 / (float(spy.loc[first, "open"]) * 1.001) - 1
        )
    return dict(
        valid=True,
        realized_pnl=realized,
        unrealized_pnl=equity - 100 - realized,
        exposure=(equity - float(summary["cash"])) / equity if equity > 0 else None,
        peak_equity=peak,
        max_drawdown=drawdown,
        recovery_runs_seen=recovery_runs,
        matched_spy_pnl=matched if summary["closed_trades"] else None,
    )
