"""Fantasy NFL projection model v0 — volume-share x efficiency (F1b).

Projects per-player fantasy points for a target (season, week) from the
``nfl_player_game`` history, under BOTH scoring formats (owner decision:
Standard and PPR are first-class; the ``scoring`` knob selects per call
and half-PPR is the mean of the two outputs).

Decomposition (the grain the stored columns support — pass attempts are
not stored, so passing efficiency is per-game, receiving/rushing are
per-touch):

    rec_pts  = targets_pg x (yds/target x 0.1 + rec_TD/target x 6)
               [+ PPR: targets_pg x catch_rate x 1.0]
    rush_pts = carries_pg x (yds/carry x 0.1 + rush_TD/carry x 6)
    pass_pts = 0.04 x pass_yds_pg + 4 x pass_TD_pg - 2 x INT_pg
    base     = rec + rush + pass - 2 x fumbles_lost_pg
    proj     = base x opp_position_adj x game_script_adj

with recency-weighted volume (half-life 3 games over the last 8),
per-touch efficiency shrunk toward position means (k=20 touches), an
opponent-vs-position adjustment (points allowed per game vs league
average, shrunk by games observed, clipped ±20%), and a game-script tilt
from the devigged moneyline win probability.

Honesty notes, load-bearing:

  * **Game environment is devigged WIN PROB, not an implied team total.**
    The odds lane ingests only the ``h2h`` market (verified in code +
    schema 2026-07-27) — spreads/totals are not stored, so true implied
    team totals are impossible today. The script tilt is a small
    PRIOR-based coefficient per position (underdogs pass more, favorites
    run more), clipped to ±8%, NOT fitted — fitting it from one season
    of moneyline-only data would be overfit theater. Upgrading to real
    implied totals requires extending the odds ingest (roadmapped).
  * **Floor/ceiling are empirical residual quantiles** (p10/p90) from a
    same-season walk-forward replay of this exact model — each historical
    week projected using only data before it. Too few residuals → the
    bounds are ``None``, never invented.
  * **Look-ahead is guarded in the model itself**: rows at/after the
    target (season, week) are dropped before anything is computed, so a
    caller passing the full table cannot leak the future.
  * ``scikit-learn at most`` (§2): v0 uses none — closed-form shrinkage
    is auditable; the ML budget stays unspent until the self-scoring
    ledger says the baseline is worth beating.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal

import numpy as np
import structlog

log = structlog.get_logger(__name__)

Scoring = Literal["std", "ppr"]

MODEL_VERSION: Final[str] = "fantasy_nfl_v0"

HALF_LIFE_GAMES: Final[float] = 3.0
MAX_TRAILING_GAMES: Final[int] = 8
MIN_SAME_SEASON_GAMES: Final[int] = 2
MIN_PRIOR_SEASON_GAMES: Final[int] = 4
PRIOR_SEASON_SHRINK: Final[float] = 0.30  # toward position mean when falling back a season
EFF_SHRINK_TOUCHES: Final[float] = 20.0  # k touches of position-mean ballast per efficiency rate
OPP_ADJ_SHRINK_GAMES: Final[float] = 4.0
OPP_ADJ_CLIP: Final[tuple[float, float]] = (0.8, 1.2)
SCRIPT_ADJ_CLIP: Final[tuple[float, float]] = (0.92, 1.08)
# Tilt per unit (win_prob - 0.5): negative -> underdog boost (pass-catchers
# chase points), positive -> favorite boost (leading teams run the clock).
# PRIORS, not fits — see module docstring.
SCRIPT_BETA_BY_POSITION: Final[dict[str, float]] = {
    "QB": -0.16,
    "WR": -0.16,
    "TE": -0.10,
    "RB": 0.20,
}
MIN_RESIDUALS_PER_POSITION: Final[int] = 30
MIN_RESIDUALS_POOLED: Final[int] = 30

# nflverse team codes (what nfl_player_game stores) vs the odds/Kalshi lane
# codes (nfl_game / nfl_odds, prod-enumerated 2026-07-02). Only two differ.
ODDS_TO_NFLVERSE_ABBR: Final[dict[str, str]] = {"JAC": "JAX", "LAR": "LA"}
NFLVERSE_TO_ODDS_ABBR: Final[dict[str, str]] = {v: k for k, v in ODDS_TO_NFLVERSE_ABBR.items()}


def nflverse_abbr(odds_abbr: str) -> str:
    """Map an odds-lane/Kalshi team code to the nflverse code."""
    return ODDS_TO_NFLVERSE_ABBR.get(odds_abbr, odds_abbr)


@dataclass(frozen=True, slots=True)
class PlayerProjection:
    """One player's projected fantasy points for one week, one format."""

    player_id: str
    player_name: str
    season: int
    week: int
    team: str
    position: str
    scoring: Scoring
    projected_points: float
    floor_points: float | None
    ceiling_points: float | None


