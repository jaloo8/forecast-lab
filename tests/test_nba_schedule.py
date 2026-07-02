"""Tests for NbaScheduleClient parsing + repository round-trip + ingest flow.

The client wraps `nba_api`, so most tests mock the API responses to keep
the suite hermetic. Schema tests use the real bootstrapped DuckDB.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from kq.clients.nba_schedule import (
    SEASON_TYPE_PLAYOFFS,
    SEASON_TYPE_PRESEASON,
    SEASON_TYPE_REGULAR,
    NbaGameRow,
    NbaScheduleClient,
    iter_dates_range,
)
from kq.flows.ingest_nba_schedule import ingest_range
from kq.storage.duckdb_store import bootstrap
from kq.storage.repositories.nba import fetch_nba_games, upsert_nba_games

# ----------------------------------------------------- iter_dates_range


def test_iter_dates_range_inclusive_both_ends() -> None:
    days = list(iter_dates_range(date(2025, 6, 1), date(2025, 6, 3)))
    assert days == [date(2025, 6, 1), date(2025, 6, 2), date(2025, 6, 3)]


def test_iter_dates_range_single_day() -> None:
    days = list(iter_dates_range(date(2025, 6, 1), date(2025, 6, 1)))
    assert days == [date(2025, 6, 1)]


def test_iter_dates_range_rejects_inverted_range() -> None:
    with pytest.raises(ValueError, match="precedes"):
        list(iter_dates_range(date(2025, 6, 5), date(2025, 6, 1)))


# ----------------------------------------------------- season-id derivation


def test_derive_season_type_for_known_prefixes() -> None:
    """Encoded prefix mapping per `nba_api` documentation."""
    from kq.clients.nba_schedule import _derive_season_type_from_game_id  # noqa: PLC0415

    assert _derive_season_type_from_game_id("0022400123") == SEASON_TYPE_REGULAR
    assert _derive_season_type_from_game_id("0042400001") == SEASON_TYPE_PLAYOFFS
    assert _derive_season_type_from_game_id("0012400001") == SEASON_TYPE_PRESEASON
    assert _derive_season_type_from_game_id("0992400001") == "Other"  # unknown prefix
    assert _derive_season_type_from_game_id("") == "Other"


def test_derive_season_from_game_id() -> None:
    """Game id encodes the season-start year in positions 3-4."""
    from kq.clients.nba_schedule import _derive_season_from_game_id  # noqa: PLC0415

    assert _derive_season_from_game_id("0022400123") == "2024-25"
    assert _derive_season_from_game_id("0021900456") == "2019-20"
    assert _derive_season_from_game_id("00") == ""  # too short


# ----------------------------------------------------- scoreboard parser


def _scoreboard_response(
    games: list[dict[str, Any]],
    *,
    include_status: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build a fake (game_header, line_score) pair matching `ScoreboardV2`'s shape.

    ``include_status=True`` adds the real payload's `GAME_STATUS_ID` /
    `GAME_STATUS_TEXT` columns (from each game's ``status_id`` /
    ``status_text`` keys); the default omits them so tests can exercise the
    conservative no-status fallback path.
    """
    header_cols = [
        "GAME_ID",
        "GAME_DATE_EST",
        "HOME_TEAM_ID",
        "VISITOR_TEAM_ID",
        "SEASON",
    ]
    if include_status:
        header_cols += ["GAME_STATUS_ID", "GAME_STATUS_TEXT"]
    header_data: list[list[Any]] = []
    for g in games:
        row = [
            g["game_id"],
            g.get("game_date", "2024-12-25T00:00:00"),
            g["home_team_id"],
            g["away_team_id"],
            g.get("season", "2024-25"),
        ]
        if include_status:
            row += [g.get("status_id"), g.get("status_text")]
        header_data.append(row)
    header = {"headers": header_cols, "data": header_data}
    # Line score has 2 rows per game (one per team).
    line_data: list[list[Any]] = []
    for g in games:
        line_data.append(
            [
                g["game_id"],
                g["home_team_id"],
                g["home_team_abbr"],
                g.get("home_score"),
            ]
        )
        line_data.append(
            [
                g["game_id"],
                g["away_team_id"],
                g["away_team_abbr"],
                g.get("away_score"),
            ]
        )
    line = {
        "headers": ["GAME_ID", "TEAM_ID", "TEAM_ABBREVIATION", "PTS"],
        "data": line_data,
    }
    return header, line


