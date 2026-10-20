"""Causal allocation signals for a finite, offline six-ETF research study.

Targets are unscaled; the separate account engine applies the 98% allocation.
Online virtual experts are gross signal calculations, not funded subaccounts.
"""

from itertools import product

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from kq.equities.allocation_study import Prices

SYMBOLS = ("SPY", "EFA", "IEF", "VNQ", "GLD", "BIL")
RISK_SYMBOLS = SYMBOLS[:-1]
STATIC_POLICIES = ("C01", "C02", "C03", "C04", "A01", "A02", "O01", "O02")
COVARIANCE_RETURNS = 126
EG_LEARNING_RATE = 0.05
_FEASIBILITY_TOLERANCE = 1e-10
_ERC_TOLERANCE = 1e-10


def _validated_covariance(covariance: NDArray[np.float64]) -> NDArray[np.float64]:
    """Validate and normalize covariance without changing its optimization."""
    if np.iscomplexobj(covariance):
        raise ValueError("Covariance must be real")
    matrix: NDArray[np.float64] = np.array(covariance, dtype=float, copy=True)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or not matrix.shape[0]:
        raise ValueError("Covariance must be a nonempty square matrix")
    if not np.isfinite(matrix).all():
        raise ValueError("Covariance must be finite")
    scale = float(np.abs(matrix).max())
    if scale <= 0:
        raise ValueError("Covariance must be positive definite")
    matrix /= scale
    if float(np.abs(matrix - matrix.T).max()) > 1e-12:
        raise ValueError("Covariance must be symmetric")
    matrix = (matrix + matrix.T) / 2
    eigenvalues = np.linalg.eigvalsh(matrix)
    if eigenvalues[0] <= 0 or not np.isfinite(eigenvalues).all():
        raise ValueError("Covariance must be positive definite")
    return matrix


def minimum_variance_weights(covariance: NDArray[np.float64]) -> NDArray[np.float64]:
    """Exactly enumerate the small long-only, 50%-capped problem's active sets.

    Each coordinate is zero, interior, or at the cap. Solving the equality
    constrained quadratic for every face includes the global minimizer.
    Numerical failure raises; equal weighting is never a failure fallback.
    """
    matrix = _validated_covariance(covariance)
    size = len(matrix)
    if not 2 <= size <= len(SYMBOLS):
        raise ValueError("Active-set enumeration supports two to six assets")
    cap = 0.5
    best: NDArray[np.float64] | None = None
    best_value = float("inf")
    for state in product((0, 1, 2), repeat=size):
        labels = np.asarray(state)
        fixed = labels == 2
        free = labels == 1
        remaining = 1.0 - cap * int(fixed.sum())
        if remaining < 0 or remaining > cap * int(free.sum()) + _FEASIBILITY_TOLERANCE:
            continue
        weights = fixed.astype(float) * cap
        if free.any():
            submatrix = matrix[np.ix_(free, free)]
            cross = matrix[np.ix_(free, fixed)] @ weights[fixed]
            solved = np.linalg.solve(submatrix, np.column_stack((np.ones(free.sum()), cross)))
            inverse_one, inverse_cross = solved[:, 0], solved[:, 1]
            denominator = float(inverse_one.sum())
            if not np.isfinite(denominator) or denominator <= 0:
                raise RuntimeError("Minimum-variance active-set solve failed")
            multiplier = (remaining + float(inverse_cross.sum())) / denominator
            weights[free] = multiplier * inverse_one - inverse_cross
        elif abs(remaining) > _FEASIBILITY_TOLERANCE:
            continue
        if (
            not np.isfinite(weights).all()
            or weights.min() < -_FEASIBILITY_TOLERANCE
            or weights.max() > cap + _FEASIBILITY_TOLERANCE
            or abs(float(weights.sum()) - 1) > _FEASIBILITY_TOLERANCE
        ):
            continue
        value = float(weights @ matrix @ weights)
        if value < best_value:
            best, best_value = weights, value
    if best is None:
        raise RuntimeError("Minimum-variance optimization found no feasible solution")
    # Only round-off-sized corrections are permitted after the exact face solve.
    best = np.clip(best, 0.0, cap)
    residual = 1.0 - float(best.sum())
    room = cap - best if residual >= 0 else best
    best[int(np.argmax(room))] += residual
    projected_gradient = matrix @ best
    free = (best > 1e-9) & (best < cap - 1e-9)
    if free.any():
        multiplier = float(projected_gradient[free].mean())
    else:
        multiplier = (
            float(
                (
                    projected_gradient[best >= cap - 1e-9].max()
                    + projected_gradient[best <= 1e-9].min()
                )
                / 2
            )
            if (best <= 1e-9).any()
            else float(projected_gradient.max())
        )
    violations = np.where(
        best <= 1e-9,
        np.maximum(multiplier - projected_gradient, 0),
        np.where(
            best >= cap - 1e-9,
            np.maximum(projected_gradient - multiplier, 0),
            np.abs(projected_gradient - multiplier),
        ),
    )
    if float(violations.max()) > 1e-8:
        raise RuntimeError("Minimum-variance solution failed the optimality check")
    return best


