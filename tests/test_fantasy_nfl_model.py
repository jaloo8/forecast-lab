"""Tests for the fantasy NFL projection model v0.

The arithmetic tests are constructed so shrinkage is a provable no-op
(single-player pools make the position ballast equal the player's own
rates), giving EXACT hand-computable expectations rather than tolerance
soup. The look-ahead test is the one that must never be deleted: the
model itself guards against future rows.
"""

from __future__ import annotations

import pytest

from kq.models.fantasy_nfl import (
    NFLVERSE_TO_ODDS_ABBR,
    ODDS_TO_NFLVERSE_ABBR,
    OPP_ADJ_CLIP,
    fit_residual_quantiles,
    nflverse_abbr,
    project_week,
)


def _row(
    *,
    player_id: str,
    name: str | None = None,
    position: str = "WR",
    team: str = "KC",
    season: int = 2024,
    week: int,
    opponent: str = "BAL",
    targets: int = 0,
    receptions: int = 0,
    rec_yards: float = 0.0,
    rec_tds: int = 0,
    carries: int = 0,
    rush_yards: float = 0.0,
    rush_tds: int = 0,
    pass_yards: float = 0.0,
    pass_tds: int = 0,
    ints: float = 0.0,
    fumbles: float = 0.0,
) -> dict[str, object]:
    pts_std = (
        0.04 * pass_yards
        + 4.0 * pass_tds
        - 2.0 * ints
        + 0.1 * (rush_yards + rec_yards)
        + 6.0 * (rush_tds + rec_tds)
        - 2.0 * fumbles
    )
    return {
        "player_id": player_id,
        "player_name": name or player_id,
        "season": season,
        "week": week,
        "season_type": "REG",
        "team": team,
        "opponent": opponent,
        "position": position,
        "snaps": 60.0,
        "snap_pct": 0.9,
        "targets": targets,
        "receptions": receptions,
        "carries": carries,
        "passing_yards": pass_yards,
        "passing_tds": pass_tds,
        "rushing_yards": rush_yards,
        "rushing_tds": rush_tds,
        "receiving_yards": rec_yards,
        "receiving_tds": rec_tds,
        "fumbles_lost": fumbles,
        "interceptions": ints,
        "red_zone_touches": None,
        "fantasy_points_std": pts_std,
        "fantasy_points_ppr": pts_std + receptions,
    }


def _uniform_wr(
    player_id: str = "wr1", *, weeks: int = 4, team: str = "KC"
) -> list[dict[str, object]]:
    """4 identical games: 8 targets, 6 catches, 80 yds, 1 TD each."""
    return [
        _row(
            player_id=player_id,
            team=team,
            week=w,
            targets=8,
            receptions=6,
            rec_yards=80.0,
            rec_tds=1,
        )
        for w in range(1, weeks + 1)
    ]


# --------------------------- exact arithmetic ---------------------------


def test_volume_times_efficiency_exact_std_and_ppr() -> None:
    """Uniform history + single-player pool -> shrinkage is a no-op and
    the decomposition is exact: std = 8 x (10 x 0.1 + 0.125 x 6) = 14.0,
    PPR adds 8 x 0.75 = 6.0."""
    history = _uniform_wr()
    std = project_week(history, season=2024, week=5, scoring="std", with_quantiles=False)
    ppr = project_week(history, season=2024, week=5, scoring="ppr", with_quantiles=False)
    assert len(std) == len(ppr) == 1
    assert std[0].projected_points == pytest.approx(14.0)
    assert ppr[0].projected_points == pytest.approx(20.0)
    assert std[0].team == "KC"
    assert std[0].position == "WR"


def test_qb_per_game_passing_component_exact() -> None:
    history = [
        _row(
            player_id="qb1",
            position="QB",
            week=w,
            pass_yards=300.0,
            pass_tds=2,
            ints=1.0,
            carries=2,
            rush_yards=10.0,
        )
        for w in range(1, 5)
    ]
    # pass: 300*.04 + 2*4 - 2 = 18.0; rush: 2 carries x (5 ypc x 0.1) = 1.0
    out = project_week(history, season=2024, week=5, scoring="std", with_quantiles=False)
    assert out[0].projected_points == pytest.approx(19.0)


# --------------------------- look-ahead guard ---------------------------


def test_future_rows_cannot_leak_into_projection() -> None:
    history = _uniform_wr()
    future = [
        _row(player_id="wr1", week=5, targets=20, receptions=20, rec_yards=300.0, rec_tds=4),
        _row(player_id="wr1", week=6, targets=20, receptions=20, rec_yards=300.0, rec_tds=4),
    ]
    clean = project_week(history, season=2024, week=5, scoring="std", with_quantiles=False)
    leaky = project_week(
        [*history, *future], season=2024, week=5, scoring="std", with_quantiles=False
    )
    assert leaky[0].projected_points == pytest.approx(clean[0].projected_points)


# --------------------------- eligibility ---------------------------


def test_single_game_player_without_prior_season_is_skipped() -> None:
    history = [
        *_uniform_wr(),
        _row(player_id="rookie", week=4, targets=9, receptions=7, rec_yards=100.0),
    ]
    out = project_week(history, season=2024, week=5, scoring="std", with_quantiles=False)
    assert {p.player_id for p in out} == {"wr1"}


def test_prior_season_fallback_projects_week_one() -> None:
    """No 2025 rows at all: a 2024 veteran is projectable for 2025 week 1;
    single-player pool makes the position-mean shrink a no-op -> exact."""
    history = _uniform_wr(weeks=6)  # 2024 season
    out = project_week(history, season=2025, week=1, scoring="std", with_quantiles=False)
    assert len(out) == 1
    assert out[0].projected_points == pytest.approx(14.0)