def _f(row: Mapping[str, object], key: str) -> float:
    v = row.get(key)
    if isinstance(v, int | float):
        return float(v)
    return 0.0


def _i(row: Mapping[str, object], key: str) -> int:
    return int(_f(row, key))


def _s(row: Mapping[str, object], key: str) -> str:
    v = row.get(key)
    return "" if v is None else str(v)


def _past_only(
    history: Sequence[Mapping[str, object]], *, season: int, week: int
) -> list[Mapping[str, object]]:
    """The model-side look-ahead guard: strictly before (season, week)."""
    out: list[Mapping[str, object]] = []
    for r in history:
        r_season, r_week = _i(r, "season"), _i(r, "week")
        if r_season < season or (r_season == season and r_week < week):
            out.append(r)
    return out


@dataclass(frozen=True, slots=True)
class _PositionRates:
    """League per-touch rates by position (the shrinkage ballast)."""

    ypt: float  # receiving yards per target
    catch_rate: float
    rec_td_rate: float  # receiving TD per target
    ypc: float  # rushing yards per carry
    rush_td_rate: float  # rushing TD per carry
    points_pg_std: float
    points_pg_ppr: float


def _position_rates(pool: Sequence[Mapping[str, object]]) -> dict[str, _PositionRates]:
    sums: dict[str, dict[str, float]] = {}
    for r in pool:
        pos = _s(r, "position") or "OTHER"
        s = sums.setdefault(
            pos,
            {
                "targets": 0.0,
                "receptions": 0.0,
                "rec_yards": 0.0,
                "rec_tds": 0.0,
                "carries": 0.0,
                "rush_yards": 0.0,
                "rush_tds": 0.0,
                "games": 0.0,
                "pts_std": 0.0,
                "pts_ppr": 0.0,
            },
        )
        s["targets"] += _f(r, "targets")
        s["receptions"] += _f(r, "receptions")
        s["rec_yards"] += _f(r, "receiving_yards")
        s["rec_tds"] += _f(r, "receiving_tds")
        s["carries"] += _f(r, "carries")
        s["rush_yards"] += _f(r, "rushing_yards")
        s["rush_tds"] += _f(r, "rushing_tds")
        s["games"] += 1.0
        s["pts_std"] += _f(r, "fantasy_points_std")
        s["pts_ppr"] += _f(r, "fantasy_points_ppr")

    def rate(num: float, den: float) -> float:
        return num / den if den > 0 else 0.0

    return {
        pos: _PositionRates(
            ypt=rate(s["rec_yards"], s["targets"]),
            catch_rate=rate(s["receptions"], s["targets"]),
            rec_td_rate=rate(s["rec_tds"], s["targets"]),
            ypc=rate(s["rush_yards"], s["carries"]),
            rush_td_rate=rate(s["rush_tds"], s["carries"]),
            points_pg_std=rate(s["pts_std"], s["games"]),
            points_pg_ppr=rate(s["pts_ppr"], s["games"]),
        )
        for pos, s in sums.items()
    }


