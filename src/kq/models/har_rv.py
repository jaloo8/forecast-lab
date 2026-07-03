"""HAR-RV benchmark for Kalshi index brackets (Phase C).

The public-benchmark analog of NDFD for weather: Corsi's Heterogeneous
AutoRegressive model of Realized Volatility (HAR-RV, 2009) forecasting the
NEXT session's close-to-close return distribution, from which bracket
probabilities follow via the same strike discipline weather uses
(``kq.clients.kalshi.strikes.yes_prob`` with the index half-width).

Model, honestly stated:

* Realized-variance proxy: with free daily OHLC (no intraday data), the
  daily squared close-to-close log return ``r_t^2`` stands in for realized
  variance. It is an unbiased but NOISY RV proxy — true HAR-RV uses
  5-minute realized variance; expect attenuated coefficients and a weaker
  fit than the literature's intraday numbers.
* Regression (OLS on levels, numpy ``lstsq``, no new deps):
      RV_{t+1} = b0 + bd*RV_t + bw*mean(RV_{t-4..t}) + bm*mean(RV_{t-21..t})
  The three horizons (day/week/month) are the "heterogeneous market"
  cascade that lets the forecast respond to vol clustering fast while
  keeping a long-memory anchor.
* Predicted distribution: Normal(mu=0, sigma=sqrt(RV_hat)) on the log
  return. mu=0 because one-day index drift (~2-4 bp) is an order of
  magnitude below sigma (~60-120 bp) and estimating it on short windows
  adds pure noise. The Gaussian tail is thinner than reality — bracket
  probabilities in the far tails are understated; a Student-t upgrade is a
  v2 ticket, not a silent tweak.
* Guard rails: OLS on levels can predict a non-positive RV after a long
  quiet stretch; predictions are floored at the training RV's 10th
  percentile so sigma never collapses to zero (an overconfident
  ladder is worse than a slightly diffuse one).

The naive baseline (``constant_vol_sigma``) is the same Normal machinery
with sigma fixed at the training window's root-mean-square return — the
"no vol dynamics" null the backtest verdict is judged against.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

DAILY_LAG = 1
WEEKLY_WINDOW = 5
MONTHLY_WINDOW = 22

# Enough returns for ~2 months of regression rows past the monthly lag.
MIN_TRAIN_RETURNS = 60

# Floor quantile for predicted RV (see module docstring guard rails).
_RV_FLOOR_QUANTILE = 10.0


@dataclass(frozen=True, slots=True)
class HarRVFit:
    """Fitted HAR-RV coefficients + the training-derived prediction floor."""

    beta0: float
    beta_daily: float
    beta_weekly: float
    beta_monthly: float
    rv_floor: float
    n_regression_rows: int


def log_returns(closes: np.ndarray) -> np.ndarray:
    """Close-to-close log returns; requires strictly positive closes."""
    closes = np.asarray(closes, dtype=float)
    if closes.ndim != 1:
        raise ValueError(f"closes must be 1-D, got shape {closes.shape}")
    if len(closes) and float(np.min(closes)) <= 0.0:
        raise ValueError("closes must be strictly positive")
    if len(closes) < 2:
        return np.empty(0, dtype=float)
    return np.diff(np.log(closes))


def _har_features(rv: np.ndarray, t: int) -> tuple[float, float, float]:
    """(daily, weekly, monthly) RV averages ending at position ``t`` inclusive."""
    daily = float(rv[t])
    weekly = float(np.mean(rv[t - WEEKLY_WINDOW + 1 : t + 1]))
    monthly = float(np.mean(rv[t - MONTHLY_WINDOW + 1 : t + 1]))
    return daily, weekly, monthly


def fit_har_rv(returns: np.ndarray) -> HarRVFit:
    """OLS-fit HAR-RV on a chronological training window of log returns."""
    returns = np.asarray(returns, dtype=float)
    if returns.ndim != 1:
        raise ValueError(f"returns must be 1-D, got shape {returns.shape}")
    if len(returns) < MIN_TRAIN_RETURNS:
        raise ValueError(
            f"need >= {MIN_TRAIN_RETURNS} training returns for HAR-RV, got {len(returns)}"
        )
    rv = returns**2
    rows = []
    targets = []
    for t in range(MONTHLY_WINDOW - 1, len(rv) - 1):
        daily, weekly, monthly = _har_features(rv, t)
        rows.append((1.0, daily, weekly, monthly))
        targets.append(float(rv[t + 1]))
    x = np.asarray(rows, dtype=float)
    y = np.asarray(targets, dtype=float)
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    rv_floor = max(float(np.percentile(rv, _RV_FLOOR_QUANTILE)), 1e-12)
    return HarRVFit(
        beta0=float(beta[0]),
        beta_daily=float(beta[1]),
        beta_weekly=float(beta[2]),
        beta_monthly=float(beta[3]),
        rv_floor=rv_floor,
        n_regression_rows=len(y),
    )


def predict_sigma(fit: HarRVFit, returns_through_today: np.ndarray) -> float:
    """Next-session return sigma from the trailing return history.

    ``returns_through_today`` must be chronological and end at the session
    whose close the caller stands on — only its trailing ``MONTHLY_WINDOW``
    entries are consumed, so passing the full history is fine (and keeps
    call sites honest about as-of alignment).
    """
    returns = np.asarray(returns_through_today, dtype=float)
    if len(returns) < MONTHLY_WINDOW:
        raise ValueError(
            f"need >= {MONTHLY_WINDOW} trailing returns to form HAR features, got {len(returns)}"
        )
    rv = returns**2
    daily, weekly, monthly = _har_features(rv, len(rv) - 1)
    rv_hat = (
        fit.beta0 + fit.beta_daily * daily + fit.beta_weekly * weekly + fit.beta_monthly * monthly
    )
    return math.sqrt(max(rv_hat, fit.rv_floor))


def constant_vol_sigma(train_returns: np.ndarray) -> float:
    """Naive baseline: root-mean-square return over the training window."""
    returns = np.asarray(train_returns, dtype=float)
    if len(returns) < 2:
        raise ValueError(f"need >= 2 training returns, got {len(returns)}")
    return float(math.sqrt(float(np.mean(returns**2))))


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def make_prob_gt(prev_close: float, sigma: float) -> Callable[[float], float]:
    """Exceedance function ``P(next close > x)`` under Normal(0, sigma) log return.

    Plugs straight into ``kq.clients.kalshi.strikes.yes_prob`` (pass the
    index half-width, not the weather default). ``x <= 0`` maps to
    probability 1 — an index print is positive by construction.
    """
    if prev_close <= 0.0:
        raise ValueError(f"prev_close must be positive, got {prev_close}")
    if sigma <= 0.0:
        raise ValueError(f"sigma must be positive, got {sigma}")

    def prob_gt(x: float) -> float:
        if x <= 0.0:
            return 1.0
        return 1.0 - _normal_cdf(math.log(x / prev_close) / sigma)

    return prob_gt


def pit_value(prev_close: float, sigma: float, observed_close: float) -> float:
    """Probability integral transform of the observed close under the forecast.

    Uniform(0,1) PIT values over the test window = a calibrated continuous
    forecast; the backtest manifest reports the PIT mean (~0.5) and std
    (~sqrt(1/12) ≈ 0.289) as the cheap first-order calibration check.
    """
    if observed_close <= 0.0:
        raise ValueError(f"observed_close must be positive, got {observed_close}")
    prob_gt = make_prob_gt(prev_close, sigma)
    return 1.0 - prob_gt(observed_close)
