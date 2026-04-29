"""Typed BacktestResult — structured result of a single backtest run."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True, slots=True)
class TradeRecord:
    """One simulated trade. All prices in dollars (0..1); pnl in dollars."""

    valid_date: date
    station: str
    threshold_f: float
    side: str  # "BUY_YES" | "BUY_NO" — we go long the cheaper side when our prob disagrees with mid
    model_prob: float
    market_bid: float
    market_ask: float
    fill_price: float  # crossed the spread
    qty: int
    fee_usd: float
    settled_yes: bool
    pnl_usd: float

    @property
    def edge_pct(self) -> float:
        """Pre-fee edge in percentage points (model vs the side we bought)."""
        return abs(self.model_prob - self.fill_price) * 100.0


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Aggregate result for one backtest configuration (station + strategy + window)."""

    station: str
    strategy: str
    n_evaluated: int
    n_traded: int
    total_pnl_usd: float
    final_bankroll_usd: float
    starting_bankroll_usd: float
    win_rate: float  # fraction of trades with pnl > 0
    avg_edge_pct_pre_fee: float
    avg_edge_pct_post_fee: float
    brier_calibrated: float
    brier_raw: float
    brier_improvement_pct: float
    max_drawdown_usd: float
    max_drawdown_pct: float
    equity_curve: tuple[tuple[date, float], ...]  # (date, cumulative_pnl)
    reliability: list[dict[str, Any]] = field(default_factory=list)
    trades: list[TradeRecord] = field(default_factory=list)

    def to_summary_dict(self) -> dict[str, Any]:
        """Compact dict for logging / manifest emission (drops the per-trade detail)."""
        return {
            "station": self.station,
            "strategy": self.strategy,
            "n_evaluated": self.n_evaluated,
            "n_traded": self.n_traded,
            "total_pnl_usd": round(self.total_pnl_usd, 2),
            "final_bankroll_usd": round(self.final_bankroll_usd, 2),
            "starting_bankroll_usd": round(self.starting_bankroll_usd, 2),
            "roi_pct": round(
                100.0
                * (self.final_bankroll_usd - self.starting_bankroll_usd)
                / self.starting_bankroll_usd
                if self.starting_bankroll_usd > 0
                else 0.0,
                2,
            ),
            "win_rate": round(self.win_rate, 4),
            "avg_edge_pct_pre_fee": round(self.avg_edge_pct_pre_fee, 3),
            "avg_edge_pct_post_fee": round(self.avg_edge_pct_post_fee, 3),
            "brier_calibrated": round(self.brier_calibrated, 4),
            "brier_raw": round(self.brier_raw, 4),
            "brier_improvement_pct": round(self.brier_improvement_pct, 2),
            "max_drawdown_usd": round(self.max_drawdown_usd, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
        }
