"""Isotonic post-hoc recalibration for any probabilistic forecast.

Wraps ``sklearn.isotonic.IsotonicRegression`` to remap raw predicted
probabilities to empirically-calibrated ones using the Pool-Adjacent-Violators
algorithm — the optimal monotone transform under squared-error loss.

Per the [Pass 1 extension memo §3](../../docs/research/PASS-1-EXTENSION-EMOS-EXECUTION.md)
and Niculescu-Mizil & Caruana (2005, ICML), isotonic on top of NGR
is the cheapest defensible Brier reduction in postprocessing — typically
2-8 % on top of an already-decent base model. Failure mode is small-sample
overfit; we fall through to identity below ``DEFAULT_MIN_PAIRS`` training
pairs.

**Pooling decision:** one calibrator per (station, fold), pooling across
all brackets and lead times. The memo notes a 7-bracket x 6-station x 7-lead
system has 294 buckets — too many to calibrate separately at our scale. The
input distribution to the calibrator is therefore the union of (raw_prob,
outcome) pairs over the bracket grid for one fold's training portion.
PIT-correct: per-fold fit, training-portion only.

Returns clipped to ``[0.01, 0.99]`` matching the engine's existing
``brier_score`` input clamp.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Self

import numpy as np
from sklearn.isotonic import IsotonicRegression

PROB_CLIP_LOW: Final = 0.01
PROB_CLIP_HIGH: Final = 0.99
# Below this, fall back to identity. Niculescu-Mizil & Caruana 2005 reports
# stable isotonic only above ~150 calibration points; below that the PAV
# step over-smooths the tails (see Henzi et al. 2021 for the regularized
# variant if we ever need <300 events per quintile).
DEFAULT_MIN_PAIRS: Final = 150


@dataclass
class IsotonicCalibrator:
    """Fit on (raw_prob, outcome) pairs; map raw probs to calibrated probs.

    Pre-fit (or under-trained), ``predict`` is identity-with-clip — safe to
    plug in unconditionally; the caller can check ``is_identity`` for telemetry.
    """

    min_pairs: int = DEFAULT_MIN_PAIRS
    _iso: IsotonicRegression | None = field(default=None, init=False, repr=False)
    _is_identity: bool = field(default=True, init=False)

    @property
    def is_identity(self) -> bool:
        return self._is_identity

    def fit(self, raw_probs: np.ndarray, outcomes: np.ndarray) -> Self:
        """Fit the monotone (raw_prob -> calibrated_prob) map.

        Falls through to identity when fewer than ``min_pairs`` pairs are
        provided after dropping NaN rows on either side.
        """
        if raw_probs.shape != outcomes.shape:
            raise ValueError(
                f"shape mismatch: raw_probs {raw_probs.shape} vs outcomes {outcomes.shape}"
            )
        valid = ~(np.isnan(raw_probs) | np.isnan(outcomes))
        n_valid = int(valid.sum())
        if n_valid < self.min_pairs:
            self._iso = None
            self._is_identity = True
            return self
        self._iso = IsotonicRegression(
            out_of_bounds="clip",
            y_min=PROB_CLIP_LOW,
            y_max=PROB_CLIP_HIGH,
        )
        self._iso.fit(raw_probs[valid], outcomes[valid])
        self._is_identity = False
        return self

    def predict(self, raw_probs: np.ndarray) -> np.ndarray:
        """Return calibrated probabilities, clipped to [0.01, 0.99]."""
        arr = np.asarray(raw_probs, dtype=float)
        if self._is_identity or self._iso is None:
            clipped: np.ndarray = np.clip(arr, PROB_CLIP_LOW, PROB_CLIP_HIGH)
            return clipped
        out = np.asarray(self._iso.predict(arr), dtype=float)
        clipped = np.clip(out, PROB_CLIP_LOW, PROB_CLIP_HIGH)
        return clipped
