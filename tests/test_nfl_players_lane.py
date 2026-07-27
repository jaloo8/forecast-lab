"""Tests for the NFL player-lane storage + ingest flow (Fantasy F1a).

The repository half pins the guarded-upsert semantics (corrections flow,
NULLs never regress stored truth — the weather_observed posture) and the
projection ledger's append-only PK. The flow half drives the real persist
path against patched client fetchers into a tmp DuckDB.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from kq.__main__ import app
from kq.clients import nfl_players as client
from kq.clients.nfl_players import PlayerGameRow
from kq.flows import ingest_nfl_players
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.nfl_players import (
    ProjectionRow,
    fetch_player_games,
    fetch_projections,
    insert_projections,
    upsert_player_games,
)


def _game_row(
    *,
    player_id: str = "00-0033873",
    snaps: float | None = 54.0,
    snap_pct: float | None = 1.0,
    fantasy_std: float | None = 14.14,
) -> PlayerGameRow:
    return PlayerGameRow(
        player_id=player_id,
        player_name="Patrick Mahomes",
        season=2024,
        week=1,
        season_type="REG",
        team="KC",
        opponent="BAL",
        position="QB",
        snaps=snaps,
        snap_pct=snap_pct,
        targets=1,
        receptions=1,
        carries=2,
        passing_yards=291.0,
        passing_tds=1,
        rushing_yards=3.0,
        rushing_tds=0,
        receiving_yards=2.0,
        receiving_tds=0,
        fumbles_lost=0.0,
        interceptions=1.0,
        red_zone_touches=None,
        fantasy_points_std=fantasy_std,
        fantasy_points_ppr=15.14 if fantasy_std is not None else None,
    )


def _projection(
    *,
    scoring_format: str = "std",
    as_of: datetime | None = None,
    points: float = 18.2,
) -> ProjectionRow:
    return ProjectionRow(
        player_id="00-0033873",
        player_name="Patrick Mahomes",
        season=2025,
        week=1,
        scoring_format=scoring_format,
        projected_points=points,
        floor_points=9.1,
        ceiling_points=28.4,
        as_of=as_of or datetime(2025, 9, 2, 11, 0, tzinfo=UTC),
        model_version="fantasy_nfl_v0",
    )


# --------------------------- repository: player games ---------------------------


def test_upsert_and_fetch_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "f1a.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        as_of = datetime(2025, 1, 10, 11, 0, tzinfo=UTC)
        n = upsert_player_games(con, [_game_row()], as_of=as_of)
        assert n == 1
        rows = fetch_player_games(con, seasons=[2024], season_type="REG", position="QB")
        assert len(rows) == 1
        r = rows[0]
        assert r["player_id"] == "00-0033873"
        assert r["fantasy_points_std"] == pytest.approx(14.14)
        assert r["fantasy_points_ppr"] == pytest.approx(15.14)
        assert r["as_of"] == as_of.replace(tzinfo=None)  # stored naive UTC
        assert r["red_zone_touches"] is None
    finally:
        con.close()


def test_upsert_correction_replaces_in_place(tmp_path: Path) -> None:
    """nflverse stat corrections must overwrite — no finality freeze here."""
    db = tmp_path / "f1a.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        upsert_player_games(con, [_game_row(fantasy_std=14.14)])
        upsert_player_games(con, [_game_row(fantasy_std=14.64)])
        rows = fetch_player_games(con)
        assert len(rows) == 1
        assert rows[0]["fantasy_points_std"] == pytest.approx(14.64)
    finally:
        con.close()


def test_upsert_null_never_regresses_stored_snaps(tmp_path: Path) -> None:
    """A tick where the snap join degraded (snaps=None) must not wipe last
    pull's good snap columns; as_of still moves so the touch is visible."""
    db = tmp_path / "f1a.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        t1 = datetime(2025, 1, 10, 11, 0, tzinfo=UTC)
        t2 = datetime(2025, 1, 11, 11, 0, tzinfo=UTC)
        upsert_player_games(con, [_game_row(snaps=54.0, snap_pct=1.0)], as_of=t1)
        upsert_player_games(con, [_game_row(snaps=None, snap_pct=None)], as_of=t2)
        r = fetch_player_games(con)[0]
        assert r["snaps"] == pytest.approx(54.0)
        assert r["snap_pct"] == pytest.approx(1.0)
        assert r["as_of"] == t2.replace(tzinfo=None)
    finally:
        con.close()


# --------------------------- repository: projections ---------------------------


def test_projection_ledger_round_trip_both_formats(tmp_path: Path) -> None:
    db = tmp_path / "f1a.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        n = insert_projections(
            con,
            [
                _projection(scoring_format="std", points=18.2),
                _projection(scoring_format="ppr", points=18.2),
            ],
        )
        assert n == 2
        std = fetch_projections(con, scoring_format="std")
        assert len(std) == 1
        assert std[0]["projected_points"] == pytest.approx(18.2)
        assert std[0]["model_version"] == "fantasy_nfl_v0"
        assert len(fetch_projections(con, season=2025, week=1)) == 2
    finally:
        con.close()