def test_fetch_games_for_date_parses_completed_game() -> None:
    """A completed game should populate scores + home_won."""
    mock_response = _scoreboard_response(
        [
            {
                "game_id": "0022400123",
                "game_date": "2024-12-25T00:00:00",
                "home_team_id": 1610612747,
                "home_team_abbr": "LAL",
                "home_score": 105,
                "away_team_id": 1610612738,
                "away_team_abbr": "BOS",
                "away_score": 99,
            },
        ]
    )
    with patch("nba_api.stats.endpoints.scoreboardv2.ScoreboardV2") as mock_board:
        instance = mock_board.return_value
        instance.game_header = MagicMock(get_dict=lambda: mock_response[0])
        instance.line_score = MagicMock(get_dict=lambda: mock_response[1])

        client = NbaScheduleClient()
        games = client.fetch_games_for_date(date(2024, 12, 25))

    assert len(games) == 1
    g = games[0]
    assert g.game_id == "0022400123"
    assert g.home_team_abbr == "LAL"
    assert g.away_team_abbr == "BOS"
    assert g.home_score == 105
    assert g.away_score == 99
    assert g.home_won is True
    assert g.season == "2024-25"
    assert g.season_type == SEASON_TYPE_REGULAR


def test_fetch_games_for_date_handles_unfinished_game() -> None:
    """Pre-game / mid-game: scores are NULL → home_won is None."""
    mock_response = _scoreboard_response(
        [
            {
                "game_id": "0022400999",
                "home_team_id": 1,
                "home_team_abbr": "X",
                "away_team_id": 2,
                "away_team_abbr": "Y",
                "home_score": None,
                "away_score": None,
            },
        ]
    )
    with patch("nba_api.stats.endpoints.scoreboardv2.ScoreboardV2") as mock_board:
        instance = mock_board.return_value
        instance.game_header = MagicMock(get_dict=lambda: mock_response[0])
        instance.line_score = MagicMock(get_dict=lambda: mock_response[1])
        client = NbaScheduleClient()
        games = client.fetch_games_for_date(date(2024, 12, 25))
    g = games[0]
    assert g.home_score is None
    assert g.away_score is None
    assert g.home_won is None


def test_fetch_games_for_date_returns_empty_on_upstream_error() -> None:
    """API error → empty list + warning, NOT a crash."""
    with patch("nba_api.stats.endpoints.scoreboardv2.ScoreboardV2") as mock_board:
        mock_board.side_effect = RuntimeError("upstream timeout")
        client = NbaScheduleClient()
        assert client.fetch_games_for_date(date(2024, 12, 25)) == []


# ------------------------------------------- finality guard (PR-H / PR-D)


def _fetch_with_mock_board(
    mock_response: tuple[dict[str, Any], dict[str, Any]],
    target: date,
) -> list[NbaGameRow]:
    with patch("nba_api.stats.endpoints.scoreboardv2.ScoreboardV2") as mock_board:
        instance = mock_board.return_value
        instance.game_header = MagicMock(get_dict=lambda: mock_response[0])
        instance.line_score = MagicMock(get_dict=lambda: mock_response[1])
        return NbaScheduleClient().fetch_games_for_date(target)


def test_in_progress_game_with_live_score_never_finalizes() -> None:
    """PR-H regression: GAME_STATUS_ID=2 (in progress) with a live PTS must
    NOT populate scores or home_won — a non-NULL home_won irreversibly
    settles paper trades. The past game_date must not override the live
    status (status wins over the conservative date rule)."""
    mock_response = _scoreboard_response(
        [
            {
                "game_id": "0022400777",
                "game_date": "2024-12-25T00:00:00",  # long past — date rule would say final
                "home_team_id": 1,
                "home_team_abbr": "LAL",
                "home_score": 55,  # live mid-game score
                "away_team_id": 2,
                "away_team_abbr": "BOS",
                "away_score": 60,
                "status_id": 2,
                "status_text": "Q3 5:32",
            },
        ],
        include_status=True,
    )
    games = _fetch_with_mock_board(mock_response, date(2024, 12, 25))
    g = games[0]
    assert g.home_won is None
    assert g.home_score is None
    assert g.away_score is None


def test_status_final_finalizes_even_same_day() -> None:
    """GAME_STATUS_ID=3 marks the game final regardless of the calendar
    date, so a game that finished tonight settles tonight."""
    from kq.clients.nba_schedule import _us_eastern_today  # noqa: PLC0415

    today = _us_eastern_today()
    mock_response = _scoreboard_response(
        [
            {
                "game_id": "0022400778",
                "game_date": f"{today.isoformat()}T00:00:00",
                "home_team_id": 1,
                "home_team_abbr": "LAL",
                "home_score": 112,
                "away_team_id": 2,
                "away_team_abbr": "BOS",
                "away_score": 104,
                "status_id": 3,
                "status_text": "Final",
            },
        ],
        include_status=True,
    )
    g = _fetch_with_mock_board(mock_response, today)[0]
    assert g.home_won is True
    assert g.home_score == 112
    assert g.away_score == 104


