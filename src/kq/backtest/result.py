"""Typed BacktestResult — structured result of a single backtest run."""

from __future__ import annotations

import math
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
    fill_price: float  # crossed the spread for taker; 1 tick inside for maker
    qty: int
    fee_usd: float
    settled_yes: bool
    pnl_usd: float
    # Phase 2 ext #2 — maker/taker order classification.
    # Defaults to "taker" so existing callers (paper executor) still work.
    order_type: str = "taker"  # "maker" | "taker"

    @property
    def prob_at_fill(self) -> float:
        """Model probability of the side we bought.

        For ``BUY_YES``, this is ``model_prob`` (the YES probability). For
        ``BUY_NO``, the side we bought is the NO contract, whose probability
        is ``1 - model_prob``. Storing the YES-side ``model_prob`` keeps the
        TradeRecord schema canonical (always YES-relative); this property
        emits the side-correct probability for downstream edge math.
        """
        return self.model_prob if self.side == "BUY_YES" else 1.0 - self.model_prob

    @property
    def edge_pct(self) -> float:
        """Pre-fee edge in percentage points (probability of the side we bought
        minus the fill price we paid for it).

        For ``BUY_YES`` this collapses to ``model_prob - fill_price``. For
        ``BUY_NO``, ``fill_price`` is the NO market ask (= ``1 - YES_bid``)
        and the side probability is ``1 - model_prob`` — using ``model_prob``
        directly gives a different, meaningless quantity (it's the gap
        between unrelated YES-side prob and NO-side ask). See
        ``prob_at_fill`` for the canonical mapping.
        """
        return abs(self.prob_at_fill - self.fill_price) * 100.0


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
    # ---- NDFD/NBM external benchmark (Phase 2 ext #1) ----
    # All NDFD metrics are computed on the **subset** of evaluations where
    # NDFD coverage exists (Open-Meteo NBM history starts ~2024-11). The
    # *_ndfd_subset variant of the model Brier is computed on the same
    # subset so the comparison is apples-to-apples — without that, an
    # uneven join would conflate model-improvement with sample-shift.
    n_evaluated_with_ndfd: int = 0
    brier_ndfd: float = float("nan")
    brier_model_ndfd_subset: float = float("nan")
    brier_improvement_vs_ndfd_pct: float = float("nan")
    # Mean (model_prob - ndfd_prob) in pp. Not closing-line value (we don't
    # have a market close); just the average prob-difference vs benchmark.
    # Renamed from `clv_vs_ndfd_pp` per audit (2026-04-29).
    mean_prob_diff_vs_ndfd_pp: float = float("nan")
    # Verdict-deepening diagnostics: per-band Brier breakdown + per-month
    # series. Empty dict when NDFD coverage is missing. JSON-safe by
    # construction (the diagnostic helpers emit None for NaN).
    diagnostics: dict[str, Any] = field(default_factory=dict)
    # Phase 2 ext #2 — maker/taker order-type telemetry.
    n_maker_trades: int = 0
    n_taker_trades: int = 0
    maker_fee_savings_usd: float = 0.0  # vs the same trades booked as takers
    # Phase 5 #3 — n-aware reliability summary (post-fix 2026-05-01). The
    # original criterion was "no bucket off by > 10pp" applied to all 10
    # equal-width buckets; in practice that flagged small-n mid-range
    # buckets where binomial-noise alone produces 30-60pp deviations. The
    # summary excludes buckets with n < min_n (default 100) and reports
    # pass/fail over the qualifying subset. See models/calibration.py.
    # Empty dict when n_evaluated == 0 (no bins to summarize).
    reliability_summary: dict[str, Any] = field(default_factory=dict)

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
            "n_evaluated_with_ndfd": self.n_evaluated_with_ndfd,
            "brier_ndfd": _round_or_none(self.brier_ndfd, 4),
            "brier_model_ndfd_subset": _round_or_none(self.brier_model_ndfd_subset, 4),
            "brier_improvement_vs_ndfd_pct": _round_or_none(self.brier_improvement_vs_ndfd_pct, 2),
            "mean_prob_diff_vs_ndfd_pp": _round_or_none(self.mean_prob_diff_vs_ndfd_pp, 3),
            "diagnostics": self.diagnostics,
            "n_maker_trades": self.n_maker_trades,
            "n_taker_trades": self.n_taker_trades,
            "maker_fee_savings_usd": round(self.maker_fee_savings_usd, 4),
            "reliability_summary": self.reliability_summary,
        }


def _round_or_none(value: float, ndigits: int) -> float | None:
    """JSON-safe rounding: NaN → None so the manifest stays valid JSON."""
    if math.isnan(value):
        return None
    return round(value, ndigits)
