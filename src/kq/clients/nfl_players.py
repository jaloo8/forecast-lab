"""NFL player-week stats client — wraps the nflverse ecosystem via
``nfl_data_py`` (§9-approved dependency, pinned).

Live-verified against real 2024 payloads (probe 2026-07-27, recorded slices
in ``tests/fixtures/nfl_players/``):

  * ``import_weekly_data`` — one row per (player, season, week); GSIS
    ``player_id`` ("00-0033873"); native ``fantasy_points`` (standard) and
    ``fantasy_points_ppr``; ``season_type`` in {'REG', 'POST'} with
    CONTINUOUS week numbering (playoffs = 19..22). **Seasons >= 2025 404
    on this legacy asset** — the fetcher falls back to the new-scheme
    nflverse release (see ``NFLVERSE_WEEKLY_URL_TEMPLATE``), normalized to
    the same shape; both paths were live-verified.
  * ``import_snap_counts`` — a separate PFR-sourced dataset keyed by
    ``pfr_player_id`` + full player name, NOT GSIS id. Joining it onto
    weekly stats needs the ``import_ids`` crosswalk (pfr_id -> gsis_id),
    with a normalized-name fallback for players the crosswalk misses.
  * ``import_weekly_rosters`` — depth-chart position + roster status per
    (player, week); fetched for the F2 draft-kit lane, not stored in v0.

Threading model: nfl_data_py is sync (downloads nflverse parquet/CSV over
HTTPS). Callers that need async should wrap in ``asyncio.to_thread``.

Testing: the autouse network guard blocks real egress, so tests patch the
``_import_*`` indirection points with recorded-fixture DataFrames — never
the network. Fetchers tolerate per-season failures (a not-yet-published
season 404s) by logging loudly and continuing; a frame missing REQUIRED
columns is rejected wholesale (schema drift means investigate, not guess).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import pandas as pd
import structlog

log = structlog.get_logger(__name__)

# Columns each dataset MUST carry (live-verified 2026-07-27). A frame
# missing any of these is rejected for that season — parsing around drift
# would silently corrupt the training set.
REQUIRED_WEEKLY_COLUMNS: Final[tuple[str, ...]] = (
    "player_id",
    "player_display_name",
    "position",
    "recent_team",
    "season",
    "week",
    "season_type",
    "opponent_team",
    "targets",
    "receptions",
    "carries",
    "passing_yards",
    "passing_tds",
    "interceptions",
    "rushing_yards",
    "rushing_tds",
    "receiving_yards",
    "receiving_tds",
    "sack_fumbles_lost",
    "rushing_fumbles_lost",
    "receiving_fumbles_lost",
    "fantasy_points",
    "fantasy_points_ppr",
)
REQUIRED_SNAP_COLUMNS: Final[tuple[str, ...]] = (
    "season",
    "week",
    "game_type",
    "team",
    "opponent",
    "player",
    "pfr_player_id",
    "position",
    "offense_snaps",
    "offense_pct",
)
REQUIRED_ROSTER_COLUMNS: Final[tuple[str, ...]] = (
    "season",
    "week",
    "team",
    "position",
    "depth_chart_position",
    "status",
    "player_id",
    "player_name",
    "pfr_id",
)
REQUIRED_ID_COLUMNS: Final[tuple[str, ...]] = ("gsis_id", "pfr_id")

_NAME_SUFFIXES: Final[frozenset[str]] = frozenset({"jr", "sr", "ii", "iii", "iv", "v"})


@dataclass(frozen=True, slots=True)
class PlayerWeekStats:
    """One player's stat line for one game week (weekly dataset row)."""

    player_id: str
    player_name: str
    position: str | None
    team: str
    season: int
    week: int
    season_type: str
    opponent: str | None
    targets: int | None
    receptions: int | None
    carries: int | None
    passing_yards: float | None
    passing_tds: int | None
    interceptions: float | None
    rushing_yards: float | None
    rushing_tds: int | None
    receiving_yards: float | None
    receiving_tds: int | None
    fumbles_lost: float | None
    fantasy_points_std: float | None
    fantasy_points_ppr: float | None