def test_no_status_same_day_scores_stay_null() -> None:
    """Conservative fallback (payload without status fields): both scores
    present is NOT enough on the game's own US/Eastern day — the game could
    still be live. Only a strictly-elapsed ET date finalizes."""
    from kq.clients.nba_schedule import _us_eastern_today  # noqa: PLC0415

    today = _us_eastern_today()
    mock_response = _scoreboard_response(
        [
            {
                "game_id": "0022400779",
                "game_date": f"{today.isoformat()}T00:00:00",
                "home_team_id": 1,
                "home_team_abbr": "LAL",
                "home_score": 88,
                "away_team_id": 2,
                "away_team_abbr": "BOS",
                "away_score": 90,
            },
        ]
    )
    g = _fetch_with_mock_board(mock_response, today)[0]
    assert g.home_won is None
    assert g.home_score is None
    assert g.away_score is None


def test_lgf_wl_none_means_not_final() -> None:
    """LeagueGameFinder carries `WL` ('W'/'L' once final, None while live).
    A live row must not finalize even when PTS is populated and the date
    has passed."""
    payload = {
        "headers": [
            "SEASON_ID",
            "GAME_ID",
            "GAME_DATE",
            "TEAM_ID",
            "TEAM_ABBREVIATION",
            "MATCHUP",
            "WL",
            "PTS",
        ],
        "data": [
            ["22024", "0022400500", "2025-01-15", 1, "BOS", "BOS @ LAL", None, 61],
            ["22024", "0022400500", "2025-01-15", 2, "LAL", "LAL vs. BOS", None, 58],
        ],
    }
    with patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder") as mock_finder:
        mock_finder.return_value.league_game_finder_results = MagicMock(get_dict=lambda: payload)
        games = NbaScheduleClient().fetch_games_for_range(
            start=date(2025, 1, 15), end=date(2025, 1, 15)
        )
    g = games[0]
    assert g.home_won is None
    assert g.home_score is None
    assert g.away_score is None


def test_fetch_games_for_range_rejects_inverted() -> None:
    client = NbaScheduleClient()
    with pytest.raises(ValueError, match="precedes"):
        client.fetch_games_for_range(start=date(2024, 6, 1), end=date(2024, 5, 1))


def test_fetch_games_for_range_aggregates_two_team_rows_per_game() -> None:
    """LeagueGameFinder returns ONE row per (game, team). Both must
    fold into one NbaGameRow with home/away resolved by `MATCHUP`."""
    payload = {
        "headers": [
            "SEASON_ID",
            "GAME_ID",
            "GAME_DATE",
            "TEAM_ID",
            "TEAM_ABBREVIATION",
            "MATCHUP",
            "PTS",
        ],
        "data": [
            ["22024", "0022400500", "2025-01-15", 1, "BOS", "BOS @ LAL", 110],
            ["22024", "0022400500", "2025-01-15", 2, "LAL", "LAL vs. BOS", 115],
        ],
    }
    with patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder") as mock_finder:
        mock_finder.return_value.league_game_finder_results = MagicMock(
            get_dict=lambda: payload,
        )
        client = NbaScheduleClient()
        games = client.fetch_games_for_range(start=date(2025, 1, 15), end=date(2025, 1, 15))

    assert len(games) == 1
    g = games[0]
    assert g.home_team_abbr == "LAL"  # "vs." marker → home
    assert g.away_team_abbr == "BOS"
    assert g.home_score == 115
    assert g.away_score == 110
    assert g.home_won is True


# ----------------------------------------------------- repository


def test_upsert_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    rows = [
        NbaGameRow(
            game_id="0022400111",
            season="2024-25",
            season_type=SEASON_TYPE_REGULAR,
            game_date=date(2024, 12, 25),
            home_team_id=1,
            home_team_abbr="LAL",
            away_team_id=2,
            away_team_abbr="BOS",
            home_score=105,
            away_score=99,
            home_won=True,
        ),
    ]
    con = duckdb.connect(str(db))
    try:
        n = upsert_nba_games(con, rows)
    finally:
        con.close()
    assert n == 1
    con = duckdb.connect(str(db), read_only=True)
    try:
        out = fetch_nba_games(con)
    finally:
        con.close()
    assert len(out) == 1
    assert out[0]["home_won"] is True
    assert out[0]["home_score"] == 105


