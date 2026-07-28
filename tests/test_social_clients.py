"""Tests for the social event-lane clients (Phase S1).

Fixture provenance (the reality-contact discipline, CLAUDE.md): every
happy-path fixture under ``tests/fixtures/social/`` is a REAL payload slice
captured live 2026-07-27 from the WSL host —

* ``reddit_nfl_new_atom.xml`` — https://www.reddit.com/r/nfl/new.rss (the
  public Atom listing; the ``.json`` listings are edge-blocked from this
  host, see ``kq/clients/social.py``), first 3 entries.
* ``espn_nfl_rss.xml`` — https://www.espn.com/espn/rss/nfl/news, first 3
  items (named-zone ``EST`` pubDates, ``US-EN-*`` guids, CDATA everywhere).
* ``cbs_nfl_rss.xml`` — https://www.cbssports.com/rss/headlines/nfl/,
  first 2 items (``+0000`` pubDates, UUID guids, enclosure noise).
* ``pft_rss.xml`` — https://profootballtalk.nbcsports.com/feed/, first 2
  items (``-0400`` pubDates, permalink-URL guids, huge content:encoded).
* ``chiefs_rss.xml`` — https://www.chiefs.com/rss/news (official team
  site), first 2 items (``GMT`` pubDates; the second item is non-English
  and has NO description — a real missing-field case).

Synthetic XML appears only in degraded-shape cases (missing id/title/date)
that the recorded payloads don't exhibit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

import kq.clients.social as social_mod
from kq.clients import _http
from kq.clients._http import HttpError
from kq.clients.social import (
    DEFAULT_SOURCES_PATH,
    SOCIAL_USER_AGENT,
    FeedSource,
    SocialClient,
    load_social_sources,
    posts_from_reddit_atom,
    posts_from_rss,
)

FIXTURES = Path(__file__).parent / "fixtures" / "social"
STAMP = datetime(2026, 7, 27, 22, 0, 0, tzinfo=UTC)


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Reddit Atom


def test_reddit_atom_parses_real_fixture() -> None:
    posts = posts_from_reddit_atom(
        _read("reddit_nfl_new_atom.xml"), "nfl", fallback_created_at=STAMP
    )
    assert len(posts) == 3
    first = posts[0]
    assert first.source == "reddit"
    assert first.source_post_id == "t3_1v8e76v"
    assert first.subreddit_or_feed == "r/nfl"
    assert first.author == "/u/expellyamos"
    assert first.title.startswith("The Miami Dolphins announced today")
    assert first.url == (
        "https://www.reddit.com/r/nfl/comments/1v8e76v/"
        "the_miami_dolphins_announced_today_that_they_have/"
    )
    assert first.created_at == datetime(2026, 7, 27, 21, 41, 18, tzinfo=UTC)
    assert first.is_official is False
    assert first.text is not None and "submitted by" in first.text
    # the injury-news entry the entity matcher cares about
    assert posts[1].source_post_id == "t3_1v8dm3p"
    assert "Alec Pierce" in posts[1].title


def test_reddit_atom_skips_entries_without_id_or_title() -> None:
    xml = (
        '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">'
        "<entry><title>no id here</title></entry>"
        "<entry><id>t3_ok</id><title>fine</title>"
        "<published>2026-07-27T00:00:00+00:00</published></entry>"
        "<entry><id>t3_untitled</id></entry>"
        "</feed>"
    )
    posts = posts_from_reddit_atom(xml, "nfl", fallback_created_at=STAMP)
    assert [p.source_post_id for p in posts] == ["t3_ok"]


def test_reddit_atom_missing_published_falls_back_to_fetch_stamp() -> None:
    xml = (
        '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">'
        "<entry><id>t3_nodate</id><title>undated</title></entry></feed>"
    )
    posts = posts_from_reddit_atom(xml, "nfl", fallback_created_at=STAMP)
    assert posts[0].created_at == STAMP


# ---------------------------------------------------------------------------
# RSS 2.0 — one test per recorded shape variant


def test_espn_rss_parses_named_est_zone_and_scoped_guids() -> None:
    feed = FeedSource(key="espn_nfl", url="https://www.espn.com/espn/rss/nfl/news", official=False)
    posts = posts_from_rss(_read("espn_nfl_rss.xml"), feed, fallback_created_at=STAMP)
    assert len(posts) == 3
    first = posts[0]
    assert first.source == "rss"
    assert first.source_post_id == "espn_nfl/US-EN-49447669"
    assert first.subreddit_or_feed == "espn_nfl"
    assert first.author == "Stephen Holder and Brooke Pryor"
    # RFC 822 obsolete named zone: 13:34:56 EST == 18:34:56 UTC
    assert first.created_at == datetime(2026, 7, 27, 18, 34, 56, tzinfo=UTC)
    assert first.text is not None and first.text.startswith("With training camps opening")
    assert first.url is not None and first.url.startswith("https://www.espn.com/nfl/story/")


def test_cbs_rss_parses_numeric_offset_and_uuid_guids() -> None:
    feed = FeedSource(
        key="cbs_nfl", url="https://www.cbssports.com/rss/headlines/nfl/", official=False
    )
    posts = posts_from_rss(_read("cbs_nfl_rss.xml"), feed, fallback_created_at=STAMP)
    assert len(posts) == 2
    first = posts[0]
    assert first.source_post_id == "cbs_nfl/324b102d-2a74-4747-b6bf-639356a7fa9d"
    assert first.author == "Zachary Pereles"
    assert first.created_at == datetime(2026, 7, 27, 20, 32, 29, tzinfo=UTC)


def test_pft_rss_parses_negative_offset_and_permalink_guids() -> None:
    feed = FeedSource(key="pft", url="https://profootballtalk.nbcsports.com/feed/", official=False)
    posts = posts_from_rss(_read("pft_rss.xml"), feed, fallback_created_at=STAMP)
    assert len(posts) == 2
    first = posts[0]
    assert first.title == "Giants worked out LB Kenneth Murray, 17 others, on Monday"
    assert first.source_post_id.startswith("pft/https://www.nbcsports.com/")
    # -0400 offset: 17:27:29 EDT == 21:27:29 UTC
    assert first.created_at == datetime(2026, 7, 27, 21, 27, 29, tzinfo=UTC)
    assert first.author == "Charean Williams"


def test_chiefs_rss_official_flag_gmt_dates_and_missing_description() -> None:
    feed = FeedSource(key="chiefs_official", url="https://www.chiefs.com/rss/news", official=True)
    posts = posts_from_rss(_read("chiefs_rss.xml"), feed, fallback_created_at=STAMP)
    assert len(posts) == 2
    first = posts[0]
    assert first.is_official is True
    assert first.author is None  # feed carries no dc:creator
    assert first.created_at == datetime(2026, 7, 25, 12, 32, 23, tzinfo=UTC)
    # the real second item is non-English and omits <description> entirely
    assert posts[1].text is None
    assert posts[1].title


def test_rss_items_without_identity_or_title_are_skipped() -> None:
    feed = FeedSource(key="x", url="https://x.example/feed", official=False)
    xml = (
        '<?xml version="1.0"?><rss version="2.0"><channel>'
        "<item><title>no guid no link</title></item>"
        "<item><link>https://x.example/a</link><title>link-only ok</title>"
        "<pubDate>Mon, 27 Jul 2026 00:00:00 +0000</pubDate></item>"
        "<item><guid>orphan-guid</guid></item>"
        "</channel></rss>"
    )
    posts = posts_from_rss(xml, feed, fallback_created_at=STAMP)
    assert [p.source_post_id for p in posts] == ["x/https://x.example/a"]


def test_rss_unparseable_pubdate_falls_back_to_fetch_stamp() -> None:
    feed = FeedSource(key="x", url="https://x.example/feed", official=False)
    xml = (
        '<?xml version="1.0"?><rss version="2.0"><channel>'
        "<item><guid>g1</guid><title>bad date</title>"
        "<pubDate>not a date</pubDate></item>"
        "</channel></rss>"
    )
    posts = posts_from_rss(xml, feed, fallback_created_at=STAMP)
    assert posts[0].created_at == STAMP


def test_malformed_xml_raises_value_error() -> None:
    feed = FeedSource(key="x", url="https://x.example/feed", official=False)
    with pytest.raises(ValueError, match="unparseable feed XML"):
        posts_from_rss("<html>an error page, not a feed", feed, fallback_created_at=STAMP)


def test_unrecognized_root_raises_value_error() -> None:
    feed = FeedSource(key="x", url="https://x.example/feed", official=False)
    with pytest.raises(ValueError, match="unrecognized feed root"):
        posts_from_rss("<opml></opml>", feed, fallback_created_at=STAMP)


# ---------------------------------------------------------------------------
# Allowlist config


def test_checked_in_sources_config_loads() -> None:
    """The real config/social_sources.toml must always parse — a broken
    allowlist would kill every cron tick."""
    sources = load_social_sources(DEFAULT_SOURCES_PATH)
    assert sources.subreddits == ("nfl", "nba", "fantasyfootball", "fantasybball")
    assert len(sources.feeds) >= 5
    assert all(f.url.startswith("https://") for f in sources.feeds)
    keys = [f.key for f in sources.feeds]
    assert len(keys) == len(set(keys))
    by_key = {f.key: f for f in sources.feeds}
    assert by_key["chiefs_official"].official is True
    assert by_key["espn_nfl"].official is False


def test_sources_config_validation_errors(tmp_path: Path) -> None:
    cases = [
        ("missing.toml", None, "missing"),
        ("notoml.toml", "subreddits = [unclosed", "unparseable"),
        ("badsub.toml", 'subreddits = ["r/nfl"]', "invalid subreddit"),
        ("dupsub.toml", 'subreddits = ["nfl", "nfl"]', "duplicate subreddit"),
        (
            "badkey.toml",
            'subreddits = []\n[[feeds]]\nkey = "Bad-Key"\nurl = "https://x.example/f"',
            "invalid feed key",
        ),
        (
            "dupkey.toml",
            'subreddits = []\n[[feeds]]\nkey = "a_feed"\nurl = "https://x.example/f"\n'
            '[[feeds]]\nkey = "a_feed"\nurl = "https://y.example/f"',
            "duplicate feed key",
        ),
        (
            "http.toml",
            'subreddits = []\n[[feeds]]\nkey = "a_feed"\nurl = "http://x.example/f"',
            "https",
        ),
        ("empty.toml", "subreddits = []\nfeeds = []", "no sources"),
    ]
    for name, content, match in cases:
        p = tmp_path / name
        if content is not None:
            p.write_text(content, encoding="utf-8")
        with pytest.raises(ValueError, match=match):
            load_social_sources(p)


# ---------------------------------------------------------------------------
# Async client behavior (MockTransport — hermetic)


async def test_client_sends_descriptive_user_agent_and_parses() -> None:
    seen_uas: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_uas.append(request.headers["User-Agent"])
        return httpx.Response(200, text=_read("reddit_nfl_new_atom.xml"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = SocialClient(http, request_spacing_s=0)
        async with client:
            posts = await client.fetch_subreddit("nfl", fallback_created_at=STAMP)
    assert len(posts) == 3
    assert seen_uas == [SOCIAL_USER_AGENT]


async def test_client_429_backs_off_then_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """429 is retried with backoff by the shared helper, then surfaces as
    HttpError — the flow's per-source skip (cron retries next tick)."""

    async def _no_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr(_http.asyncio, "sleep", _no_sleep)
    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(429, text="rate limited")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = SocialClient(http, request_spacing_s=0)
        async with client:
            with pytest.raises(HttpError) as excinfo:
                await client.fetch_feed(
                    FeedSource(key="x", url="https://x.example/feed", official=False)
                )
    assert excinfo.value.status == 429
    assert len(calls) == 3  # initial + 2 retries, then skip


async def test_reddit_429_fails_fast_without_retries() -> None:
    """Reddit's listing budget refills ~1/min (measured live 2026-07-27) —
    in-call retries can never succeed, so the Reddit fetch must NOT hammer:
    exactly one request, then skip until the next tick."""
    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(429, text="rate limited")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = SocialClient(http, request_spacing_s=0)
        async with client:
            with pytest.raises(HttpError):
                await client.fetch_subreddit("nfl", fallback_created_at=STAMP)
    assert len(calls) == 1


async def test_client_spaces_consecutive_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Politeness: the 2nd+ request sleeps the configured spacing; the
    first does not."""
    sleeps: list[float] = []

    async def _record_sleep(s: float) -> None:
        sleeps.append(s)

    monkeypatch.setattr(social_mod.asyncio, "sleep", _record_sleep)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_read("reddit_nfl_new_atom.xml"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = SocialClient(http, request_spacing_s=2.0)
        async with client:
            await client.fetch_subreddit("nfl", fallback_created_at=STAMP)
            await client.fetch_subreddit("nba", fallback_created_at=STAMP)
    assert sleeps == [2.0]