@dataclass(frozen=True, slots=True)
class SnapCountRow:
    """One player's snap participation for one game (PFR dataset row)."""

    season: int
    week: int
    game_type: str
    team: str
    opponent: str | None
    player_name: str
    pfr_player_id: str | None
    position: str | None
    offense_snaps: float | None
    offense_pct: float | None


@dataclass(frozen=True, slots=True)
class RosterRow:
    """One player's roster/depth-chart status for one week."""

    season: int
    week: int
    team: str
    position: str | None
    depth_chart_position: str | None
    status: str | None
    player_id: str | None
    player_name: str | None
    pfr_id: str | None


@dataclass(frozen=True, slots=True)
class PlayerGameRow:
    """Storage-shaped merged row — maps 1:1 to ``nfl_player_game`` minus
    ``as_of`` (the repository stamps that at upsert).

    ``red_zone_touches`` is always ``None`` in v0: red-zone usage is not in
    the weekly dataset and needs play-by-play aggregation (documented
    follow-up), so the field exists to keep the storage contract honest,
    not to pretend we have the data.
    """

    player_id: str
    player_name: str
    season: int
    week: int
    season_type: str
    team: str
    opponent: str | None
    position: str | None
    snaps: float | None
    snap_pct: float | None
    targets: int | None
    receptions: int | None
    carries: int | None
    passing_yards: float | None
    passing_tds: int | None
    rushing_yards: float | None
    rushing_tds: int | None
    receiving_yards: float | None
    receiving_tds: int | None
    fumbles_lost: float | None
    interceptions: float | None
    red_zone_touches: float | None
    fantasy_points_std: float | None
    fantasy_points_ppr: float | None


# ---------------------------------------------------------------------------
# nfl_data_py indirection — the patch surface for tests (network-guarded
# suite) and a single seam if the upstream package is ever swapped.

# nflverse restructured its release assets during the 2025 offseason: the
# legacy player_stats_{year}.parquet that nfl_data_py 0.3.2 downloads stops
# at 2024, so import_weekly_data 404s for 2025+ (live-verified 2026-07-27;
# snap counts / rosters / ids still publish under the old names). The
# new-scheme asset carries every column we require under two renames plus
# defense/kicker rows we filter out. Its standard + PPR fantasy-points
# arithmetic was re-verified against 22 real 2025 rows (0 mismatches;
# recorded fixture stats_player_week_2025_w1_kc_phi.csv).
NFLVERSE_WEEKLY_URL_TEMPLATE: Final[str] = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "stats_player/stats_player_week_{season}.parquet"
)
NEW_SCHEME_RENAMES: Final[dict[str, str]] = {
    "team": "recent_team",
    "passing_interceptions": "interceptions",
}
# Offense skill positions only — matches what the legacy dataset contained,
# so both paths feed identical downstream shapes. Kicker scoring needs the
# fg_* columns and a different formula (explicitly out of v0 scope).
NEW_SCHEME_POSITION_GROUPS: Final[frozenset[str]] = frozenset({"QB", "RB", "WR", "TE"})


def _import_weekly(years: list[int]) -> pd.DataFrame:
    import nfl_data_py as nfl  # noqa: PLC0415

    return nfl.import_weekly_data(years)


def _read_weekly_new_scheme(season: int) -> pd.DataFrame:
    """Fetch one season's weekly stats from the new-scheme nflverse asset
    and normalize it to the legacy column shape the parser expects."""
    df = pd.read_parquet(NFLVERSE_WEEKLY_URL_TEMPLATE.format(season=season))
    df = df[df["position_group"].isin(NEW_SCHEME_POSITION_GROUPS)]
    return df.rename(columns=NEW_SCHEME_RENAMES)


def _import_snap_counts(years: list[int]) -> pd.DataFrame:
    import nfl_data_py as nfl  # noqa: PLC0415

    return nfl.import_snap_counts(years)


