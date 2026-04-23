"""FiveThirtyEight-style CARM-Elo for NBA with rest/travel/altitude adjustments.

Phase 3 deliverable. Base 1300, K adjusted for margin of victory,
home-court ~100 Elo, back-to-back -46 Elo, travel ~-16 Elo, altitude bonus.
"""

from __future__ import annotations


class NbaEloModel:
    """Placeholder. Phase 3 fills in."""

    def fit(self) -> None:
        raise NotImplementedError("Phase 3 task")

    def predict_proba(self) -> None:
        raise NotImplementedError("Phase 3 task")
