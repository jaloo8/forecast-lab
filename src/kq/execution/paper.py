"""Paper-trading executor.

By construction this module never imports from ``kq.execution.live`` and never
opens a network connection — it cannot place a real-money order. The executor
is a thin wrapper around two pure functions:

- :func:`evaluate_market` — given a model probability and a market quote,
  decide whether the post-fee edge clears the threshold and (if so) emit a
  :class:`PaperTradeIntent`. Shares the trade rule with
  ``kq.backtest.engine._maybe_trade`` so backtest and paper agree on the
  decision boundary; paper additionally understands prod one-sided-book
  sentinels and caps qty at the displayed quote size (2026-07-01 audit).
- :func:`settlement_pnl` — given a filled trade and the realized outcome,
  compute realized P&L. Mirrors the backtest's payout math.

The executor class composes these into a stateful pipeline: ``submit`` writes
a (signal, paper_trade) row pair via the paper-trade repository; ``settle``
walks unsettled trades and resolves any whose underlying truth has landed.
Both operations are idempotent — re-running for the same (model, market) does
not double-record because the row IDs are deterministic from the natural key.

The CLI wraps both passes in :func:`kq.flows.paper_trade.run_once`.
"""

from __future__ import annotations

import hashlib
import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

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

    ``signal_id`` is a content hash of (model_name, ticker) so submitting
    an intent for the same market twice is a no-op insert — see
    :func:`make_signal_id` for why the key carries no date component.

    ``market_yes_bid`` / ``market_yes_ask`` record the quote as displayed.
    On a one-sided book the absent side is recorded in Kalshi's own sentinel
    encoding: ``0.0`` for "no resting bid", ``1.0`` for "no resting ask".
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
    # Resolution semantics captured at submit time (PR-B) so settlement never
    # re-derives them from ticker text. None only for legacy demo payloads,
    # which settle under the historical greater-at-ticker-threshold rule.
    strike_type: str | None = None  # 'greater' | 'less' | 'between'
    floor_strike: float | None = None
    cap_strike: float | None = None

    @property
    def stake_usd(self) -> float:
        """Notional capital at risk on this trade, excluding fees."""
        return round(self.limit_price * self.qty, 4)


