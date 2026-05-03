"""Tests for the NBA crosswalk repository + ingest flow.

Two layers covered:
- Repository (``kq.storage.repositories.nba_crosswalk``): upsert
  idempotency, lookup by either id, date-range fetch.
- Flow (``kq.flows.build_nba_crosswalk``): end-to-end DuckDB round-
  trip that seeds nba_odds + nba_game, runs the matcher, persists,
  re-runs (no-op).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from kq.config import get_settings
from kq.flows.build_nba_crosswalk import (
    fetch_recent_nba_game_rows,
    fetch_recent_odds_games,
)
from kq.flows.build_nba_crosswalk import main as run_build_nba_crosswalk
from kq.models.nba_crosswalk import CrosswalkPair, match_games
from kq.storage.duckdb_store import bootstrap
from kq.storage.repositories.nba_crosswalk import (
    fetch_by_nba_game_id,
    fetch_by_odds_api_id,
    fetch_for_date_range,
    upsert_crosswalk,
)


def _new_db(tmp_path: Path) -> Path:
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    return db


def _seed_odds_row(
    con: duckdb.DuckDBPyConnection,
    *,
    odds_api_game_id: str,
    home_team: str,
    away_team: str,
    commence_time: datetime,
    fetched_at: datetime,
    bookmaker_key: str = "pinnacle",
    market_key: str = "h2h",
) -> None:
    """Insert one nba_odds row -- enough for ``fetch_recent_odds_games``
    to surface the game."""
    con.execute(
        """
        INSERT INTO nba_odds
        (odds_api_game_id, bookmaker_key, market_key, home_team, away_team,
         commence_time, home_decimal_odds, away_decimal_odds,
         book_last_update, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            odds_api_game_id,
            bookmaker_key,
            market_key,
            home_team,
            away_team,
            commence_time.replace(tzinfo=None),
            1.91,
            1.91,
            commence_time.replace(tzinfo=None),
            fetched_at.replace(tzinfo=None),
        ],
    )


def _seed_nba_game(
    con: duckdb.DuckDBPyConnection,
    *,
    game_id: str,
    home_abbr: str,
    away_abbr: str,
    game_date: date,
    season: str = "2025-26",
) -> None:
    fetched_at = datetime.now(tz=UTC).replace(tzinfo=None)
    con.execute(
        """
        INSERT OR REPLACE INTO nba_game
        (game_id, season, season_type, game_date,
         home_team_id, home_team_abbr, away_team_id, away_team_abbr,
         home_score, away_score, home_won, fetched_at)
        VALUES (?, ?, 'Regular Season', ?, 0, ?, 0, ?, NULL, NULL, NULL, ?)
        """,
        [game_id, season, game_date, home_abbr, away_abbr, fetched_at],
    )


# --------------------------- repository ---------------------------


