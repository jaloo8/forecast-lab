"""Schedule <-> odds cross-walk for NFL games.

The NFL lane's schedule AND results come from The Odds API ``/scores``
endpoint (see docs/research/MULTI-SPORT-NFL-PGA-DESIGN.md §2), so — unlike
NBA — both ``nfl_game`` and ``nfl_odds`` are keyed by The Odds API's own
event id and the crosswalk pairs are usually identity mappings. The
crosswalk still earns its keep:

* it is the (game_date, home_abbr, away_abbr) -> odds_api_game_id lookup
  the paper flow uses to go from a parsed Kalshi ticker to the latest
  Pinnacle quote (the exact join the NBA flow does), and
* it is insurance against the ``/odds`` and ``/scores`` endpoints ever
  disagreeing on ids — the match runs on the 3-tuple, never on the id.

Team-name mapping: The Odds API uses full names ("Jacksonville Jaguars");
Kalshi tickers use short codes. The codes below are the COMPLETE 32-team
set as Kalshi uses it, enumerated from live prod markets 2026-07-02 —
note ``JAC`` (Kalshi), not ESPN's ``JAX``.

Date convention: ``nfl_game.game_date`` is the US/Eastern kickoff calendar
date — the same date Kalshi embeds in the ticker (verified live 2026-07-02:
a 03:00 UTC Aug-16 kickoff carries ``26AUG15``). We reuse the NBA lane's
fixed -5h projection; NFL kickoffs run ~17:00-02:00 UTC so the no-DST
approximation never crosses a date boundary in practice.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Final

from kq.clients.kalshi._ticker_parser_nfl import NFL_TEAM_ABBRS
from kq.models.nba_crosswalk import odds_api_to_us_eastern_date

if TYPE_CHECKING:
    from kq.clients.the_odds_api import OddsApiGame, OddsApiScore

# Odds API full team name -> Kalshi ticker code (prod-verified 2026-07-02).
NFL_TEAM_NAME_TO_ABBR: Final[dict[str, str]] = {
    "Arizona Cardinals": "ARI",
    "Atlanta Falcons": "ATL",
    "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF",
    "Carolina Panthers": "CAR",
    "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN",
    "Cleveland Browns": "CLE",
    "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN",
    "Detroit Lions": "DET",
    "Green Bay Packers": "GB",
    "Houston Texans": "HOU",
    "Indianapolis Colts": "IND",
    "Jacksonville Jaguars": "JAC",
    "Kansas City Chiefs": "KC",
    "Las Vegas Raiders": "LV",
    "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LAR",
    "Miami Dolphins": "MIA",
    "Minnesota Vikings": "MIN",
    "New England Patriots": "NE",
    "New Orleans Saints": "NO",
    "New York Giants": "NYG",
    "New York Jets": "NYJ",
    "Philadelphia Eagles": "PHI",
    "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF",
    "Seattle Seahawks": "SEA",
    "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN",
    "Washington Commanders": "WAS",
}

# Guard against the two conventions drifting apart: every mapped code must
# be a code the Kalshi ticker parser accepts, and all 32 must be covered.
assert set(NFL_TEAM_NAME_TO_ABBR.values()) == set(NFL_TEAM_ABBRS)


@dataclass(frozen=True, slots=True)
class NflGameRow:
    """One NFL game's flat representation. Maps 1:1 to the ``nfl_game`` schema.

    ``completed`` is the finality gate (NOT ``home_won`` — NFL games can end
    in a tie, in which case ``completed=True`` and ``home_won is None``).
    Scores stay ``None`` until the source reports the game complete with
    both scores present.
    """

    game_id: str
    season: int
    game_date: date
    commence_time: datetime  # naive-UTC normalization happens in the repo
    home_team: str
    home_team_abbr: str
    away_team: str
    away_team_abbr: str
    home_score: int | None
    away_score: int | None
    completed: bool
    home_won: bool | None

    @property
    def is_tie(self) -> bool:
        """True for a completed game with equal scores (real in the NFL)."""
        return self.completed and self.home_score is not None and self.home_score == self.away_score


@dataclass(frozen=True, slots=True)
class NflCrosswalkPair:
    """One matched ``(odds_api, nfl_game)`` id pair."""

    odds_api_game_id: str
    nfl_game_id: str
    home_team_abbr: str
    away_team_abbr: str
    game_date: date


def nfl_season_start_year(game_date: date) -> int:
    """The NFL season a game belongs to, by its start year.

    Preseason (Aug) through the regular season (Sep-Jan) into the playoffs /
    Super Bowl (Jan-Feb) all belong to the season that started that August:
    months Aug-Dec map to the same year, Jan-Jul to the previous one.
    """
    return game_date.year if game_date.month >= 8 else game_date.year - 1


def normalize_nfl_team(name: str) -> str | None:
    """Project an Odds API team name to its Kalshi code. ``None`` on a name
    we don't recognize (relocation, rename, typo) — callers skip-and-log."""
    return NFL_TEAM_NAME_TO_ABBR.get(name.strip())