# --------------------------- opponent adjustment ---------------------------


def _league_history() -> list[dict[str, object]]:
    """Four WRs on four teams, weeks 1-4. WRs facing AAA score double
    their baseline; WRs facing BBB score half — AAA is a soft defense,
    BBB a stingy one, and the league average sits between."""
    rows: list[dict[str, object]] = []
    schedule = {  # team -> opponent per week (round-robin-ish, static)
        "T1": ["AAA", "BBB", "CCC", "DDD"],
        "T2": ["BBB", "AAA", "DDD", "CCC"],
        "T3": ["CCC", "DDD", "AAA", "BBB"],
        "T4": ["DDD", "CCC", "BBB", "AAA"],
    }
    for team, opps in schedule.items():
        for w, opp in enumerate(opps, start=1):
            scale = {"AAA": 2.0, "BBB": 0.5}.get(opp, 1.0)
            rows.append(
                _row(
                    player_id=f"wr_{team}",
                    team=team,
                    week=w,
                    opponent=opp,
                    targets=8,
                    receptions=6,
                    rec_yards=80.0 * scale,
                    rec_tds=0,
                )
            )
    return rows


def test_opponent_adjustment_direction_and_cap() -> None:
    history = _league_history()
    neutral = project_week(history, season=2024, week=5, scoring="std", with_quantiles=False)
    vs_soft = project_week(
        history,
        season=2024,
        week=5,
        scoring="std",
        opponents={"T1": "AAA"},
        with_quantiles=False,
    )
    vs_stingy = project_week(
        history,
        season=2024,
        week=5,
        scoring="std",
        opponents={"T1": "BBB"},
        with_quantiles=False,
    )
    n = {p.player_id: p.projected_points for p in neutral}
    soft = {p.player_id: p.projected_points for p in vs_soft}
    stingy = {p.player_id: p.projected_points for p in vs_stingy}
    assert soft["wr_T1"] > n["wr_T1"] > stingy["wr_T1"]
    # Other teams got no opponent entry -> untouched.
    assert soft["wr_T2"] == pytest.approx(n["wr_T2"])
    # The multiplicative tilt stays inside the documented clip band.
    assert soft["wr_T1"] / n["wr_T1"] <= OPP_ADJ_CLIP[1] + 1e-9
    assert stingy["wr_T1"] / n["wr_T1"] >= OPP_ADJ_CLIP[0] - 1e-9


# --------------------------- game-script tilt ---------------------------


def test_script_tilt_directions() -> None:
    wr_history = _uniform_wr()
    rb_history = [
        _row(
            player_id="rb1",
            position="RB",
            team="SF",
            week=w,
            carries=18,
            rush_yards=90.0,
            rush_tds=1,
        )
        for w in range(1, 5)
    ]
    history = wr_history + rb_history

    neutral = {
        p.player_id: p.projected_points
        for p in project_week(history, season=2024, week=5, scoring="std", with_quantiles=False)
    }
    tilted = {
        p.player_id: p.projected_points
        for p in project_week(
            history,
            season=2024,
            week=5,
            scoring="std",
            win_probs={"KC": 0.2, "SF": 0.8},  # KC big dog, SF big favorite
            with_quantiles=False,
        )
    }
    assert tilted["wr1"] > neutral["wr1"]  # underdog WR throws more
    assert tilted["rb1"] > neutral["rb1"]  # favorite RB runs the clock
    inverse = {
        p.player_id: p.projected_points
        for p in project_week(
            history,
            season=2024,
            week=5,
            scoring="std",
            win_probs={"KC": 0.8, "SF": 0.2},
            with_quantiles=False,
        )
    }
    assert inverse["wr1"] < neutral["wr1"]
    assert inverse["rb1"] < neutral["rb1"]


# --------------------------- residual quantiles ---------------------------


def _noisy_league(*, weeks: int = 8, n_players: int = 12) -> list[dict[str, object]]:
    """Deterministic +/- alternation around each player's baseline so the
    walk-forward residual pool has real spread without RNG flakiness."""
    rows: list[dict[str, object]] = []
    for i in range(n_players):
        for w in range(1, weeks + 1):
            swing = 40.0 if (i + w) % 2 == 0 else -40.0
            rows.append(
                _row(
                    player_id=f"wr{i}",
                    team=f"T{i}",
                    week=w,
                    opponent=f"D{(i + w) % 4}",
                    targets=8,
                    receptions=6,
                    rec_yards=80.0 + swing,
                    rec_tds=0,
                )
            )
    return rows


def test_quantiles_bound_the_projection() -> None:
    history = _noisy_league()
    out = project_week(history, season=2024, week=9, scoring="std", with_quantiles=True)
    assert out
    for p in out:
        assert p.floor_points is not None and p.ceiling_points is not None
        assert p.floor_points <= p.projected_points <= p.ceiling_points
        assert p.floor_points >= 0.0


def test_quantiles_refused_when_history_too_thin() -> None:
    history = _uniform_wr()
    qmap = fit_residual_quantiles(history, season=2024, through_week=5, scoring="std")
    assert qmap == {}
    out = project_week(history, season=2024, week=5, scoring="std", with_quantiles=True)
    assert out[0].floor_points is None
    assert out[0].ceiling_points is None


# --------------------------- team-code mapping ---------------------------


def test_abbr_mapping_round_trip() -> None:
    assert nflverse_abbr("JAC") == "JAX"
    assert nflverse_abbr("LAR") == "LA"
    assert nflverse_abbr("KC") == "KC"
    assert NFLVERSE_TO_ODDS_ABBR["JAX"] == "JAC"
    assert ODDS_TO_NFLVERSE_ABBR["LAR"] == "LA"
