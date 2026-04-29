"""Raw-forecast probability model.

When a station's backtest shows the bias-corrected NGR doing WORSE than the
raw deterministic forecast (LAX/MIA in our PR H results), we want a model
that just emits the naive Gaussian probability around the raw forecast and
calls it a day. Same `.predict_proba(...)` interface as `WeatherNGRModel`
so the strategy router can dispatch interchangeably.

There's no fitting step — the only "parameter" is the raw_sigma (per-station
residual std) which the caller supplies. Typically this comes from the
training manifest's `fit_metadata.raw_residual_std`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from scipy import stats

PROB_CLIP_LOW: Final = 0.01
PROB_CLIP_HIGH: Final = 0.99
MIN_SIGMA: Final = 0.5  # numeric floor; sigma below this would cause overflow


@dataclass
class RawForecastModel:
    """Naive baseline: T ~ N(forecast, raw_sigma_f^2). No fitting required."""

    raw_sigma_f: float

    def __post_init__(self) -> None:
        if self.raw_sigma_f < MIN_SIGMA:
            raise ValueError(f"raw_sigma_f must be >= {MIN_SIGMA}, got {self.raw_sigma_f}")

    @property
    def is_fit(self) -> bool:
        return True  # always "fit" — no training step

    def predict_distribution(
        self,
        ens_mean: float | np.ndarray,
        *,
        ens_var: float | np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return ``(mu, sigma)`` for the naive predictive distribution."""
        _ = ens_var  # unused — raw model has fixed sigma
        mu = np.asarray(ens_mean, dtype=float)
        sigma = np.full_like(mu, self.raw_sigma_f)
        return mu, sigma

    def predict_proba(
        self,
        ens_mean: float | np.ndarray,
        threshold: float,
        *,
        ens_var: float | np.ndarray | None = None,
    ) -> np.ndarray:
        """``P(T > threshold)``, clipped to ``[0.01, 0.99]``."""
        mu, sigma = self.predict_distribution(ens_mean, ens_var=ens_var)
        prob = stats.norm.sf(threshold, loc=mu, scale=sigma)
        clipped: np.ndarray = np.clip(prob, PROB_CLIP_LOW, PROB_CLIP_HIGH)
        return clipped