_NEUTRAL_RATES = _PositionRates(
    ypt=0.0,
    catch_rate=0.0,
    rec_td_rate=0.0,
    ypc=0.0,
    rush_td_rate=0.0,
    points_pg_std=0.0,
    points_pg_ppr=0.0,
)


def _opp_allowed_adj(
    pool: Sequence[Mapping[str, object]], *, season: int, scoring: Scoring
) -> dict[tuple[str, str], float]:
    """(defense_team, position) -> multiplicative adjustment, from fantasy
    points ALLOWED per game vs the league average, shrunk + clipped."""
    pts_key = "fantasy_points_std" if scoring == "std" else "fantasy_points_ppr"
    allowed: dict[tuple[str, str], float] = {}
    games: dict[tuple[str, str], set[int]] = {}
    for r in pool:
        if _i(r, "season") != season:
            continue
        opp = _s(r, "opponent")
        if not opp:
            continue
        pos = _s(r, "position") or "OTHER"
        key = (opp, pos)
        allowed[key] = allowed.get(key, 0.0) + _f(r, pts_key)
        games.setdefault(key, set()).add(_i(r, "week"))

    per_game: dict[tuple[str, str], tuple[float, int]] = {}
    league: dict[str, list[float]] = {}
    for key, total in allowed.items():
        n = len(games[key])
        if n == 0:
            continue
        pg = total / n
        per_game[key] = (pg, n)
        league.setdefault(key[1], []).append(pg)

    out: dict[tuple[str, str], float] = {}
    for (team, pos), (pg, n) in per_game.items():
        pos_league = league.get(pos, [])
        avg = sum(pos_league) / len(pos_league) if pos_league else 0.0
        if avg <= 0:
            continue
        raw = pg / avg
        shrunk = 1.0 + (raw - 1.0) * (n / (n + OPP_ADJ_SHRINK_GAMES))
        out[(team, pos)] = float(np.clip(shrunk, *OPP_ADJ_CLIP))
    return out


def _script_adj(position: str, win_prob: float | None) -> float:
    if win_prob is None:
        return 1.0
    beta = SCRIPT_BETA_BY_POSITION.get(position, 0.0)
    return float(np.clip(1.0 + beta * (win_prob - 0.5), *SCRIPT_ADJ_CLIP))


@dataclass(frozen=True, slots=True)
class _BaseProjection:
    player_id: str
    player_name: str
    team: str
    position: str
    base_points: float


def _weighted_base(
    rows: Sequence[Mapping[str, object]],
    *,
    scoring: Scoring,
    pos_rates: _PositionRates,
    recency_weighted: bool,
) -> float:
    """Volume x efficiency base points from a player's trailing rows
    (most recent LAST). Uniform weights for prior-season fallback."""
    n = len(rows)
    weights: list[float]
    if recency_weighted:
        weights = [0.5 ** ((n - 1 - i) / HALF_LIFE_GAMES) for i in range(n)]
    else:
        weights = [1.0] * n
    w_sum = sum(weights)

    def wmean(key: str) -> float:
        return sum(w * _f(r, key) for w, r in zip(weights, rows, strict=True)) / w_sum

    def wtotal(key: str) -> float:
        return sum(w * _f(r, key) for w, r in zip(weights, rows, strict=True))

    k = EFF_SHRINK_TOUCHES
    targets_pg = wmean("targets")
    carries_pg = wmean("carries")
    w_targets = wtotal("targets")
    w_carries = wtotal("carries")

    ypt = (wtotal("receiving_yards") + k * pos_rates.ypt) / (w_targets + k)
    catch_rate = (wtotal("receptions") + k * pos_rates.catch_rate) / (w_targets + k)
    rec_td_rate = (wtotal("receiving_tds") + k * pos_rates.rec_td_rate) / (w_targets + k)
    ypc = (wtotal("rushing_yards") + k * pos_rates.ypc) / (w_carries + k)
    rush_td_rate = (wtotal("rushing_tds") + k * pos_rates.rush_td_rate) / (w_carries + k)

    rec_pts = targets_pg * (ypt * 0.1 + rec_td_rate * 6.0)
    if scoring == "ppr":
        rec_pts += targets_pg * catch_rate * 1.0
    rush_pts = carries_pg * (ypc * 0.1 + rush_td_rate * 6.0)
    pass_pts = (
        0.04 * wmean("passing_yards") + 4.0 * wmean("passing_tds") - 2.0 * wmean("interceptions")
    )
    fumble_pts = -2.0 * wmean("fumbles_lost")
    return rec_pts + rush_pts + pass_pts + fumble_pts


