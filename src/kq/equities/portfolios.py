"""Frozen, pure candidates for nine prospective stock paper portfolios.

Each result contains one row per event-conditioned symbol. ``ranked`` means
selected for the paper ledger; other rows retain explicit exclusion evidence.
All momentum uses completed, real, positive-volume sessions aligned with SPY.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import dataclass
from typing import Any

import pandas as pd

from kq.equities.challenger import screen
from kq.equities.research import daily_bars

_METHOD = {
    "version": "stock-portfolios-v1",
    "universe": "captured_catalogue_intersect_earnings_calendar",
    "bars": "completed_regular_real_positive_volume_aligned_with_spy",
    "history": "max_21_lookback_plus_1_sessions",
    "momentum": "last_close_divided_by_close_lookback_sessions_ago_minus_1_less_spy_return",
    "liquidity": "median_last_20_close_times_volume_at_least_20000000",
    "price": "last_close_at_least_5",
    "earnings": (
        "verified_report_within_7_days_estimate_positive_actual_available_beat_at_least_5pct"
    ),
    "rank": "positive_excess_descending_then_symbol_ascending_top_3",
    "entry": "next_regular_open_after_actual_order_creation_completed_bar_required",
    "order_notional": 10,
    "initial_cash": 100,
    "max_active": 5,
    "cost_each_side": 0.001,
    "loss_pause": 10,
}
_COLUMNS = [
    "symbol",
    "horizon_sessions",
    "as_of",
    "session_date",
    "close",
    "benchmark_close",
    "excess_momentum",
    "status",
    "selected",
    "rank",
    "reason",
    "reasons",
    "price_as_of",
    "median_dollar_volume_20d",
    "report_date",
    "eps_estimate",
    "eps_actual",
    "earnings_beat",
    "earnings_reason",
    "history_sessions",
    "lookback_sessions",
    "portfolio_id",
    "protocol_id",
    "last_bar_session_date",
]


@dataclass(frozen=True)
class PortfolioSpec:
    portfolio_id: str
    family: str
    lookback: int
    holding_sessions: int
    protocol_id: str


def portfolio_specs() -> tuple[PortfolioSpec, ...]:
    """Return the nine predeclared families, horizons and method hashes."""
    specs: list[PortfolioSpec] = []
    for family, hold in (("momentum", 5), ("momentum", 20), ("earnings", 20)):
        for lookback in (10, 20, 60):
            portfolio_id = f"{family}{hold}_{lookback}"
            method = {**_METHOD, "family": family, "holding_sessions": hold, "lookback": lookback}
            digest = hashlib.sha256(
                json.dumps(method, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            specs.append(PortfolioSpec(portfolio_id, family, lookback, hold, digest))
    return tuple(specs)


def _aligned(stock: pd.DataFrame, spy: pd.DataFrame, length: int) -> bool:
    if len(stock) < length or len(spy) < length:
        return False
    selected = stock.tail(length)
    return (
        selected.session_date.tolist() == spy.tail(length).session_date.tolist()
        and bool(selected.volume.gt(0).all())
        and bool(spy.tail(length).volume.gt(0).all())
    )


def portfolio_research(snapshot: dict[str, Any], spec: PortfolioSpec) -> pd.DataFrame:
    """Adapt the shared validated capture to one frozen candidate protocol.

    Schema is ``_COLUMNS``. ``as_of`` is UTC and ``session_date`` is a date.
    Missing scores use zero solely to keep excluded rows ledger-compatible.
    """
    if spec not in portfolio_specs():
        raise ValueError("unknown portfolio method")
    screened = screen(snapshot)
    bars = daily_bars(snapshot)
    spy = bars.loc[bars.symbol == "SPY"].sort_values("session_date")
    length = max(21, spec.lookback + 1)
    rows: list[dict[str, Any]] = []
    for source in screened.to_dict("records"):
        symbol = str(source["symbol"])
        stock = bars.loc[bars.symbol == symbol].sort_values("session_date")
        last = stock.iloc[-1] if not stock.empty else None
        close = float(last["close"]) if last is not None else None
        reasons: list[str] = []
        median: float | None = None
        excess = 0.0
        benchmark_close: float | None = None
        if not _aligned(stock, spy, length):
            reasons.append("missing_history")
        if close is not None and close < 5:
            reasons.append("low_price")
        if len(stock) >= 20:
            median = float(
                statistics.median((stock.tail(20)["close"] * stock.tail(20)["volume"]).tolist())
            )
            if median < 20_000_000:
                reasons.append("illiquid")
        if "missing_history" not in reasons:
            assert close is not None
            benchmark_close = float(spy.iloc[-1]["close"])
            stock_return = close / float(stock.iloc[-spec.lookback - 1]["close"]) - 1
            spy_return = benchmark_close / float(spy.iloc[-spec.lookback - 1]["close"]) - 1
            excess = stock_return - spy_return
            if excess <= 0:
                reasons.append("nonpositive_excess")
        earnings_reason = source["earnings_reason"]
        if spec.family == "earnings" and isinstance(earnings_reason, str) and earnings_reason:
            reasons.append(earnings_reason)
        rows.append(
            {
                "symbol": symbol,
                "horizon_sessions": spec.holding_sessions,
                "as_of": source["as_of"],
                "session_date": spy.iloc[-1]["session_date"],
                "close": close,
                "benchmark_close": benchmark_close,
                "excess_momentum": excess,
                "status": "excluded",
                "selected": False,
                "rank": None,
                "reason": reasons[0] if reasons else None,
                "reasons": ";".join(reasons) or None,
                "price_as_of": source["price_as_of"],
                "median_dollar_volume_20d": median,
                "report_date": source["report_date"],
                "eps_estimate": source["eps_estimate"],
                "eps_actual": source["eps_actual"],
                "earnings_beat": source["earnings_beat"],
                "earnings_reason": earnings_reason,
                "history_sessions": len(stock),
                "lookback_sessions": spec.lookback,
                "portfolio_id": spec.portfolio_id,
                "protocol_id": spec.protocol_id,
                "last_bar_session_date": None if last is None else last["session_date"],
            }
        )
    ranked = sorted(
        (row for row in rows if row["reason"] is None),
        key=lambda row: (-row["excess_momentum"], row["symbol"]),
    )
    for rank, row in enumerate(ranked, 1):
        row["rank"] = rank
        if rank <= 3:
            row["selected"] = True
            row["status"] = "ranked"
        else:
            row["reason"] = "outside_top_three"
            row["reasons"] = "outside_top_three"
    result = pd.DataFrame(rows, columns=_COLUMNS)
    result["as_of"] = pd.to_datetime(result["as_of"], utc=True)
    result["price_as_of"] = pd.to_datetime(result["price_as_of"], utc=True)
    return result
