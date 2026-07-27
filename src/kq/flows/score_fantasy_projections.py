"""Score stored fantasy projections against actuals (F1b) — the
reality-contact ledger for the fantasy lane, same discipline as the
weather Brier ledger: every projection is graded after games settle, and
the verdict is written where future sessions will trip over it
(``models/fantasy_nfl_manifest.json``).

Scoring policy, stated where it can be audited:

  * Grades the LATEST ``as_of`` revision per (player, season, week,
    format, model_version) — the final pre-game number. Earlier revisions
    stay in the ledger for future revision-skill studies but are not
    graded here.
  * Only players with an actuals row are graded. A projected player who
    never played (inactive, late scratch) is currently NOT counted as a
    miss — an honest v0 gap (no kickoff/inactive feed wired), listed in
    the manifest caveats rather than hidden.
  * Rank correlation (Spearman) is computed WITHIN each (season, week,
    position) slate of >= MIN_RANK_GROUP graded players — matching how
    start/sit decisions actually consume rankings — then averaged.

**Recommended cron** (UTC, in-season): Wednesday, after the Tuesday/
Wednesday stats ingest has landed the week's actuals::

    0 12 * * 3    kq score-fantasy-projections
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import structlog
from scipy.stats import spearmanr

from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings

log = structlog.get_logger(__name__)

MODELS_DIR: Path = Path("models")
MANIFEST_PATH: Path = MODELS_DIR / "fantasy_nfl_manifest.json"

MIN_RANK_GROUP: int = 5


def _fv(row: dict[str, object], key: str) -> float:
    v = row[key]
    if isinstance(v, int | float):
        return float(v)
    raise TypeError(f"{key!r} is not numeric: {v!r}")


def _iv(row: dict[str, object], key: str) -> int:
    return int(_fv(row, key))


def fetch_scored_rows(
    con: duckdb.DuckDBPyConnection, *, season: int | None = None
) -> list[dict[str, object]]:
    """Latest-revision projections joined to actuals. One dict per graded
    (player, week, format, model_version)."""
    where_season = "AND p.season = ?" if season is not None else ""
    params: list[object] = [season] if season is not None else []
    rows = con.execute(
        f"""
        WITH latest AS (
            SELECT *,
                   row_number() OVER (
                       PARTITION BY player_id, season, week, scoring_format, model_version
                       ORDER BY as_of DESC
                   ) AS rn
            FROM nfl_player_projection
        )
        SELECT p.model_version, p.scoring_format, p.season, p.week, p.player_id,
               g.position,
               p.projected_points, p.floor_points, p.ceiling_points,
               CASE WHEN p.scoring_format = 'std' THEN g.fantasy_points_std
                    ELSE g.fantasy_points_ppr END AS actual_points
        FROM latest p
        JOIN nfl_player_game g
          ON g.player_id = p.player_id AND g.season = p.season AND g.week = p.week
        WHERE p.rn = 1
          AND (CASE WHEN p.scoring_format = 'std' THEN g.fantasy_points_std
                    ELSE g.fantasy_points_ppr END) IS NOT NULL
          {where_season}
        ORDER BY p.model_version, p.scoring_format, p.season, p.week, p.player_id
        """,
        params,
    ).fetchall()
    cols = (
        "model_version",
        "scoring_format",
        "season",
        "week",
        "player_id",
        "position",
        "projected_points",
        "floor_points",
        "ceiling_points",
        "actual_points",
    )
    return [dict(zip(cols, row, strict=False)) for row in rows]


def _group_metrics(rows: list[dict[str, object]]) -> dict[str, Any]:
    """MAE / bias / interval coverage plus per-slate Spearman for one
    (model_version, scoring_format, position) group."""
    errors = [_fv(r, "projected_points") - _fv(r, "actual_points") for r in rows]
    n = len(errors)
    mae = sum(abs(e) for e in errors) / n
    bias = sum(errors) / n

    bounded = [r for r in rows if r["floor_points"] is not None and r["ceiling_points"] is not None]
    coverage = (
        sum(
            1
            for r in bounded
            if _fv(r, "floor_points") <= _fv(r, "actual_points") <= _fv(r, "ceiling_points")
        )
        / len(bounded)
        if bounded
        else None
    )

    by_slate: dict[tuple[int, int], list[dict[str, object]]] = {}
    for r in rows:
        by_slate.setdefault((_iv(r, "season"), _iv(r, "week")), []).append(r)
    rhos: list[float] = []
    for slate in by_slate.values():
        if len(slate) < MIN_RANK_GROUP:
            continue
        rho = float(
            spearmanr(
                [_fv(r, "projected_points") for r in slate],
                [_fv(r, "actual_points") for r in slate],
            ).statistic
        )
        if not math.isnan(rho):  # constant inputs produce NaN
            rhos.append(rho)
    return {
        "n": n,
        "mae": round(mae, 4),
        "bias": round(bias, 4),
        "floor_ceiling_coverage_p10_p90": round(coverage, 4) if coverage is not None else None,
        "n_bounded": len(bounded),
        "mean_weekly_spearman": round(sum(rhos) / len(rhos), 4) if rhos else None,
        "n_rank_slates": len(rhos),
    }


def summarize(rows: list[dict[str, object]]) -> dict[str, Any]:
    """Nest metrics as model_version -> scoring_format -> {overall, positions}."""
    out: dict[str, Any] = {}
    by_mv_fmt: dict[tuple[str, str], list[dict[str, object]]] = {}
    for r in rows:
        by_mv_fmt.setdefault((str(r["model_version"]), str(r["scoring_format"])), []).append(r)
    for (mv, fmt), grp in sorted(by_mv_fmt.items()):
        by_pos: dict[str, list[dict[str, object]]] = {}
        for r in grp:
            by_pos.setdefault(str(r["position"] or "OTHER"), []).append(r)
        out.setdefault(mv, {})[fmt] = {
            "overall": _group_metrics(grp),
            "positions": {pos: _group_metrics(g) for pos, g in sorted(by_pos.items())},
        }
    return out


def write_manifest(
    models: dict[str, Any], *, n_scored: int, out_path: Path = MANIFEST_PATH
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "evaluation": "fantasy_nfl_projection_scoring",
        "n_scored": n_scored,
        "models": models,
        "honest_caveats": [
            "Grades the LATEST as_of revision per (player, week, format, "
            "model); pre-game-ness is enforced structurally at projection "
            "time (players with actuals are never projected), not by "
            "kickoff timestamps — no kickoff feed is joined here.",
            "Projected players with NO actuals row (inactive/DNP) are not "
            "graded — a v0 gap that flatters MAE slightly; an "
            "inactive-aware grade needs a roster-status join (F2/F3).",
            "Rank correlation is per (season, week, position) slate with "
            f">= {MIN_RANK_GROUP} graded players, then averaged — matching "
            "start/sit consumption, not a global pool.",
            "Game-environment input is devigged h2h WIN PROB (no "
            "totals/spreads are ingested), applied as small prior-based "
            "tilts; see kq.models.fantasy_nfl.",
            "floor/ceiling coverage should read ~0.80 for honest p10/p90 "
            "bounds once n_bounded is meaningful.",
        ],
    }
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
    return out_path


def main(
    *,
    season: int | None = None,
    db_path: Path | None = None,
    manifest_path: Path | None = None,
) -> int:
    """``python -m kq score-fantasy-projections`` entrypoint. Returns the
    count of graded projection rows; 0 is a normal pre-season /
    nothing-settled-yet state (manifest still written so consumers see
    freshness)."""
    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)
    try:
        con = duckdb.connect(str(path), read_only=True)
    except duckdb.Error as exc:
        log.warning("fantasy_nfl_scoring.db_unavailable", error=str(exc), db=str(path))
        print(f"cannot open {path} read-only -- nothing to score")
        return 0
    try:
        try:
            rows = fetch_scored_rows(con, season=season)
        except duckdb.CatalogException:
            # Tables predate F1a/F1b on this DB — a normal fresh state for a
            # read-only observer (never create tables from a scorer).
            log.info("fantasy_nfl_scoring.tables_missing", db=str(path))
            print("projection tables not present yet -- nothing to score")
            return 0
    finally:
        con.close()

    models = summarize(rows)
    out_path = write_manifest(models, n_scored=len(rows), out_path=manifest_path or MANIFEST_PATH)
    log.info(
        "fantasy_nfl_scoring.done",
        n_scored=len(rows),
        n_models=len(models),
        manifest=str(out_path),
    )
    print(f"scored {len(rows)} projection rows -> {out_path}")
    return len(rows)


__all__ = ["MANIFEST_PATH", "MIN_RANK_GROUP", "fetch_scored_rows", "main", "summarize"]
