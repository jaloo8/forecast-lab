"""Paper-trading executor. Records intended trades without hitting the live API.

Phase 2 deliverable. Uses the Kalshi fee model and the configured Kelly fraction.
Cannot - by construction - reach the live endpoint; that lives in `live.py`.
"""

from __future__ import annotations


class PaperExecutor:
    """Not implemented until Phase 2."""

    def submit(self) -> None:
        raise NotImplementedError("Phase 2 task")
