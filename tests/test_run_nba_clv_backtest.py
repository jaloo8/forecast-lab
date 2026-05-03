"""Tests for the NBA CLV backtest flow.

Coverage:
- DuckDB-row hydration helpers (finished games, Pinnacle quotes,
  crosswalk).
- Chronological replay updates Elo state; per-game predictions use
  the BEFORE-game state (the load-bearing PIT property).
- Manifest writes JSON-safely with all aggregate fields.
- main() runs against a fully-seeded DB and produces a non-trivial
  manifest; runs against an empty DB and exits clean with
  n_evaluated=0.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pytest

from kq.backtest.nba_clv import FinishedGame, PinnacleQuote
from kq.flows.run_nba_clv_backtest import (
    fetch_crosswalk_rows,
    fetch_finished_games,
    fetch_finished_games_with_dates,
    fetch_latest_pinnacle_quotes,
    replay_and_evaluate,
    write_manifest,
)
from kq.flows.run_nba_clv_backtest import main as run_main
from kq.models.nba_crosswalk import CrosswalkPair
from kq.models.nba_elo import INITIAL_RATING, NbaEloRatings
from kq.storage.duckdb_store import bootstrap


def _new_db(tmp_path: Path) -> Path:
    db = tmp_path / "nba_clv.duckdb"
    bootstrap(db)
    return db


def _seed_finished_game(
    con: duckdb.DuckDBPyConnection,
    *,
    game_id: str,
    home_abbr: str,
    away_abbr: str,
    home_score: int,
    away_score: int,
    game_date: date,
) -> None:
    con.execute(
        """
        INSERT OR REPLACE INTO nba_game
        (game_id, season, season_type, game_date,
         home_team_id, home_team_abbr, away_team_id, away_team_abbr,
         home_score, away_score, home_won, fetched_at)
        VALUES (?, '2025-26', 'Regular Season', ?, 0, ?, 0, ?, ?, ?, ?, ?)
        """,
        [
            game_id,
            game_date,
            home_abbr,
            away_abbr,
            home_score,
            away_score,
            home_score > away_score,
            datetime.now(tz=UTC).replace(tzinfo=None),
        ],
    )


def _seed_pinnacle_quote(
    con: duckdb.DuckDBPyConnection,
    *,
    odds_api_game_id: str,
    home_team: str,
    away_team: str,
    home_decimal_odds: float,
    away_decimal_odds: float,
    commence_time: datetime,
) -> None:
    con.execute(
        """
        INSERT INTO nba_odds
        (odds_api_game_id, bookmaker_key, market_key, home_team, away_team,
         commence_time, home_decimal_odds, away_decimal_odds,
         book_last_update, fetched_at)
        VALUES (?, 'pinnacle', 'h2h', ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            odds_api_game_id,
            home_team,
            away_team,
            commence_time.replace(tzinfo=None),
            home_decimal_odds,
            away_decimal_odds,
            commence_time.replace(tzinfo=None),
            commence_time.replace(tzinfo=None),
        ],
    )


