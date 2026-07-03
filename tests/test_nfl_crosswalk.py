"""Tests for the NFL crosswalk: 3-tuple matcher, persistence, and the
build flow end-to-end over a seeded DuckDB."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

from kq.clients.the_odds_api import OddsApiGame, parse_odds_response, parse_scores_response
from kq.flows.build_nfl_crosswalk import (
    fetch_recent_nfl_game_rows,
    fetch_recent_nfl_odds_games,
)
from kq.models.nfl_crosswalk import (
    NflGameRow,
    match_nfl_games,
    nfl_game_row_from_score,
)
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.nfl import upsert_nfl_games
from kq.storage.repositories.nfl_crosswalk import (
    fetch_nfl_crosswalk_for_date_range,
    upsert_nfl_crosswalk,
)
from kq.storage.repositories.nfl_odds import odds_rows_from_games, upsert_nfl_odds_rows

H2H_FIXTURE = Path(__file__).parent / "fixtures" / "the_odds_api_nfl_h2h.json"
SCORES_FIXTURE = Path(__file__).parent / "fixtures" / "the_odds_api_nfl_scores.json"


def _fixture_games() -> list[OddsApiGame]:
    return parse_odds_response(json.loads(H2H_FIXTURE.read_text(encoding="utf-8")))


def _fixture_game_rows() -> list[NflGameRow]:
    rows = []
    for score in parse_scores_response(json.loads(SCORES_FIXTURE.read_text(encoding="utf-8"))):
        row = nfl_game_row_from_score(score)
        if row is not None:
            rows.append(row)
    return rows


# --------------------------- matcher ---------------------------


def test_match_pairs_odds_to_schedule_on_three_tuple() -> None:
    pairs = match_nfl_games(_fixture_games(), _fixture_game_rows())
    by_odds_id = {p.odds_api_game_id: p for p in pairs}
    # Both h2h fixture games exist in the scores fixture (shared ids).
    assert set(by_odds_id) == {
        "nfl1234abcd1234abcd1234abcd1234ab",
        "nfl5678efgh5678efgh5678efgh5678ef",
    }
    dal_nyg = by_odds_id["nfl1234abcd1234abcd1234abcd1234ab"]
    assert dal_nyg.nfl_game_id == "nfl1234abcd1234abcd1234abcd1234ab"  # identity in v1
    assert dal_nyg.home_team_abbr == "NYG"
    assert dal_nyg.away_team_abbr == "DAL"
    assert dal_nyg.game_date == date(2026, 9, 13)


def test_match_drops_odds_games_without_schedule_row() -> None:
    games = _fixture_games()
    pairs = match_nfl_games(games, [])
    assert pairs == []


def test_match_is_id_agnostic() -> None:
    """The match runs on (home, away, date) — if the /odds and /scores ids
    ever diverge, the bridge still lands (this is the crosswalk's whole
    insurance value for NFL)."""
    schedule = _fixture_game_rows()
    renamed = [
        NflGameRow(
            game_id=f"different-{r.game_id}",
            season=r.season,
            game_date=r.game_date,
            commence_time=r.commence_time,
            home_team=r.home_team,
            home_team_abbr=r.home_team_abbr,
            away_team=r.away_team,
            away_team_abbr=r.away_team_abbr,
            home_score=r.home_score,
            away_score=r.away_score,
            completed=r.completed,
            home_won=r.home_won,
        )
        for r in schedule
    ]
    pairs = match_nfl_games(_fixture_games(), renamed)
    assert len(pairs) == 2
    assert all(p.nfl_game_id.startswith("different-") for p in pairs)


# --------------------------- persistence ---------------------------


def test_upsert_and_fetch_crosswalk(tmp_path: Path) -> None:
    db = tmp_path / "nfl.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        pairs = match_nfl_games(_fixture_games(), _fixture_game_rows())
        n = upsert_nfl_crosswalk(con, pairs)
        assert n == 2
        # Idempotent re-run.
        assert upsert_nfl_crosswalk(con, pairs) == 2
        count = con.execute("SELECT COUNT(*) FROM nfl_game_crosswalk").fetchone()
        assert count is not None and int(count[0]) == 2
        rows = fetch_nfl_crosswalk_for_date_range(
            con, start_date=date(2026, 9, 13), end_date=date(2026, 9, 13)
        )
        assert len(rows) == 2
    finally:
        con.close()


# --------------------------- build flow end-to-end ---------------------------


def test_build_flow_end_to_end(tmp_path: Path, monkeypatch: object) -> None:
    """Seed nfl_odds + nfl_game from the fixtures, run the flow's fetch +
    match + upsert path directly against the DB."""
    db = tmp_path / "nfl.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        upsert_nfl_odds_rows(
            con,
            odds_rows_from_games(
                _fixture_games(), fetched_at=datetime(2026, 9, 13, 15, 0, tzinfo=UTC)
            ),
        )
        upsert_nfl_games(con, _fixture_game_rows())

        odds_games = fetch_recent_nfl_odds_games(con, since=datetime(2026, 9, 1, tzinfo=UTC))
        nfl_rows = fetch_recent_nfl_game_rows(con, since=date(2026, 9, 1))
        assert len(odds_games) == 2
        assert len(nfl_rows) == 4
        pairs = match_nfl_games(odds_games, nfl_rows)
        assert len(pairs) == 2
        assert upsert_nfl_crosswalk(con, pairs) == 2
    finally:
        con.close()

    # Read-only verification the bridge is queryable the way the paper flow joins it.
    ro = duckdb.connect(str(db), read_only=True)
    try:
        row = ro.execute(
            """
            SELECT o.home_decimal_odds
            FROM nfl_game_crosswalk c
            JOIN nfl_odds o ON o.odds_api_game_id = c.odds_api_game_id
            WHERE c.game_date = ? AND c.home_team_abbr = 'NYG' AND c.away_team_abbr = 'DAL'
              AND o.bookmaker_key = 'pinnacle'
            """,
            [date(2026, 9, 13)],
        ).fetchone()
        assert row is not None and float(row[0]) == 2.38
    finally:
        ro.close()