def _import_weekly_rosters(years: list[int]) -> pd.DataFrame:
    import nfl_data_py as nfl  # noqa: PLC0415

    return nfl.import_weekly_rosters(years)


def _import_ids() -> pd.DataFrame:
    import nfl_data_py as nfl  # noqa: PLC0415

    return nfl.import_ids()


# ---------------------------------------------------------------------------
# Coercers — nflverse frames downcast to numpy float32/int32 with NaN for
# missing; DuckDB binds want native Python scalars with None.


def _f(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _i(value: object) -> int | None:
    f = _f(value)
    return None if f is None else int(f)


def _s(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _require_columns(df: pd.DataFrame, required: Sequence[str], source: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{source} frame missing required columns: {missing}")


def normalize_player_name(name: str) -> str:
    """Collapse a player name for fuzzy joins: lowercase, strip punctuation
    and generational suffixes ("Marvin Harrison Jr." == "marvin harrison")."""
    cleaned = name.lower().replace(".", "").replace("'", "").replace("-", " ")
    tokens = [t for t in cleaned.split() if t]
    while tokens and tokens[-1] in _NAME_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


# ---------------------------------------------------------------------------
# Fetchers


def fetch_weekly_stats(seasons: Sequence[int]) -> list[PlayerWeekStats]:
    """Weekly player stat lines for the given seasons (REG + POST).

    Seasons <= 2024 come through nfl_data_py's legacy asset; when that
    404s (2025+ — see the new-scheme note above) the fetch falls back to
    the new-scheme nflverse asset normalized to the same shape. Per-season
    failures of BOTH paths (season not yet published, transient outage,
    column drift) are logged loudly and skipped; the function returns
    whatever it could fetch.
    """
    out: list[PlayerWeekStats] = []
    for season in dict.fromkeys(int(s) for s in seasons):
        try:
            df = _import_weekly([season])
        except Exception as legacy_exc:
            log.info(
                "nfl_players.weekly_legacy_fetch_failed",
                season=season,
                error=str(legacy_exc),
                action="trying new-scheme nflverse asset",
            )
            try:
                df = _read_weekly_new_scheme(season)
                log.info("nfl_players.weekly_fetched_new_scheme", season=season, n_rows=len(df))
            except Exception as exc:
                log.warning("nfl_players.weekly_fetch_failed", season=season, error=str(exc))
                continue
        try:
            _require_columns(df, REQUIRED_WEEKLY_COLUMNS, f"weekly[{season}]")
        except ValueError as exc:
            log.warning("nfl_players.weekly_fetch_failed", season=season, error=str(exc))
            continue
        out.extend(_weekly_rows_from_frame(df))
    return out


def _weekly_rows_from_frame(df: pd.DataFrame) -> list[PlayerWeekStats]:
    rows: list[PlayerWeekStats] = []
    n_skipped = 0
    for rec in df.to_dict(orient="records"):
        player_id = _s(rec.get("player_id"))
        player_name = _s(rec.get("player_display_name"))
        team = _s(rec.get("recent_team"))
        season = _i(rec.get("season"))
        week = _i(rec.get("week"))
        season_type = _s(rec.get("season_type"))
        if (
            not (player_id and player_name and team and season_type)
            or season is None
            or week is None
        ):
            n_skipped += 1
            continue
        fumble_parts = [
            _f(rec.get("sack_fumbles_lost")),
            _f(rec.get("rushing_fumbles_lost")),
            _f(rec.get("receiving_fumbles_lost")),
        ]
        fumbles_lost = (
            None if all(p is None for p in fumble_parts) else sum(p or 0.0 for p in fumble_parts)
        )
        rows.append(
            PlayerWeekStats(
                player_id=player_id,
                player_name=player_name,
                position=_s(rec.get("position")),
                team=team,
                season=season,
                week=week,
                season_type=season_type,
                opponent=_s(rec.get("opponent_team")),
                targets=_i(rec.get("targets")),
                receptions=_i(rec.get("receptions")),
                carries=_i(rec.get("carries")),
                passing_yards=_f(rec.get("passing_yards")),
                passing_tds=_i(rec.get("passing_tds")),
                interceptions=_f(rec.get("interceptions")),
                rushing_yards=_f(rec.get("rushing_yards")),
                rushing_tds=_i(rec.get("rushing_tds")),
                receiving_yards=_f(rec.get("receiving_yards")),
                receiving_tds=_i(rec.get("receiving_tds")),
                fumbles_lost=fumbles_lost,
                fantasy_points_std=_f(rec.get("fantasy_points")),
                fantasy_points_ppr=_f(rec.get("fantasy_points_ppr")),
            )
        )
    if n_skipped:
        log.warning("nfl_players.weekly_rows_skipped", n_skipped=n_skipped)
    return rows


def fetch_snap_counts(seasons: Sequence[int]) -> list[SnapCountRow]:
    """Per-game snap participation for the given seasons. Same per-season
    failure tolerance as :func:`fetch_weekly_stats`."""
    out: list[SnapCountRow] = []
    for season in dict.fromkeys(int(s) for s in seasons):
        try:
            df = _import_snap_counts([season])
            _require_columns(df, REQUIRED_SNAP_COLUMNS, f"snap_counts[{season}]")
        except Exception as exc:
            log.warning("nfl_players.snap_fetch_failed", season=season, error=str(exc))
            continue
        for rec in df.to_dict(orient="records"):
            season_v = _i(rec.get("season"))
            week = _i(rec.get("week"))
            team = _s(rec.get("team"))
            player_name = _s(rec.get("player"))
            game_type = _s(rec.get("game_type"))
            if season_v is None or week is None or not (team and player_name and game_type):
                continue
            out.append(
                SnapCountRow(
                    season=season_v,
                    week=week,
                    game_type=game_type,
                    team=team,
                    opponent=_s(rec.get("opponent")),
                    player_name=player_name,
                    pfr_player_id=_s(rec.get("pfr_player_id")),
                    position=_s(rec.get("position")),
                    offense_snaps=_f(rec.get("offense_snaps")),
                    offense_pct=_f(rec.get("offense_pct")),
                )
            )
    return out


def fetch_weekly_rosters(seasons: Sequence[int]) -> list[RosterRow]:
    """Weekly roster/depth-chart rows (F2 draft-kit input; not stored in
    v0). Same per-season failure tolerance as the other fetchers."""
    out: list[RosterRow] = []
    for season in dict.fromkeys(int(s) for s in seasons):
        try:
            df = _import_weekly_rosters([season])
            _require_columns(df, REQUIRED_ROSTER_COLUMNS, f"weekly_rosters[{season}]")
        except Exception as exc:
            log.warning("nfl_players.roster_fetch_failed", season=season, error=str(exc))
            continue
        for rec in df.to_dict(orient="records"):
            season_v = _i(rec.get("season"))
            week = _i(rec.get("week"))
            team = _s(rec.get("team"))
            if season_v is None or week is None or not team:
                continue
            out.append(
                RosterRow(
                    season=season_v,
                    week=week,
                    team=team,
                    position=_s(rec.get("position")),
                    depth_chart_position=_s(rec.get("depth_chart_position")),
                    status=_s(rec.get("status")),
                    player_id=_s(rec.get("player_id")),
                    player_name=_s(rec.get("player_name")),
                    pfr_id=_s(rec.get("pfr_id")),
                )
            )
    return out


def fetch_pfr_to_gsis() -> dict[str, str]:
    """The nflverse id crosswalk as a pfr_id -> gsis_id mapping (the snap
    join key). Returns {} on failure — the merge then degrades to the
    normalized-name fallback rather than dying."""
    try:
        df = _import_ids()
        _require_columns(df, REQUIRED_ID_COLUMNS, "ids")
    except Exception as exc:
        log.warning("nfl_players.ids_fetch_failed", error=str(exc))
        return {}
    mapping: dict[str, str] = {}
    for rec in df.to_dict(orient="records"):
        pfr = _s(rec.get("pfr_id"))
        gsis = _s(rec.get("gsis_id"))
        if pfr and gsis:
            mapping[pfr] = gsis
    return mapping


# ---------------------------------------------------------------------------
# Merge


def merge_player_weeks(
    stats: Sequence[PlayerWeekStats],
    snaps: Sequence[SnapCountRow],
    pfr_to_gsis: dict[str, str],
) -> list[PlayerGameRow]:
    """Join snap participation onto weekly stat lines, producing
    storage-shaped rows.

    Join strategy (in order):
      1. exact — snap ``pfr_player_id`` -> GSIS id via the ids crosswalk,
         keyed (gsis_id, season, week);
      2. fallback — (normalized name, team, season, week). A normalized-name
         collision inside one (team, season, week) makes that key AMBIGUOUS
         and it is refused (logged) — a wrong snap count is worse than a
         NULL one.

    Snap-only players (offensive line, defense) have no weekly stats row
    and are intentionally dropped; stats rows with no snap match keep
    ``snaps``/``snap_pct`` NULL.
    """
    by_gsis: dict[tuple[str, int, int], SnapCountRow] = {}
    by_name: dict[tuple[str, str, int, int], SnapCountRow | None] = {}
    for snap in snaps:
        gsis = pfr_to_gsis.get(snap.pfr_player_id or "")
        if gsis:
            by_gsis[(gsis, snap.season, snap.week)] = snap
        name_key = (normalize_player_name(snap.player_name), snap.team, snap.season, snap.week)
        existing = by_name.get(name_key)
        if name_key in by_name:
            if existing is not None and existing.pfr_player_id != snap.pfr_player_id:
                log.warning(
                    "nfl_players.snap_name_collision",
                    name=snap.player_name,
                    team=snap.team,
                    season=snap.season,
                    week=snap.week,
                )
                by_name[name_key] = None
        else:
            by_name[name_key] = snap

    out: list[PlayerGameRow] = []
    for r in stats:
        matched = by_gsis.get((r.player_id, r.season, r.week)) or by_name.get(
            (normalize_player_name(r.player_name), r.team, r.season, r.week)
        )
        out.append(
            PlayerGameRow(
                player_id=r.player_id,
                player_name=r.player_name,
                season=r.season,
                week=r.week,
                season_type=r.season_type,
                team=r.team,
                opponent=r.opponent,
                position=r.position,
                snaps=matched.offense_snaps if matched else None,
                snap_pct=matched.offense_pct if matched else None,
                targets=r.targets,
                receptions=r.receptions,
                carries=r.carries,
                passing_yards=r.passing_yards,
                passing_tds=r.passing_tds,
                rushing_yards=r.rushing_yards,
                rushing_tds=r.rushing_tds,
                receiving_yards=r.receiving_yards,
                receiving_tds=r.receiving_tds,
                fumbles_lost=r.fumbles_lost,
                interceptions=r.interceptions,
                red_zone_touches=None,
                fantasy_points_std=r.fantasy_points_std,
                fantasy_points_ppr=r.fantasy_points_ppr,
            )
        )
    return out


__all__ = [
    "NEW_SCHEME_POSITION_GROUPS",
    "NEW_SCHEME_RENAMES",
    "NFLVERSE_WEEKLY_URL_TEMPLATE",
    "REQUIRED_ID_COLUMNS",
    "REQUIRED_ROSTER_COLUMNS",
    "REQUIRED_SNAP_COLUMNS",
    "REQUIRED_WEEKLY_COLUMNS",
    "PlayerGameRow",
    "PlayerWeekStats",
    "RosterRow",
    "SnapCountRow",
    "fetch_pfr_to_gsis",
    "fetch_snap_counts",
    "fetch_weekly_rosters",
    "fetch_weekly_stats",
    "merge_player_weeks",
    "normalize_player_name",
]