def test_projection_new_as_of_appends_ledger(tmp_path: Path) -> None:
    """Tuesday's projection and Sunday-morning's projection are different
    point-in-time statements — both stay in the ledger."""
    db = tmp_path / "f1a.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        insert_projections(con, [_projection(as_of=datetime(2025, 9, 2, 11, 0, tzinfo=UTC))])
        insert_projections(con, [_projection(as_of=datetime(2025, 9, 7, 13, 0, tzinfo=UTC))])
        assert len(fetch_projections(con)) == 2
    finally:
        con.close()


def test_projection_unknown_scoring_format_refused(tmp_path: Path) -> None:
    db = tmp_path / "f1a.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        with pytest.raises(ValueError, match="scoring_format"):
            insert_projections(con, [_projection(scoring_format="half_ppr")])
        assert fetch_projections(con) == []
    finally:
        con.close()


# --------------------------- flow ---------------------------


@pytest.fixture
def patched_flow_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drive the flow with client-shaped rows built from the recorded-real
    fixture CSVs (loaded via the client test's patched fetch path)."""
    fixtures = Path(__file__).parent / "fixtures" / "nfl_players"

    def fake_weekly(years: list[int]) -> pd.DataFrame:
        df = pd.read_csv(fixtures / "weekly_2024_w1_kc_phi.csv")
        return df[df["season"].isin(years)].copy()

    def fake_snaps(years: list[int]) -> pd.DataFrame:
        df = pd.read_csv(fixtures / "snap_counts_2024_w1_kc_phi.csv")
        return df[df["season"].isin(years)].copy()

    monkeypatch.setattr(client, "_import_weekly", fake_weekly)
    monkeypatch.setattr(client, "_import_snap_counts", fake_snaps)
    monkeypatch.setattr(
        client, "_import_ids", lambda: pd.read_csv(fixtures / "ids_kc_phi_2024w1.csv")
    )


def test_flow_run_persists_merged_rows(tmp_path: Path, patched_flow_sources: None) -> None:
    db = tmp_path / "flow.duckdb"  # no bootstrap on purpose — the flow must self-bootstrap
    n = ingest_nfl_players.run(seasons=[2024], db_path=db)
    assert n == 19
    con = connect(db, read_only=True)
    try:
        rows = fetch_player_games(con, seasons=[2024])
        assert len(rows) == 19
        assert all(r["as_of"] is not None for r in rows)
        m = next(r for r in rows if r["player_id"] == "00-0033873")
        assert m["snaps"] == pytest.approx(54.0)
        assert m["fantasy_points_ppr"] == pytest.approx(15.14, abs=1e-4)
    finally:
        con.close()


def test_flow_run_returns_zero_when_no_weekly_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A season with nothing published (cron entry predating the season)
    is a clean no-op, not a crash."""

    def nothing(years: list[int]) -> object:
        raise RuntimeError("404 not yet published")

    monkeypatch.setattr(client, "_import_weekly", nothing)
    assert ingest_nfl_players.run(seasons=[2199], db_path=tmp_path / "x.duckdb") == 0


def test_flow_degraded_snaps_then_recovery_never_regresses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, patched_flow_sources: None
) -> None:
    """End-to-end guard: snaps source down -> rows land snapless; next tick
    with snaps fills them; a later degraded tick leaves them intact."""
    db = tmp_path / "flow.duckdb"
    real_snaps = client._import_snap_counts

    def snaps_down(years: list[int]) -> object:
        raise RuntimeError("PFR mirror down")

    monkeypatch.setattr(client, "_import_snap_counts", snaps_down)
    ingest_nfl_players.run(seasons=[2024], db_path=db)
    con = connect(db, read_only=True)
    try:
        assert all(r["snaps"] is None for r in fetch_player_games(con))
    finally:
        con.close()

    monkeypatch.setattr(client, "_import_snap_counts", real_snaps)
    ingest_nfl_players.run(seasons=[2024], db_path=db)
    monkeypatch.setattr(client, "_import_snap_counts", snaps_down)
    ingest_nfl_players.run(seasons=[2024], db_path=db)
    con = connect(db, read_only=True)
    try:
        m = next(r for r in fetch_player_games(con) if r["player_id"] == "00-0033873")
        assert m["snaps"] == pytest.approx(54.0)  # survived the degraded third tick
    finally:
        con.close()


def test_flow_main_prints_summary(
    tmp_path: Path, patched_flow_sources: None, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "flow.duckdb"
    n = ingest_nfl_players.main(seasons=[2024], db_path=db)
    assert n == 19
    out = capsys.readouterr().out
    assert "19 NFL player-week rows" in out


# --------------------------- CLI ---------------------------


def test_cli_help_lists_season_option() -> None:
    result = CliRunner().invoke(app, ["ingest-nfl-players", "--help"])
    assert result.exit_code == 0
    assert "--season" in result.output
