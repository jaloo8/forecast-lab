"""538-style NBA Elo with rest, travel, and altitude adjustments.

The core model is the standard logistic-Elo formulation; the
adjustments come from the FiveThirtyEight CARM-Elo public methodology
(`https://fivethirtyeight.com/methodology/how-our-nba-predictions-work/`).
We implement the deployable subset:

- Base rating 1500, regression 1/4 toward 1505 between seasons.
- Home-court advantage: +100 Elo (538 finds ~3.5 points; the
  conventional Elo conversion is ~28-30 per point, so 100 is the
  "3.5 ppts" equivalent. We pin 100.0 for v1).
- Back-to-back penalty: -46 Elo on the second leg. 538 cites
  empirical -3 nets to ~-46 on the Elo scale.
- Travel penalty: roughly -1 Elo per 250 miles flown since the last
  game. Defaults to 0 because we don't ingest team-to-team distance
  in v1; the slot is left open for the next phase.
- Altitude bonus: KDEN gets +30 Elo at home (538-tier number; arena
  elevation > 1500 m is the trigger). Implemented as a fixed bonus
  on a hardcoded altitude-team list.
- K-factor: 20 for regular season, scaled by the margin-of-victory
  multiplier ``((abs(home_score - away_score) + 3) ** 0.8) / (7.5 +
  0.006 * elo_diff_winner)`` where ``elo_diff_winner`` is the winner's
  Elo edge INCLUDING home-court advantage. This is the canonical 538
  margin-of-victory adjustment.

Why this scope: enough to clear "538-style fallback model" per
CLAUDE.md §5 Phase 3, no more. The Elo is *only* a fallback for when
Pinnacle isn't quoted or the line moves so slow it's stale; the
primary edge source is the vig-stripped Pinnacle quote.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Final

from kq.models.nba_crosswalk import TEAM_NAME_TO_ABBR

# Initial / regression-target rating (538 uses 1505 as the
# between-seasons regression target so the league mean drifts toward
# the all-time mean rather than always re-centering on 1500).
INITIAL_RATING: Final = 1500.0
REGRESSION_TARGET: Final = 1505.0
# 3/4 weight stays on the team's rating; 1/4 pulls toward the target
# (2026-07-01 audit T4: this comment previously stated the inverse).
REGRESSION_FRACTION: Final = 0.25

# Home-court advantage in Elo points. ~100 Elo == 3.5 ppts == ~62.5 %
# home win rate at parity, matching long-run NBA averages.
HOME_COURT_ELO: Final = 100.0

# Back-to-back fatigue: second leg of a B2B costs ~3 ppts == ~46 Elo.
BACK_TO_BACK_ELO: Final = -46.0

# Altitude bonus for home teams whose arenas sit above ~1500 m.
# Currently only the Denver Nuggets qualify (Ball Arena, 1610 m).
# Value is the 538-cited 0.75 ppts == ~30 Elo.
ALTITUDE_ELO: Final = 30.0
ALTITUDE_TEAMS: Final[frozenset[str]] = frozenset({"DEN"})

# Travel penalty per mile flown since the prior game. 538 uses
# ~-0.045 Elo per mile (-1 per 22 miles); our v1 default rate is 0
# since we don't ingest distances. Callers can override.
TRAVEL_PENALTY_PER_MILE: Final = 0.0

# K-factor base: how aggressively a single result moves a rating.
# 20 is the 538 regular-season default; playoffs typically use ~24.
DEFAULT_K_FACTOR: Final = 20.0

# Data-sufficiency floor for trading on an Elo rating. A never-seen team
# rates INITIAL_RATING, so an Elo "prediction" for it is just the
# 100-Elo home-court prior restated (~0.64 home prob) — enough to clear
# the paper trader's edge gate on a fresh DB with zero information
# behind it (2026-07-01 audit, Tier 1). Expected rating movement is
# roughly K * E[MOV multiplier] * |actual - expected| ~= 10-15 Elo per
# settled game, so ~10 games is the earliest a rating can have absorbed
# signal on the same order as the venue prior it must overcome. Below
# this floor, consumers must not produce trading signals from the rating
# (see NbaEloRatings.has_min_history).
MIN_SETTLED_GAMES_FOR_RATING: Final = 10

# Canonical NBA team abbreviations (30 teams), derived from the odds
# crosswalk's pinned name map so expansion/relocation is updated in
# exactly one place. Any other abbreviation in a ticker or nba_game row
# is payload drift / corruption and must not be rated or traded
# (2026-07-01 audit, Tier 1: unknown teams silently rated 1500).
KNOWN_TEAM_ABBRS: Final[frozenset[str]] = frozenset(TEAM_NAME_TO_ABBR.values())

# Margin-of-victory adjustment scaling. The numerator constant (3) and
# denominator constants (7.5, 0.006) match the 538 published formula.
MOV_OFFSET: Final = 3.0
MOV_DENOM_BASE: Final = 7.5
MOV_DENOM_ELO_COEF: Final = 0.006


def season_start_year(game_date: date) -> int:
    """Map a game date to the fall year of the NBA season it belongs to.

    Seasons run October-June (preseason from early October); nothing is
    played in August/September, so an August cutoff cleanly assigns Jan-Jul
    games to the season that started the previous fall. Derived from the
    date rather than the stored ``nba_game.season`` string because the two
    ingest paths disagree on format ("2024-25" from the scoreboard vs a raw
    ``SEASON_ID`` like "22024" from LeagueGameFinder).

    Replay loops use this to detect season boundaries and apply
    :meth:`NbaEloRatings.regress_to_baseline` between seasons.
    """
    return game_date.year if game_date.month >= 8 else game_date.year - 1


@dataclass(frozen=True, slots=True)
class GameContext:
    """Per-game adjustments stacking on top of base ratings."""

    home_back_to_back: bool = False
    away_back_to_back: bool = False
    home_travel_miles: float = 0.0
    away_travel_miles: float = 0.0


@dataclass
class NbaEloRatings:
    """Mutable container for current per-team Elo ratings.

    Use :func:`update_after_game` to fold a finished game's outcome
    into the ratings. Use :func:`predict_win_prob` to query a
    pre-game home-team win probability without mutation.

    ``games_played`` counts the settled games folded in per team;
    :meth:`has_min_history` is the data-sufficiency gate consumers must
    check before trading on a rating (2026-07-01 audit, Tier 1: a fresh
    state rates every team 1500, and the home-court prior alone cleared
    the paper trader's edge gate).
    """

    ratings: dict[str, float] = field(default_factory=dict)
    games_played: dict[str, int] = field(default_factory=dict)

    def get(self, team_abbr: str) -> float:
        """Return the team's current rating, defaulting new teams to
        the initial rating so unseen teams behave neutrally."""
        return self.ratings.get(team_abbr, INITIAL_RATING)

    def games_recorded(self, team_abbr: str) -> int:
        """Number of settled games folded into this state for the team."""
        return self.games_played.get(team_abbr, 0)

    def has_min_history(
        self, team_abbr: str, *, min_games: int = MIN_SETTLED_GAMES_FOR_RATING
    ) -> bool:
        """True when the team's rating rests on at least ``min_games``
        settled games — the floor below which an Elo-fallback rating
        must not produce trading signals (it would mostly restate the
        home-court prior)."""
        return self.games_recorded(team_abbr) >= min_games

    def regress_to_baseline(self) -> None:
        """Apply the 538 between-seasons regression: pull every team
        toward ``REGRESSION_TARGET`` by ``REGRESSION_FRACTION``.

        Idempotent in the sense that repeated calls converge toward
        the target rather than diverge. Call this once at the start
        of a new season's training pass.
        """
        for team in list(self.ratings):
            current = self.ratings[team]
            self.ratings[team] = (
                current * (1.0 - REGRESSION_FRACTION) + REGRESSION_TARGET * REGRESSION_FRACTION
            )


def adjusted_home_rating(
    home_team_abbr: str,
    *,
    base_rating: float,
    ctx: GameContext,
    travel_penalty_per_mile: float = TRAVEL_PENALTY_PER_MILE,
) -> float:
    """Apply all stacking home-side adjustments to a base rating."""
    adjusted = base_rating + HOME_COURT_ELO
    if ctx.home_back_to_back:
        adjusted += BACK_TO_BACK_ELO
    if home_team_abbr in ALTITUDE_TEAMS:
        adjusted += ALTITUDE_ELO
    adjusted += ctx.home_travel_miles * travel_penalty_per_mile
    return adjusted


def adjusted_away_rating(
    *,
    base_rating: float,
    ctx: GameContext,
    travel_penalty_per_mile: float = TRAVEL_PENALTY_PER_MILE,
) -> float:
    """Apply all stacking away-side adjustments to a base rating.

    No home-court bump; the altitude bonus only applies on home
    soil so the away team doesn't get it even when visiting Denver.
    """
    adjusted = base_rating
    if ctx.away_back_to_back:
        adjusted += BACK_TO_BACK_ELO
    adjusted += ctx.away_travel_miles * travel_penalty_per_mile
    return adjusted


def predict_win_prob(
    *,
    home_rating: float,
    away_rating: float,
    home_team_abbr: str,
    ctx: GameContext | None = None,
    travel_penalty_per_mile: float = TRAVEL_PENALTY_PER_MILE,
) -> float:
    """Return the home-team win probability under the standard logistic
    Elo formula, after stacking home / back-to-back / altitude /
    travel adjustments.

    The result is clipped to (0.001, 0.999) so downstream Brier /
    isotonic / Kelly math stays well-defined at extreme rating
    differences (a +600 Elo gap predicts ~97 % under the raw
    formula; we don't want true zeros / ones in the pipeline).
    """
    actual_ctx = ctx or GameContext()
    h = adjusted_home_rating(
        home_team_abbr,
        base_rating=home_rating,
        ctx=actual_ctx,
        travel_penalty_per_mile=travel_penalty_per_mile,
    )
    a = adjusted_away_rating(
        base_rating=away_rating,
        ctx=actual_ctx,
        travel_penalty_per_mile=travel_penalty_per_mile,
    )
    elo_diff = h - a
    # 538 / standard Elo: P(home wins) = 1 / (1 + 10 ** (-diff / 400)).
    raw = 1.0 / (1.0 + math.pow(10.0, -elo_diff / 400.0))
    return min(0.999, max(0.001, raw))


def margin_of_victory_multiplier(
    *,
    home_score: int,
    away_score: int,
    home_rating: float,
    away_rating: float,
) -> float:
    """The 538 MOV multiplier applied to K. Grows sub-linearly with the
    victory margin and shrinks as the winner's venue-adjusted Elo edge
    grows — the formula explicitly down-weights blowouts by FAVORITES
    (whose big margins are partly autocorrelation) and up-weights
    underdog wins (2026-07-01 audit T4: this docstring previously
    stated the inverse).

    Formula (538, "How Our NBA Predictions Work"):
        m = ((|score_diff| + 3) ** 0.8) / (7.5 + 0.006 * elo_diff_winner)
    where ``elo_diff_winner`` is the winner's Elo edge INCLUDING the
    home-court advantage — 538 computes the diff from the home team's
    HCA-adjusted rating, so venue enters the K scaling too. Omitting it
    biased K by ~8 % per game by venue (2026-07-01 audit, Tier 2).
    Back-to-back / travel / altitude stay out of the update path,
    matching the published methodology.
    """
    score_diff = home_score - away_score
    abs_diff = abs(score_diff)
    home_adjusted = home_rating + HOME_COURT_ELO
    elo_diff_winner = (
        (home_adjusted - away_rating) if score_diff > 0 else (away_rating - home_adjusted)
    )
    numerator = math.pow(abs_diff + MOV_OFFSET, 0.8)
    denominator = MOV_DENOM_BASE + MOV_DENOM_ELO_COEF * elo_diff_winner
    return float(numerator / denominator)


def update_after_game(
    state: NbaEloRatings,
    *,
    home_team_abbr: str,
    away_team_abbr: str,
    home_score: int,
    away_score: int,
    ctx: GameContext | None = None,
    k_factor: float = DEFAULT_K_FACTOR,
    travel_penalty_per_mile: float = TRAVEL_PENALTY_PER_MILE,
) -> NbaEloRatings:
    """Fold a single finished game into ``state``. Returns the same
    ``NbaEloRatings`` object (mutated in place).

    Uses the 538 MOV multiplier on K. Home-court advantage enters both
    the win-probability calculation AND the MOV multiplier's winner Elo
    diff (per the published 538 formula); the remaining adjustments
    (back-to-back, altitude, travel) feed ONLY the win-probability
    calculation, matching the methodology where context affects
    predictions but rating updates are based on on-court outcomes.

    Both teams get the same magnitude rating delta, opposite signs,
    keeping the league-wide rating sum invariant. Each team's
    ``games_played`` count increments by one.
    """
    actual_ctx = ctx or GameContext()
    home_rating_before = state.get(home_team_abbr)
    away_rating_before = state.get(away_team_abbr)
    expected_home = predict_win_prob(
        home_rating=home_rating_before,
        away_rating=away_rating_before,
        home_team_abbr=home_team_abbr,
        ctx=actual_ctx,
        travel_penalty_per_mile=travel_penalty_per_mile,
    )
    actual_home = 1.0 if home_score > away_score else 0.0
    mov_mult = margin_of_victory_multiplier(
        home_score=home_score,
        away_score=away_score,
        home_rating=home_rating_before,
        away_rating=away_rating_before,
    )
    delta = k_factor * mov_mult * (actual_home - expected_home)
    state.ratings[home_team_abbr] = home_rating_before + delta
    state.ratings[away_team_abbr] = away_rating_before - delta
    state.games_played[home_team_abbr] = state.games_played.get(home_team_abbr, 0) + 1
    state.games_played[away_team_abbr] = state.games_played.get(away_team_abbr, 0) + 1
    return state


__all__ = [
    "ALTITUDE_ELO",
    "ALTITUDE_TEAMS",
    "BACK_TO_BACK_ELO",
    "DEFAULT_K_FACTOR",
    "HOME_COURT_ELO",
    "INITIAL_RATING",
    "KNOWN_TEAM_ABBRS",
    "MIN_SETTLED_GAMES_FOR_RATING",
    "REGRESSION_FRACTION",
    "REGRESSION_TARGET",
    "TRAVEL_PENALTY_PER_MILE",
    "GameContext",
    "NbaEloRatings",
    "adjusted_away_rating",
    "adjusted_home_rating",
    "margin_of_victory_multiplier",
    "predict_win_prob",
    "season_start_year",
    "update_after_game",
]
