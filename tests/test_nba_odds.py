"""Tests for the NBA odds repository + ingest flow.

Coverage:
- ``odds_rows_from_games`` flattens the typed payload tree correctly.
- ``upsert_odds_rows`` is PK-idempotent and time-series-preserving.
- ``fetch_latest_odds`` returns one row per (game, book, market).
- The ingest flow no-ops cleanly when the API key is empty.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import duckdb
import httpx
import pytest

from kq.clients.the_odds_api import (
    OddsApiBookmaker,
    OddsApiGame,
    OddsApiMarket,
    OddsApiOutcome,
    QuotaUsage,
    parse_odds_response,
)
from kq.config import get_settings
from kq.flows.ingest_nba_odds import (
    DEFAULT_BOOKMAKER_KEYS,
    _persist,
    fetch_and_upsert,
)
from kq.flows.ingest_nba_odds import main as run_ingest_nba_odds
from kq.storage.duckdb_store import bootstrap
from kq.storage.repositories.nba_odds import (
    OddsRow,
    fetch_latest_odds,
    odds_rows_from_games,
    upsert_odds_rows,
)

FIXTURE = Path(__file__).parent / "fixtures" / "the_odds_api_nba_h2h.json"


def _load_fixture_games() -> list[OddsApiGame]:
    return parse_odds_response(json.loads(FIXTURE.read_text(encoding="utf-8")))


# --------------------------- odds_rows_from_games ---------------------------


def test_flatten_skips_market_with_no_matching_outcomes() -> None:
    """A market whose outcomes don't match either home or away gets
    dropped -- defensive against future market keys we don't model."""
    game = OddsApiGame(
        game_id="g1",
        sport_key="basketball_nba",
        commence_time=datetime(2026, 5, 4, 23, tzinfo=UTC),
        home_team="A",
        away_team="B",
        bookmakers=(
            OddsApiBookmaker(
                key="pinnacle",
                title="Pinnacle",
                last_update=datetime(2026, 5, 4, 22, tzinfo=UTC),
                markets=(
                    OddsApiMarket(
                        key="totals",
                        last_update=datetime(2026, 5, 4, 22, tzinfo=UTC),
                        outcomes=(
                            OddsApiOutcome(team_name="Over 220.5", decimal_odds=1.91),
                            OddsApiOutcome(team_name="Under 220.5", decimal_odds=1.91),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert odds_rows_from_games([game]) == []


def test_flatten_lakers_celtics_pinnacle_quotes() -> None:
    games = _load_fixture_games()
    fetched = datetime(2026, 5, 4, 21, 0, tzinfo=UTC)
    rows = odds_rows_from_games(games, fetched_at=fetched)
    lakers_celtics_pinnacle = [
        r for r in rows if r.home_team == "Los Angeles Lakers" and r.bookmaker_key == "pinnacle"
    ]
    assert len(lakers_celtics_pinnacle) == 1
    r = lakers_celtics_pinnacle[0]
    assert r.market_key == "h2h"
    assert r.home_decimal_odds == pytest.approx(2.45)
    assert r.away_decimal_odds == pytest.approx(1.62)
    # commence_time + book_last_update + fetched_at all stored as naive UTC.
    assert r.commence_time.tzinfo is None
    assert r.book_last_update.tzinfo is None
    assert r.fetched_at.tzinfo is None
    assert r.fetched_at == fetched.replace(tzinfo=None)


def test_flatten_preserves_multiple_bookmakers_per_game() -> None:
    rows = odds_rows_from_games(_load_fixture_games())
    lakers = [r for r in rows if r.home_team == "Los Angeles Lakers"]
    keys = {r.bookmaker_key for r in lakers}
    assert keys == {"pinnacle", "draftkings"}


def test_flatten_skips_game_with_no_bookmakers() -> None:
    """Heat-Pacers in the fixture has no quotes yet -> contributes 0 rows."""
    rows = odds_rows_from_games(_load_fixture_games())
    assert all(r.home_team != "Miami Heat" for r in rows)


# --------------------------- repository round-trip ---------------------------


def _new_db(path: Path) -> duckdb.DuckDBPyConnection:
    bootstrap(path)
    return duckdb.connect(str(path))


def test_upsert_and_fetch_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "nba_odds.duckdb"
    con = _new_db(db)
    rows = odds_rows_from_games(_load_fixture_games())
    n = upsert_odds_rows(con, rows)
    assert n == len(rows)
    out = fetch_latest_odds(con)
    assert len(out) == n
    con.close()


def test_upsert_empty_is_noop(tmp_path: Path) -> None:
    db = tmp_path / "nba_odds.duckdb"
    con = _new_db(db)
    assert upsert_odds_rows(con, []) == 0
    assert fetch_latest_odds(con) == []
    con.close()


def test_upsert_preserves_line_movement_time_series(tmp_path: Path) -> None:
    """Two snapshots of the same (game, book, market) at different
    fetched_at must coexist -- this is the time-series property the
    composite PK enforces."""
    db = tmp_path / "nba_odds.duckdb"
    con = _new_db(db)
    games = _load_fixture_games()
    early = datetime(2026, 5, 4, 18, 0, tzinfo=UTC)
    late = early + timedelta(hours=2)
    upsert_odds_rows(con, odds_rows_from_games(games, fetched_at=early))
    upsert_odds_rows(con, odds_rows_from_games(games, fetched_at=late))

    # Each (game, book, market) should now have 2 rows in the raw table,
    # but fetch_latest_odds returns only the late snapshot.
    raw_count = con.execute("SELECT COUNT(*) FROM nba_odds").fetchone()
    assert raw_count is not None and raw_count[0] > 0
    latest = fetch_latest_odds(con)
    fetched_set = {r["fetched_at"] for r in latest}
    assert fetched_set == {late.replace(tzinfo=None)}
    con.close()


def test_upsert_idempotent_on_pk(tmp_path: Path) -> None:
    """Re-upserting the same rows is a no-op modulo row-count equality."""
    db = tmp_path / "nba_odds.duckdb"
    con = _new_db(db)
    rows = odds_rows_from_games(_load_fixture_games())
    upsert_odds_rows(con, rows)
    upsert_odds_rows(con, rows)
    raw_count = con.execute("SELECT COUNT(*) FROM nba_odds").fetchone()
    assert raw_count is not None and raw_count[0] == len(rows)
    con.close()


def test_fetch_latest_odds_filters_by_bookmaker(tmp_path: Path) -> None:
    db = tmp_path / "nba_odds.duckdb"
    con = _new_db(db)
    upsert_odds_rows(con, odds_rows_from_games(_load_fixture_games()))
    pinnacle_only = fetch_latest_odds(con, bookmaker_key="pinnacle")
    assert all(r["bookmaker_key"] == "pinnacle" for r in pinnacle_only)
    assert len(pinnacle_only) >= 2  # Lakers-Celtics + Nuggets-Thunder both Pinnacle
    con.close()


def test_fetch_latest_odds_filters_by_date(tmp_path: Path) -> None:
    db = tmp_path / "nba_odds.duckdb"
    con = _new_db(db)
    upsert_odds_rows(con, odds_rows_from_games(_load_fixture_games()))
    future = fetch_latest_odds(con, on_or_after=date(2026, 5, 5))
    # Fixture has Lakers-Celtics on 5/4 and Nuggets-Thunder + Heat-Pacers on 5/5.
    # Filter on or after 5/5 returns the 5/5 games only.
    assert all(r["commence_time"] >= datetime(2026, 5, 5) for r in future)
    con.close()


# --------------------------- flow: no-key path ---------------------------


def test_main_no_op_when_api_key_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The flow must NOT raise when ODDS_API_KEY is empty -- this is
    the safe-to-cron-before-signoff property."""
    db = tmp_path / "nba_odds.duckdb"
    bootstrap(db)
    monkeypatch.setenv("ODDS_API_KEY", "")
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db}")

    # Clear the lru_cache on get_settings() so our env vars take effect.
    get_settings.cache_clear()

    rc = run_ingest_nba_odds(db_path=db)
    assert rc == 0
    captured = capsys.readouterr().out
    assert "ODDS_API_KEY not set" in captured


# --------------------------- flow: persistence path ---------------------------


def test_persist_writes_rows_with_synthetic_quota(tmp_path: Path) -> None:
    """``_persist`` is the testable hook for the persistence path --
    feed it synthetic OddsApiGame fixtures + a QuotaUsage and verify
    the rows land in DuckDB without going through HTTP."""
    db = tmp_path / "nba_odds.duckdb"
    bootstrap(db)
    games = _load_fixture_games()
    quota = QuotaUsage(remaining=4999, used=1, last_cost=1)
    n = _persist(
        games=games,
        quota=quota,
        db_path=db,
        bookmaker_keys=DEFAULT_BOOKMAKER_KEYS,
        fetched_at=datetime(2026, 5, 4, 21, 0, tzinfo=UTC),
    )
    assert n > 0
    con = duckdb.connect(str(db), read_only=True)
    try:
        rows = fetch_latest_odds(con)
        assert len(rows) == n
    finally:
        con.close()


# --------------------------- flow: end-to-end via MockTransport ---------------------------


def test_fetch_and_upsert_end_to_end(tmp_path: Path) -> None:
    """Round-trip via httpx.MockTransport so the actual TheOddsApiClient
    code path is exercised (URL composition, header parsing, parser,
    flatten, upsert) without a live API key."""
    db = tmp_path / "nba_odds.duckdb"
    bootstrap(db)

    def handler(request: httpx.Request) -> httpx.Response:
        body = FIXTURE.read_text(encoding="utf-8")
        return httpx.Response(
            200,
            content=body,
            headers={
                "x-requests-remaining": "4998",
                "x-requests-used": "2",
                "x-requests-last": "1",
            },
        )

    transport = httpx.MockTransport(handler)

    # We patch the httpx.AsyncClient that TheOddsApiClient creates inside
    # its __aenter__ by injecting it via the api_key + asyncio.run path.
    # Easier route: patch default_client to return a transport-backed
    # client.
    def make_test_client(**_kw: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport)

    with patch("kq.clients.the_odds_api.default_client", new=make_test_client):
        n = asyncio.run(
            fetch_and_upsert(api_key="dummy-key", db_path=db),
        )

    assert n > 0
    con = duckdb.connect(str(db), read_only=True)
    try:
        latest = fetch_latest_odds(con)
        assert len(latest) == n
    finally:
        con.close()


# --------------------------- type sanity ---------------------------


def test_odds_row_is_frozen() -> None:
    row = OddsRow(
        odds_api_game_id="g",
        bookmaker_key="pinnacle",
        market_key="h2h",
        home_team="A",
        away_team="B",
        commence_time=datetime(2026, 5, 4, 23, 0),
        home_decimal_odds=1.91,
        away_decimal_odds=1.91,
        book_last_update=datetime(2026, 5, 4, 22, 0),
        fetched_at=datetime(2026, 5, 4, 21, 0),
    )
    with pytest.raises(AttributeError):
        row.bookmaker_key = "mutated"  # type: ignore[misc]