def _base_projections(
    pool: Sequence[Mapping[str, object]], *, season: int, scoring: Scoring
) -> list[_BaseProjection]:
    """Per-player base points (before opponent/script adjustment) for every
    player projectable from ``pool``: same-season trailing form when they
    have >= MIN_SAME_SEASON_GAMES, else prior-season fallback shrunk toward
    the position mean, else skipped."""
    rates = _position_rates(pool)
    by_player: dict[str, list[Mapping[str, object]]] = {}
    for r in sorted(pool, key=lambda r: (_i(r, "season"), _i(r, "week"))):
        by_player.setdefault(_s(r, "player_id"), []).append(r)

    out: list[_BaseProjection] = []
    for player_id, rows in by_player.items():
        current = [r for r in rows if _i(r, "season") == season][-MAX_TRAILING_GAMES:]
        prior = [r for r in rows if _i(r, "season") == season - 1][-MAX_TRAILING_GAMES:]
        latest = rows[-1]
        position = _s(latest, "position") or "OTHER"
        pos_rates = rates.get(position, _NEUTRAL_RATES)
        if len(current) >= MIN_SAME_SEASON_GAMES:
            base = _weighted_base(
                current, scoring=scoring, pos_rates=pos_rates, recency_weighted=True
            )
        elif len(prior) >= MIN_PRIOR_SEASON_GAMES:
            raw = _weighted_base(
                prior, scoring=scoring, pos_rates=pos_rates, recency_weighted=False
            )
            pos_mean = pos_rates.points_pg_std if scoring == "std" else pos_rates.points_pg_ppr
            base = (1.0 - PRIOR_SEASON_SHRINK) * raw + PRIOR_SEASON_SHRINK * pos_mean
        else:
            continue
        out.append(
            _BaseProjection(
                player_id=player_id,
                player_name=_s(latest, "player_name"),
                team=_s(latest, "team"),
                position=position,
                base_points=base,
            )
        )
    return out


def _project_unbounded(
    history: Sequence[Mapping[str, object]],
    *,
    season: int,
    week: int,
    scoring: Scoring,
    opponents: Mapping[str, str] | None,
    win_probs: Mapping[str, float] | None,
) -> list[PlayerProjection]:
    pool = _past_only(history, season=season, week=week)
    if not pool:
        return []
    opp_adj = _opp_allowed_adj(pool, season=season, scoring=scoring)
    out: list[PlayerProjection] = []
    for bp in _base_projections(pool, season=season, scoring=scoring):
        opponent = (opponents or {}).get(bp.team)
        adj = opp_adj.get((opponent, bp.position), 1.0) if opponent else 1.0
        script = _script_adj(bp.position, (win_probs or {}).get(bp.team))
        out.append(
            PlayerProjection(
                player_id=bp.player_id,
                player_name=bp.player_name,
                season=season,
                week=week,
                team=bp.team,
                position=bp.position,
                scoring=scoring,
                projected_points=bp.base_points * adj * script,
                floor_points=None,
                ceiling_points=None,
            )
        )
    return out


