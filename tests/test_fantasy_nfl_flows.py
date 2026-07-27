"""Tests for the fantasy projection flows: ledger writer + self-scorer.

Everything runs against tmp DuckDBs seeded through the real repositories —
no network, no patching of the model itself (it is deterministic). The
odds-context test seeds the REAL nfl_game / nfl_odds tables the flow
reads, including the JAC->JAX code translation that would silently
neutralize every adjustment if wrong.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest
from typer.testing import CliRunner

from kq.__main__ import app
from kq.clients.nfl_players import PlayerGameRow
from kq.flows.project_fantasy_nfl import _default_week, _upcoming_context, run
from kq.flows.score_fantasy_projections import main as score_main
from kq.models.fantasy_nfl import MODEL_VERSION
from kq.models.nfl_crosswalk import NflGameRow
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.nfl import upsert_nfl_games
from kq.storage.repositories.nfl_odds import OddsRow, upsert_nfl_odds_rows
from kq.storage.repositories.nfl_players import (
    ProjectionRow,
    fetch_projections,
    insert_projections,
    upsert_player_games,
)

NOW = datetime(2024, 10, 1, 12, 0, tzinfo=UTC)  # Tuesday of 2024 week 5


def _game_row(
    *,
    player_id: str,
    week: int,
    team: str = "KC",
    targets: int = 8,
    receptions: int = 6,
    rec_yards: float = 80.0,
) -> PlayerGameRow:
    pts = 0.1 * rec_yards
    return PlayerGameRow(
        player_id=player_id,
        player_name=player_id,
        season=2024,
        week=week,
        season_type="REG",
        team=team,
        opponent="BAL",
        position="WR",
        snaps=60.0,
        snap_pct=0.9,
        targets=targets,
        receptions=receptions,
        carries=0,
        passing_yards=0.0,
        passing_tds=0,
        rushing_yards=0.0,
        rushing_tds=0,
        receiving_yards=rec_yards,
        receiving_tds=0,
        fumbles_lost=0.0,
        interceptions=0.0,
        red_zone_touches=None,
        fantasy_points_std=pts,
        fantasy_points_ppr=pts + receptions,
    )


def _seed_stats(db: Path, *, player_ids: tuple[str, ...] = ("wr1", "wr2"), weeks: int = 4) -> None:
    bootstrap(db)
    con = connect(db)
    try:
        rows = [_game_row(player_id=p, week=w) for p in player_ids for w in range(1, weeks + 1)]
        upsert_player_games(con, rows)
    finally:
        con.close()


# --------------------------- projection flow ---------------------------


def test_default_week_is_next_unplayed() -> None:
    assert _default_week([], season=2024) == 1
    hist: list[dict[str, object]] = [{"season": 2024, "week": 4}, {"season": 2023, "week": 18}]
    assert _default_week(hist, season=2024) == 5


def test_run_writes_both_formats_to_ledger(tmp_path: Path) -> None:
    db = tmp_path / "f1b.duckdb"
    _seed_stats(db)
    n = run(db_path=db, season=2024, week=5, now=NOW)
    assert n == 4  # 2 players x 2 formats
    con = connect(db, read_only=True)
    try:
        rows = fetch_projections(con, season=2024, week=5)
    finally:
        con.close()
    assert len(rows) == 4
    assert {str(r["scoring_format"]) for r in rows} == {"std", "ppr"}
    assert all(str(r["model_version"]) == MODEL_VERSION for r in rows)
    assert all(r["as_of"] == NOW.replace(tzinfo=None) for r in rows)
    by_fmt = {(str(r["player_id"]), str(r["scoring_format"])): r for r in rows}
    # PPR strictly above std for a pass catcher.
    assert float(by_fmt[("wr1", "ppr")]["projected_points"]) > float(  # type: ignore[arg-type]
        by_fmt[("wr1", "std")]["projected_points"]  # type: ignore[arg-type]
    )


def test_run_skips_players_whose_game_already_settled(tmp_path: Path) -> None:
    db = tmp_path / "f1b.duckdb"
    _seed_stats(db)
    con = connect(db)
    try:
        upsert_player_games(con, [_game_row(player_id="wr1", week=5)])  # wr1 played Thursday
    finally:
        con.close()
    n = run(db_path=db, season=2024, week=5, now=NOW)
    assert n == 2  # only wr2, both formats
    con = connect(db, read_only=True)
    try:
        rows = fetch_projections(con, season=2024, week=5)
    finally:
        con.close()
    assert {str(r["player_id"]) for r in rows} == {"wr2"}


def test_rerun_appends_new_as_of_revision(tmp_path: Path) -> None:
    db = tmp_path / "f1b.duckdb"
    _seed_stats(db)
    run(db_path=db, season=2024, week=5, now=NOW)
    run(db_path=db, season=2024, week=5, now=NOW + timedelta(days=2))
    con = connect(db, read_only=True)
    try:
        rows = fetch_projections(con, season=2024, week=5)
    finally:
        con.close()
    assert len(rows) == 8  # two revisions x 2 players x 2 formats


def test_upcoming_context_translates_odds_codes_and_devigs(tmp_path: Path) -> None:
    """JAC (odds lane) must arrive as JAX (nflverse) or every Jaguars
    adjustment silently neutralizes; devig must be the shared
    proportional math."""
    db = tmp_path / "ctx.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        kickoff = (NOW + timedelta(days=5)).replace(tzinfo=None)
        upsert_nfl_games(
            con,
            [
                NflGameRow(
                    game_id="g1",
                    season=2024,
                    game_date=kickoff.date(),
                    commence_time=kickoff,
                    home_team="Jacksonville Jaguars",
                    home_team_abbr="JAC",
                    away_team="Kansas City Chiefs",
                    away_team_abbr="KC",
                    home_score=None,
                    away_score=None,
                    completed=False,
                    home_won=None,
                )
            ],
        )
        upsert_nfl_odds_rows(
            con,
            [
                OddsRow(
                    odds_api_game_id="g1",
                    bookmaker_key="pinnacle",
                    market_key="h2h",
                    home_team="Jacksonville Jaguars",
                    away_team="Kansas City Chiefs",
                    commence_time=kickoff,
                    home_decimal_odds=3.0,
                    away_decimal_odds=1.4,
                    book_last_update=NOW.replace(tzinfo=None),
                    fetched_at=NOW.replace(tzinfo=None),
                )
            ],
        )
        opponents, win_probs = _upcoming_context(con, now=NOW.replace(tzinfo=None))
    finally:
        con.close()
    assert opponents == {"JAX": "KC", "KC": "JAX"}
    # Proportional devig: (1/3) / (1/3 + 1/1.4)
    assert win_probs["JAX"] == pytest.approx((1 / 3.0) / (1 / 3.0 + 1 / 1.4))
    assert win_probs["KC"] == pytest.approx(1.0 - win_probs["JAX"])


def test_run_survives_empty_odds_lane(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Dead ODDS_API_KEY / off-season: no nfl_game rows at all -> neutral
    adjustments, projections still written, note printed."""
    db = tmp_path / "f1b.duckdb"
    _seed_stats(db)
    n = run(db_path=db, season=2024, week=5, now=NOW)
    assert n == 4
    assert "adjustments neutral" in capsys.readouterr().out


