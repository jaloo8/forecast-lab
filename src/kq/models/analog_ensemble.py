"""Analog-ensemble weather model (Hamill & Whitaker 2006 style, simplified).

Non-parametric postprocessing: given today's deterministic forecast, find the
``k`` most similar *past* forecasts in the training pool and use the empirical
fraction of their verified observations exceeding the bracket threshold as
``P(Tmax > threshold)``. The analogs' observed highs *are* the predictive
distribution -- no Gaussian/skew-normal assumption.

Same ``fit`` / ``predict_proba`` interface as ``WeatherNGRModel`` and
``RawForecastModel`` so the backtest engine + router dispatch it
interchangeably. Fit **per fold on the fold's training rows** (PIT-correct:
analogs only ever come from the past).

The hope (Renaissance artifact): at KAUS/KMDW/KDEN the parametric NGR misfits
the true Tmax shape, so a distribution-free analog might recover ~2-5 % CRPS.

**Empirical verdict (2026-05-25, off-by-default): it does NOT — this simple
analog is WORSE than NGR at every station.** Brier-vs-NDFD per station, NGR vs
``weather_analog_v1`` on the ~1yr backfill: KAUS -8.9 % → -110 %, KDEN -25 % →
-102 %, KJFK -6.7 % → -79 %, KLAX +39 % → +12 %, KMDW -43 % → -165 %, KMIA
+2.4 % → -62 %. At lead-1 with a *single* predictor (``ens_mean``) and only
~60-300 training rows per fold, the k-NN exceedance fraction is coarse (steps
of 1/k) and badly mis-calibrated; NGR's parametric smoothness dominates. The
Hamill-Whitaker gain needs *richer* analog predictors (multiple fields,
seasonal window, a far larger pool) than v1 has.

So this ships as an **off-by-default, runnable-for-A/B** mechanism (strategy
``weather_analog_v1``), **not** a router leg and **not** in the active config --
the same disposition as the climatology blend (ROADMAP item #5). Kept so the
richer-predictor version has a foundation + the negative result is recorded.

CPU-only, numpy-only -- **no new dependencies.**
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

import numpy as np

# Default analog count. Our rolling-origin training pools run ~60-300 rows;
# k=30 keeps the estimate local (a real "similar days" subset) without going
# so small that the fraction is dominated by binomial noise.
DEFAULT_K: Final = 30

PROB_CLIP_LOW: Final = 0.01
PROB_CLIP_HIGH: Final = 0.99


@dataclass
class AnalogEnsembleModel:
    """K-nearest-analog predictive probability for Tmax brackets.

    ``k`` is the analog count; ``kernel`` controls how the k analogs are
    weighted when forming the exceedance fraction:

    - ``"uniform"`` (default): each of the k nearest analogs counts equally.
    - ``"gaussian"``: weight ``exp(-0.5 (d/h)^2)`` with bandwidth ``h`` = the
      median analog distance, so closer analogs count more. Smoother, less
      sensitive to the exact ``k``.
    """

    k: int = DEFAULT_K
    kernel: str = "uniform"
    # Fitted analog pool (set by ``fit``). Plain fields with None defaults so
    # the dataclass stays mutable like the other model classes.
    _forecasts: np.ndarray | None = field(default=None, repr=False)
    _observed: np.ndarray | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.k < 1:
            raise ValueError(f"k must be >= 1, got {self.k}")
        if self.kernel not in ("uniform", "gaussian"):
            raise ValueError(f"kernel must be 'uniform' or 'gaussian', got {self.kernel!r}")

    @property
    def is_fit(self) -> bool:
        return self._forecasts is not None and self._forecasts.size > 0

    def fit(
        self,
        ens_means: np.ndarray,
        observed: np.ndarray,
        *,
        ens_vars: np.ndarray | None = None,
    ) -> AnalogEnsembleModel:
        """Store the (forecast, observed) analog pool. ``ens_vars`` ignored
        (the analog estimate is distribution-free). NaN pairs are dropped."""
        _ = ens_vars
        f = np.asarray(ens_means, dtype=float)
        o = np.asarray(observed, dtype=float)
        if f.shape != o.shape:
            raise ValueError(f"shape mismatch: ens_means {f.shape} vs observed {o.shape}")
        mask = ~(np.isnan(f) | np.isnan(o))
        self._forecasts = f[mask]
        self._observed = o[mask]
        if self._forecasts.size == 0:
            raise ValueError("no valid (forecast, observed) pairs to fit analogs on")
        return self

    def _proba_one(self, forecast: float, threshold: float) -> float:
        assert self._forecasts is not None and self._observed is not None
        dist = np.abs(self._forecasts - forecast)
        k = min(self.k, dist.size)
        # k nearest by forecast distance (argpartition is O(n), no full sort).
        nearest = np.argpartition(dist, k - 1)[:k]
        d = dist[nearest]
        exceed = (self._observed[nearest] > threshold).astype(float)
        if self.kernel == "gaussian":
            h = max(float(np.median(d)), 1e-6)
            w = np.exp(-0.5 * (d / h) ** 2)
            wsum = float(w.sum())
            p = float((w * exceed).sum() / wsum) if wsum > 0 else float(exceed.mean())
        else:
            p = float(exceed.mean())
        return float(np.clip(p, PROB_CLIP_LOW, PROB_CLIP_HIGH))

    def predict_proba(
        self,
        ens_mean: float | np.ndarray,
        threshold: float,
        *,
        ens_var: float | np.ndarray | None = None,
    ) -> np.ndarray:
        """``P(Tmax > threshold)`` per query forecast, clipped to [0.01, 0.99]."""
        _ = ens_var
        if not self.is_fit:
            raise RuntimeError("AnalogEnsembleModel.predict_proba called before fit()")
        arr = np.atleast_1d(np.asarray(ens_mean, dtype=float))
        return np.array([self._proba_one(float(f), threshold) for f in arr], dtype=float)


__all__ = ["DEFAULT_K", "AnalogEnsembleModel"]
