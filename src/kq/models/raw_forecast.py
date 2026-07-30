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
    """Naive baseline: T ~ N(forecast + bias_f, raw_sigma_f^2).

    ``bias_f`` is a per-station additive correction to the ensemble mean,
    measured from history by :mod:`kq.models.station_calibration`. It defaults
    to 0.0 so every existing caller keeps the old behaviour.

    WHY IT EXISTS (measured 2026-07-29 on 14,599 true lead-1 station-days,
    2 years, 20 stations): the ensemble mean is systematically COLD. Pooled
    bias is **+1.78F** and every station but KLAX is positive (KATL +3.00,
    KPHX +2.70, KPHL +2.54). Kalshi brackets are 2F wide, so an uncorrected
    1.8F offset displaces nearly a whole bracket of probability mass. The
    realised spread is also tighter than assumed: 2.55F pooled against the
    3.5F fallback this model was usually constructed with.

    Applying both corrections improves bracket Brier by 8.9% overall and on
    19 of 20 stations (KPHX +21.8%, KLAS +18.8%, KMIA +16.2%), validated
    causally with an expanding window over 153,588 bracket predictions --
    see `kq calibrate-stations`.
    """

    raw_sigma_f: float
    bias_f: float = 0.0

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
        mu = np.asarray(ens_mean, dtype=float) + self.bias_f
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