# --------------------------- scoring flow ---------------------------


def _seed_projection(
    db: Path,
    *,
    player_id: str,
    projected: float,
    as_of: datetime,
    scoring_format: str = "std",
    floor: float | None = None,
    ceiling: float | None = None,
) -> None:
    con = connect(db)
    try:
        insert_projections(
            con,
            [
                ProjectionRow(
                    player_id=player_id,
                    player_name=player_id,
                    season=2024,
                    week=4,
                    scoring_format=scoring_format,
                    projected_points=projected,
                    floor_points=floor,
                    ceiling_points=ceiling,
                    as_of=as_of,
                    model_version=MODEL_VERSION,
                )
            ],
        )
    finally:
        con.close()


def test_scorer_grades_latest_revision_against_actuals(tmp_path: Path) -> None:
    db = tmp_path / "score.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        # Five WRs with actual std points 4,6,8,10,12 in week 4.
        rows = [_game_row(player_id=f"wr{i}", week=4, rec_yards=40.0 + 20.0 * i) for i in range(5)]
        upsert_player_games(con, rows)
    finally:
        con.close()
    early = NOW - timedelta(days=6)
    late = NOW - timedelta(days=3)
    for i in range(5):
        actual = 4.0 + 2.0 * i
        # Early revision is garbage; the late (graded) one is off by exactly +1
        # and rank-orders the slate perfectly.
        _seed_projection(db, player_id=f"wr{i}", projected=99.0, as_of=early)
        _seed_projection(
            db,
            player_id=f"wr{i}",
            projected=actual + 1.0,
            as_of=late,
            floor=actual - 2.0,
            ceiling=actual + 2.0,
        )

    manifest_path = tmp_path / "fantasy_manifest.json"
    n = score_main(season=2024, db_path=db, manifest_path=manifest_path)
    assert n == 5  # latest revision only — the early-garbage rows are not graded

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["evaluation"] == "fantasy_nfl_projection_scoring"
    assert payload["n_scored"] == 5
    std = payload["models"][MODEL_VERSION]["std"]
    assert std["overall"]["n"] == 5
    assert std["overall"]["mae"] == pytest.approx(1.0)
    assert std["overall"]["bias"] == pytest.approx(1.0)
    wr = std["positions"]["WR"]
    assert wr["mean_weekly_spearman"] == pytest.approx(1.0)
    assert wr["n_rank_slates"] == 1
    assert wr["floor_ceiling_coverage_p10_p90"] == pytest.approx(1.0)
    assert payload["honest_caveats"]


def test_scorer_zero_state_on_missing_tables(tmp_path: Path) -> None:
    """A DB that predates the fantasy lane must read as 'nothing to
    score', never get tables created by a read-only observer."""
    db = tmp_path / "old.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE unrelated (i INTEGER)")
    con.close()
    n = score_main(db_path=db, manifest_path=tmp_path / "m.json")
    assert n == 0
    assert not (tmp_path / "m.json").exists()
    con = duckdb.connect(str(db), read_only=True)
    try:
        tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    finally:
        con.close()
    assert tables == {"unrelated"}


def test_scorer_zero_state_on_missing_db(tmp_path: Path) -> None:
    n = score_main(db_path=tmp_path / "nope.duckdb", manifest_path=tmp_path / "m.json")
    assert n == 0


# --------------------------- CLI ---------------------------


def test_cli_help_for_both_commands() -> None:
    runner = CliRunner()
    r1 = runner.invoke(app, ["project-fantasy-nfl", "--help"])
    assert r1.exit_code == 0
    assert "--week" in r1.output
    r2 = runner.invoke(app, ["score-fantasy-projections", "--help"])
    assert r2.exit_code == 0
    assert "--season" in r2.output
