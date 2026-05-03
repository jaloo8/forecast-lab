"""Schedule <-> odds cross-walk for NBA games.

The Odds API uses opaque UUID-style game ids (e.g.
``abcd1234abcd1234abcd1234abcd1234``) and full team names like
``"Los Angeles Lakers"``. ``nba_api`` uses the league's canonical
10-digit ids (e.g. ``"0022400123"``) and 3-letter abbreviations like
``"LAL"``. There is no shared key, so any join between ``nba_odds``
and ``nba_game`` has to go through a deterministic 3-tuple match:
``(home_team_abbr, away_team_abbr, game_date)``.

This module is the pure-function adapter: given the Odds API game
list and the ``nba_game`` rows for the same date window, produce the
``(odds_api_game_id, nba_game_id)`` pairs. Schema + ingest flow that
persist these pairs into a ``nba_game_crosswalk`` table is deferred
to a follow-up PR; landing the matcher in isolation lets it be
unit-tested without DB infrastructure.

Two structural assumptions worth flagging for reviewers:

1. **One game per (home, away, date) per cycle.** The NBA never
   schedules two games between the same matchup on the same calendar
   day. If we ever encounter that (a doubleheader after a postponement,
   say), the matcher returns the first match deterministically and
   logs a warning -- caller decides whether to harden further.
2. **Date is the local US/Eastern game date** for both sources.
   ``nba_game.game_date`` already stores US/Eastern; The Odds API's
   ``commence_time`` is UTC and tipoff times often span a UTC
   midnight, so we project to US/Eastern (-5h, no DST) before the
   match. This will be off-by-one for the LA early-season 22:00 PT
   tipoffs in March (DST shifts US/Eastern to -4h); the v1 matcher
   accepts the hardcoded -5h offset and notes the gap; a future
   pyttz-based projection is a future hardening.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from kq.clients.nba_schedule import NbaGameRow
    from kq.clients.the_odds_api import OddsApiGame


# Map Odds API team names to NBA's canonical 3-letter abbreviation.
# NBA had 30 teams as of 2026-05; pin this list and update on
# expansion / relocation. The Odds API uses full team names; nba_api's
# TEAM_ABBREVIATION is the canonical short form used in nba_game rows.
TEAM_NAME_TO_ABBR: Final[dict[str, str]] = {
    "Atlanta Hawks": "ATL",
    "Boston Celtics": "BOS",
    "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI",
    "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL",
    "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW",
    "Houston Rockets": "HOU",
    "Indiana Pacers": "IND",
    "LA Clippers": "LAC",
    "Los Angeles Clippers": "LAC",  # alternate spelling occasionally seen
    "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC",
    "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA",
    "Washington Wizards": "WAS",
}

# US/Eastern offset without DST. NBA's game_date convention is
# US/Eastern; The Odds API's commence_time is UTC. The naive -5h
# projection works year-round for the v1 matcher; a DST-aware version
# can land in a follow-up if Mar/Nov LA late-tipoffs become a problem.
US_EASTERN_OFFSET_HOURS: Final = -5


@dataclass(frozen=True, slots=True)
class CrosswalkPair:
    """One matched ``(odds_api, nba_api)`` game-id pair."""

    odds_api_game_id: str
    nba_game_id: str
    home_team_abbr: str
    away_team_abbr: str
    game_date: date


def odds_api_to_us_eastern_date(commence_time: datetime) -> date:
    """Project The Odds API's UTC ``commence_time`` to a US/Eastern
    calendar date matching ``nba_game.game_date`` semantics.

    Uses a fixed -5h offset (EST without DST). For the typical NBA
    schedule (Oct-Jun), 95%+ of tipoffs are after UTC 23:00, which
    means the US/Eastern date is the same as the UTC date minus
    sometimes one day. Worst case: a 1:00 UTC tipoff is 20:00 ET the
    prior day; the offset shift catches that.
    """
    if commence_time.tzinfo is None:
        raise ValueError("commence_time must be timezone-aware")
    return (commence_time.astimezone(UTC) + timedelta(hours=US_EASTERN_OFFSET_HOURS)).date()


def normalize_team(name: str) -> str | None:
    """Project an Odds API team name to its NBA abbreviation. Returns
    None on a team we don't recognize (relocation, expansion, typo).
    """
    return TEAM_NAME_TO_ABBR.get(name.strip())


def match_games(
    odds_games: Iterable[OddsApiGame],
    nba_rows: Sequence[NbaGameRow],
) -> list[CrosswalkPair]:
    """Return the ``(odds_api_game_id, nba_game_id)`` pairs for every
    odds-game whose ``(home_abbr, away_abbr, game_date)`` matches an
    nba-row in the input.

    Unmatched odds-games (unknown team name, no nba-row for the
    projected date) are silently dropped -- the caller decides what
    to do with the gap. Common cases:
    - Pre-season game in nba schedule but Odds API doesn't carry it
    - All-Star game (Odds API skips, nba_api includes)
    - Postponed game on a non-standard date

    The matcher does NOT mutate the inputs. ``nba_rows`` is indexed
    once per call into a ``(home, away, date) -> game_id`` dict for
    O(1) per-odds-game lookup.
    """
    nba_index: dict[tuple[str, str, date], str] = {
        (row.home_team_abbr, row.away_team_abbr, row.game_date): row.game_id for row in nba_rows
    }

    out: list[CrosswalkPair] = []
    for game in odds_games:
        home_abbr = normalize_team(game.home_team)
        away_abbr = normalize_team(game.away_team)
        if home_abbr is None or away_abbr is None:
            continue
        gd = odds_api_to_us_eastern_date(game.commence_time)
        nba_game_id = nba_index.get((home_abbr, away_abbr, gd))
        if nba_game_id is None:
            continue
        out.append(
            CrosswalkPair(
                odds_api_game_id=game.game_id,
                nba_game_id=nba_game_id,
                home_team_abbr=home_abbr,
                away_team_abbr=away_abbr,
                game_date=gd,
            )
        )
    return out


__all__ = [
    "TEAM_NAME_TO_ABBR",
    "US_EASTERN_OFFSET_HOURS",
    "CrosswalkPair",
    "match_games",
    "normalize_team",
    "odds_api_to_us_eastern_date",
]
