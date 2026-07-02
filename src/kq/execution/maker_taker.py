"""Maker-vs-taker order policy for Kalshi-style markets.

Per the [Pass 1 extension memo §2 + bonus](../../docs/research/PASS-1-EXTENSION-EMOS-EXECUTION.md):

> "Post passively when fair value is >= 2 ticks better than the marginal
> taker price post-fee, withdraw maker on every NWS METAR push.
> ~25 bps savings per round-trip."

The policy answers: given a model fair value and a market quote, should we
(a) cross the spread (taker), (b) post passively inside the spread (maker),
or (c) skip the trade because edge is below threshold?

**Decision tree:**

1. Compute ``edge_pre_fee = |model_prob - market_marginal_price|``.
2. If ``edge_pre_fee - taker_fee < min_skip_edge_pct/100``, return ``"skip"``.
3. If ``edge_pre_fee - taker_fee >= maker_min_edge_pct/100`` (default 2%
   = 2 ticks post taker-fee, the memo's rule (a) verbatim), return
   ``"maker"``. Posting maker captures the maker-fee discount AND a
   1-tick-better fill price if the resting order eventually crosses.
4. Otherwise return ``"taker"`` — cross the spread now.

Both thresholds are ABSOLUTE post-taker-fee edges, per the memo. With the
defaults (``maker 2 <= skip 4``) every trade that survives the skip gate
posts maker — exactly the memo's "free money" posture; ``"taker"`` is
reachable only when a caller configures ``maker_min_edge_pct`` above
``skip_min_edge_pct`` (a deliberately conservative maker gate). A previous
revision required ``skip + maker`` (6 pp) before posting maker, which
contradicted this contract and the memo it cites; fixed 2026-07-01.

**Backtest fill assumption:** When ``"maker"`` is chosen, the engine
simulates a fill at 1 tick inside the marginal taker price, with maker
fees applied. Default ``maker_fill_rate=1.0`` matches the memo's stated
"~25 bps savings" framing (assumes adverse-selection-aware withdrawal on
news pushes is effective). Users can lower the fill rate in
``BacktestConfig`` for sensitivity analysis.

**Live caveat:** real maker fills depend on order-book dynamics we don't
simulate. The 1.0 fill rate is optimistic; production deployment should
track realized maker fill rate and tune accordingly. The memo's "withdraw
maker on every NWS METAR push" guidance is for the live executor, not
backtest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from kq.execution.fees import fee_per_contract

# Kalshi tick size: 1 cent. Documented in the fee schedule.
KALSHI_TICK_USD: Final = 0.01

OrderType = Literal["maker", "taker", "skip"]


@dataclass(frozen=True, slots=True)
class MakerTakerPolicy:
    """Decide order type per (model_prob, market_quote) per the Pass 1 ext rule.

    Args:
        maker_min_edge_pct: minimum post-taker-fee edge in pp (absolute,
            not relative to the skip gate) to prefer maker. 2.0 = 2 ticks
            per the memo. At or above this, post maker.
        skip_min_edge_pct: minimum post-taker-fee edge in pp to trade at
            all. Mirrors the engine's existing ``cfg.min_edge_pct``.
        tick_size_usd: Kalshi tick size for the maker-side fill price
            improvement.
    """

    maker_min_edge_pct: float = 2.0
    skip_min_edge_pct: float = 4.0
    tick_size_usd: float = KALSHI_TICK_USD

    def decide(
        self,
        *,
        edge_pre_fee: float,
        fill_price_taker: float,
    ) -> OrderType:
        """Return ``"maker" | "taker" | "skip"`` for the given edge + price.

        ``edge_pre_fee`` is signed; we use absolute value internally.
        ``fill_price_taker`` is the price we'd pay if we crossed the spread.
        """
        edge_abs = abs(edge_pre_fee)
        taker_fee = fee_per_contract(fill_price_taker, side="taker")
        edge_after_taker_fee = edge_abs - taker_fee
        edge_after_taker_fee_pct = edge_after_taker_fee * 100.0

        if edge_after_taker_fee_pct < self.skip_min_edge_pct:
            return "skip"
        if edge_after_taker_fee_pct >= self.maker_min_edge_pct:
            # Pass-1 rule (a): fair value >= maker_min_edge_pct (2 ticks by
            # default) better than the marginal taker price AFTER fees →
            # post maker. The threshold is absolute, NOT stacked on top of
            # the skip gate.
            return "maker"
        return "taker"

    def maker_fill_price(self, fill_price_taker: float, *, side: str) -> float:
        """Maker fill price = 1 tick inside the marginal taker price.

        For ``BUY_YES`` (which would have crossed at ``ask``), maker posts
        at ``ask - 1 tick``. For ``BUY_NO`` (which crosses at ``1 - bid``),
        maker posts at ``(1 - bid) - 1 tick``. Both improve the fill by
        the tick size if the resting order is filled.
        """
        improved = fill_price_taker - self.tick_size_usd
        # Don't go below the prob clip — sanity floor matching the engine.
        return max(improved, 0.01)