def equal_risk_weights(
    covariance: NDArray[np.float64], *, max_iterations: int = 10_000
) -> NDArray[np.float64]:
    """Solve equal component risk via positive-root coordinate descent."""
    matrix = _validated_covariance(covariance)
    size = len(matrix)
    budget = 1.0 / size
    values = np.ones(size, dtype=float)
    for _ in range(max_iterations):
        for i in range(size):
            diagonal = matrix[i, i]
            off_diagonal = float(matrix[i] @ values - diagonal * values[i])
            discriminant = np.sqrt(off_diagonal**2 + 4 * diagonal * budget)
            if off_diagonal >= 0:
                values[i] = 2 * budget / (off_diagonal + discriminant)
            else:
                values[i] = (-off_diagonal + discriminant) / (2 * diagonal)
        weights: NDArray[np.float64] = values / values.sum()
        contributions = weights * (matrix @ weights)
        total = float(contributions.sum())
        if (
            not np.isfinite(weights).all()
            or (weights <= 0).any()
            or not np.isfinite(total)
            or total <= 0
        ):
            raise RuntimeError("Equal-risk iteration produced invalid weights")
        if float(np.abs(contributions / total - budget).max()) <= _ERC_TOLERANCE:
            return weights
    raise RuntimeError("Equal-risk optimization did not converge")


def universal_experts() -> NDArray[np.float64]:
    """The complete six-asset 25%-increment grid, in deterministic order."""
    return (
        np.asarray(
            [weights for weights in product(range(5), repeat=len(SYMBOLS)) if sum(weights) == 4],
            dtype=float,
        )
        / 4
    )


def _validate_online(weights: NDArray[np.float64], relatives: NDArray[np.float64]) -> None:
    if (
        weights.shape != relatives.shape
        or weights.ndim != 1
        or not np.isfinite(weights).all()
        or (weights < 0).any()
        or abs(float(weights.sum()) - 1) > 1e-12
        or not np.isfinite(relatives).all()
        or (relatives <= 0).any()
    ):
        raise ValueError("Invalid online weights or observed price relatives")


