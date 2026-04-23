"""NBA data clients.

Phase 3 deliverable. Wraps `nba_api`, `nbainjuries`, and balldontlie/the-odds-api
for cross-book comparisons.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class Game:
    game_id: str
    game_date: date
    home_team: str
    away_team: str
    tipoff_utc: datetime


@dataclass(frozen=True)
class InjuryStatus:
    player_id: str
    player_name: str
    team: str
    status: str  # OUT | DOUBTFUL | QUESTIONABLE | PROBABLE | AVAILABLE
    reason: str | None
    as_of: datetime


class NbaClient:
    """Not implemented until Phase 3."""

    async def schedule(self, for_date: date) -> list[Game]:
        _ = for_date
        raise NotImplementedError("Phase 3 task")

    async def injury_report(self, as_of: datetime) -> list[InjuryStatus]:
        _ = as_of
        raise NotImplementedError("Phase 3 task")