def test_upsert_idempotent_on_game_id(tmp_path: Path) -> None:
    """Re-upserting same game_id refreshes the row but doesn't duplicate."""
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    row = NbaGameRow(
        game_id="0022400222",
        season="2024-25",
        season_type=SEASON_TYPE_REGULAR,
        game_date=date(2024, 12, 26),
        home_team_id=1,
        home_team_abbr="LAL",
        away_team_id=2,
        away_team_abbr="BOS",
        home_score=None,
        away_score=None,
        home_won=None,
    )
    finished = NbaGameRow(
        game_id="0022400222",  # same id
        season="2024-25",
        season_type=SEASON_TYPE_REGULAR,
        game_date=date(2024, 12, 26),
        home_team_id=1,
        home_team_abbr="LAL",
        away_team_id=2,
        away_team_abbr="BOS",
        home_score=110,
        away_score=105,
        home_won=True,
    )
    con = duckdb.connect(str(db))
    try:
        upsert_nba_games(con, [row])
        upsert_nba_games(con, [finished])
    finally:
        con.close()
    con = duckdb.connect(str(db), read_only=True)
    try:
        out = fetch_nba_games(con)
    finally:
        con.close()
    assert len(out) == 1
    # Pre-game NULLs replaced with finished scores after re-upsert.
    assert out[0]["home_score"] == 110
    assert out[0]["home_won"] is True


def _game_row(
    *,
    game_id: str = "0022400333",
    home_score: int | None,
    away_score: int | None,
    home_won: bool | None,
) -> NbaGameRow:
    return NbaGameRow(
        game_id=game_id,
        season="2024-25",
        season_type=SEASON_TYPE_REGULAR,
        game_date=date(2024, 12, 26),
        home_team_id=1,
        home_team_abbr="LAL",
        away_team_id=2,
        away_team_abbr="BOS",
        home_score=home_score,
        away_score=away_score,
        home_won=home_won,
    )


def test_upsert_degraded_refetch_cannot_regress_a_final(tmp_path: Path) -> None:
    """PR-H regression: once home_won is recorded, a later degraded fetch
    (scores/status missing → all-NULL row) must NOT null the result back
    out — settlement is irreversible, so the recorded final is frozen."""
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    con = duckdb.connect(str(db))
    try:
        upsert_nba_games(con, [_game_row(home_score=110, away_score=105, home_won=True)])
        upsert_nba_games(con, [_game_row(home_score=None, away_score=None, home_won=None)])
        row = con.execute(
            "SELECT home_score, away_score, home_won FROM nba_game WHERE game_id = '0022400333'"
        ).fetchone()
    finally:
        con.close()
    assert row == (110, 105, True)


def test_upsert_frozen_final_ignores_conflicting_rescore(tmp_path: Path) -> None:
    """A recorded final's scores and outcome never change on refetch, even if
    the new payload claims different (e.g. partial live) values."""
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    con = duckdb.connect(str(db))
    try:
        upsert_nba_games(con, [_game_row(home_score=110, away_score=105, home_won=True)])
        upsert_nba_games(con, [_game_row(home_score=50, away_score=60, home_won=False)])
        row = con.execute(
            "SELECT home_score, away_score, home_won FROM nba_game WHERE game_id = '0022400333'"
        ).fetchone()
    finally:
        con.close()
    assert row == (110, 105, True)


def test_settlement_never_fires_on_in_progress_row(tmp_path: Path) -> None:
    """End-to-end PR-H guard: an in-progress scoreboard payload (live score,
    GAME_STATUS_ID=2) is ingested with home_won NULL, so the NBA settlement
    pass leaves the paper trade unsettled."""
    from datetime import UTC, datetime  # noqa: PLC0415

    from kq.execution.paper import PaperTradeIntent  # noqa: PLC0415
    from kq.storage.repositories.paper_trades import (  # noqa: PLC0415
        insert_paper_trade_with_signal,
        settle_due_nba_paper_trades,
    )

    mock_response = _scoreboard_response(
        [
            {
                "game_id": "0022400888",
                "game_date": "2024-12-26T00:00:00",
                "home_team_id": 1,
                "home_team_abbr": "LAL",
                "home_score": 55,  # live mid-game score
                "away_team_id": 2,
                "away_team_abbr": "BOS",
                "away_score": 60,
                "status_id": 2,
                "status_text": "Q3 5:32",
            },
        ],
        include_status=True,
    )
    games = _fetch_with_mock_board(mock_response, date(2024, 12, 26))

    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    con = duckdb.connect(str(db))
    try:
        upsert_nba_games(con, games)
        intent = PaperTradeIntent(
            signal_id="sig-in-progress",
            as_of=datetime(2024, 12, 26, 23, 0, tzinfo=UTC),
            ticker="KXNBAGAME-24DEC26BOSLAL-LAL",  # BOS @ LAL, YES = home
            side="BUY_YES",
            limit_price=0.50,
            qty=10,
            fee_usd=0.10,
            model_prob_yes=0.60,
            market_yes_bid=0.49,
            market_yes_ask=0.50,
            edge_bps=1000,
            model_name="nba_pinnacle_anchored_v1",
        )
        insert_paper_trade_with_signal(con, intent)
        assert settle_due_nba_paper_trades(con) == 0
        row = con.execute("SELECT settled_at FROM paper_trade").fetchone()
        game = con.execute("SELECT home_won FROM nba_game WHERE game_id = '0022400888'").fetchone()
    finally:
        con.close()
    assert row is not None and row[0] is None  # trade still open
    assert game is not None and game[0] is None  # home_won stayed NULL


