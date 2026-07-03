"""Tests for the NFL schedule lane: /scores parsing, the score->game-row
adapter (ties!), the finality-freeze upsert, and the ingest flow.

The scores fixture carries the four wire states that matter:
completed-with-scores, upcoming (scores null), completed TIE, and the
degraded completed-without-scores payload that must never settle anything.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

import duckdb
import httpx
import pytest

from kq.clients.the_odds_api import (
    OddsApiScore,
    QuotaUsage,
    TheOddsApiClient,
    parse_scores_response,
)
from kq.config import get_settings
from kq.flows.ingest_nfl_schedule import _persist, fetch_and_upsert
from kq.flows.ingest_nfl_schedule import main as run_ingest_nfl_schedule
from kq.models.nfl_crosswalk import (
    NFL_TEAM_NAME_TO_ABBR,
    NflGameRow,
    nfl_game_row_from_score,
    nfl_season_start_year,
)
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.nfl import fetch_nfl_games, upsert_nfl_games

FIXTURE = Path(__file__).parent / "fixtures" / "the_odds_api_nfl_scores.json"


def _load_fixture_scores() -> list[OddsApiScore]:
    return parse_scores_response(json.loads(FIXTURE.read_text(encoding="utf-8")))


# --------------------------- parse_scores_response ---------------------------


def test_parse_scores_completed_game() -> None:
    scores = {s.game_id: s for s in _load_fixture_scores()}
    done = scores["nfl5678efgh5678efgh5678efgh5678ef"]
    assert done.completed is True
    assert done.home_team == "Jacksonville Jaguars"
    assert done.home_score == 27
    assert done.away_score == 13
    assert done.last_update is not None


def test_parse_scores_upcoming_game_has_no_scores() -> None:
    scores = {s.game_id: s for s in _load_fixture_scores()}
    upcoming = scores["nfl1234abcd1234abcd1234abcd1234ab"]
    assert upcoming.completed is False
    assert upcoming.home_score is None
    assert upcoming.away_score is None
    assert upcoming.last_update is None


def test_parse_scores_tie_parses_as_completed_equal_scores() -> None:
    scores = {s.game_id: s for s in _load_fixture_scores()}
    tie = scores["nfl9999tttt9999tttt9999tttt9999tt"]
    assert tie.completed is True
    assert tie.home_score == tie.away_score == 20


def test_parse_scores_downgrades_completed_without_scores() -> None:
    """A completed flag with a null scores array is a degraded payload;
    it must parse as NOT completed so settlement never fires on it."""
    scores = {s.game_id: s for s in _load_fixture_scores()}
    degraded = scores["nflaaaadddd0000dddd0000dddd0000dd"]
    assert degraded.completed is False
    assert degraded.home_score is None


# --------------------------- score -> NflGameRow adapter ---------------------------


def test_game_row_from_completed_score() -> None:
    scores = {s.game_id: s for s in _load_fixture_scores()}
    row = nfl_game_row_from_score(scores["nfl5678efgh5678efgh5678efgh5678ef"])
    assert row is not None
    assert row.home_team_abbr == "JAC"  # Kalshi's code, not ESPN's JAX
    assert row.away_team_abbr == "CLE"
    assert row.game_date == date(2026, 9, 13)  # 17:00 UTC -> same ET date
    assert row.completed is True
    assert row.home_won is True
    assert row.is_tie is False
    assert row.season == 2026


def test_game_row_tie_keeps_home_won_null() -> None:
    scores = {s.game_id: s for s in _load_fixture_scores()}
    row = nfl_game_row_from_score(scores["nfl9999tttt9999tttt9999tttt9999tt"])
    assert row is not None
    assert row.completed is True
    assert row.home_won is None
    assert row.is_tie is True


def test_game_row_late_utc_kickoff_maps_to_us_eastern_date() -> None:
    """DAL@NYG kicks 2026-09-14 00:20 UTC = Sunday 2026-09-13 evening ET —
    the ticker date Kalshi uses (KXNFLGAME-26SEP13DALNYG, prod-verified)."""
    scores = {s.game_id: s for s in _load_fixture_scores()}
    row = nfl_game_row_from_score(scores["nfl1234abcd1234abcd1234abcd1234ab"])
    assert row is not None
    assert row.game_date == date(2026, 9, 13)
    assert row.home_team_abbr == "NYG"
    assert row.away_team_abbr == "DAL"


def test_game_row_unknown_team_returns_none() -> None:
    score = OddsApiScore(
        game_id="x",
        sport_key="americanfootball_nfl",
        commence_time=datetime(2026, 9, 13, 17, 0, tzinfo=UTC),
        completed=False,
        home_team="London Monarchs",
        away_team="Dallas Cowboys",
        home_score=None,
        away_score=None,
        last_update=None,
    )
    assert nfl_game_row_from_score(score) is None


def test_team_name_map_is_complete() -> None:
    assert len(NFL_TEAM_NAME_TO_ABBR) == 32


def test_season_start_year_spans_the_calendar_flip() -> None:
    assert nfl_season_start_year(date(2026, 8, 6)) == 2026  # preseason
    assert nfl_season_start_year(date(2026, 12, 25)) == 2026
    assert nfl_season_start_year(date(2027, 1, 10)) == 2026  # playoffs
    assert nfl_season_start_year(date(2027, 2, 14)) == 2026  # Super Bowl


# --------------------------- upsert finality freeze ---------------------------


def _row(
    *,
    game_id: str = "g1",
    completed: bool = False,
    home_score: int | None = None,
    away_score: int | None = None,
    home_won: bool | None = None,
    commence_time: datetime | None = None,
    home_abbr: str = "NYG",
    away_abbr: str = "DAL",
) -> NflGameRow:
    return NflGameRow(
        game_id=game_id,
        season=2026,
        game_date=date(2026, 9, 13),
        commence_time=commence_time or datetime(2026, 9, 14, 0, 20),
        home_team="New York Giants",
        home_team_abbr=home_abbr,
        away_team="Dallas Cowboys",
        away_team_abbr=away_abbr,
        home_score=home_score,
        away_score=away_score,
        completed=completed,
        home_won=home_won,
    )


def test_upsert_freezes_completed_rows(tmp_path: Path) -> None:
    """Once completed, nothing but fetched_at may move — a degraded or
    malicious refetch must not rewrite the result OR the identity keys
    settlement looks up by."""
    db = tmp_path / "nfl.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        upsert_nfl_games(con, [_row(completed=True, home_score=24, away_score=17, home_won=True)])
        # Adversarial refetch: different scores, flipped outcome, re-keyed teams.
        upsert_nfl_games(
            con,
            [
                _row(
                    completed=True,
                    home_score=3,
                    away_score=40,
                    home_won=False,
                    home_abbr="PHI",
                    away_abbr="WAS",
                    commence_time=datetime(2026, 9, 15, 0, 0),
                )
            ],
        )
        rows = fetch_nfl_games(con)
        assert len(rows) == 1
        r = rows[0]
        assert r["home_score"] == 24
        assert r["home_won"] is True
        assert r["home_team_abbr"] == "NYG"
        assert r["commence_time"] == datetime(2026, 9, 14, 0, 20)
    finally:
        con.close()


def test_upsert_null_never_regresses_pre_final_truth(tmp_path: Path) -> None:
    """While not completed, incoming NULLs keep stored values (degraded
    payload clobbers nothing) but non-NULLs update (reschedules flow)."""
    db = tmp_path / "nfl.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        upsert_nfl_games(con, [_row(commence_time=datetime(2026, 9, 14, 0, 20))])
        # Flexed kickoff: new commence_time lands while not final.
        upsert_nfl_games(con, [_row(commence_time=datetime(2026, 9, 14, 1, 20))])
        rows = fetch_nfl_games(con)
        assert rows[0]["commence_time"] == datetime(2026, 9, 14, 1, 20)
        assert rows[0]["completed"] is False
        # Completion then arrives and freezes.
        upsert_nfl_games(con, [_row(completed=True, home_score=20, away_score=20, home_won=None)])
        rows = fetch_nfl_games(con)
        assert rows[0]["completed"] is True
        assert rows[0]["home_won"] is None  # tie stays NULL forever
        assert rows[0]["home_score"] == 20
    finally:
        con.close()


def test_upsert_completed_flag_never_unsets(tmp_path: Path) -> None:
    db = tmp_path / "nfl.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        upsert_nfl_games(con, [_row(completed=True, home_score=24, away_score=17, home_won=True)])
        upsert_nfl_games(con, [_row(completed=False)])  # stale refetch
        rows = fetch_nfl_games(con)
        assert rows[0]["completed"] is True
        assert rows[0]["home_score"] == 24
    finally:
        con.close()


# --------------------------- flow ---------------------------


def test_persist_writes_fixture_rows(tmp_path: Path) -> None:
    db = tmp_path / "nfl.duckdb"
    bootstrap(db)
    n = _persist(
        scores=_load_fixture_scores(),
        quota=QuotaUsage(remaining=498, used=2, last_cost=2),
        db_path=db,
    )
    assert n == 4  # all fixture teams are mappable
    con = duckdb.connect(str(db), read_only=True)
    try:
        rows = fetch_nfl_games(con)
        assert len(rows) == 4
        completed = [r for r in rows if r["completed"]]
        # The degraded completed-without-scores row was downgraded at parse.
        assert len(completed) == 2
    finally:
        con.close()


def test_main_no_op_when_api_key_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "nfl.duckdb"
    bootstrap(db)
    monkeypatch.setenv("ODDS_API_KEY", "")
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db}")
    get_settings.cache_clear()

    rc = run_ingest_nfl_schedule(db_path=db)
    assert rc == 0
    assert "ODDS_API_KEY not set" in capsys.readouterr().out


def test_fetch_and_upsert_end_to_end(tmp_path: Path) -> None:
    """MockTransport round trip: the /scores URL carries daysFrom and the
    rows land through the guarded upsert."""
    db = tmp_path / "nfl.duckdb"
    bootstrap(db)
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(
            200,
            content=FIXTURE.read_text(encoding="utf-8"),
            headers={"x-requests-remaining": "498", "x-requests-used": "2"},
        )

    def make_test_client(**_kw: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with patch("kq.clients.the_odds_api.default_client", new=make_test_client):
        n = asyncio.run(fetch_and_upsert(api_key="dummy-key", db_path=db))

    assert n == 4
    assert seen_urls and "americanfootball_nfl/scores" in seen_urls[0]
    assert "daysFrom=3" in seen_urls[0]


def test_fetch_scores_rejects_out_of_band_days_from() -> None:
    async def _go() -> None:
        async with TheOddsApiClient(api_key="k") as client:
            with pytest.raises(ValueError, match="days_from"):
                await client.fetch_scores("americanfootball_nfl", days_from=9)

    asyncio.run(_go())
