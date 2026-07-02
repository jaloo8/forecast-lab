"""Non-homogeneous Gaussian Regression (NGR / EMOS) bias-correction model.

Full NGR form (used when ensemble variance is informative):

    T_obs ~ N(mu = a + b * ens_mean, sigma^2 = c + d * ens_var)

Degenerate form (deterministic input — what we have today via the Open-Meteo
Historical Forecast API):

    T_obs ~ N(mu = a + b * forecast, sigma^2)

Both are fit by minimizing the negative log-likelihood under a Gaussian
predictive distribution. The full form falls back to the degenerate form
automatically when ``ens_vars`` is None or all-zero.

Calibrated probabilities for Kalshi-style bracket questions
(``P(T > threshold)``) are computed directly from the predictive Gaussian's
CDF and clipped to ``[0.01, 0.99]`` per CLAUDE.md §6.

References:
    Gneiting, Raftery, Westveld, Goldman (2005) — original NGR paper.
    Wilks (2018) — Statistical Methods in the Atmospheric Sciences, ch.8.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Final

import numpy as np
from scipy import optimize, stats

PROB_CLIP_LOW: Final = 0.01
PROB_CLIP_HIGH: Final = 0.99
MIN_VARIANCE: Final = 1e-6  # numerical floor; never fit a zero-variance Gaussian
# Bound on the log-variance parameters of the full-form MLE. exp(50) is
# ~5e21 °F² — far beyond any physical temperature variance — so anything
# past this is the optimizer wandering, not a fit. Guards both the
# objective (no OverflowError mid-optimization) and the accepted result.
MAX_LOG_VARIANCE: Final = 50.0


@dataclass(frozen=True)
class NGRParameters:
    """Fitted parameters. ``d`` is 0.0 in the degenerate (deterministic) case."""

    a: float
    b: float
    c: float
    d: float

    @property
    def is_degenerate(self) -> bool:
        return self.d == 0.0


@dataclass
class WeatherNGRModel:
    """NGR / EMOS bias-correction model for one (station, lead-time) pair."""

    params: NGRParameters | None = None
    fit_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_fit(self) -> bool:
        return self.params is not None

    def fit(
        self,
        ens_means: np.ndarray,
        observed: np.ndarray,
        *,
        ens_vars: np.ndarray | None = None,
    ) -> NGRParameters:
        """Fit NGR parameters by minimizing negative log-likelihood.

        ``ens_vars`` is optional. When None or all values <= MIN_VARIANCE,
        the model fits the degenerate form (constant variance).
        """
        ens_means = np.asarray(ens_means, dtype=float)
        observed = np.asarray(observed, dtype=float)
        if ens_means.shape != observed.shape:
            raise ValueError(
                f"shape mismatch: ens_means {ens_means.shape} vs observed {observed.shape}"
            )
        if ens_means.size < 2:
            raise ValueError(f"need at least 2 samples to fit, got {ens_means.size}")

        use_full_form = ens_vars is not None and bool(np.any(np.asarray(ens_vars) > MIN_VARIANCE))
        full_fit_info: dict[str, Any] = {}
        if use_full_form and ens_vars is not None:  # second clause is type-narrowing
            params, full_fit_info = self._fit_full(
                ens_means, np.asarray(ens_vars, dtype=float), observed
            )
        else:
            params = self._fit_degenerate(ens_means, observed)

        self.params = params
        self.fit_metadata = {
            "n_samples": int(ens_means.size),
            # `form` reflects the ACCEPTED parameters: a full-form attempt
            # that fell back to the degenerate seed reports "degenerate"
            # (plus the fallback flags from full_fit_info), never "full".
            "form": "full" if params.d != 0.0 else "degenerate",
            "obs_mean": float(observed.mean()),
            "obs_std": float(observed.std(ddof=1)) if observed.size > 1 else 0.0,
            "raw_residual_std": float((observed - ens_means).std(ddof=1))
            if observed.size > 1
            else 0.0,
            **full_fit_info,
        }
        return params

    @staticmethod
    def _fit_degenerate(ens_means: np.ndarray, observed: np.ndarray) -> NGRParameters:
        """Closed-form OLS for ``T_obs = a + b*ens_mean + epsilon`` then sigma^2 = MSE."""
        n = ens_means.size
        x_mean = ens_means.mean()
        y_mean = observed.mean()
        cov = np.sum((ens_means - x_mean) * (observed - y_mean))
        var_x = np.sum((ens_means - x_mean) ** 2)
        # If forecast values are constant, no slope is identifiable; set b=1 and let `a` absorb.
        b = float(cov / var_x) if var_x > MIN_VARIANCE else 1.0
        a = float(y_mean - b * x_mean)
        residuals = observed - (a + b * ens_means)
        # Sample variance with bias correction (n-2 for two fit params).
        if n > 2:
            sigma2 = float(np.sum(residuals**2) / (n - 2))
        else:
            sigma2 = float(np.sum(residuals**2) / max(n - 1, 1))
        sigma2 = max(sigma2, MIN_VARIANCE)
        return NGRParameters(a=a, b=b, c=sigma2, d=0.0)

    @staticmethod
    def _fit_full(
        ens_means: np.ndarray,
        ens_vars: np.ndarray,
        observed: np.ndarray,
    ) -> tuple[NGRParameters, dict[str, Any]]:
        """MLE fit of ``T ~ N(a + b*mean, c + d*var)`` via scipy.optimize.

        2026-07-01 audit (Tier 2): the old implementation accepted whatever
        Nelder-Mead returned — no ``result.success`` check, no
        worse-than-seed fallback, and an unbounded ``exp`` that could
        overflow mid-optimization. Mirrors the skew sibling now: on
        optimizer failure, non-finite/out-of-bound parameters, or a fit
        whose NLL is worse than the degenerate seed's, fall back to the
        degenerate parameters (strict no-worse property). Returns
        ``(params, info)`` where ``info`` carries the fallback telemetry
        merged into ``fit_metadata``.
        """

        def nll_at(a: float, b: float, sigma2: np.ndarray) -> float:
            resid = observed - (a + b * ens_means)
            s2 = np.maximum(sigma2, MIN_VARIANCE)
            return float(0.5 * np.sum(resid**2 / s2 + np.log(s2)))

        def neg_log_likelihood(theta: np.ndarray) -> float:
            a, b, log_c, log_d = theta
            if not np.all(np.isfinite(theta)):
                return float("inf")
            if log_c > MAX_LOG_VARIANCE or log_d > MAX_LOG_VARIANCE:
                # Bounded exp: beyond this the variance is unphysical and
                # math.exp would eventually raise OverflowError.
                return float("inf")
            sigma2 = math.exp(log_c) + math.exp(log_d) * ens_vars
            value = nll_at(float(a), float(b), sigma2)
            return value if math.isfinite(value) else float("inf")

        # Warm-start from the degenerate solution, then let scipy refine.
        seed = WeatherNGRModel._fit_degenerate(ens_means, observed)
        seed_nll = nll_at(seed.a, seed.b, np.full_like(ens_vars, max(seed.c, MIN_VARIANCE)))
        x0 = np.array([seed.a, seed.b, math.log(max(seed.c, MIN_VARIANCE)), math.log(0.1)])
        result = optimize.minimize(neg_log_likelihood, x0, method="Nelder-Mead")

        a, b, log_c, log_d = (float(v) for v in result.x)
        params_ok = (
            bool(result.success)
            and all(math.isfinite(v) for v in (a, b, log_c, log_d))
            and log_c <= MAX_LOG_VARIANCE
            and log_d <= MAX_LOG_VARIANCE
        )
        fitted_nll = (
            nll_at(a, b, math.exp(log_c) + math.exp(log_d) * ens_vars)
            if params_ok
            else float("inf")
        )
        info: dict[str, Any] = {"optimizer_success": bool(result.success)}
        if not params_ok or fitted_nll > seed_nll:
            info["full_fit_fallback_to_degenerate"] = True
            return seed, info
        info["full_fit_fallback_to_degenerate"] = False
        return NGRParameters(a=a, b=b, c=math.exp(log_c), d=math.exp(log_d)), info

    def predict_distribution(
        self,
        ens_mean: float | np.ndarray,
        *,
        ens_var: float | np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return ``(mu, sigma)`` for the calibrated forecast distribution(s)."""
        if self.params is None:
            raise RuntimeError("model not fit; call .fit(...) first")
        p = self.params
        mu = p.a + p.b * np.asarray(ens_mean, dtype=float)
        if p.d == 0.0 or ens_var is None:
            sigma2 = np.full_like(mu, p.c)
        else:
            sigma2 = p.c + p.d * np.asarray(ens_var, dtype=float)
        sigma2 = np.maximum(sigma2, MIN_VARIANCE)
        return mu, np.sqrt(sigma2)

    def predict_proba(
        self,
        ens_mean: float | np.ndarray,
        threshold: float,
        *,
        ens_var: float | np.ndarray | None = None,
    ) -> np.ndarray:
        """``P(T > threshold)``, clipped to ``[0.01, 0.99]`` per coding standards."""
        mu, sigma = self.predict_distribution(ens_mean, ens_var=ens_var)
        # P(T > threshold) = 1 - CDF(threshold; mu, sigma) = SF(threshold; mu, sigma)
        prob = stats.norm.sf(threshold, loc=mu, scale=sigma)
        clipped: np.ndarray = np.clip(prob, PROB_CLIP_LOW, PROB_CLIP_HIGH)
        return clipped

    def brier_score(
        self,
        ens_means: np.ndarray,
        observed: np.ndarray,
        thresholds: np.ndarray,
        *,
        ens_vars: np.ndarray | None = None,
    ) -> float:
        """Mean Brier across (sample, threshold) pairs.

        For each ``(forecast_i, threshold_j)`` evaluates ``(P_ij - 1{obs_i > t_j})^2``.
        """
        ens_means = np.asarray(ens_means, dtype=float)
        observed = np.asarray(observed, dtype=float)
        thresholds = np.asarray(thresholds, dtype=float)
        if ens_means.shape != observed.shape:
            raise ValueError("ens_means and observed must have the same shape")
        if ens_means.size == 0:
            raise ValueError("empty arrays")
        # Vectorize across (samples x thresholds).
        mu, sigma = self.predict_distribution(ens_means, ens_var=ens_vars)
        probs = stats.norm.sf(thresholds[None, :], loc=mu[:, None], scale=sigma[:, None])
        probs = np.clip(probs, PROB_CLIP_LOW, PROB_CLIP_HIGH)
        outcomes = (observed[:, None] > thresholds[None, :]).astype(float)
        return float(np.mean((probs - outcomes) ** 2))


def raw_brier_score(
    ens_means: np.ndarray,
    observed: np.ndarray,
    thresholds: np.ndarray,
    *,
    raw_sigma: float,
) -> float:
    """Brier of the *raw* forecast (no bias correction) for benchmark comparison.

    Treats the forecast as ``T ~ N(forecast, raw_sigma^2)`` — a common
    eyeballed baseline. ``raw_sigma`` is the residual std of (observed -
    forecast) on the same data; pass it from `WeatherNGRModel.fit_metadata`.
    """
    ens_means = np.asarray(ens_means, dtype=float)
    observed = np.asarray(observed, dtype=float)
    thresholds = np.asarray(thresholds, dtype=float)
    sigma = max(raw_sigma, math.sqrt(MIN_VARIANCE))
    probs = stats.norm.sf(thresholds[None, :], loc=ens_means[:, None], scale=sigma)
    probs = np.clip(probs, PROB_CLIP_LOW, PROB_CLIP_HIGH)
    outcomes = (observed[:, None] > thresholds[None, :]).astype(float)
    return float(np.mean((probs - outcomes) ** 2))
