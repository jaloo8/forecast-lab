"""Tests for the 538-style NBA Elo model.

Coverage:
- Standard Elo logistic at parity / extremes / clipping.
- Home-court / back-to-back / altitude / travel adjustments stack
  in the right direction and magnitude.
- Margin-of-victory multiplier matches 538's published formula on
  worked examples.
- update_after_game is sum-zero across the two teams, scales with
  margin, and handles unseen teams via INITIAL_RATING.
- Between-seasons regression converges toward REGRESSION_TARGET.
- Property tests with hypothesis: rating updates always sum to zero;
  win prob always lies in (0, 1); home advantage strictly increases
  home win prob.
"""

from __future__ import annotations

import math
from datetime import date

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from kq.models.nba_elo import (
    ALTITUDE_ELO,
    ALTITUDE_TEAMS,
    BACK_TO_BACK_ELO,
    DEFAULT_K_FACTOR,
    HOME_COURT_ELO,
    INITIAL_RATING,
    REGRESSION_FRACTION,
    REGRESSION_TARGET,
    GameContext,
    NbaEloRatings,
    adjusted_away_rating,
    adjusted_home_rating,
    margin_of_victory_multiplier,
    predict_win_prob,
    season_start_year,
    update_after_game,
)

# --------------------------- predict_win_prob ---------------------------


def test_parity_with_no_context_returns_home_advantage_prob() -> None:
    """Equal-rated teams; home court alone should bump the home team
    above 0.5. With +100 Elo, P(home) = 1 / (1 + 10**(-100/400)) ~= 0.640."""
    p = predict_win_prob(home_rating=1500.0, away_rating=1500.0, home_team_abbr="BOS")
    assert p == pytest.approx(0.6400, abs=1e-3)


def test_parity_with_back_to_backs_balances_to_50_50() -> None:
    """Both teams on B2B cancels the relative penalty; +100 Elo home
    advantage stays."""
    ctx = GameContext(home_back_to_back=True, away_back_to_back=True)
    p = predict_win_prob(home_rating=1500.0, away_rating=1500.0, home_team_abbr="BOS", ctx=ctx)
    # Same as parity-no-context (both b2b cancels, home advantage remains).
    assert p == pytest.approx(0.6400, abs=1e-3)


def test_home_b2b_only_drops_below_parity() -> None:
    """Home on a back-to-back, away rested -> home advantage shrinks
    by 46 Elo (HOME_COURT_ELO + BACK_TO_BACK_ELO = 100 - 46 = +54 net)."""
    ctx = GameContext(home_back_to_back=True, away_back_to_back=False)
    p = predict_win_prob(home_rating=1500.0, away_rating=1500.0, home_team_abbr="BOS", ctx=ctx)
    expected_diff = HOME_COURT_ELO + BACK_TO_BACK_ELO  # 54
    expected = 1.0 / (1.0 + 10.0 ** (-expected_diff / 400.0))
    assert p == pytest.approx(expected, abs=1e-3)


def test_altitude_bonus_only_applies_at_home_for_listed_team() -> None:
    """KDEN at home gets +30 Elo; same matchup with KDEN on the road
    should NOT get the bonus."""
    p_home = predict_win_prob(home_rating=1500.0, away_rating=1500.0, home_team_abbr="DEN")
    p_away = predict_win_prob(home_rating=1500.0, away_rating=1500.0, home_team_abbr="LAL")
    # Difference between the two should equal the altitude bonus's
    # contribution: ~ +30 Elo on the home side.
    expected_home = 1.0 / (1.0 + 10.0 ** (-(HOME_COURT_ELO + ALTITUDE_ELO) / 400.0))
    expected_lal_home = 1.0 / (1.0 + 10.0 ** (-HOME_COURT_ELO / 400.0))
    assert p_home == pytest.approx(expected_home, abs=1e-3)
    assert p_away == pytest.approx(expected_lal_home, abs=1e-3)


