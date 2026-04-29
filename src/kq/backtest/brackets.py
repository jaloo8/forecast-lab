"""Synthetic Kalshi-style bracket generation for backtests.

Kalshi weather markets resolve as binary contracts at integer Fahrenheit
thresholds clustered around the most recent forecast (typically every 1F or
2F over a +/-7F window). We don't have a historical archive of *actual*
Kalshi brackets per station per day, so the backtest synthesizes a plausible
set centered on the forecast mean. This is intentionally conservative: real
Kalshi books may have tighter or wider spacing depending on the day, but the
edge our model produces over the *naive market* baseline (see
`synthetic_market.py`) is invariant to bracket choice as long as the
brackets straddle the predictive distribution.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Bracket:
    """A single Kalshi-style "high temp >= threshold" binary contract."""

    threshold_f: float

    @property
    def name(self) -> str:
        return f"high_ge_{int(self.threshold_f)}f"


def generate_brackets(
    forecast_mean_f: float,
    *,
    n_brackets: int = 7,
    spacing_f: float = 2.0,
) -> list[Bracket]:
    """Return ``n_brackets`` integer-F thresholds centered on ``forecast_mean_f``.

    With defaults, we get 7 brackets at +/-6F around the forecast in 2F steps,
    which approximates the typical Kalshi daily-high book.
    """
    if n_brackets < 1:
        raise ValueError(f"n_brackets must be >= 1, got {n_brackets}")
    if spacing_f <= 0:
        raise ValueError(f"spacing_f must be positive, got {spacing_f}")
    half = (n_brackets - 1) / 2.0
    base = round(forecast_mean_f)
    return [Bracket(threshold_f=base + (i - half) * spacing_f) for i in range(n_brackets)]
