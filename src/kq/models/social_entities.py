"""Conservative entity matching for social posts (Phase S1).

Posts are matched only to entities the system already models — exact or
normalized-name matches, no fuzzy guessing (design rule, FANTASY-SPORTS-
DESIGN.md § Phase S). An unmatched post is stored inert, never dropped.

* **NFL players** — normalized full-name containment against the names the
  F1a lane has stored in ``nfl_player_game`` (GSIS ids). Normalization is
  the snap-join transform (:func:`kq.clients.nfl_players.
  normalize_player_name`) plus a punctuation collapse on both sides, so
  "[Schefter] Colts placed WR Alec Pierce on the ..." matches "Alec
  Pierce" and "D.J. Williams" matches "DJ Williams". Normalized-name
  collisions are REFUSED at build time (F1a posture: a wrong id is worse
  than no id) and single-token names are dropped — one word inside running
  text is noise, not identity.
* **NFL / NBA teams** — full-name containment against the existing
  crosswalk dicts ("Miami Dolphins" -> MIA). Nicknames alone ("Colts",
  "Heat", "Jazz") are deliberately NOT matched in v0: several NBA
  nicknames are ordinary English words ("heat wave", "jazz fan") and no
  curated-ambiguity design exists yet. Documented follow-up, not a silent
  gap.

Priority when a post mentions several entities: NFL player > NFL team >
NBA team, then earliest mention in the text, then lexicographic id —
deterministic, and a single (type, id) per post because the v0 schema
stores one match (multi-entity capture is a schema follow-up).

Rookie caveat: a player enters the matcher only once a stat week is stored
for them, so draft-class players are unmatchable until they first play (or
a roster-based name source lands — follow-up).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final

import structlog

from kq.clients.nfl_players import normalize_player_name
from kq.models.nba_crosswalk import TEAM_NAME_TO_ABBR
from kq.models.nfl_crosswalk import NFL_TEAM_NAME_TO_ABBR

log = structlog.get_logger(__name__)

ENTITY_NFL_PLAYER: Final = "nfl_player"
ENTITY_NFL_TEAM: Final = "nfl_team"
ENTITY_NBA_TEAM: Final = "nba_team"

_NON_ALNUM_RE: Final = re.compile(r"[^a-z0-9]+")


def normalize_match_text(text: str) -> str:
    """Normalize free text for containment matching, with the same
    character conventions as player-name normalization: periods and
    apostrophes (straight + curly) are REMOVED ("D.J." == "DJ",
    "Ja'Marr" == "JaMarr"), every other non-alphanumeric run becomes one
    space, and the result is space-padded so ``needle in haystack`` is
    word-boundary matching ("Alec Pierce" never matches "Alec Piercee")."""
    cleaned = text.lower().replace(".", "").replace("'", "").replace("’", "")  # noqa: RUF001
    collapsed = " ".join(_NON_ALNUM_RE.sub(" ", cleaned).split())
    return f" {collapsed} "


def _player_needle(name: str) -> str | None:
    """A player name as a match needle; None when too short to be safe."""
    collapsed = " ".join(_NON_ALNUM_RE.sub(" ", normalize_player_name(name)).split())
    if len(collapsed.split()) < 2:
        return None
    return collapsed


def _team_needles(mapping: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    """Crosswalk full names as (needle, abbr) pairs (sorted: determinism)."""
    out: list[tuple[str, str]] = []
    for full_name, abbr in sorted(mapping.items()):
        needle = " ".join(
            _NON_ALNUM_RE.sub(" ", full_name.lower().replace(".", "").replace("'", "")).split()
        )
        out.append((needle, abbr))
    return tuple(out)


@dataclass(frozen=True, slots=True)
class EntityMatch:
    """One matched entity: ('nfl_player', GSIS id) or ('nfl_team'/'nba_team', abbr)."""

    entity_type: str
    entity_id: str


class SocialEntityMatcher:
    """Built once per flow run from stored player names + the static team
    crosswalks; :meth:`match` is pure after that."""

    def __init__(self, nfl_players: Iterable[tuple[str, str]] = ()) -> None:
        """``nfl_players``: (player_name, player_id) pairs — e.g.
        ``SELECT DISTINCT player_name, player_id FROM nfl_player_game``.
        An empty iterable (fresh DB, F1a not yet ingested) degrades to
        team-only matching."""
        needles: dict[str, str | None] = {}  # normalized name -> id; None = collision
        for name, player_id in nfl_players:
            needle = _player_needle(name)
            if needle is None:
                continue
            if needle in needles:
                if needles[needle] is not None and needles[needle] != player_id:
                    log.warning(
                        "social_entities.player_name_collision",
                        name=name,
                        action="both ids refused — ambiguous names never match",
                    )
                    needles[needle] = None
            else:
                needles[needle] = player_id
        self._players: tuple[tuple[str, str], ...] = tuple(
            sorted((n, pid) for n, pid in needles.items() if pid is not None)
        )
        self._nfl_teams = _team_needles(NFL_TEAM_NAME_TO_ABBR)
        self._nba_teams = _team_needles(TEAM_NAME_TO_ABBR)

    def match(self, text: str) -> EntityMatch | None:
        """The single top-priority entity mentioned in ``text``, or None."""
        hay = normalize_match_text(text)
        tiers: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
            (ENTITY_NFL_PLAYER, self._players),
            (ENTITY_NFL_TEAM, self._nfl_teams),
            (ENTITY_NBA_TEAM, self._nba_teams),
        )
        for entity_type, needles in tiers:
            hits = [
                (hay.index(f" {needle} "), entity_id)
                for needle, entity_id in needles
                if f" {needle} " in hay
            ]
            if hits:
                return EntityMatch(entity_type=entity_type, entity_id=min(hits)[1])
        return None


__all__ = [
    "ENTITY_NBA_TEAM",
    "ENTITY_NFL_PLAYER",
    "ENTITY_NFL_TEAM",
    "EntityMatch",
    "SocialEntityMatcher",
    "normalize_match_text",
]
