"""Backtest reporting metrics: equity curve + drawdown.

Brier and reliability primitives live in `kq.models.calibration`; this module
focuses on P&L-derived metrics that the backtest engine emits.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import numpy as np


def equity_curve(
    trade_dates: Sequence[date],
    trade_pnl_usd: Sequence[float],
    *,
    starting_bankroll_usd: float,
) -> list[tuple[date, float]]:
    """Cumulative bankroll over time. One point per trade date.

    When multiple trades land on the same date, they're summed before the
    cumulative point is emitted (one entry per unique date).
    """
    if len(trade_dates) != len(trade_pnl_usd):
        raise ValueError("trade_dates and trade_pnl_usd must have the same length")
    if not trade_dates:
        return [(date.today(), starting_bankroll_usd)]
    # Group by date, preserving chronological order.
    pnl_by_date: dict[date, float] = {}
    for d, p in zip(trade_dates, trade_pnl_usd, strict=True):
        pnl_by_date[d] = pnl_by_date.get(d, 0.0) + float(p)
    curve: list[tuple[date, float]] = []
    cumulative = starting_bankroll_usd
    for d in sorted(pnl_by_date):
        cumulative += pnl_by_date[d]
        curve.append((d, cumulative))
    return curve


def max_drawdown(
    equity: Sequence[tuple[date, float]],
    *,
    starting_equity: float | None = None,
) -> tuple[float, float]:
    """Return ``(max_drawdown_usd, max_drawdown_pct)``.

    ``pct`` is relative to the prior peak. Both values are non-negative.

    ``starting_equity`` (2026-07-01 audit, Tier 2): the bankroll BEFORE the
    first trade. The equity curve's first point is *after* the first trade
    date's P&L, so without this anchor a losses-first sequence has its
    initial drawdown invisible (the first post-loss point becomes the
    "peak") and the pct denominator is anchored to the wrong peak. When
    provided, it is prepended as the first equity value.
    """
    if starting_equity is not None:
        equity = [(equity[0][0] if equity else date.today(), float(starting_equity)), *equity]
    if not equity:
        return 0.0, 0.0
    values = np.array([v for _, v in equity], dtype=float)
    peaks = np.maximum.accumulate(values)
    drawdowns = peaks - values
    if len(drawdowns) == 0:
        return 0.0, 0.0
    max_dd_usd = float(np.max(drawdowns))
    # Dollar and percentage drawdown maxima can occur at different peaks.
    percentages = np.divide(drawdowns, peaks, out=np.zeros_like(drawdowns), where=peaks > 0)
    max_dd_pct = float(np.max(percentages) * 100.0)
    return max_dd_usd, float(max_dd_pct)


def hit_rate(trade_pnl_usd: Sequence[float]) -> float:
    """Fraction of trades with strictly positive P&L."""
    if not trade_pnl_usd:
        return 0.0
    wins = sum(1 for p in trade_pnl_usd if p > 0)
    return wins / len(trade_pnl_usd)
