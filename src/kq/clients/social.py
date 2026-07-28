"""Social / open-news event-lane clients — Reddit listings + RSS feeds (Phase S1).

Owner amendment 2026-07-27 (CLAUDE.md §2; design in
docs/research/FANTASY-SPORTS-DESIGN.md § "Phase S"): curated allowlists,
event triggers only — nothing fetched here ever sets a model probability.

Reality contact (probed live 2026-07-27 from the WSL host; recorded slices
in ``tests/fixtures/social/``):

* **Reddit's public JSON listings are edge-blocked from this host.** The
  ``www``/``old``/``api`` ``.json`` variants all return HTTP 403 "blocked"
  HTML for every user agent tried (descriptive, reddit-convention, browser)
  over both curl and httpx — the block keys on the network/TLS fingerprint,
  not the UA string. The public **Atom feed** of the same listing
  (``/r/{subreddit}/new.rss``) serves 200 to our descriptive UA, so the
  Reddit lane rides Atom: same allowlist, same politeness, and one URL
  template to swap if the JSON endpoints ever unblock.
* **RSS 2.0 reality varies by publisher** (every shape below is recorded,
  not assumed): guids are UUIDs (CBS, Chiefs), publisher-scoped ids (ESPN
  ``US-EN-...``), or permalink URLs (PFT, no ``isPermaLink`` attr);
  ``pubDate`` arrives as ``+0000``, ``GMT``, ``-0400``, and ESPN's *named*
  ``EST`` zone (an RFC 822 obsolete form — ``email.utils`` parses it; note
  ESPN labels July timestamps "EST", so its wall-clock times may sit an
  hour off true EDT — upstream's label, stored as parsed);
  ``dc:creator`` and ``description`` are optional (the Chiefs feed's
  non-English items omit ``description``).

Parsing is stdlib ``xml.etree`` only — feedparser would be a new dependency
(§9, not approved). RSS guid uniqueness is only promised *per feed*, so RSS
``source_post_id`` is namespaced ``{feed_key}/{guid-or-link}``; Reddit ids
are the venue's globally-unique ``t3_*`` fullnames.

Politeness: descriptive contactable UA on every request, ~2 s spacing
between consecutive requests, and 429/5xx retry-with-backoff via the shared
helper — after retries the source is skipped and the next cron tick retries.
"""

from __future__ import annotations

import asyncio
import re
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Final
from xml.etree import ElementTree

import httpx
import structlog

from kq.clients._http import default_client, request_text
from kq.config import REPO_ROOT

log = structlog.get_logger(__name__)

REDDIT_ATOM_URL_TEMPLATE: Final = "https://www.reddit.com/r/{subreddit}/new.rss"
SOCIAL_USER_AGENT: Final = (
    "forecast-lab/0.0.1 (personal research event lane; contact jloo1997@yahoo.com)"
)
REQUEST_SPACING_S: Final = 2.0
DEFAULT_SOURCES_PATH: Final = REPO_ROOT / "config" / "social_sources.toml"

_ATOM_NS: Final = "{http://www.w3.org/2005/Atom}"
_DC_CREATOR: Final = "{http://purl.org/dc/elements/1.1/}creator"
_SUBREDDIT_RE: Final = re.compile(r"^[A-Za-z0-9_]{2,50}$")
_FEED_KEY_RE: Final = re.compile(r"^[a-z0-9_]{2,50}$")


@dataclass(frozen=True, slots=True)
class SocialPost:
    """One allowlisted post/headline, source-truth fields only (the
    repository stamps ``fetched_at``/``as_of`` and entity matches land at
    the flow layer)."""

    source: str  # 'reddit' | 'rss'
    source_post_id: str  # reddit: t3_* fullname; rss: '{feed_key}/{guid-or-link}'
    subreddit_or_feed: str  # 'r/nfl' | feed key ('espn_nfl')
    author: str | None
    title: str
    text: str | None  # reddit: content HTML; rss: <description> (summary)
    url: str | None
    created_at: datetime  # source clock, tz-aware UTC
    is_official: bool


