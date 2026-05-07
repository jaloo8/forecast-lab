"""Paper-trading executor.

By construction this module never imports from ``kq.execution.live`` and never
opens a network connection — it cannot place a real-money order. The executor
is a thin wrapper around two pure functions:

- :func:`evaluate_market` — given a model probability and a market quote,
  decide whether the post-fee edge clears the threshold and (if so) emit a
  :class:`PaperTradeIntent`. Mirrors ``kq.backtest.engine._maybe_trade``
  exactly so the backtest and paper trader agree on every trade decision.
- :func:`settlement_pnl` — given a filled trade and the realized outcome,
  compute realized P&L. Mirrors the backtest's payout math.

The executor class composes these into a stateful pipeline: ``submit`` writes
a (signal, paper_trade) row pair via the paper-trade repository; ``settle``
walks unsettled trades and resolves any whose underlying truth has landed.
Both operations are idempotent — re-running on the same (signal, day) does
not double-record because the row IDs are deterministic from the natural key.

The CLI wraps both passes in :func:`kq.flows.paper_trade.run_once`.
"""

from __future__ import annotations

import hashlib
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Literal, cast

from kq.execution.fees import fee_per_contract
from kq.execution.kelly import fractional_kelly_stake

Side = Literal["BUY_YES", "BUY_NO"]

# Defaults mirror the backtest engine so paper and backtest agree decision-for-decision.
DEFAULT_MIN_EDGE_PCT: Final = 4.0
DEFAULT_KELLY_FRACTION: Final = 0.15
DEFAULT_MAX_STAKE_USD: Final = 50.0


@dataclass(frozen=True, slots=True)
class PaperTradeIntent:
    """An evaluated, sized intent to record in the paper book.

    All prices are in dollars (0..1); ``fee_usd`` and ``edge_bps`` are also
    populated so the row can be written to the ``signal`` table without
    re-deriving anything.

    ``signal_id`` is a content hash of (model_name, ticker, as_of_date) so
    submitting the same intent twice on the same day is a no-op insert.
    """

    signal_id: str
    as_of: datetime
    ticker: str
    side: Side
    limit_price: float  # what we'd pay per contract, in dollars
    qty: int
    fee_usd: float
    model_prob_yes: float  # always the YES-side probability, regardless of side
    market_yes_bid: float
    market_yes_ask: float
    edge_bps: int
    model_name: str

    @property
    def stake_usd(self) -> float:
        """Notional capital at risk on this trade, excluding fees."""
        return round(self.limit_price * self.qty, 4)