def nfl_game_row_from_score(score: OddsApiScore) -> NflGameRow | None:
    """Adapt one ``/scores`` row into an ``NflGameRow`` ready for upsert.

    Returns ``None`` when either team name is unknown — an unmappable row
    would poison every downstream (abbr, date) join, so it never lands.
    ``home_won`` derives from the scores only when the game is completed;
    a completed tie keeps ``home_won=None`` (the ``completed`` flag is the
    finality gate, and Kalshi resolves ties at $0.50 per side).
    """
    home_abbr = normalize_nfl_team(score.home_team)
    away_abbr = normalize_nfl_team(score.away_team)
    if home_abbr is None or away_abbr is None:
        return None
    game_date = odds_api_to_us_eastern_date(score.commence_time)
    home_won: bool | None = None
    if (
        score.completed
        and score.home_score is not None
        and score.away_score is not None
        and score.home_score != score.away_score
    ):
        home_won = score.home_score > score.away_score
    return NflGameRow(
        game_id=score.game_id,
        season=nfl_season_start_year(game_date),
        game_date=game_date,
        commence_time=score.commence_time,
        home_team=score.home_team,
        home_team_abbr=home_abbr,
        away_team=score.away_team,
        away_team_abbr=away_abbr,
        home_score=score.home_score if score.completed else None,
        away_score=score.away_score if score.completed else None,
        completed=score.completed,
        home_won=home_won,
    )


def match_nfl_games(
    odds_games: Iterable[OddsApiGame],
    nfl_rows: Sequence[NflGameRow],
) -> list[NflCrosswalkPair]:
    """Return crosswalk pairs for every odds-game whose
    ``(home_abbr, away_abbr, game_date)`` matches an ``nfl_game`` row.

    Same contract as the NBA matcher: unmatched odds-games (unknown team
    name, no schedule row for the projected date) are silently dropped —
    the caller decides what the gap means. Deterministic and read-only.
    """
    nfl_index: dict[tuple[str, str, date], str] = {
        (row.home_team_abbr, row.away_team_abbr, row.game_date): row.game_id for row in nfl_rows
    }
    out: list[NflCrosswalkPair] = []
    for game in odds_games:
        home_abbr = normalize_nfl_team(game.home_team)
        away_abbr = normalize_nfl_team(game.away_team)
        if home_abbr is None or away_abbr is None:
            continue
        gd = odds_api_to_us_eastern_date(game.commence_time)
        nfl_game_id = nfl_index.get((home_abbr, away_abbr, gd))
        if nfl_game_id is None:
            continue
        out.append(
            NflCrosswalkPair(
                odds_api_game_id=game.game_id,
                nfl_game_id=nfl_game_id,
                home_team_abbr=home_abbr,
                away_team_abbr=away_abbr,
                game_date=gd,
            )
        )
    return out


__all__ = [
    "NFL_TEAM_NAME_TO_ABBR",
    "NflCrosswalkPair",
    "NflGameRow",
    "match_nfl_games",
    "nfl_game_row_from_score",
    "nfl_season_start_year",
    "normalize_nfl_team",
]
