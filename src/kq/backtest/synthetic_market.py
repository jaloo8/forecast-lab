"""Naive-market price model.

We don't have a historical archive of Kalshi orderbook prices for weather
markets (production access only; demo doesn't seed weather). The honest
proxy: assume the market price equals what an unsophisticated trader would
infer from the *raw* deterministic forecast alone, treated as a point
estimate with a fixed climatological standard deviation.

This is a CONSERVATIVE stand-in for real Kalshi pricing because:
- Real market makers use sophisticated models too, so the *real* mispricing
  is generally smaller than this baseline implies.
- Therefore P&L from backtesting against this baseline is an UPPER BOUND on
  what we'd actually capture on Kalshi.
- The model's *Brier improvement* over this baseline is what's invariant
  and what we should focus on as the headline metric.

The naive market spread mirrors Kalshi's actual fee structure indirectly:
we add a wider bid-ask than the implied probability so the simulator must
overcome a realistic round-trip cost.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

from kq.backtest.brackets import Bracket

NAIVE_RAW_SIGMA_F = 3.5  # climatological residual std; ~0.18 raw Brier per Pass 1 §1b
PROB_CLIP_LOW = 0.01
PROB_CLIP_HIGH = 0.99
DEFAULT_HALF_SPREAD = 0.02  # +/-2c from mid is a reasonable Kalshi weather-market half-spread


@dataclass(frozen=True, slots=True)
class MarketQuote:
    """Bid/ask in dollars (0..1)."""

    bid: float
    ask: float

    @property
    def mid(self) -> float:
        return 0.5 * (self.bid + self.ask)


def naive_market_quote(
    forecast_mean_f: float,
    bracket: Bracket,
    *,
    raw_sigma_f: float = NAIVE_RAW_SIGMA_F,
    half_spread: float = DEFAULT_HALF_SPREAD,
) -> MarketQuote:
    """Return ``MarketQuote`` for a YES contract on ``bracket``.

    The mid price is the survival function of N(forecast, raw_sigma); bid and
    ask are mid -/+ half_spread, clipped to [0.01, 0.99].
    """
    if raw_sigma_f <= 0:
        raise ValueError(f"raw_sigma_f must be positive, got {raw_sigma_f}")
    if not 0.0 < half_spread < 0.5:
        raise ValueError(f"half_spread must be in (0, 0.5), got {half_spread}")
    mid = float(stats.norm.sf(bracket.threshold_f, loc=forecast_mean_f, scale=raw_sigma_f))
    mid = float(np.clip(mid, PROB_CLIP_LOW + half_spread, PROB_CLIP_HIGH - half_spread))
    return MarketQuote(
        bid=float(np.clip(mid - half_spread, PROB_CLIP_LOW, PROB_CLIP_HIGH)),
        ask=float(np.clip(mid + half_spread, PROB_CLIP_LOW, PROB_CLIP_HIGH)),
    )