def exponentiated_update(
    weights: NDArray[np.float64], relatives: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Update only from a newly completed monthly interval."""
    _validate_online(weights, relatives)
    gradient = EG_LEARNING_RATE * relatives / float(weights @ relatives)
    shifted = gradient - gradient.max()
    updated = weights * np.exp(shifted)
    normalized: NDArray[np.float64] = updated / updated.sum()
    return normalized


def _validate_prices(prices: Prices) -> pd.DataFrame:
    closes = prices.closed
    dates = closes.index
    if (
        not isinstance(dates, pd.DatetimeIndex)
        or dates.tz is not None
        or dates.hasnans
        or not dates.is_monotonic_increasing
        or dates.has_duplicates
        or not dates.equals(dates.normalize())
        or not closes.index.equals(prices.opened.index)
        or tuple(closes.columns) != SYMBOLS
        or tuple(prices.opened.columns) != SYMBOLS
        or closes.empty
    ):
        raise ValueError("Expected aligned ordered six-asset observed-session prices")
    for frame in (closes, prices.opened):
        values = frame.to_numpy(float)
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError("Prices must be finite and positive")
    return closes


def _as_of(day: pd.Timestamp) -> pd.Timestamp:
    return (day + pd.Timedelta(hours=16)).tz_localize("America/New_York").tz_convert("UTC")


def build_signals(prices: Prices) -> dict[str, pd.DataFrame]:  # noqa: PLR0915
    """Return execution-date targets based exclusively on completed sessions.

    A month is complete only when an observed next-month session exists.
    Consequently, appending future rows cannot revise any existing signal.
    The synthetic 16:00 timestamp is a convention, not a receipt-time audit.
    """
    closes = _validate_prices(prices)
    dates, count = closes.index, len(closes)
    months = dates.to_period("M")
    values = closes.to_numpy(float)
    arrays = {policy: np.zeros((count, len(SYMBOLS))) for policy in STATIC_POLICIES}
    schedules = {policy: np.zeros(count, dtype=bool) for policy in STATIC_POLICIES}
    ready = {policy: np.zeros(count, dtype=bool) for policy in STATIC_POLICIES}
    decisions = {
        policy: pd.Series(pd.NaT, index=dates, dtype="datetime64[ns]") for policy in STATIC_POLICIES
    }
    current: dict[str, NDArray[np.float64]] = {}
    target_dates: dict[str, pd.Timestamp] = {}
    experts = universal_experts()
    log_expert_wealth = np.zeros(len(experts))
    eg = np.full(len(SYMBOLS), 1.0 / len(SYMBOLS))
    previous_month: NDArray[np.float64] | None = None
    for i in range(1, count):
        decision = i - 1
        for policy, ticker in (("C01", None), ("C02", "BIL"), ("C03", "SPY")):
            if ticker is not None:
                arrays[policy][i, SYMBOLS.index(ticker)] = 1.0
            ready[policy][i] = True
            decisions[policy].iloc[i] = dates[decision]
        new_month = months[i] != months[decision]
        if new_month:
            latest = values[decision]
            current["C04"] = np.r_[np.full(len(RISK_SYMBOLS), 0.2), 0.0]
            if previous_month is not None:
                relatives = latest / previous_month
                log_expert_wealth += np.log(experts @ relatives)
                eg = exponentiated_update(eg, relatives)
            previous_month = latest.copy()
            posterior = np.exp(log_expert_wealth - log_expert_wealth.max())
            current["O01"] = posterior @ experts / posterior.sum()
            current["O02"] = eg.copy()
            if decision >= COVARIANCE_RETURNS:
                history = values[decision - COVARIANCE_RETURNS : decision + 1, :-1]
                returns = history[1:] / history[:-1] - 1
                sample = np.cov(returns, rowvar=False, ddof=1)
                covariance = (sample + np.diag(np.diag(sample))) / 2
                current["A01"] = np.r_[minimum_variance_weights(covariance), 0.0]
                current["A02"] = np.r_[equal_risk_weights(covariance), 0.0]
            for policy in current:
                target_dates[policy] = dates[decision]
        for policy, target in current.items():
            arrays[policy][i] = target
            schedules[policy][i] = new_month
            ready[policy][i] = True
            decisions[policy].iloc[i] = target_dates[policy]
    result = {}
    for policy in STATIC_POLICIES:
        frame = pd.DataFrame(arrays[policy], index=dates, columns=SYMBOLS)
        frame["rebalance"] = schedules[policy]
        frame["warmup_ready"] = ready[policy]
        frame["decision_date"] = decisions[policy]
        frame["as_of"] = decisions[policy].map(lambda day: _as_of(day) if pd.notna(day) else pd.NaT)
        result[policy] = frame
    return result
