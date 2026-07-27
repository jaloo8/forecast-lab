"""End-to-end tests for the social ingest flow (Phase S1).

Fixture-driven: httpx.MockTransport routes each allowlisted URL to a
recorded 2026-07-27 payload (see test_social_clients.py for provenance),
plus one permanently-429 source and one source serving an HTML error page
— both must be skipped loudly while the rest of the tick lands.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from kq.__main__ import app
from kq.clients import _http
from kq.clients.nfl_players import PlayerGameRow
from kq.clients.social import SocialClient
from kq.flows.ingest_social import _rotated, ingest_once
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.nfl_players import upsert_player_games
from kq.storage.repositories.social import fetch_social_posts

FIXTURES = Path(__file__).parent / "fixtures" / "social"

SOURCES_TOML = """\
subreddits = ["nfl"]

[[feeds]]
key = "espn_nfl"
url = "https://www.espn.com/espn/rss/nfl/news"
official = false

[[feeds]]
key = "chiefs_official"
url = "https://www.chiefs.com/rss/news"
official = true

[[feeds]]
key = "dead_feed"
url = "https://dead.example/feed"
official = false

[[feeds]]
key = "garbage_feed"
url = "https://garbage.example/feed"
official = false
"""


def _alec_pierce_row() -> PlayerGameRow:
    return PlayerGameRow(
        player_id="00-0037247",
        player_name="Alec Pierce",
        season=2025,
        week=1,
        season_type="REG",
        team="IND",
        opponent="HOU",
        position="WR",
        snaps=40.0,
        snap_pct=0.62,
        targets=6,
        receptions=3,
        carries=0,
        passing_yards=None,
        passing_tds=None,
        rushing_yards=None,
        rushing_tds=None,
        receiving_yards=51.0,
        receiving_tds=0,
        fumbles_lost=0.0,
        interceptions=None,
        red_zone_touches=None,
        fantasy_points_std=5.1,
        fantasy_points_ppr=8.1,
    )


def _handler(request: httpx.Request) -> httpx.Response:
    host = request.url.host
    if host == "www.reddit.com":
        assert request.url.path == "/r/nfl/new.rss"
        body = (FIXTURES / "reddit_nfl_new_atom.xml").read_text(encoding="utf-8")
        return httpx.Response(200, text=body)
    if host == "www.espn.com":
        body = (FIXTURES / "espn_nfl_rss.xml").read_text(encoding="utf-8")
        return httpx.Response(200, text=body)
    if host == "www.chiefs.com":
        body = (FIXTURES / "chiefs_rss.xml").read_text(encoding="utf-8")
        return httpx.Response(200, text=body)
    if host == "dead.example":
        return httpx.Response(429, text="rate limited")
    if host == "garbage.example":
        return httpx.Response(200, text="<html><body>maintenance page</body></html>")
    raise AssertionError(f"unexpected URL fetched: {request.url}")


async def test_ingest_end_to_end_with_failures_and_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _no_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr(_http.asyncio, "sleep", _no_sleep)  # 429 backoff, not politeness

    db_path = tmp_path / "social.duckdb"
    sources_path = tmp_path / "social_sources.toml"
    sources_path.write_text(SOURCES_TOML, encoding="utf-8")

    # Seed the F1a lane so the matcher knows one real player.
    bootstrap(db_path)
    con = connect(db_path)
    try:
        upsert_player_games(con, [_alec_pierce_row()])
    finally:
        con.close()

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as http:
        n1 = await ingest_once(
            db_path=db_path,
            sources_path=sources_path,
            social_client=SocialClient(http, request_spacing_s=0),
        )
        # 3 reddit + 3 espn + 2 chiefs; dead_feed (429) + garbage_feed (HTML) skipped
        assert n1 == 8

        con = connect(db_path)
        try:
            posts = fetch_social_posts(con)
            assert len(posts) == 8
            by_id = {str(p["source_post_id"]): p for p in posts}

            pierce = by_id["t3_1v8dm3p"]
            assert pierce["matched_entity_type"] == "nfl_player"
            assert pierce["matched_entity_id"] == "00-0037247"

            dolphins = by_id["t3_1v8e76v"]
            assert dolphins["matched_entity_type"] == "nfl_team"
            assert dolphins["matched_entity_id"] == "MIA"

            chiefs_rows = [p for p in posts if p["subreddit_or_feed"] == "chiefs_official"]
            assert len(chiefs_rows) == 2
            assert all(bool(p["is_official"]) for p in chiefs_rows)

            assert all(p["as_of"] is not None for p in posts)
            first_as_of = {str(p["source_post_id"]): p["as_of"] for p in posts}
        finally:
            con.close()

        # Re-run: idempotent — nothing duplicates, first-sighting as_of frozen.
        n2 = await ingest_once(
            db_path=db_path,
            sources_path=sources_path,
            social_client=SocialClient(http, request_spacing_s=0),
        )
        assert n2 == 8

    con = connect(db_path)
    try:
        posts_after = fetch_social_posts(con)
        assert len(posts_after) == 8
        for p in posts_after:
            assert p["as_of"] == first_as_of[str(p["source_post_id"])]
    finally:
        con.close()


async def test_ingest_survives_all_sources_failing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fully-dark tick (every source down) returns 0 and leaves the DB
    consistent — the cron retries next tick, no crash."""

    async def _no_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr(_http.asyncio, "sleep", _no_sleep)

    def all_down(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    db_path = tmp_path / "social.duckdb"
    sources_path = tmp_path / "social_sources.toml"
    sources_path.write_text(SOURCES_TOML, encoding="utf-8")

    async with httpx.AsyncClient(transport=httpx.MockTransport(all_down)) as http:
        n = await ingest_once(
            db_path=db_path,
            sources_path=sources_path,
            social_client=SocialClient(http, request_spacing_s=0),
        )
    assert n == 0
    con = connect(db_path)
    try:
        assert fetch_social_posts(con) == []
    finally:
        con.close()


def test_subreddit_rotation_covers_all_positions() -> None:
    """The rotation must (a) preserve the full set, (b) start at a
    different subreddit as the tick minute advances — Reddit's ~1-fetch/min
    budget otherwise starves everything after the first config entry."""
    subs = ("nfl", "nba", "fantasyfootball", "fantasybball")
    # the recommended :03/:18/:33/:48 grid cycles all four start positions
    starts = {_rotated(subs, h * 60 + m)[0] for h in (0, 1, 2, 3) for m in (3, 18, 33, 48)}
    assert starts == set(subs)
    for minute in (0, 3, 18, 33, 48, 1439):
        rotated = _rotated(subs, minute)
        assert sorted(rotated) == sorted(subs)
    assert _rotated((), 7) == ()


def test_cli_ingest_social_help() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["ingest-social", "--help"])
    assert result.exit_code == 0
    assert "Reddit" in result.output