def _seed_crosswalk(
    con: duckdb.DuckDBPyConnection,
    *,
    odds_api_game_id: str,
    nba_game_id: str,
    home_abbr: str,
    away_abbr: str,
    game_date: date,
) -> None:
    con.execute(
        """
        INSERT OR REPLACE INTO nba_game_crosswalk
        (odds_api_game_id, nba_game_id, home_team_abbr, away_team_abbr,
         game_date, matched_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            odds_api_game_id,
            nba_game_id,
            home_abbr,
            away_abbr,
            game_date,
            datetime.now(tz=UTC).replace(tzinfo=None),
        ],
    )


# --------------------------- hydration helpers ---------------------------


def test_fetch_finished_games_filters_unsettled(tmp_path: Path) -> None:
    """Only games with non-NULL home_score AND away_score should land."""
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    _seed_finished_game(
        con,
        game_id="g1",
        home_abbr="LAL",
        away_abbr="BOS",
        home_score=110,
        away_score=100,
        game_date=date(2026, 5, 4),
    )
    # Insert an unsettled game (NULL scores).
    con.execute(
        """
        INSERT INTO nba_game
        (game_id, season, season_type, game_date, home_team_id, home_team_abbr,
         away_team_id, away_team_abbr, home_score, away_score, home_won, fetched_at)
        VALUES ('g2', '2025-26', 'Regular Season', ?, 0, 'MIA', 0, 'NYK', NULL, NULL, NULL, ?)
        """,
        [date(2026, 5, 5), datetime.now(tz=UTC).replace(tzinfo=None)],
    )
    games = fetch_finished_games(con)
    assert len(games) == 1
    assert games[0].nba_game_id == "g1"
    con.close()


def test_fetch_finished_games_filters_by_date_range(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    seed_set = (
        ("g1", date(2026, 5, 1)),
        ("g2", date(2026, 5, 4)),
        ("g3", date(2026, 5, 7)),
    )
    for game_id, gd in seed_set:
        _seed_finished_game(
            con,
            game_id=game_id,
            home_abbr="LAL",
            away_abbr="BOS",
            home_score=110,
            away_score=100,
            game_date=gd,
        )
    games = fetch_finished_games(con, start_date=date(2026, 5, 3), end_date=date(2026, 5, 5))
    assert {g.nba_game_id for g in games} == {"g2"}
    con.close()


def test_fetch_finished_games_with_dates_returns_paired_tuples(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    _seed_finished_game(
        con,
        game_id="g1",
        home_abbr="LAL",
        away_abbr="BOS",
        home_score=110,
        away_score=100,
        game_date=date(2026, 5, 4),
    )
    pairs = fetch_finished_games_with_dates(con)
    assert len(pairs) == 1
    game, gd = pairs[0]
    assert game.nba_game_id == "g1"
    assert gd == date(2026, 5, 4)
    con.close()


def test_fetch_latest_pinnacle_quotes_picks_max_fetched_at(tmp_path: Path) -> None:
    """Two snapshots of the same game; the helper picks the latest
    fetched_at row."""
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    early = datetime(2026, 5, 4, 18, 0, tzinfo=UTC)
    late = datetime(2026, 5, 4, 22, 0, tzinfo=UTC)
    _seed_pinnacle_quote(
        con,
        odds_api_game_id="abc-123",
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        home_decimal_odds=2.0,  # early
        away_decimal_odds=1.83,
        commence_time=early,
    )
    _seed_pinnacle_quote(
        con,
        odds_api_game_id="abc-123",
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        home_decimal_odds=1.91,  # late (closer to tipoff)
        away_decimal_odds=1.91,
        commence_time=late,
    )
    quotes = fetch_latest_pinnacle_quotes(con)
    assert len(quotes) == 1
    assert quotes["abc-123"].home_decimal_odds == pytest.approx(1.91)
    con.close()


def test_fetch_latest_pinnacle_quotes_skips_non_pinnacle_books(tmp_path: Path) -> None:
    """A DraftKings quote in nba_odds should NOT show up in the
    Pinnacle-only fetch."""
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    con.execute(
        """
        INSERT INTO nba_odds
        (odds_api_game_id, bookmaker_key, market_key, home_team, away_team,
         commence_time, home_decimal_odds, away_decimal_odds,
         book_last_update, fetched_at)
        VALUES ('dk-only', 'draftkings', 'h2h', 'LAL', 'BOS', ?, 2.0, 1.85, ?, ?)
        """,
        [
            datetime(2026, 5, 4, 23, tzinfo=UTC).replace(tzinfo=None),
            datetime(2026, 5, 4, 22, tzinfo=UTC).replace(tzinfo=None),
            datetime(2026, 5, 4, 22, tzinfo=UTC).replace(tzinfo=None),
        ],
    )
    quotes = fetch_latest_pinnacle_quotes(con)
    assert quotes == {}
    con.close()


def test_fetch_crosswalk_rows_returns_typed_pairs(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    _seed_crosswalk(
        con,
        odds_api_game_id="abc-123",
        nba_game_id="g1",
        home_abbr="LAL",
        away_abbr="BOS",
        game_date=date(2026, 5, 4),
    )
    pairs = fetch_crosswalk_rows(con)
    assert len(pairs) == 1
    assert pairs[0].odds_api_game_id == "abc-123"
    assert pairs[0].nba_game_id == "g1"
    assert pairs[0].game_date == date(2026, 5, 4)
    con.close()


# --------------------------- replay_and_evaluate (PIT discipline) ---------------------------


def test_replay_uses_before_game_elo_state() -> None:
    """The load-bearing PIT property: per-game predictions are made
    with Elo state from BEFORE the game, then the state updates with
    the realized outcome.

    Construct two games where LAL wins twice. The second prediction
    should use the post-game-1 state (LAL stronger) -> our_prob_home
    on game 2 > our_prob_home on game 1.
    """

    games_with_dates = [
        (
            FinishedGame(
                nba_game_id="g1",
                home_team_abbr="LAL",
                away_team_abbr="BOS",
                home_score=110,
                away_score=100,
            ),
            date(2026, 5, 1),
        ),
        (
            FinishedGame(
                nba_game_id="g2",
                home_team_abbr="LAL",
                away_team_abbr="BOS",
                home_score=110,
                away_score=100,
            ),
            date(2026, 5, 8),
        ),
    ]
    quotes = {
        "oid-1": PinnacleQuote(
            odds_api_game_id="oid-1",
            home_decimal_odds=1.91,
            away_decimal_odds=1.91,
        ),
        "oid-2": PinnacleQuote(
            odds_api_game_id="oid-2",
            home_decimal_odds=1.91,
            away_decimal_odds=1.91,
        ),
    }
    crosswalk = [
        CrosswalkPair(
            odds_api_game_id="oid-1",
            nba_game_id="g1",
            home_team_abbr="LAL",
            away_team_abbr="BOS",
            game_date=date(2026, 5, 1),
        ),
        CrosswalkPair(
            odds_api_game_id="oid-2",
            nba_game_id="g2",
            home_team_abbr="LAL",
            away_team_abbr="BOS",
            game_date=date(2026, 5, 8),
        ),
    ]
    summary, final_elo = replay_and_evaluate(
        games_with_dates=games_with_dates,
        quotes=quotes,
        crosswalk=crosswalk,
    )
    assert summary.n_evaluated == 2
    g1_pred = summary.evaluations[0].our_prob_home
    g2_pred = summary.evaluations[1].our_prob_home
    # After game 1, LAL is stronger -> game 2 prediction is higher.
    assert g2_pred > g1_pred
    # Final state has LAL above INITIAL_RATING and BOS below.
    assert final_elo.ratings["LAL"] > INITIAL_RATING
    assert final_elo.ratings["BOS"] < INITIAL_RATING


def test_replay_updates_elo_even_for_unevaluated_games() -> None:
    """A game that's skipped (no odds quote) should still update the
    Elo state -- the model tracks team strength regardless of whether
    we had a quote."""

    games_with_dates = [
        (
            FinishedGame(
                nba_game_id="g1",
                home_team_abbr="LAL",
                away_team_abbr="BOS",
                home_score=110,
                away_score=100,
            ),
            date(2026, 5, 1),
        ),
    ]
    summary, final_elo = replay_and_evaluate(
        games_with_dates=games_with_dates,
        quotes={},  # no quotes -> skip
        crosswalk=[],  # also no crosswalk
    )
    assert summary.n_evaluated == 0
    # Elo still moved despite no evaluation.
    assert final_elo.ratings["LAL"] > INITIAL_RATING
    assert final_elo.ratings["BOS"] < INITIAL_RATING


def test_replay_handles_empty_inputs() -> None:
    """Empty games list -> empty summary, untouched Elo state."""
    summary, final_elo = replay_and_evaluate(games_with_dates=[], quotes={}, crosswalk=[])
    assert summary.n_evaluated == 0
    assert summary.brier_model is None
    assert final_elo.ratings == {}


# --------------------------- write_manifest ---------------------------


def test_manifest_round_trips_through_json(tmp_path: Path) -> None:
    """Empty summary still produces a valid JSON manifest."""
    summary, final_elo = replay_and_evaluate(games_with_dates=[], quotes={}, crosswalk=[])
    out = tmp_path / "manifest.json"
    written = write_manifest(summary, final_elo, out_path=out)
    assert written == out
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["n_evaluated"] == 0
    assert payload["mean_signed_clv"] is None
    assert "honest_caveats" in payload
    assert payload["final_elo_ratings"] == {}


def test_manifest_includes_final_elo_state(tmp_path: Path) -> None:
    """After a non-trivial replay, the manifest carries every team's
    final rating (sorted for determinism)."""
    elo = NbaEloRatings(ratings={"LAL": 1700.0, "BOS": 1300.0})
    summary, _ = replay_and_evaluate(games_with_dates=[], quotes={}, crosswalk=[])
    out = tmp_path / "manifest.json"
    write_manifest(summary, elo, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["final_elo_ratings"] == {"BOS": 1300.0, "LAL": 1700.0}


# --------------------------- main: end-to-end ---------------------------


def test_main_end_to_end_with_seeded_data(tmp_path: Path) -> None:
    """Seed nba_game + nba_odds + crosswalk; run main; verify the
    manifest lands and reports a non-zero n_evaluated."""
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    _seed_finished_game(
        con,
        game_id="g1",
        home_abbr="LAL",
        away_abbr="BOS",
        home_score=110,
        away_score=100,
        game_date=date(2026, 5, 4),
    )
    _seed_pinnacle_quote(
        con,
        odds_api_game_id="abc-123",
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        home_decimal_odds=1.91,
        away_decimal_odds=1.91,
        commence_time=datetime(2026, 5, 4, 23, tzinfo=UTC),
    )
    _seed_crosswalk(
        con,
        odds_api_game_id="abc-123",
        nba_game_id="g1",
        home_abbr="LAL",
        away_abbr="BOS",
        game_date=date(2026, 5, 4),
    )
    con.close()

    out = tmp_path / "manifest.json"
    n = run_main(db_path=db, manifest_path=out)
    assert n == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["n_evaluated"] == 1
    assert payload["mean_signed_clv"] is not None


def test_main_with_empty_db_exits_clean(tmp_path: Path) -> None:
    """No games seeded -> n_evaluated=0, manifest still lands."""
    db = _new_db(tmp_path)
    out = tmp_path / "manifest.json"
    n = run_main(db_path=db, manifest_path=out)
    assert n == 0
    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["n_evaluated"] == 0