def make_signal_id(*, model_name: str, ticker: str) -> str:
    """Deterministic, idempotent signal id keyed on (model, ticker) — no date.

    A Kalshi ticker names exactly one contract with exactly one settlement:
    weather tickers embed the valid_date (``KXHIGHLAX-26JUN12-T81``) and NBA
    tickers embed the game date (``KXNBAGAME-26APR30BOSPHI-PHI``), so the
    ticker IS the natural idempotency key for one paper intent per market in
    both verticals. The previous key added the as_of UTC DATE to approximate
    that, which broke for NBA evening games spanning UTC midnight: cron
    ticks at 23:50 and 00:10 minted two ids for the same market — double
    Kelly exposure and double-counted settles. Re-evaluating the same market
    at any later time (same day or not) must be the same intent, so the date
    component is gone entirely.
    """
    key = f"{model_name}|{ticker}"
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
    yes_bid_size: float | None = None,
    yes_ask_size: float | None = None,
    min_edge_pct: float = DEFAULT_MIN_EDGE_PCT,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    max_stake_usd: float = DEFAULT_MAX_STAKE_USD,
    strike_type: str | None = None,
    floor_strike: float | None = None,
    cap_strike: float | None = None,
) -> PaperTradeIntent | None:
    """Decide whether to record a paper trade for one market.

    Returns ``None`` when no edge clears the post-fee threshold or when the
    sized stake collapses to zero contracts. Otherwise returns the intent —
    fully sized, ready to write.

    Decision rule (same trade rule as ``kq.backtest.engine._maybe_trade``):
    1. If model_prob > yes_ask → BUY_YES at the ask.
    2. Elif model_prob < yes_bid → BUY_NO at (1 - yes_bid).
    3. Else: model is inside the spread, no trade.
    Then: edge_after_fee_pct must be >= min_edge_pct, and the fee-aware
    Kelly stake must round to >= 1 contract.

    One-sided books (2026-07-01 audit): Kalshi prod serves a one-sided book
    with sentinel prices — bid ``0.0000`` means "no resting bid" and ask
    ``1.0000`` means "no resting ask" (recorded prod fixtures, 2026-06-11).
    A sentinel (or missing) side is treated as ABSENT, not as a bad quote:
    BUY_YES only needs a real ask and BUY_NO only needs a real bid, so the
    executable side of a one-sided book still trades. Prices outside [0, 1]
    or a crossed book remain data errors → no trade.

    Displayed liquidity: ``yes_bid_size`` / ``yes_ask_size`` are the quoted
    top-of-book sizes (``Market.yes_bid_size`` / ``.yes_ask_size``). ``qty``
    is capped at the displayed size of the side the trade hits; a displayed
    size below one whole contract is untradable. ``None`` means the payload
    carried no size (legacy/demo) — sizing is uncapped, the pre-size-aware
    behavior.
    """
    if not 0.0 < model_prob_yes < 1.0:
        raise ValueError(f"model_prob_yes must be in (0, 1), got {model_prob_yes}")
    # Garbage prices (outside [0, 1]) poison the whole quote — skip the market.
    if (yes_bid is not None and not 0.0 <= yes_bid <= 1.0) or (
        yes_ask is not None and not 0.0 <= yes_ask <= 1.0
    ):
        return None
    # Normalize sentinel/degenerate sides to "absent": bid at 0.0 and ask at
    # 1.0 are Kalshi's no-resting-order encodings (an ask of 0.0 / bid of 1.0
    # would be free money and is equally non-actionable).
    bid: float | None = yes_bid if yes_bid is not None and 0.0 < yes_bid < 1.0 else None
    ask: float | None = yes_ask if yes_ask is not None and 0.0 < yes_ask < 1.0 else None
    empty_book = bid is None and ask is None
    crossed_book = bid is not None and ask is not None and bid > ask
    if empty_book or crossed_book:
        return None

    if ask is not None and model_prob_yes > ask:
        side: Side = "BUY_YES"
        fill_price = ask
        prob_at_fill = model_prob_yes
        displayed_size = yes_ask_size
    elif bid is not None and model_prob_yes < bid:
        side = "BUY_NO"
        fill_price = 1.0 - bid
        prob_at_fill = 1.0 - model_prob_yes
        displayed_size = yes_bid_size
    else:
        return None  # inside spread, or the side we'd need is absent

    edge = prob_at_fill - fill_price
    fee_per = fee_per_contract(fill_price, side="taker")
    edge_after_fee_pct = (edge - fee_per) * 100.0
    if edge_after_fee_pct < min_edge_pct:
        return None

    # Fee-aware Kelly: the same taker fee the edge gate subtracts also
    # reduces the sizing edge, so gating and sizing agree (2026-07-01 audit).
    stake_usd = fractional_kelly_stake(
        prob=prob_at_fill,
        price=fill_price,
        bankroll_usd=bankroll_usd,
        fraction=kelly_fraction,
        max_stake_usd=max_stake_usd,
        fee_per_contract_usd=fee_per,
    )
    size_cap = math.floor(displayed_size) if displayed_size is not None else None
    if stake_usd <= 0 or (size_cap is not None and size_cap < 1):
        return None  # zero stake, or displayed liquidity below one contract
    qty = max(1, math.floor(stake_usd / fill_price))
    if size_cap is not None:
        qty = min(qty, size_cap)
    fee_total = round(fee_per * qty, 4)

    return PaperTradeIntent(
        signal_id=make_signal_id(model_name=model_name, ticker=ticker),
        as_of=as_of,
        ticker=ticker,
        side=side,
        limit_price=fill_price,
        qty=qty,
        fee_usd=fee_total,
        model_prob_yes=model_prob_yes,
        market_yes_bid=0.0 if bid is None else bid,
        market_yes_ask=1.0 if ask is None else ask,
        edge_bps=round(edge * 10_000.0),
        model_name=model_name,
        strike_type=strike_type,
        floor_strike=floor_strike,
        cap_strike=cap_strike,
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
        yes_bid_size: float | None = None,
        yes_ask_size: float | None = None,
        strike_type: str | None = None,
        floor_strike: float | None = None,
        cap_strike: float | None = None,
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
            yes_bid_size=yes_bid_size,
            yes_ask_size=yes_ask_size,
            min_edge_pct=self.min_edge_pct,
            kelly_fraction=self.kelly_fraction,
            max_stake_usd=self.max_stake_usd,
            strike_type=strike_type,
            floor_strike=floor_strike,
            cap_strike=cap_strike,
        )

    @staticmethod
    def fresh_trade_id() -> str:
        """For tests that need a non-derived trade id (rare)."""
        return f"paper-{uuid.uuid4().hex[:16]}"
