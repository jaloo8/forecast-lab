"""Calibration primitives: Brier score and reliability diagram bins."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def brier_score(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Binary Brier score: mean((p - y)^2).

    Parameters
    ----------
    probs
        Predicted probabilities in [0, 1], shape (n,).
    outcomes
        Realized binary outcomes {0, 1}, shape (n,).
    """
    probs = np.asarray(probs, dtype=float)
    outcomes = np.asarray(outcomes, dtype=float)
    if probs.shape != outcomes.shape:
        raise ValueError(f"shape mismatch: probs {probs.shape} vs outcomes {outcomes.shape}")
    if probs.size == 0:
        raise ValueError("empty arrays")
    return float(np.mean((probs - outcomes) ** 2))


@dataclass(frozen=True)
class ReliabilityBin:
    lower: float
    upper: float
    n: int
    mean_predicted: float
    mean_observed: float


def reliability_bins(
    probs: np.ndarray,
    outcomes: np.ndarray,
    *,
    n_bins: int = 10,
) -> list[ReliabilityBin]:
    """Bucket predictions into `n_bins` equal-width buckets on [0, 1]."""
    probs = np.asarray(probs, dtype=float)
    outcomes = np.asarray(outcomes, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins: list[ReliabilityBin] = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (probs >= lo) & (probs < hi if i < n_bins - 1 else probs <= hi)
        n = int(mask.sum())
        if n == 0:
            bins.append(ReliabilityBin(lo, hi, 0, float("nan"), float("nan")))
        else:
            bins.append(
                ReliabilityBin(
                    lower=float(lo),
                    upper=float(hi),
                    n=n,
                    mean_predicted=float(probs[mask].mean()),
                    mean_observed=float(outcomes[mask].mean()),
                )
            )
    return bins