def test_fetch_filters_by_date_range(tmp_path: Path) -> None:
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    rows = [
        NbaGameRow(
            game_id=f"002240{i:04d}",
            season="2024-25",
            season_type=SEASON_TYPE_REGULAR,
            game_date=date(2024, 12, day),
            home_team_id=1,
            home_team_abbr="A",
            away_team_id=2,
            away_team_abbr="B",
            home_score=None,
            away_score=None,
            home_won=None,
        )
        for i, day in enumerate([20, 25, 30])
    ]
    con = duckdb.connect(str(db))
    try:
        upsert_nba_games(con, rows)
    finally:
        con.close()
    con = duckdb.connect(str(db), read_only=True)
    try:
        out = fetch_nba_games(con, start_date=date(2024, 12, 24), end_date=date(2024, 12, 27))
    finally:
        con.close()
    assert len(out) == 1
    assert out[0]["game_date"] == date(2024, 12, 25)


def test_fetch_filters_by_season_type(tmp_path: Path) -> None:
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    rows = [
        NbaGameRow(
            game_id="0022400001",
            season="2024-25",
            season_type=SEASON_TYPE_REGULAR,
            game_date=date(2024, 12, 25),
            home_team_id=1,
            home_team_abbr="A",
            away_team_id=2,
            away_team_abbr="B",
            home_score=None,
            away_score=None,
            home_won=None,
        ),
        NbaGameRow(
            game_id="0042400001",
            season="2024-25",
            season_type=SEASON_TYPE_PLAYOFFS,
            game_date=date(2025, 4, 20),
            home_team_id=1,
            home_team_abbr="A",
            away_team_id=2,
            away_team_abbr="B",
            home_score=None,
            away_score=None,
            home_won=None,
        ),
    ]
    con = duckdb.connect(str(db))
    try:
        upsert_nba_games(con, rows)
    finally:
        con.close()
    con = duckdb.connect(str(db), read_only=True)
    try:
        out = fetch_nba_games(con, season_types=(SEASON_TYPE_PLAYOFFS,))
    finally:
        con.close()
    assert len(out) == 1
    assert out[0]["season_type"] == SEASON_TYPE_PLAYOFFS


# ----------------------------------------------------- ingest_range


def test_ingest_range_calls_client_per_day(tmp_path: Path) -> None:
    """ingest_range loops day-by-day and aggregates upserts."""
    db = tmp_path / "ing.duckdb"
    bootstrap(db)

    fake_client = MagicMock()
    fake_client.fetch_games_for_date.return_value = [
        NbaGameRow(
            game_id="0022400001",
            season="2024-25",
            season_type=SEASON_TYPE_REGULAR,
            game_date=date(2024, 12, 25),
            home_team_id=1,
            home_team_abbr="A",
            away_team_id=2,
            away_team_abbr="B",
            home_score=None,
            away_score=None,
            home_won=None,
        ),
    ]
    n = ingest_range(
        start=date(2024, 12, 25), end=date(2024, 12, 27), db_path=db, client=fake_client
    )

    # 3 days x 1 game per day = 3 upserts (the same game_id; idempotent re-upsert).
    assert n == 3
    # Idempotency means only 1 distinct row in the DB.
    con = duckdb.connect(str(db), read_only=True)
    try:
        rows = fetch_nba_games(con)
    finally:
        con.close()
    assert len(rows) == 1
    assert fake_client.fetch_games_for_date.call_count == 3


def test_ingest_range_rejects_inverted_window(tmp_path: Path) -> None:
    db = tmp_path / "ing.duckdb"
    bootstrap(db)
    with pytest.raises(ValueError, match="precedes"):
        ingest_range(start=date(2024, 12, 27), end=date(2024, 12, 25), db_path=db)
