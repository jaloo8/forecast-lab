"""Skew-normal NGR (extended EMOS) — replaces NGR's Gaussian likelihood with
the skew-normal distribution.

Addresses bounded-below + heavy-upper-tail Tmax distributions that NGR's
symmetric Gaussian can't capture: KMIA's sea-breeze ceiling, KDEN's chinook
upper-tail outliers, KMDW's continental cold-air-mass arrivals. The
post-#14 verdict diagnostic showed wing-band Brier collapse at every
continental station — the structural reason traces directly to the
Gaussian assumption.

Parameterization (degenerate form, deterministic input — what we have today):

    T_obs ~ SN(xi = a + b * forecast, omega = sqrt(c), alpha)

Where ``xi`` is the LOCATION (not the mean), ``omega`` is the SCALE
(not the std), and ``alpha`` is the shape parameter. The mean of the
predictive distribution is:

    mean = xi + omega * delta * sqrt(2/pi),  delta = alpha / sqrt(1 + alpha^2)

A positive alpha makes the distribution right-skewed (heavy upper tail);
negative alpha makes it left-skewed (heavy lower tail). alpha = 0 reduces
exactly to Gaussian, so the model can degrade gracefully when no skewness
is present in the data.

The MLE is fit via scipy.optimize, warm-starting from a Gaussian NGR fit
(alpha = 0). If the optimizer doesn't converge or produces an alpha outside
[-ALPHA_BOUND, +ALPHA_BOUND], we fall back to the Gaussian seed — that
keeps the model strictly no-worse than NGR, preserving the safety property
that adding this option can only improve Brier or leave it unchanged.

References:
    Allen, Evans, Buchanan, Kwasniok (2023, MWR) — operational skew-normal
    EMOS on MOGREPS-UK; documents 8-15% upper-tail Brier improvement at
    +2-sigma thresholds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Final

import numpy as np
from scipy import optimize, stats

from kq.models.weather_ngr import WeatherNGRModel

PROB_CLIP_LOW: Final = 0.01
PROB_CLIP_HIGH: Final = 0.99
MIN_OMEGA2: Final = 1e-6  # numerical floor on scale^2
# |alpha| > 10 is numerically suspect — tail behavior gets weird and the
# optimizer is probably picking up noise rather than real skewness.
ALPHA_BOUND: Final = 10.0


@dataclass(frozen=True)
class SkewNormalParameters:
    """Fitted skew-normal NGR parameters (degenerate form).

    Note ``a`` and ``b`` parameterize the LOCATION ``xi``, not the mean.
    The predictive mean is ``a + b*forecast + sqrt(omega2) * delta * sqrt(2/pi)``
    where ``delta = alpha / sqrt(1 + alpha^2)``.
    """

    a: float
    b: float
    omega2: float
    alpha: float

    @property
    def is_gaussian(self) -> bool:
        """True when alpha is essentially zero (degrades to Gaussian NGR)."""
        return abs(self.alpha) < 1e-3


@dataclass
class WeatherSkewNGRModel:
    """Skew-normal NGR for one (station, lead-time) pair.

    Fall-through to Gaussian seed when MLE does not improve over alpha=0.
    """

    params: SkewNormalParameters | None = None
    fit_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_fit(self) -> bool:
        return self.params is not None

    def fit(  # noqa: PLR0915 — multi-start MLE has irreducible per-seed setup; splitting muddles the fall-back-to-Gaussian invariant
        self,
        ens_means: np.ndarray,
        observed: np.ndarray,
    ) -> SkewNormalParameters:
        """MLE fit by minimizing -log L under SN(a + b*x, sqrt(omega2), alpha)."""
        ens_means = np.asarray(ens_means, dtype=float)
        observed = np.asarray(observed, dtype=float)
        if ens_means.shape != observed.shape:
            raise ValueError(
                f"shape mismatch: ens_means {ens_means.shape} vs observed {observed.shape}"
            )
        if ens_means.size < 4:
            raise ValueError(
                f"need >= 4 samples to fit skew-normal NGR, got {ens_means.size}"
            )

        # Warm-start from Gaussian NGR (alpha=0 reduces SN to Gaussian).
        ngr_seed = WeatherNGRModel()
        ngr_seed.fit(ens_means, observed)
        seed = ngr_seed.params
        if seed is None:  # pragma: no cover — fit() always sets params or raises
            raise RuntimeError("Gaussian seed fit failed unexpectedly")
        gaussian_params = SkewNormalParameters(
            a=seed.a,
            b=seed.b,
            omega2=max(seed.c, MIN_OMEGA2),
            alpha=0.0,
        )
        gaussian_nll = self._neg_log_likelihood(
            np.array([seed.a, seed.b, math.log(max(seed.c, MIN_OMEGA2)), 0.0]),
            ens_means,
            observed,
        )

        # Multi-start to escape the Gaussian (alpha=0) local minimum.
        # Nelder-Mead's default simplex perturbs by ~5%, which is too small
        # to find a clearly-skewed mode when starting at alpha=0. We try
        # three alpha seeds and keep the best NLL — order-of-2-3x slower but
        # the per-fold compute cost is still negligible.
        #
        # For non-zero alpha starts, we adjust the intercept ``a`` to preserve
        # the conditional mean at the Gaussian seed's value. The Gaussian
        # seed's ``a`` parameterizes the conditional MEAN; skew-normal's
        # ``a`` parameterizes the LOCATION (xi). The mean of SN(xi, omega, alpha)
        # is ``xi + omega * delta * sqrt(2/pi)`` with ``delta = alpha/sqrt(1+alpha^2)``,
        # so we set ``xi = mean - mean_shift`` to keep the predictive mean
        # invariant at start. Without this correction, the alpha=2 start sits
        # on a wrong-mean ridge and the optimizer drifts back to alpha=0.
        log_omega2_seed = math.log(max(seed.c, MIN_OMEGA2))
        omega_seed = math.sqrt(max(seed.c, MIN_OMEGA2))
        alpha_starts = [0.0, 2.0, -2.0]
        best_result: optimize.OptimizeResult | None = None
        best_nll = float("inf")
        for alpha0 in alpha_starts:
            if alpha0 != 0.0:
                delta0 = alpha0 / math.sqrt(1 + alpha0 * alpha0)
                mean_shift = omega_seed * delta0 * math.sqrt(2 / math.pi)
                a0 = seed.a - mean_shift
            else:
                a0 = seed.a
            x0 = np.array([a0, seed.b, log_omega2_seed, alpha0])
            try:
                result = optimize.minimize(
                    self._neg_log_likelihood,
                    x0,
                    args=(ens_means, observed),
                    method="Nelder-Mead",
                    options={"maxiter": 1000, "xatol": 1e-5, "fatol": 1e-5},
                )
            except Exception:  # pragma: no cover — defensive against scipy edge cases
                continue
            if result.success and result.fun < best_nll:
                best_result = result
                best_nll = float(result.fun)

        if best_result is not None:
            optimizer_success = True
            fitted_nll = best_nll
            fitted_alpha = float(best_result.x[3])
            result = best_result
        else:
            optimizer_success = False
            fitted_nll = float("inf")
            fitted_alpha = 0.0

        # Fall back to Gaussian seed if:
        #   - optimizer didn't converge,
        #   - fit produced a wild alpha,
        #   - or the fit is *worse* than Gaussian (numerical safety net).
        if (
            not optimizer_success
            or abs(fitted_alpha) > ALPHA_BOUND
            or fitted_nll > gaussian_nll
        ):
            params = gaussian_params
            fallback_used = True
        else:
            a, b, log_omega2, alpha = result.x
            params = SkewNormalParameters(
                a=float(a),
                b=float(b),
                omega2=max(math.exp(log_omega2), MIN_OMEGA2),
                alpha=float(alpha),
            )
            fallback_used = False

        self.params = params
        # Engine reads `raw_residual_std` from fit_metadata to set the
        # naive market sigma. Compute it the same way WeatherNGRModel does
        # so a SkewNGR can drop into the engine without the engine knowing.
        raw_residual_std = (
            float((observed - ens_means).std(ddof=1)) if observed.size > 1 else 0.0
        )
        self.fit_metadata = {
            "n_samples": int(ens_means.size),
            "form": "skew_normal",
            "fitted_alpha": params.alpha,
            "optimizer_success": optimizer_success,
            "fallback_to_gaussian": fallback_used,
            "raw_residual_std": raw_residual_std,
        }
        return params

    @staticmethod
    def _neg_log_likelihood(
        theta: np.ndarray,
        ens_means: np.ndarray,
        observed: np.ndarray,
    ) -> float:
        """Negative log-likelihood under SN(a + b*x, sqrt(exp(log_omega2)), alpha)."""
        a, b, log_omega2, alpha = theta
        omega = math.sqrt(math.exp(log_omega2))
        xi = a + b * ens_means
        log_pdf = stats.skewnorm.logpdf(observed, alpha, loc=xi, scale=omega)
        if not np.all(np.isfinite(log_pdf)):
            return float("inf")
        return float(-np.sum(log_pdf))

    def predict_distribution(
        self,
        ens_mean: float | np.ndarray,
        *,
        ens_var: float | np.ndarray | None = None,  # unused; signature parity with NGR
    ) -> tuple[np.ndarray, np.ndarray, float]:
        """Return ``(xi, omega, alpha)`` for the calibrated skew-normal forecast."""
        if self.params is None:
            raise RuntimeError("model not fit; call .fit(...) first")
        p = self.params
        xi = p.a + p.b * np.asarray(ens_mean, dtype=float)
        omega = np.full_like(xi, math.sqrt(max(p.omega2, MIN_OMEGA2)))
        return xi, omega, p.alpha

    def predict_proba(
        self,
        ens_mean: float | np.ndarray,
        threshold: float,
        *,
        ens_var: float | np.ndarray | None = None,  # unused; signature parity with NGR
    ) -> np.ndarray:
        """``P(T > threshold)``, clipped to ``[0.01, 0.99]`` per coding standards."""
        xi, omega, alpha = self.predict_distribution(ens_mean)
        prob = stats.skewnorm.sf(threshold, alpha, loc=xi, scale=omega)
        clipped: np.ndarray = np.clip(prob, PROB_CLIP_LOW, PROB_CLIP_HIGH)
        return clipped