def fit_residual_quantiles(
    history: Sequence[Mapping[str, object]],
    *,
    season: int,
    through_week: int,
    scoring: Scoring,
) -> dict[str, tuple[float, float]]:
    """Position -> (p10, p90) residual offsets from a same-season
    walk-forward replay: each week < ``through_week`` is projected with
    only the data before it (opponents taken from that week's own rows —
    known retrospectively; game script neutral, which widens residuals
    slightly and errs conservative). Falls back to a pooled all-position
    quantile when a position is thin; returns {} when even the pool is
    too thin to be honest."""
    pts_key = "fantasy_points_std" if scoring == "std" else "fantasy_points_ppr"
    season_rows = [r for r in history if _i(r, "season") == season]
    weeks = sorted({_i(r, "week") for r in season_rows if _i(r, "week") < through_week})
    residuals: dict[str, list[float]] = {}
    for w in weeks:
        week_rows = [r for r in season_rows if _i(r, "week") == w]
        actual_by_player = {_s(r, "player_id"): _f(r, pts_key) for r in week_rows}
        opponents = {
            _s(r, "team"): _s(r, "opponent")
            for r in week_rows
            if _s(r, "team") and _s(r, "opponent")
        }
        for proj in _project_unbounded(
            history, season=season, week=w, scoring=scoring, opponents=opponents, win_probs=None
        ):
            actual = actual_by_player.get(proj.player_id)
            if actual is None:
                continue  # did not play — the MAE ledger owns that miss, not the quantiles
            residuals.setdefault(proj.position, []).append(actual - proj.projected_points)

    pooled = [res for lst in residuals.values() for res in lst]
    if len(pooled) < MIN_RESIDUALS_POOLED:
        return {}
    pooled_q = (float(np.quantile(pooled, 0.1)), float(np.quantile(pooled, 0.9)))
    out: dict[str, tuple[float, float]] = {"__pooled__": pooled_q}
    for pos, lst in residuals.items():
        if len(lst) >= MIN_RESIDUALS_PER_POSITION:
            out[pos] = (float(np.quantile(lst, 0.1)), float(np.quantile(lst, 0.9)))
    return out


def project_week(
    history: Sequence[Mapping[str, object]],
    *,
    season: int,
    week: int,
    scoring: Scoring,
    opponents: Mapping[str, str] | None = None,
    win_probs: Mapping[str, float] | None = None,
    with_quantiles: bool = True,
) -> list[PlayerProjection]:
    """Project every projectable player for (season, week) under one
    scoring format. ``opponents`` / ``win_probs`` are keyed by nflverse
    team code; missing entries degrade to neutral adjustments (the odds
    lane being down must never block projections)."""
    projections = _project_unbounded(
        history, season=season, week=week, scoring=scoring, opponents=opponents, win_probs=win_probs
    )
    if not with_quantiles or not projections:
        return projections
    qmap = fit_residual_quantiles(history, season=season, through_week=week, scoring=scoring)
    if not qmap:
        return projections
    out: list[PlayerProjection] = []
    for p in projections:
        q10, q90 = qmap.get(p.position, qmap["__pooled__"])
        out.append(
            PlayerProjection(
                player_id=p.player_id,
                player_name=p.player_name,
                season=p.season,
                week=p.week,
                team=p.team,
                position=p.position,
                scoring=p.scoring,
                projected_points=p.projected_points,
                floor_points=max(0.0, p.projected_points + q10),
                ceiling_points=p.projected_points + q90,
            )
        )
    return out


__all__ = [
    "MODEL_VERSION",
    "NFLVERSE_TO_ODDS_ABBR",
    "ODDS_TO_NFLVERSE_ABBR",
    "PlayerProjection",
    "Scoring",
    "fit_residual_quantiles",
    "nflverse_abbr",
    "project_week",
]
