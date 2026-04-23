"""NGR / EMOS-style bias-corrected ensemble model.

`T_obs ~ N(a + b * ens_mean, c + d * ens_var)` fit per station × lead time.
Phase 2 deliverable. See CLAUDE.md §5 Phase 2.
"""

from __future__ import annotations


class WeatherEnsembleModel:
    """Placeholder class. Phase 2 fills in fit + predict_proba."""

    def fit(self) -> None:
        raise NotImplementedError("Phase 2 task")

    def predict_proba(self) -> None:
        raise NotImplementedError("Phase 2 task")

    def brier_score(self) -> float:
        raise NotImplementedError("Phase 2 task")