def make_signal_id(*, model_name: str, ticker: str, as_of: datetime) -> str:
    """Deterministic, idempotent signal id keyed on (model, ticker, as_of-day).

    Re-running the submit pass on the same UTC day with the same model + ticker
    must produce the same id so the DB upsert is a no-op. Adopting day-level
    granularity (not minute-level) means we don't double-record if cron fires
    twice in the same hour for the same forecast row.
    """
    key = f"{model_name}|{ticker}|{as_of.astimezone(UTC).date().isoformat()}"
    digest = hashlib.sha1(key.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"sig-{digest[:16]}"


def make_trade_id(signal_id: str) -> str:
    """1:1 paper trade id derived from a signal id (one trade per signal in v1)."""
    return (
        signal_id.replace("sig-", "paper-", 1)
        if signal_id.startswith("sig-")
        else (f"paper-{signal_id}")
    )


def evaluate_market(
    *,
    model_prob_yes: float,
    yes_bid: float | None,
    yes_ask: float | None,
    bankroll_usd: float,
    as_of: datetime,
    ticker: str,
    model_name: str,
    min_edge_pct: float = DEFAULT_MIN_EDGE_PCT,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    max_stake_usd: float = DEFAULT_MAX_STAKE_USD,
) -> PaperTradeIntent | None:
    """Decide whether to record a paper trade for one market.

    Returns ``None`` when no edge clears the post-fee threshold or when the
    sized stake collapses to zero contracts. Otherwise returns the intent —
    fully sized, ready to write.

    Decision rule (identical to ``kq.backtest.engine._maybe_trade``):
    1. If model_prob > yes_ask → BUY_YES at the ask.
    2. Elif model_prob < yes_bid → BUY_NO at (1 - yes_bid).
    3. Else: model is inside the spread, no trade.
    Then: edge_after_fee_pct must be >= min_edge_pct, and the Kelly stake
    must round to >= 1 contract.
    """
    if not 0.0 < model_prob_yes < 1.0:
        raise ValueError(f"model_prob_yes must be in (0, 1), got {model_prob_yes}")
    # One guard for "untradable quote": missing side, out-of-range price, or crossed book.
    quote_unusable = (
        yes_bid is None
        or yes_ask is None
        or not 0.0 < yes_bid < 1.0
        or not 0.0 < yes_ask < 1.0
        or yes_bid > yes_ask
    )
    if quote_unusable:
        return None
    # Past quote_unusable both sides are guaranteed non-None; ``cast`` is
    # the type-narrow without the bandit-flagged ``assert`` (which gets
    # stripped under ``python -O``).
    yes_bid = cast(float, yes_bid)
    yes_ask = cast(float, yes_ask)

    if model_prob_yes > yes_ask:
        side: Side = "BUY_YES"
        fill_price = yes_ask
        prob_at_fill = model_prob_yes
    elif model_prob_yes < yes_bid:
        side = "BUY_NO"
        fill_price = 1.0 - yes_bid
        prob_at_fill = 1.0 - model_prob_yes
    else:
        return None  # inside spread

    edge = prob_at_fill - fill_price
    fee_per = fee_per_contract(fill_price, side="taker")
    edge_after_fee_pct = (edge - fee_per) * 100.0
    if edge_after_fee_pct < min_edge_pct:
        return None

    stake_usd = fractional_kelly_stake(
        prob=prob_at_fill,
        price=fill_price,
        bankroll_usd=bankroll_usd,
        fraction=kelly_fraction,
        max_stake_usd=max_stake_usd,
    )
    if stake_usd <= 0:
        return None
    qty = max(1, math.floor(stake_usd / fill_price))
    fee_total = round(fee_per * qty, 4)

    return PaperTradeIntent(
        signal_id=make_signal_id(model_name=model_name, ticker=ticker, as_of=as_of),
        as_of=as_of,
        ticker=ticker,
        side=side,
        limit_price=fill_price,
        qty=qty,
        fee_usd=fee_total,
        model_prob_yes=model_prob_yes,
        market_yes_bid=yes_bid,
        market_yes_ask=yes_ask,
        edge_bps=round(edge * 10_000.0),
        model_name=model_name,
    )


def settlement_pnl(
    *,
    side: Side,
    fill_price: float,
    qty: int,
    fee_usd: float,
    outcome_yes: bool,
) -> float:
    """Realized P&L in dollars for a settled paper trade.

    Mirrors ``kq.backtest.engine._maybe_trade`` exactly. For a BUY_YES, the
    contract pays $1 if the outcome is YES else $0. For a BUY_NO, the
    contract pays $1 if the outcome is NO. Fees are subtracted regardless of
    outcome (Kalshi keeps the taker fee on every fill).
    """
    won = outcome_yes if side == "BUY_YES" else not outcome_yes
    payout_per_contract = 1.0 if won else 0.0
    return round(qty * (payout_per_contract - fill_price) - fee_usd, 4)


@dataclass
class PaperExecutor:
    """Stateful façade around evaluate_market + settlement_pnl.

    Holds the bankroll snapshot used to size new trades. Ingest one
    (model_prob, market_quote) at a time via :meth:`evaluate`, and call
    :func:`kq.storage.repositories.paper_trades.insert_paper_trade_with_signal`
    on each non-None result.

    The executor cannot place a real-money order — it has no client.
    """

    bankroll_usd: float = 1_000.0
    model_name: str = "weather_router_v1"
    min_edge_pct: float = DEFAULT_MIN_EDGE_PCT
    kelly_fraction: float = DEFAULT_KELLY_FRACTION
    max_stake_usd: float = DEFAULT_MAX_STAKE_USD

    def evaluate(
        self,
        *,
        model_prob_yes: float,
        yes_bid: float | None,
        yes_ask: float | None,
        ticker: str,
        as_of: datetime,
    ) -> PaperTradeIntent | None:
        """Single-market evaluation; returns the sized intent or ``None``."""
        return evaluate_market(
            model_prob_yes=model_prob_yes,
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            bankroll_usd=self.bankroll_usd,
            as_of=as_of,
            ticker=ticker,
            model_name=self.model_name,
            min_edge_pct=self.min_edge_pct,
            kelly_fraction=self.kelly_fraction,
            max_stake_usd=self.max_stake_usd,
        )

    @staticmethod
    def fresh_trade_id() -> str:
        """For tests that need a non-derived trade id (rare)."""
        return f"paper-{uuid.uuid4().hex[:16]}"