def test_extreme_ratings_get_clipped() -> None:
    """A 600 Elo rating gap is ~97 % home win, but raw Elo can hit
    99 %+ on absurd inputs. Verify the (0.001, 0.999) clip holds."""
    # +1000 Elo gap -> raw ~99.7 % which is past our 0.999 ceiling.
    p_high = predict_win_prob(home_rating=2500.0, away_rating=1500.0, home_team_abbr="BOS")
    assert 0.001 < p_high < 1.0
    assert p_high <= 0.999
    # -1000 Elo gap -> below our 0.001 floor.
    p_low = predict_win_prob(home_rating=500.0, away_rating=1500.0, home_team_abbr="BOS")
    assert 0.0 < p_low < 1.0
    assert p_low >= 0.001


def test_travel_penalty_default_is_zero_no_op() -> None:
    """v1 default travel rate is 0; travel_miles fields are inert
    until callers override the rate."""
    ctx_with_travel = GameContext(home_travel_miles=1000.0, away_travel_miles=2000.0)
    p_no_travel = predict_win_prob(home_rating=1500.0, away_rating=1500.0, home_team_abbr="BOS")
    p_default_rate = predict_win_prob(
        home_rating=1500.0,
        away_rating=1500.0,
        home_team_abbr="BOS",
        ctx=ctx_with_travel,
    )
    assert p_no_travel == p_default_rate


def test_travel_penalty_is_applied_when_rate_set() -> None:
    """Override the travel rate -> away travel hurts the away team."""
    ctx = GameContext(home_travel_miles=0.0, away_travel_miles=1000.0)
    p = predict_win_prob(
        home_rating=1500.0,
        away_rating=1500.0,
        home_team_abbr="BOS",
        ctx=ctx,
        travel_penalty_per_mile=-0.045,  # 538-cited rate
    )
    # Home advantage + (-(-0.045 * 1000)) = +100 + 45 Elo
    # away has -0.045*1000 = -45 Elo, home has 0; net diff = 145.
    expected = 1.0 / (1.0 + 10.0 ** (-(100.0 + 45.0) / 400.0))
    assert p == pytest.approx(expected, abs=1e-3)


# --------------------------- adjustments stack ---------------------------


def test_adjusted_home_rating_stacks_all_modifiers() -> None:
    """Home + B2B + altitude + travel all sum on the home side."""
    ctx = GameContext(home_back_to_back=True, home_travel_miles=500.0)
    rating = adjusted_home_rating(
        "DEN",
        base_rating=1500.0,
        ctx=ctx,
        travel_penalty_per_mile=-0.045,
    )
    expected = 1500.0 + HOME_COURT_ELO + BACK_TO_BACK_ELO + ALTITUDE_ELO + (500.0 * -0.045)
    assert rating == pytest.approx(expected)


def test_adjusted_away_rating_excludes_home_court_and_altitude() -> None:
    """Away side never gets home-court or altitude bonuses, even when
    visiting a high-altitude team."""
    ctx = GameContext(away_back_to_back=True, away_travel_miles=500.0)
    rating = adjusted_away_rating(
        base_rating=1500.0,
        ctx=ctx,
        travel_penalty_per_mile=-0.045,
    )
    expected = 1500.0 + BACK_TO_BACK_ELO + (500.0 * -0.045)
    assert rating == pytest.approx(expected)
    # No home-court, no altitude on the away side.
    assert "DEN" in ALTITUDE_TEAMS
    assert HOME_COURT_ELO not in (rating - 1500.0,)


# --------------------------- margin_of_victory_multiplier ---------------------------


def test_mov_multiplier_at_one_point_equal_ratings_is_canonical_value() -> None:
    """1-point home win between equal-rated teams: m = (1+3)**0.8 / 7.5 ~= 0.404."""
    m = margin_of_victory_multiplier(
        home_score=101, away_score=100, home_rating=1500.0, away_rating=1500.0
    )
    expected = math.pow(4.0, 0.8) / 7.5
    assert m == pytest.approx(expected)


