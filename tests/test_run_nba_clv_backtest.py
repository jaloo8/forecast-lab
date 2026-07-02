"""Tests for the NBA CLV backtest flow.

Coverage:
- DuckDB-row hydration helpers (finished games, pre-tipoff Pinnacle
  quotes, crosswalk).
- The pre-tipoff anchor discipline (2026-06-11 audit): in-play rows
  (fetched_at >= commence_time) must NEVER move the entry/close
  anchors; games with ONLY in-play rows are excluded and counted.
- Chronological replay updates Elo state; per-game predictions use
  the BEFORE-game state (the load-bearing PIT property).
- Manifest writes JSON-safely with all aggregate fields, new schema
  (mean_clv), and no trace of the retired mean_signed_clv.
- main() runs against a fully-seeded DB and produces a non-trivial
  manifest; runs against an empty DB and exits clean with
  n_evaluated=0.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from kq.backtest.nba_clv import FinishedGame, GameQuotes, PinnacleQuote
from kq.flows.run_nba_clv_backtest import (
    fetch_crosswalk_rows,
    fetch_finished_games,
    fetch_finished_games_with_dates,
    fetch_pretipoff_pinnacle_quotes,
    replay_and_evaluate,
    write_manifest,
)
from kq.flows.run_nba_clv_backtest import main as run_main
from kq.models.nba_crosswalk import CrosswalkPair
from kq.models.nba_elo import INITIAL_RATING, NbaEloRatings, update_after_game
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
    fetched_at: datetime | None = None,
) -> None:
    """Insert one Pinnacle h2h snapshot. ``fetched_at`` defaults to one
    hour BEFORE tipoff (a valid pre-tipoff row); pass an explicit value
    at/after ``commence_time`` to simulate an in-play snapshot."""
    fetched = fetched_at if fetched_at is not None else commence_time - timedelta(hours=1)
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
            fetched.replace(tzinfo=None),
            fetched.replace(tzinfo=None),
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


def _gq(oid: str, home: float, away: float) -> GameQuotes:
    q = PinnacleQuote(odds_api_game_id=oid, home_decimal_odds=home, away_decimal_odds=away)
    return GameQuotes(odds_api_game_id=oid, entry=q, close=q)


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


def test_fetch_pretipoff_quotes_entry_is_earliest_close_is_latest(tmp_path: Path) -> None:
    """Two pre-tipoff snapshots: entry = earliest, close = latest."""
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    tipoff = datetime(2026, 5, 5, 0, 0, tzinfo=UTC)
    _seed_pinnacle_quote(
        con,
        odds_api_game_id="abc-123",
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        home_decimal_odds=2.0,  # opening line
        away_decimal_odds=1.83,
        commence_time=tipoff,
        fetched_at=tipoff - timedelta(hours=6),
    )
    _seed_pinnacle_quote(
        con,
        odds_api_game_id="abc-123",
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        home_decimal_odds=1.91,  # closing line (closest to tipoff)
        away_decimal_odds=1.91,
        commence_time=tipoff,
        fetched_at=tipoff - timedelta(hours=1),
    )
    quotes, inplay_only = fetch_pretipoff_pinnacle_quotes(con)
    assert len(quotes) == 1
    assert inplay_only == set()
    gq = quotes["abc-123"]
    assert gq.entry.home_decimal_odds == pytest.approx(2.0)
    assert gq.close.home_decimal_odds == pytest.approx(1.91)
    con.close()


def test_inplay_quote_does_not_move_the_closing_anchor(tmp_path: Path) -> None:
    """THE audit fix (root cause #10): a snapshot fetched AFTER tipoff --
    which embeds the realized outcome (home at 1.05 here) -- must never
    become the closing anchor. Under the old MAX(fetched_at) fetch with
    no pre-tipoff filter, this test fails (close would be 1.05)."""
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    tipoff = datetime(2026, 5, 5, 0, 0, tzinfo=UTC)
    _seed_pinnacle_quote(
        con,
        odds_api_game_id="abc-123",
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        home_decimal_odds=1.91,
        away_decimal_odds=1.91,
        commence_time=tipoff,
        fetched_at=tipoff - timedelta(hours=1),
    )
    _seed_pinnacle_quote(
        con,
        odds_api_game_id="abc-123",
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        home_decimal_odds=1.05,  # in-play: home is up 20 in the 4th
        away_decimal_odds=12.0,
        commence_time=tipoff,
        fetched_at=tipoff + timedelta(hours=2),
    )
    quotes, inplay_only = fetch_pretipoff_pinnacle_quotes(con)
    assert quotes["abc-123"].close.home_decimal_odds == pytest.approx(1.91)
    assert quotes["abc-123"].entry.home_decimal_odds == pytest.approx(1.91)
    assert inplay_only == set()
    con.close()


def test_game_with_only_inplay_quotes_is_reported_for_exclusion(tmp_path: Path) -> None:
    """No pre-tipoff row at all -> the game id lands in the exclusion
    set (and NOT in the quotes dict), so the evaluator can count it in
    n_excluded_no_pretipoff_close rather than scoring it."""
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    tipoff = datetime(2026, 5, 5, 0, 0, tzinfo=UTC)
    _seed_pinnacle_quote(
        con,
        odds_api_game_id="abc-123",
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        home_decimal_odds=1.05,
        away_decimal_odds=12.0,
        commence_time=tipoff,
        fetched_at=tipoff + timedelta(minutes=30),
    )
    quotes, inplay_only = fetch_pretipoff_pinnacle_quotes(con)
    assert quotes == {}
    assert inplay_only == {"abc-123"}
    con.close()


def test_fetch_pretipoff_quotes_skips_non_pinnacle_books(tmp_path: Path) -> None:
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
    quotes, inplay_only = fetch_pretipoff_pinnacle_quotes(con)
    assert quotes == {}
    assert inplay_only == set()
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
        "oid-1": _gq("oid-1", 1.91, 1.91),
        "oid-2": _gq("oid-2", 1.91, 1.91),
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


def test_replay_counts_inplay_only_exclusions() -> None:
    """A crosswalked game whose odds id sits in the in-play-only set is
    excluded + counted; its outcome still updates Elo."""
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
    crosswalk = [
        CrosswalkPair(
            odds_api_game_id="oid-1",
            nba_game_id="g1",
            home_team_abbr="LAL",
            away_team_abbr="BOS",
            game_date=date(2026, 5, 1),
        ),
    ]
    summary, final_elo = replay_and_evaluate(
        games_with_dates=games_with_dates,
        quotes={},
        crosswalk=crosswalk,
        inplay_only_odds_ids={"oid-1"},
    )
    assert summary.n_evaluated == 0
    assert summary.n_excluded_no_pretipoff_close == 1
    assert summary.n_skipped_no_odds == 0
    assert final_elo.ratings["LAL"] > INITIAL_RATING


def test_replay_handles_empty_inputs() -> None:
    """Empty games list -> empty summary, untouched Elo state."""
    summary, final_elo = replay_and_evaluate(games_with_dates=[], quotes={}, crosswalk=[])
    assert summary.n_evaluated == 0
    assert summary.brier_model is None
    assert final_elo.ratings == {}


def test_replay_regresses_elo_at_season_boundary() -> None:
    """Crossing a season boundary (June game -> October game) must pull
    every rating 1/4 toward 1505 before the new season's games fold in.

    Regression for the 2026-06-11 audit finding that
    ``regress_to_baseline`` was dead code: a multi-season replay used to
    carry June's ratings straight into October.
    """
    game = FinishedGame(
        nba_game_id="g1",
        home_team_abbr="LAL",
        away_team_abbr="BOS",
        home_score=110,
        away_score=100,
    )
    game2 = FinishedGame(
        nba_game_id="g2",
        home_team_abbr="LAL",
        away_team_abbr="BOS",
        home_score=110,
        away_score=100,
    )
    games_with_dates = [
        (game, date(2026, 4, 10)),  # season 2025-26
        (game2, date(2026, 10, 25)),  # season 2026-27
    ]
    # No quotes/crosswalk: evaluation is skipped but the Elo replay (the
    # part under test) still runs both updates + the boundary regression.
    _summary, final_elo = replay_and_evaluate(
        games_with_dates=games_with_dates, quotes={}, crosswalk=[]
    )

    expected = NbaEloRatings()
    update_after_game(
        expected,
        home_team_abbr="LAL",
        away_team_abbr="BOS",
        home_score=110,
        away_score=100,
    )
    expected.regress_to_baseline()
    update_after_game(
        expected,
        home_team_abbr="LAL",
        away_team_abbr="BOS",
        home_score=110,
        away_score=100,
    )

    unregressed = NbaEloRatings()
    for _ in range(2):
        update_after_game(
            unregressed,
            home_team_abbr="LAL",
            away_team_abbr="BOS",
            home_score=110,
            away_score=100,
        )

    assert final_elo.ratings["LAL"] == pytest.approx(expected.ratings["LAL"])
    assert final_elo.ratings["BOS"] == pytest.approx(expected.ratings["BOS"])
    assert final_elo.ratings["LAL"] != pytest.approx(unregressed.ratings["LAL"])


# --------------------------- write_manifest ---------------------------


def test_manifest_round_trips_through_json(tmp_path: Path) -> None:
    """Empty summary still produces a valid JSON manifest with the new
    (post-audit) schema and no retired keys."""
    summary, final_elo = replay_and_evaluate(games_with_dates=[], quotes={}, crosswalk=[])
    out = tmp_path / "manifest.json"
    written = write_manifest(summary, final_elo, out_path=out)
    assert written == out
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["n_evaluated"] == 0
    assert payload["mean_clv"] is None
    assert payload["mean_edge_vs_close"] is None
    assert payload["n_excluded_no_pretipoff_close"] == 0
    assert payload["n_picked"] == 0
    assert "honest_caveats" in payload
    assert payload["final_elo_ratings"] == {}
    # The outcome-conditioned metrics are gone -- not null, GONE.
    assert "mean_signed_clv" not in payload
    assert "mean_clv_vs_pinnacle" not in payload


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
    """Seed nba_game + nba_odds + crosswalk (including an in-play row
    that must NOT anchor); run main; verify the manifest lands with the
    price-based CLV computed from the PRE-TIPOFF close only."""
    db = _new_db(tmp_path)
    con = duckdb.connect(str(db))
    tipoff = datetime(2026, 5, 4, 23, tzinfo=UTC)
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
        commence_time=tipoff,
        fetched_at=tipoff - timedelta(hours=1),
    )
    # In-play snapshot embedding the outcome; latest by fetched_at, but
    # it must not move the anchor.
    _seed_pinnacle_quote(
        con,
        odds_api_game_id="abc-123",
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        home_decimal_odds=1.02,
        away_decimal_odds=21.0,
        commence_time=tipoff,
        fetched_at=tipoff + timedelta(hours=1),
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
    assert payload["n_picked"] == 1
    assert payload["n_excluded_no_pretipoff_close"] == 0
    # Elo at parity leans home -> bought home at 1/1.91; the pre-tipoff
    # close devigs to 0.5. If the in-play 1.02 row had leaked into the
    # anchor this would be ~0.95 - 0.52 = +0.43 instead.
    assert payload["mean_clv"] == pytest.approx(0.5 - 1 / 1.91)
    assert "mean_signed_clv" not in payload


def test_main_with_empty_db_exits_clean(tmp_path: Path) -> None:
    """No games seeded -> n_evaluated=0, manifest still lands."""
    db = _new_db(tmp_path)
    out = tmp_path / "manifest.json"
    n = run_main(db_path=db, manifest_path=out)
    assert n == 0
    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["n_evaluated"] == 0
