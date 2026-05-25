"""Parse Kalshi NFL-game-winner ticker strings to typed metadata.

Format (from Kalshi's public catalog, web-verified 2026-05-24 — the
per-side YES suffix remains UNVERIFIED against a live ``kalshi_market``):

    KXNFLGAME-<YY><MMM><DD><AWAY><HOME>-<YES_SIDE_TEAM>

Example:

    KXNFLGAME-26JAN04WASPHI-PHI   ->  2026-01-04, WAS @ PHI, YES = home (PHI)
    KXNFLGAME-26JAN04LACSF-LAC    ->  2026-01-04, LAC @ SF,  YES = away (LAC)

Unlike NBA, **NFL team codes are not uniformly 3 letters** (``SF``, ``NE``,
``GB``, ``KC`` are 2; ``LAC``, ``LAR``, ``JAX`` are 3). So the concatenated
``<AWAY><HOME>`` block cannot be split by fixed width like the NBA parser
does. Instead we use the trailing ``<YES>`` token — which is one of the two
teams — to disambiguate: if the block ends with YES, YES is the home team
and the prefix is away; if it starts with YES, YES is away and the suffix is
home. Both halves are then validated against the 32-team abbreviation set.

⚠️ Unverified against production Kalshi (demo seeds 0 NFL markets, and it is
NFL off-season as of this writing). The series ticker ``KXNFLGAME`` and the
date+team layout are taken from Kalshi's public market browser; the exact
per-side suffix is a best guess by analogy to the (also-inferred) NBA format.
The round-trip test in ``tests/test_kalshi_ticker_parser_nfl.py`` is the
authority until prod access confirms it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Final

_MONTH_ABBR_TO_NUM: Final[dict[str, int]] = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}  # fmt: skip

_NUM_TO_MONTH_ABBR: Final[dict[int, str]] = {v: k for k, v in _MONTH_ABBR_TO_NUM.items()}

# Standard 32-team NFL abbreviation set (ESPN / Kalshi convention). Mixed
# 2- and 3-character codes — the reason this parser can't split by width.
NFL_TEAM_ABBRS: Final[frozenset[str]] = frozenset(
    [
        "ARI",
        "ATL",
        "BAL",
        "BUF",
        "CAR",
        "CHI",
        "CIN",
        "CLE",
        "DAL",
        "DEN",
        "DET",
        "GB",
        "HOU",
        "IND",
        "JAX",
        "KC",
        "LV",
        "LAC",
        "LAR",
        "MIA",
        "MIN",
        "NE",
        "NO",
        "NYG",
        "NYJ",
        "PHI",
        "PIT",
        "SF",
        "SEA",
        "TB",
        "TEN",
        "WAS",
    ]
)

# <AWAY><HOME> block is two codes of 2-3 chars => 4-6 chars; YES is 2-3.
NFL_TICKER_RE: Final = re.compile(
    r"^KXNFLGAME-"
    r"(?P<yy>\d{2})(?P<mmm>[A-Z]{3})(?P<dd>\d{2})"
    r"(?P<teams>[A-Z]{4,6})"
    r"-(?P<yes>[A-Z]{2,3})$"
)


@dataclass(frozen=True, slots=True)
class NflMarketRef:
    """Parsed identifier for a single Kalshi NFL game-winner contract.

    Pays YES when ``yes_team_abbr`` wins. ``yes_is_home`` is precomputed
    for the (future) paper-trade + settlement callers, mirroring the NBA
    parser's ergonomics.
    """

    game_date: date
    away_team_abbr: str
    home_team_abbr: str
    yes_team_abbr: str
    raw_ticker: str

    @property
    def yes_is_home(self) -> bool:
        """True when the YES contract pays on the home team winning."""
        return self.yes_team_abbr == self.home_team_abbr


def _split_teams(block: str, yes: str) -> tuple[str, str] | None:
    """Split the concatenated ``<AWAY><HOME>`` block using the YES token.

    Returns ``(away, home)`` or ``None`` if the split is ambiguous or the
    halves aren't both valid NFL abbreviations. The YES token disambiguates
    because it equals exactly one of the two teams: a suffix match means
    YES is home, a prefix match means YES is away.
    """
    candidates: list[tuple[str, str]] = []
    if block.endswith(yes):
        away = block[: -len(yes)]
        if away:
            candidates.append((away, yes))  # YES is home
    if block.startswith(yes):
        home = block[len(yes) :]
        if home:
            candidates.append((yes, home))  # YES is away
    # Keep only splits where both halves are known teams and differ.
    valid = [
        (a, h) for (a, h) in candidates if a != h and a in NFL_TEAM_ABBRS and h in NFL_TEAM_ABBRS
    ]
    # De-dup (a prefix==suffix coincidence on equal halves is excluded above).
    valid = list(dict.fromkeys(valid))
    if len(valid) != 1:
        return None
    return valid[0]


def parse_nfl_market_ticker(ticker: str) -> NflMarketRef | None:
    """Return an ``NflMarketRef`` if ``ticker`` matches, else None. Never raises."""
    match = NFL_TICKER_RE.match(ticker.strip())
    if match is None:
        return None
    month = _MONTH_ABBR_TO_NUM.get(match.group("mmm"))
    if month is None:
        return None
    try:
        year = 2000 + int(match.group("yy"))
        day = int(match.group("dd"))
        game_date = date(year, month, day)
    except ValueError:
        return None

    yes = match.group("yes")
    if yes not in NFL_TEAM_ABBRS:
        return None
    split = _split_teams(match.group("teams"), yes)
    if split is None:
        return None
    away, home = split

    return NflMarketRef(
        game_date=game_date,
        away_team_abbr=away,
        home_team_abbr=home,
        yes_team_abbr=yes,
        raw_ticker=ticker.strip(),
    )


def build_nfl_market_ticker(
    *,
    game_date: date,
    home_team_abbr: str,
    away_team_abbr: str,
    yes_team_abbr: str,
) -> str:
    """Construct a Kalshi NFL-game ticker. Inverse of :func:`parse_nfl_market_ticker`.

    Raises ``ValueError`` on unknown teams, a self-matchup, or a YES side
    that isn't one of the two teams.
    """
    if yes_team_abbr not in (home_team_abbr, away_team_abbr):
        raise ValueError(
            f"yes_team_abbr {yes_team_abbr!r} must equal home {home_team_abbr!r} "
            f"or away {away_team_abbr!r}"
        )
    if home_team_abbr == away_team_abbr:
        raise ValueError(f"home and away cannot be the same team ({home_team_abbr!r})")
    for t in (home_team_abbr, away_team_abbr):
        if t not in NFL_TEAM_ABBRS:
            raise ValueError(f"unknown NFL team abbreviation {t!r}")
    yy = f"{game_date.year % 100:02d}"
    mmm = _NUM_TO_MONTH_ABBR[game_date.month]
    dd = f"{game_date.day:02d}"
    return f"KXNFLGAME-{yy}{mmm}{dd}{away_team_abbr}{home_team_abbr}-{yes_team_abbr}"


__all__ = [
    "NFL_TEAM_ABBRS",
    "NFL_TICKER_RE",
    "NflMarketRef",
    "build_nfl_market_ticker",
    "parse_nfl_market_ticker",
]