def test_mov_multiplier_grows_with_margin() -> None:
    m_close = margin_of_victory_multiplier(
        home_score=101, away_score=100, home_rating=1500.0, away_rating=1500.0
    )
    m_blowout = margin_of_victory_multiplier(
        home_score=130, away_score=100, home_rating=1500.0, away_rating=1500.0
    )
    assert m_blowout > m_close


def test_mov_multiplier_dampens_for_favored_winners() -> None:
    """Same on-court score; a heavily favored winner gets a *smaller*
    multiplier (rating goes up less) than an underdog winner with the
    same score. This is the 538 dampening property."""
    m_underdog = margin_of_victory_multiplier(
        home_score=110, away_score=100, home_rating=1400.0, away_rating=1600.0
    )
    m_favorite = margin_of_victory_multiplier(
        home_score=110, away_score=100, home_rating=1600.0, away_rating=1400.0
    )
    assert m_underdog > m_favorite


# --------------------------- update_after_game ---------------------------


def test_update_after_game_is_sum_zero_across_teams() -> None:
    """Both teams' rating deltas should be equal magnitude opposite
    sign -- the league-wide rating sum is invariant."""
    state = NbaEloRatings()
    update_after_game(
        state,
        home_team_abbr="LAL",
        away_team_abbr="BOS",
        home_score=110,
        away_score=100,
    )
    delta_lal = state.ratings["LAL"] - INITIAL_RATING
    delta_bos = state.ratings["BOS"] - INITIAL_RATING
    assert delta_lal == pytest.approx(-delta_bos)


def test_update_after_game_handles_unseen_teams() -> None:
    """Both teams missing from state should default to INITIAL_RATING
    before the update."""
    state = NbaEloRatings()
    update_after_game(
        state,
        home_team_abbr="UNKNOWN1",
        away_team_abbr="UNKNOWN2",
        home_score=120,
        away_score=100,
    )
    # Home won by 20; both teams started at INITIAL_RATING.
    assert state.ratings["UNKNOWN1"] > INITIAL_RATING
    assert state.ratings["UNKNOWN2"] < INITIAL_RATING


def test_update_after_game_scales_with_margin() -> None:
    state_close = NbaEloRatings()
    update_after_game(
        state_close,
        home_team_abbr="LAL",
        away_team_abbr="BOS",
        home_score=101,
        away_score=100,
    )
    state_blowout = NbaEloRatings()
    update_after_game(
        state_blowout,
        home_team_abbr="LAL",
        away_team_abbr="BOS",
        home_score=130,
        away_score=100,
    )
    delta_close = state_close.ratings["LAL"] - INITIAL_RATING
    delta_blowout = state_blowout.ratings["LAL"] - INITIAL_RATING
    assert delta_blowout > delta_close


def test_update_after_game_k_factor_overridable() -> None:
    """A higher K -> larger absolute rating swing on the same input."""
    state_low_k = NbaEloRatings()
    update_after_game(
        state_low_k,
        home_team_abbr="LAL",
        away_team_abbr="BOS",
        home_score=110,
        away_score=100,
        k_factor=10.0,
    )
    state_high_k = NbaEloRatings()
    update_after_game(
        state_high_k,
        home_team_abbr="LAL",
        away_team_abbr="BOS",
        home_score=110,
        away_score=100,
        k_factor=40.0,
    )
    assert abs(state_high_k.ratings["LAL"] - INITIAL_RATING) > abs(
        state_low_k.ratings["LAL"] - INITIAL_RATING
    )


def test_default_k_factor_pinned() -> None:
    """20 is the 538 regular-season default; pin it so changes are
    deliberate."""
    assert DEFAULT_K_FACTOR == 20.0


# --------------------------- regression toward baseline ---------------------------


def test_regress_to_baseline_pulls_high_team_down() -> None:
    state = NbaEloRatings(ratings={"BOS": 1700.0, "LAL": 1300.0})
    state.regress_to_baseline()
    expected_bos = 1700.0 * (1 - REGRESSION_FRACTION) + REGRESSION_TARGET * REGRESSION_FRACTION
    expected_lal = 1300.0 * (1 - REGRESSION_FRACTION) + REGRESSION_TARGET * REGRESSION_FRACTION
    assert state.ratings["BOS"] == pytest.approx(expected_bos)
    assert state.ratings["LAL"] == pytest.approx(expected_lal)


