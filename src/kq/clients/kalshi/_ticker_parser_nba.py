"""Parse Kalshi NBA-game-winner ticker strings to typed metadata.

Format (inferred from PR #62 test fixtures + Kalshi's public catalog conventions):

    KXNBAGAME-<YY><MMM><DD><AWAY3><HOME3>-<YES_SIDE_TEAM3>

Examples:

    KXNBAGAME-26APR30BOSPHI-PHI   ->  2026-04-30, BOS @ PHI, YES = home (PHI)
    KXNBAGAME-26MAY04LALBOS-LAL   ->  2026-05-04, LAL @ BOS, YES = away (LAL)

NBA tickers are *per-side* in Kalshi's catalog -- the same game generates two
markets, one with YES=home and one with YES=away. Whichever side the bettor
wants to back, they buy the YES contract on the corresponding ticker.

The 3-letter team codes match NBA stats convention (`nba_api.teams`), e.g.
LAL = Los Angeles Lakers, PHI = Philadelphia 76ers, BOS = Boston Celtics.
GSW = Golden State Warriors (3 chars, not 2).

⚠️ Unverified against production Kalshi until we have a Kalshi NBA market
landed in `kalshi_market`. The format is consistent with what Kalshi
publishes in their public market browser; the round-trip test in
``tests/test_kalshi_ticker_parser_nba.py`` is the authority here. When prod
access is available, run a manual probe and tighten this if needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Final

# Three-letter month abbreviations Kalshi uses in YYMMMDD (year is 2-digit).
# Duplicated rather than imported from _ticker_parser to keep the two parsers
# decoupled — they may diverge if Kalshi changes one and not the other.
_MONTH_ABBR_TO_NUM: Final[dict[str, int]] = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}  # fmt: skip

_NUM_TO_MONTH_ABBR: Final[dict[int, str]] = {v: k for k, v in _MONTH_ABBR_TO_NUM.items()}

# Pattern: KXNBAGAME-<YY><MMM><DD><AWAY3><HOME3>-<YES_TEAM3>
NBA_TICKER_RE: Final = re.compile(
    r"^KXNBAGAME-"
    r"(?P<yy>\d{2})(?P<mmm>[A-Z]{3})(?P<dd>\d{2})"
    r"(?P<away>[A-Z]{3})(?P<home>[A-Z]{3})"
    r"-(?P<yes>[A-Z]{3})$"
)


@dataclass(frozen=True, slots=True)
class NbaMarketRef:
    """Parsed identifier for a single Kalshi NBA game-winner contract.

    The contract pays YES when the team identified by ``yes_team_abbr`` wins
    the game. ``yes_is_home`` is precomputed for ergonomic callers — both the
    paper-trade flow (which needs to know which Pinnacle side to compare to)
    and the settlement loop (which needs to know which sign of ``home_won``
    means YES) use it.
    """

    game_date: date  # the calendar date AS WRITTEN in the ticker
    away_team_abbr: str  # e.g. "BOS"
    home_team_abbr: str  # e.g. "PHI"
    yes_team_abbr: str  # the team backed by the YES side of this contract
    raw_ticker: str  # the ticker exactly as Kalshi published it

    @property
    def yes_is_home(self) -> bool:
        """True when the YES contract pays on the home team winning."""
        return self.yes_team_abbr == self.home_team_abbr


def parse_nba_market_ticker(ticker: str) -> NbaMarketRef | None:
    """Return an ``NbaMarketRef`` if ``ticker`` matches the NBA-game pattern,
    else None. Never raises — defensive against unknown formats.

    Validates that ``yes_team_abbr`` is one of the two teams in the matchup;
    a ticker that names a third team in the YES slot is rejected.
    """
    match = NBA_TICKER_RE.match(ticker.strip())
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

    away = match.group("away")
    home = match.group("home")
    yes = match.group("yes")
    if yes not in (home, away):
        # Defensive: a YES side that isn't one of the two teams is malformed.
        return None
    if home == away:
        # A team can't play itself. Reject rather than emit a confusing parse.
        return None

    return NbaMarketRef(
        game_date=game_date,
        away_team_abbr=away,
        home_team_abbr=home,
        yes_team_abbr=yes,
        raw_ticker=ticker.strip(),
    )


def build_nba_market_ticker(
    *,
    game_date: date,
    home_team_abbr: str,
    away_team_abbr: str,
    yes_team_abbr: str,
) -> str:
    """Construct a Kalshi NBA-game ticker. Inverse of :func:`parse_nba_market_ticker`.

    Raises ``ValueError`` if ``yes_team_abbr`` isn't one of the two teams.
    """
    if yes_team_abbr not in (home_team_abbr, away_team_abbr):
        raise ValueError(
            f"yes_team_abbr {yes_team_abbr!r} must equal home {home_team_abbr!r} "
            f"or away {away_team_abbr!r}"
        )
    if home_team_abbr == away_team_abbr:
        raise ValueError(f"home and away cannot be the same team ({home_team_abbr!r})")
    if not all(
        len(t) == 3 and t.isalpha() and t.isupper()
        for t in (home_team_abbr, away_team_abbr, yes_team_abbr)
    ):
        raise ValueError(
            "team abbreviations must be 3 uppercase letters "
            f"(got home={home_team_abbr!r}, away={away_team_abbr!r}, yes={yes_team_abbr!r})"
        )
    yy = f"{game_date.year % 100:02d}"
    mmm = _NUM_TO_MONTH_ABBR[game_date.month]
    dd = f"{game_date.day:02d}"
    return f"KXNBAGAME-{yy}{mmm}{dd}{away_team_abbr}{home_team_abbr}-{yes_team_abbr}"


__all__ = [
    "NBA_TICKER_RE",
    "NbaMarketRef",
    "build_nba_market_ticker",
    "parse_nba_market_ticker",
]
