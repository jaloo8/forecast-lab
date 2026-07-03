"""Tests for the NFL odds lane: shared flatten/upsert against ``nfl_odds``,
the ingest flow's persistence + no-key paths, and the MockTransport
end-to-end round trip (URL composition for ``americanfootball_nfl``).

Mirrors ``test_nba_odds.py`` — the shared ``odds_common`` core is the same
code, so these tests pin the NFL table wiring, not re-prove the math.
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

from kq.clients.the_odds_api import QuotaUsage, parse_odds_response
from kq.config import get_settings
from kq.flows.ingest_nfl_odds import (
    DEFAULT_BOOKMAKER_KEYS,
    _persist,
    fetch_and_upsert,
)
from kq.flows.ingest_nfl_odds import (
    main as run_ingest_nfl_odds,
)
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.nfl_odds import (
    fetch_latest_nfl_odds,
    odds_rows_from_games,
    upsert_nfl_odds_rows,
)

FIXTURE = Path(__file__).parent / "fixtures" / "the_odds_api_nfl_h2h.json"


def _load_fixture_games() -> list[object]:
    return parse_odds_response(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _new_db(path: Path) -> duckdb.DuckDBPyConnection:
    bootstrap(path)
    return connect(path)


# --------------------------- repository ---------------------------


def test_fixture_flattens_and_upserts_into_nfl_odds(tmp_path: Path) -> None:
    con = _new_db(tmp_path / "nfl.duckdb")
    try:
        games = _load_fixture_games()
        rows = odds_rows_from_games(games, fetched_at=datetime(2026, 9, 13, 15, 30, tzinfo=UTC))
        assert rows, "fixture should flatten to at least one row"
        n = upsert_nfl_odds_rows(con, rows)
        assert n == len(rows)
        # Pinnacle quoted both fixture games; the JAC game also has BetMGM.
        latest = fetch_latest_nfl_odds(con, bookmaker_key="pinnacle")
        assert len(latest) == 2
        by_home = {r["home_team"]: r for r in latest}
        assert by_home["New York Giants"]["away_team"] == "Dallas Cowboys"
        assert by_home["Jacksonville Jaguars"]["home_decimal_odds"] == pytest.approx(1.35)
    finally:
        con.close()


def test_reupsert_same_fetch_is_idempotent(tmp_path: Path) -> None:
    con = _new_db(tmp_path / "nfl.duckdb")
    try:
        rows = odds_rows_from_games(
            _load_fixture_games(), fetched_at=datetime(2026, 9, 13, 15, 30, tzinfo=UTC)
        )
        upsert_nfl_odds_rows(con, rows)
        upsert_nfl_odds_rows(con, rows)  # same PK -> replace in place
        count = con.execute("SELECT COUNT(*) FROM nfl_odds").fetchone()
        assert count is not None and int(count[0]) == len(rows)
    finally:
        con.close()


def test_new_fetch_preserves_line_movement_time_series(tmp_path: Path) -> None:
    con = _new_db(tmp_path / "nfl.duckdb")
    try:
        games = _load_fixture_games()
        upsert_nfl_odds_rows(
            con, odds_rows_from_games(games, fetched_at=datetime(2026, 9, 13, 15, 0, tzinfo=UTC))
        )
        upsert_nfl_odds_rows(
            con, odds_rows_from_games(games, fetched_at=datetime(2026, 9, 13, 16, 0, tzinfo=UTC))
        )
        distinct = con.execute("SELECT COUNT(DISTINCT fetched_at) FROM nfl_odds").fetchone()
        assert distinct is not None and int(distinct[0]) == 2
        # "latest" view returns one row per (game, book, market).
        latest = fetch_latest_nfl_odds(con)
        assert all(r["fetched_at"] == datetime(2026, 9, 13, 16, 0) for r in latest)
    finally:
        con.close()


def test_nfl_rows_never_land_in_nba_table(tmp_path: Path) -> None:
    """The table-parameterized core must route NFL rows to nfl_odds only."""
    con = _new_db(tmp_path / "nfl.duckdb")
    try:
        rows = odds_rows_from_games(_load_fixture_games())
        upsert_nfl_odds_rows(con, rows)
        nba_count = con.execute("SELECT COUNT(*) FROM nba_odds").fetchone()
        assert nba_count is not None and int(nba_count[0]) == 0
    finally:
        con.close()


def test_on_or_after_filter(tmp_path: Path) -> None:
    con = _new_db(tmp_path / "nfl.duckdb")
    try:
        upsert_nfl_odds_rows(con, odds_rows_from_games(_load_fixture_games()))
        # DAL@NYG kicks 2026-09-14 00:20 UTC; CLE@JAC 2026-09-13 17:00 UTC.
        future = fetch_latest_nfl_odds(con, on_or_after=date(2026, 9, 14))
        assert future
        assert all(r["commence_time"] >= datetime(2026, 9, 14) for r in future)
    finally:
        con.close()


# --------------------------- flow: no-key path ---------------------------


def test_main_no_op_when_api_key_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Cron-safe before the key exists: no raise, exit-0 semantics."""
    db = tmp_path / "nfl_odds.duckdb"
    bootstrap(db)
    monkeypatch.setenv("ODDS_API_KEY", "")
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db}")
    get_settings.cache_clear()

    rc = run_ingest_nfl_odds(db_path=db)
    assert rc == 0
    captured = capsys.readouterr().out
    assert "ODDS_API_KEY not set" in captured


# --------------------------- flow: persistence path ---------------------------


def test_persist_writes_rows_with_synthetic_quota(tmp_path: Path) -> None:
    db = tmp_path / "nfl_odds.duckdb"
    bootstrap(db)
    games = _load_fixture_games()
    quota = QuotaUsage(remaining=4999, used=1, last_cost=1)
    n = _persist(
        games=games,  # type: ignore[arg-type]
        quota=quota,
        db_path=db,
        bookmaker_keys=DEFAULT_BOOKMAKER_KEYS,
        fetched_at=datetime(2026, 9, 13, 15, 30, tzinfo=UTC),
    )
    assert n > 0
    con = duckdb.connect(str(db), read_only=True)
    try:
        rows = fetch_latest_nfl_odds(con)
        assert len(rows) == n
    finally:
        con.close()


# --------------------------- flow: end-to-end via MockTransport ---------------------------


def test_fetch_and_upsert_end_to_end(tmp_path: Path) -> None:
    """Round-trip via httpx.MockTransport: URL must target the NFL sport
    key and rows must land in ``nfl_odds``."""
    db = tmp_path / "nfl_odds.duckdb"
    bootstrap(db)
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(
            200,
            content=FIXTURE.read_text(encoding="utf-8"),
            headers={
                "x-requests-remaining": "4998",
                "x-requests-used": "2",
                "x-requests-last": "1",
            },
        )

    transport = httpx.MockTransport(handler)

    def make_test_client(**_kw: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport)

    with patch("kq.clients.the_odds_api.default_client", new=make_test_client):
        n = asyncio.run(fetch_and_upsert(api_key="dummy-key", db_path=db))

    assert n > 0
    assert seen_urls and "americanfootball_nfl" in seen_urls[0]
    con = duckdb.connect(str(db), read_only=True)
    try:
        assert len(fetch_latest_nfl_odds(con)) == n
    finally:
        con.close()