def test_regress_to_baseline_converges_with_repeated_calls() -> None:
    """Repeated regression converges to REGRESSION_TARGET."""
    state = NbaEloRatings(ratings={"BOS": 1700.0})
    for _ in range(50):
        state.regress_to_baseline()
    assert state.ratings["BOS"] == pytest.approx(REGRESSION_TARGET, abs=1e-3)


# --------------------------- property tests ---------------------------


@given(
    home_rating=st.floats(min_value=1000.0, max_value=2000.0),
    away_rating=st.floats(min_value=1000.0, max_value=2000.0),
)
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=200)
def test_predict_win_prob_always_in_unit_interval(home_rating: float, away_rating: float) -> None:
    p = predict_win_prob(home_rating=home_rating, away_rating=away_rating, home_team_abbr="BOS")
    assert 0.0 < p < 1.0


@given(
    home_rating=st.floats(min_value=1000.0, max_value=2000.0),
    away_rating=st.floats(min_value=1000.0, max_value=2000.0),
)
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=200)
def test_home_advantage_strictly_increases_win_prob(home_rating: float, away_rating: float) -> None:
    """Same matchup with vs without the home-court bonus -> the bonused
    side has strictly higher win prob. Verifies via two predict calls
    on identical ratings (LAL = no altitude) where the only
    difference is which team is "home"."""
    p_home_lal = predict_win_prob(
        home_rating=home_rating, away_rating=away_rating, home_team_abbr="LAL"
    )
    p_home_bos = predict_win_prob(
        home_rating=away_rating, away_rating=home_rating, home_team_abbr="BOS"
    )
    # Both should sum to >= 1 because both home-court bonuses lean
    # toward whichever team is "home" in that scenario.
    # When LAL is home with rating r1 vs BOS rating r2: P(LAL).
    # When BOS is home with rating r2 vs LAL rating r1: P(BOS).
    # Sum should equal 1 + (some home-advantage-driven margin).
    assert p_home_lal + p_home_bos > 1.0


@given(
    home_score=st.integers(min_value=80, max_value=140),
    away_score=st.integers(min_value=80, max_value=140),
    base_h=st.floats(min_value=1300.0, max_value=1700.0),
    base_a=st.floats(min_value=1300.0, max_value=1700.0),
)
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=200)
def test_update_after_game_preserves_rating_sum(
    home_score: int, away_score: int, base_h: float, base_a: float
) -> None:
    """League rating sum invariant under any single game update."""
    if home_score == away_score:
        return  # not a real outcome; ties don't happen in NBA regulation+OT
    state = NbaEloRatings(ratings={"H": base_h, "A": base_a})
    sum_before = state.ratings["H"] + state.ratings["A"]
    update_after_game(
        state,
        home_team_abbr="H",
        away_team_abbr="A",
        home_score=home_score,
        away_score=away_score,
    )
    sum_after = state.ratings["H"] + state.ratings["A"]
    assert sum_before == pytest.approx(sum_after, abs=1e-9)


# --------------------------- season_start_year ---------------------------


def test_season_start_year_assigns_fall_and_spring_to_same_season() -> None:
    """October 2025 through June 2026 is all the 2025-26 season; the
    August cutoff starts the next season (nothing is played Aug/Sep)."""
    assert season_start_year(date(2025, 10, 21)) == 2025  # opening night
    assert season_start_year(date(2025, 12, 25)) == 2025  # Christmas slate
    assert season_start_year(date(2026, 1, 15)) == 2025  # mid-season
    assert season_start_year(date(2026, 6, 15)) == 2025  # Finals
    assert season_start_year(date(2026, 7, 31)) == 2025  # edge: pre-cutoff
    assert season_start_year(date(2026, 8, 1)) == 2026  # edge: cutoff
    assert season_start_year(date(2026, 10, 20)) == 2026  # next opening night