@dataclass(frozen=True, slots=True)
class FeedSource:
    """One allowlisted RSS/Atom feed."""

    key: str
    url: str
    official: bool


@dataclass(frozen=True, slots=True)
class SocialSources:
    """The parsed allowlists from ``config/social_sources.toml``."""

    subreddits: tuple[str, ...]
    feeds: tuple[FeedSource, ...]


def _parse_subreddits(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise ValueError("'subreddits' must be a list of subreddit names")
    subreddits: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not _SUBREDDIT_RE.match(item):
            raise ValueError(f"invalid subreddit name (letters/digits/_, no 'r/'): {item!r}")
        if item in subreddits:
            raise ValueError(f"duplicate subreddit: {item!r}")
        subreddits.append(item)
    return tuple(subreddits)


def _parse_feeds(raw: object) -> tuple[FeedSource, ...]:
    if not isinstance(raw, list):
        raise ValueError("'feeds' must be an array of tables ([[feeds]])")
    feeds: list[FeedSource] = []
    seen_keys: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(f"feed entry must be a table with key/url: {entry!r}")
        key = entry.get("key")
        url = entry.get("url")
        official = entry.get("official", False)
        if not isinstance(key, str) or not _FEED_KEY_RE.match(key):
            raise ValueError(f"invalid feed key (lowercase [a-z0-9_]): {key!r}")
        if key in seen_keys:
            raise ValueError(f"duplicate feed key: {key!r}")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ValueError(f"feed {key!r} url must start with https:// : {url!r}")
        if not isinstance(official, bool):
            raise ValueError(f"feed {key!r} 'official' must be a boolean")
        seen_keys.add(key)
        feeds.append(FeedSource(key=key, url=url, official=official))
    return tuple(feeds)


def load_social_sources(path: Path | None = None) -> SocialSources:
    """Load + validate the allowlist config (TOML — stdlib ``tomllib``, the
    format the repo already speaks via pyproject.toml; yaml would need a new
    dep). Editable without code changes; the flow re-reads it every tick.

    Raises ``ValueError`` with a plain-English message on any problem — a
    malformed allowlist must stop the tick loudly, not half-ingest.
    """
    p = path or DEFAULT_SOURCES_PATH
    try:
        with p.open("rb") as fh:
            raw = tomllib.load(fh)
    except FileNotFoundError as exc:
        raise ValueError(f"social sources config missing: {p}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"social sources config unparseable ({p}): {exc}") from exc

    subreddits = _parse_subreddits(raw.get("subreddits", []))
    feeds = _parse_feeds(raw.get("feeds", []))
    if not subreddits and not feeds:
        raise ValueError(f"social sources config lists no sources: {p}")
    return SocialSources(subreddits=subreddits, feeds=feeds)


# ---------------------------------------------------------------------------
# Feed parsing (stdlib xml.etree; handles both RSS 2.0 and Atom)


@dataclass(frozen=True, slots=True)
class _FeedItem:
    """Parser-internal: one entry/item in source-neutral form."""

    item_id: str | None
    title: str | None
    link: str | None
    author: str | None
    body: str | None
    published: datetime | None


def _text_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _parse_rfc822(value: str) -> datetime | None:
    """RSS pubDate → tz-aware UTC. Handles numeric offsets AND the RFC 822
    obsolete named zones (GMT/EST/EDT/...) that real feeds use."""
    try:
        dt = parsedate_to_datetime(value.strip())
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:  # '-0000' parses naive; treat as UTC
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _parse_iso(value: str) -> datetime | None:
    """Atom published/updated (ISO 8601) → tz-aware UTC."""
    try:
        dt = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _item_from_atom_entry(entry: ElementTree.Element) -> _FeedItem:
    link_el = entry.find(f"{_ATOM_NS}link")
    published_raw = _text_or_none(entry.findtext(f"{_ATOM_NS}published")) or _text_or_none(
        entry.findtext(f"{_ATOM_NS}updated")
    )
    return _FeedItem(
        item_id=_text_or_none(entry.findtext(f"{_ATOM_NS}id")),
        title=_text_or_none(entry.findtext(f"{_ATOM_NS}title")),
        link=link_el.get("href") if link_el is not None else None,
        author=_text_or_none(entry.findtext(f"{_ATOM_NS}author/{_ATOM_NS}name")),
        body=_text_or_none(entry.findtext(f"{_ATOM_NS}content"))
        or _text_or_none(entry.findtext(f"{_ATOM_NS}summary")),
        published=_parse_iso(published_raw) if published_raw else None,
    )


def _item_from_rss_item(item: ElementTree.Element) -> _FeedItem:
    published_raw = _text_or_none(item.findtext("pubDate"))
    return _FeedItem(
        item_id=_text_or_none(item.findtext("guid")),
        title=_text_or_none(item.findtext("title")),
        link=_text_or_none(item.findtext("link")),
        author=_text_or_none(item.findtext(_DC_CREATOR)) or _text_or_none(item.findtext("author")),
        body=_text_or_none(item.findtext("description")),
        published=_parse_rfc822(published_raw) if published_raw else None,
    )


def _parse_feed_items(xml_text: str) -> list[_FeedItem]:
    """Parse an RSS 2.0 or Atom document into neutral items. Raises
    ``ValueError`` on non-XML or an unrecognized root (an HTML error page
    from an intermediary must skip the source loudly, not half-parse)."""
    try:
        # B314: defusedxml would be a new dependency (§9). Accepted here
        # because inputs are allowlisted publisher feeds (config/social_
        # sources.toml), ElementTree never resolves external entities, and
        # CPython 3.12 bundles expat >= 2.6 whose billion-laughs
        # amplification limits are on by default.
        root = ElementTree.fromstring(xml_text)  # nosec B314
    except ElementTree.ParseError as exc:
        raise ValueError(f"unparseable feed XML: {exc}") from exc
    if root.tag == f"{_ATOM_NS}feed":
        return [_item_from_atom_entry(e) for e in root.findall(f"{_ATOM_NS}entry")]
    channel = root.find("channel")
    if root.tag == "rss" and channel is not None:
        return [_item_from_rss_item(i) for i in channel.findall("item")]
    raise ValueError(f"unrecognized feed root element: {root.tag!r}")


def posts_from_reddit_atom(
    xml_text: str, subreddit: str, *, fallback_created_at: datetime
) -> list[SocialPost]:
    """Adapt one subreddit Atom listing into posts.

    Entries without a stable id or a title are skipped (logged): without an
    id the upsert cannot dedupe honestly, and the title is the matching
    surface + a NOT NULL column. ``created_at`` falls back to the fetch
    stamp when ``published`` is missing/unparseable (never observed live —
    recorded payloads always carry it — but a fetch-time upper bound beats
    dropping a real event).
    """
    posts: list[SocialPost] = []
    n_skipped = 0
    for item in _parse_feed_items(xml_text):
        if not item.item_id or not item.title:
            n_skipped += 1
            continue
        posts.append(
            SocialPost(
                source="reddit",
                source_post_id=item.item_id,
                subreddit_or_feed=f"r/{subreddit}",
                author=item.author,
                title=item.title,
                text=item.body,
                url=item.link,
                created_at=item.published or fallback_created_at,
                is_official=False,
            )
        )
    if n_skipped:
        log.warning("social.reddit_entries_skipped", subreddit=subreddit, n_skipped=n_skipped)
    return posts


def posts_from_rss(
    xml_text: str, feed: FeedSource, *, fallback_created_at: datetime
) -> list[SocialPost]:
    """Adapt one RSS/Atom feed document into posts. Identity is the guid
    when present, else the link (PFT-style feeds use permalink guids
    anyway); items with neither, or without a title, are skipped (logged).
    """
    posts: list[SocialPost] = []
    n_skipped = 0
    for item in _parse_feed_items(xml_text):
        identity = item.item_id or item.link
        if not identity or not item.title:
            n_skipped += 1
            continue
        posts.append(
            SocialPost(
                source="rss",
                source_post_id=f"{feed.key}/{identity}",
                subreddit_or_feed=feed.key,
                author=item.author,
                title=item.title,
                text=item.body,
                url=item.link,
                created_at=item.published or fallback_created_at,
                is_official=feed.official,
            )
        )
    if n_skipped:
        log.warning("social.rss_items_skipped", feed=feed.key, n_skipped=n_skipped)
    return posts


# ---------------------------------------------------------------------------
# Async client


class SocialClient:
    """Async fetcher for allowlisted subreddit listings + RSS feeds.

    Sends the descriptive contactable UA on every request (also when a
    caller injects its own httpx client) and sleeps ``request_spacing_s``
    between consecutive requests — the polite ~1-request-per-2-s cadence
    Reddit asks of bots. 429/5xx retry twice with backoff in the shared
    helper, then raise ``HttpError``; callers skip the source and the next
    cron tick retries.
    """

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        request_spacing_s: float = REQUEST_SPACING_S,
    ) -> None:
        self._client = client
        self._owns_client = client is None
        self._spacing = request_spacing_s
        self._made_request = False

    async def __aenter__(self) -> SocialClient:
        if self._client is None:
            self._client = default_client(headers={"User-Agent": SOCIAL_USER_AGENT})
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _fetch_text(self, url: str, *, max_retries: int = 2) -> str:
        if self._client is None:
            raise RuntimeError("use `async with SocialClient()` or pass a client")
        if self._made_request and self._spacing > 0:
            await asyncio.sleep(self._spacing)
        self._made_request = True
        return await request_text(
            self._client,
            url,
            headers={"User-Agent": SOCIAL_USER_AGENT},
            max_retries=max_retries,
        )

    async def fetch_subreddit(
        self, subreddit: str, *, fallback_created_at: datetime | None = None
    ) -> list[SocialPost]:
        """Fetch one subreddit's newest posts via the public Atom listing.

        No in-call retries (``max_retries=0``): Reddit's unauthenticated
        listing budget was MEASURED at roughly one fetch per ~60 s from
        this host (live smoke 2026-07-27 — one subreddit 200s, the rest
        429 for ~a minute), so a quick retry can never succeed and only
        hammers the venue. A 429 skips the subreddit; the next cron tick
        (plus the flow's rotation) is the retry.
        """
        stamp = fallback_created_at or datetime.now(tz=UTC)
        xml_text = await self._fetch_text(
            REDDIT_ATOM_URL_TEMPLATE.format(subreddit=subreddit), max_retries=0
        )
        return posts_from_reddit_atom(xml_text, subreddit, fallback_created_at=stamp)

    async def fetch_feed(
        self, feed: FeedSource, *, fallback_created_at: datetime | None = None
    ) -> list[SocialPost]:
        """Fetch one allowlisted RSS/Atom feed."""
        stamp = fallback_created_at or datetime.now(tz=UTC)
        xml_text = await self._fetch_text(feed.url)
        return posts_from_rss(xml_text, feed, fallback_created_at=stamp)


__all__ = [
    "DEFAULT_SOURCES_PATH",
    "REDDIT_ATOM_URL_TEMPLATE",
    "REQUEST_SPACING_S",
    "SOCIAL_USER_AGENT",
    "FeedSource",
    "SocialClient",
    "SocialPost",
    "SocialSources",
    "load_social_sources",
    "posts_from_reddit_atom",
    "posts_from_rss",
]