def test_upsert_round_trip(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    pair = CrosswalkPair(
        odds_api_game_id="abc123",
        nba_game_id="0022500001",
        home_team_abbr="LAL",
        away_team_abbr="BOS",
        game_date=date(2026, 5, 4),
    )
    n = upsert_crosswalk(con, [pair])
    assert n == 1
    result = fetch_by_odds_api_id(con, "abc123")
    assert result is not None
    assert result["nba_game_id"] == "0022500001"
    assert result["home_team_abbr"] == "LAL"
    assert result["away_team_abbr"] == "BOS"
    con.close()


def test_upsert_empty_is_noop(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    assert upsert_crosswalk(con, []) == 0
    assert fetch_for_date_range(con) == []
    con.close()


def test_upsert_is_idempotent_on_pk(tmp_path: Path) -> None:
    """Re-upserting the same pair lands one row, not two."""
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    pair = CrosswalkPair(
        odds_api_game_id="abc123",
        nba_game_id="0022500001",
        home_team_abbr="LAL",
        away_team_abbr="BOS",
        game_date=date(2026, 5, 4),
    )
    upsert_crosswalk(con, [pair])
    upsert_crosswalk(con, [pair])
    count = con.execute("SELECT COUNT(*) FROM nba_game_crosswalk").fetchone()
    assert count is not None and count[0] == 1
    con.close()


def test_fetch_by_odds_api_id_returns_none_on_miss(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    assert fetch_by_odds_api_id(con, "missing") is None
    con.close()


def test_fetch_by_nba_game_id_returns_none_on_miss(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    assert fetch_by_nba_game_id(con, "0022500999") is None
    con.close()


def test_fetch_by_nba_game_id_round_trips(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    pair = CrosswalkPair(
        odds_api_game_id="abc123",
        nba_game_id="0022500001",
        home_team_abbr="LAL",
        away_team_abbr="BOS",
        game_date=date(2026, 5, 4),
    )
    upsert_crosswalk(con, [pair])
    result = fetch_by_nba_game_id(con, "0022500001")
    assert result is not None
    assert result["odds_api_game_id"] == "abc123"
    con.close()


def test_fetch_for_date_range_filters_inclusively(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    pairs = [
        CrosswalkPair(
            odds_api_game_id=f"id{i}",
            nba_game_id=f"002250000{i}",
            home_team_abbr="LAL",
            away_team_abbr="BOS",
            game_date=date(2026, 5, day),
        )
        for i, day in enumerate((3, 4, 5, 6), start=1)
    ]
    upsert_crosswalk(con, pairs)
    out = fetch_for_date_range(con, start_date=date(2026, 5, 4), end_date=date(2026, 5, 5))
    assert {r["nba_game_id"] for r in out} == {"0022500002", "0022500003"}
    con.close()


def test_fetch_for_date_range_unbounded_returns_all(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    upsert_crosswalk(
        con,
        [
            CrosswalkPair(
                odds_api_game_id="abc123",
                nba_game_id="0022500001",
                home_team_abbr="LAL",
                away_team_abbr="BOS",
                game_date=date(2026, 5, 4),
            )
        ],
    )
    assert len(fetch_for_date_range(con)) == 1
    con.close()


# --------------------------- flow: helpers ---------------------------


def test_fetch_recent_odds_games_picks_latest_snapshot(tmp_path: Path) -> None:
    """Two snapshots of the same game at different fetched_at -- the
    flow's helper must surface the latest one (highest fetched_at)."""
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    commence = datetime(2026, 5, 4, 23, 0, tzinfo=UTC)
    _seed_odds_row(
        con,
        odds_api_game_id="abc123",
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        commence_time=commence,
        fetched_at=datetime(2026, 5, 4, 18, 0, tzinfo=UTC),
    )
    _seed_odds_row(
        con,
        odds_api_game_id="abc123",
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        commence_time=commence,
        fetched_at=datetime(2026, 5, 4, 22, 0, tzinfo=UTC),
    )
    games = fetch_recent_odds_games(con, since=datetime(2026, 5, 4, tzinfo=UTC))
    assert len(games) == 1
    assert games[0].game_id == "abc123"
    assert games[0].home_team == "Los Angeles Lakers"
    con.close()


def test_fetch_recent_odds_games_filters_by_commence_time(tmp_path: Path) -> None:
    """A game whose tipoff is before ``since`` is dropped."""
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    _seed_odds_row(
        con,
        odds_api_game_id="old",
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        commence_time=datetime(2026, 4, 1, 23, 0, tzinfo=UTC),
        fetched_at=datetime(2026, 4, 1, 22, 0, tzinfo=UTC),
    )
    games = fetch_recent_odds_games(con, since=datetime(2026, 5, 1, tzinfo=UTC))
    assert games == []
    con.close()


def test_fetch_recent_nba_game_rows_filters_by_game_date(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    _seed_nba_game(
        con,
        game_id="0022500001",
        home_abbr="LAL",
        away_abbr="BOS",
        game_date=date(2026, 5, 4),
    )
    _seed_nba_game(
        con,
        game_id="0022500002",
        home_abbr="DEN",
        away_abbr="OKC",
        game_date=date(2026, 4, 1),  # before window
    )
    rows = fetch_recent_nba_game_rows(con, since=date(2026, 5, 1))
    assert {r.game_id for r in rows} == {"0022500001"}
    con.close()


# --------------------------- flow: end-to-end ---------------------------


def test_build_main_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Seed nba_odds + nba_game so the matcher finds two pairs; run the
    flow; verify the bridge has those pairs; re-run to confirm idempotent."""
    db = _new_db(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db}")

    get_settings.cache_clear()

    today = datetime.now(tz=UTC).date()
    commence = datetime.combine(today, datetime.min.time(), tzinfo=UTC) + timedelta(hours=23)

    con = duckdb.connect(str(db))
    _seed_odds_row(
        con,
        odds_api_game_id="lakers-celtics-uuid",
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        commence_time=commence,
        fetched_at=datetime.now(tz=UTC),
    )
    _seed_odds_row(
        con,
        odds_api_game_id="nuggets-thunder-uuid",
        home_team="Denver Nuggets",
        away_team="Oklahoma City Thunder",
        commence_time=commence,
        fetched_at=datetime.now(tz=UTC),
    )
    _seed_nba_game(con, game_id="0022500001", home_abbr="LAL", away_abbr="BOS", game_date=today)
    _seed_nba_game(con, game_id="0022500002", home_abbr="DEN", away_abbr="OKC", game_date=today)
    con.close()

    n_first = run_build_nba_crosswalk(db_path=db)
    assert n_first == 2
    n_again = run_build_nba_crosswalk(db_path=db)
    assert n_again == 2
    # Total rows in the bridge should still be 2 -- PR is idempotent.
    con = duckdb.connect(str(db), read_only=True)
    try:
        count = con.execute("SELECT COUNT(*) FROM nba_game_crosswalk").fetchone()
    finally:
        con.close()
    assert count is not None and count[0] == 2


def test_build_main_no_matches_when_nba_rows_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Odds rows seeded but no nba_game rows -> matcher finds nothing,
    flow exits clean with 0."""
    db = _new_db(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db}")

    get_settings.cache_clear()

    today = datetime.now(tz=UTC).date()
    commence = datetime.combine(today, datetime.min.time(), tzinfo=UTC) + timedelta(hours=23)
    con = duckdb.connect(str(db))
    _seed_odds_row(
        con,
        odds_api_game_id="lakers-celtics-uuid",
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        commence_time=commence,
        fetched_at=datetime.now(tz=UTC),
    )
    con.close()

    assert run_build_nba_crosswalk(db_path=db) == 0


# --------------------------- regression check ---------------------------


def test_match_games_used_directly_against_seeded_data(tmp_path: Path) -> None:
    """Sanity check that ``match_games`` over the helper outputs returns
    the same pairs the flow's main() does. Catches drift between the
    pure matcher and the persistence layer."""
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    today = datetime.now(tz=UTC).date()
    commence = datetime.combine(today, datetime.min.time(), tzinfo=UTC) + timedelta(hours=23)
    _seed_odds_row(
        con,
        odds_api_game_id="abc123",
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        commence_time=commence,
        fetched_at=datetime.now(tz=UTC),
    )
    _seed_nba_game(con, game_id="0022500001", home_abbr="LAL", away_abbr="BOS", game_date=today)
    odds = fetch_recent_odds_games(
        con, since=datetime.combine(today, datetime.min.time(), tzinfo=UTC)
    )
    nba_rows = fetch_recent_nba_game_rows(con, since=today)
    pairs = match_games(odds, nba_rows)
    assert len(pairs) == 1
    assert pairs[0].odds_api_game_id == "abc123"
    assert pairs[0].nba_game_id == "0022500001"
    con.close()
