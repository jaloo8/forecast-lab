"""Social / open-news event-lane ingest (Phase S1) — Reddit + RSS.

One tick loads the allowlists from ``config/social_sources.toml``, fetches
each subreddit's public Atom listing and each RSS feed (descriptive UA,
~2 s spacing between requests), matches title+text against known entities
(F1a stored player names + the NFL/NBA team crosswalks — conservative
exact matching, unmatched posts stored inert), and upserts into
``social_post`` keyed (source, source_post_id): re-fetches never
duplicate, and the first-sighting ``as_of``/``created_at`` stamps never
move (the latency-edge ledger depends on that).

**Event triggers only (CLAUDE.md §2):** this lane stores raw, timestamped
posts so the lane's real latency edge vs Kalshi book moves can be
MEASURED later; nothing here feeds a model probability.

**Recommended cron** (UTC; in-season): every 15 minutes at an offset that
dodges the DuckDB single-writer minute grid (metar :00/:15/:30/:45,
kalshi :07/:22/:37/:52, heartbeat :05/:35):

    3,18,33,48 * * * *    kq ingest-social

Off-season / low-stakes, hourly at :12 is plenty. Scheduler registration
is a follow-up ops PR — scripts/install-scheduled-tasks.ps1 is untouched
by S1.

Failure posture: every source is fetched independently. A 429 (RSS feeds:
after the client's backoff retries; Reddit: immediately — see below),
transport error, or unparseable payload logs a loud warning and skips THAT
source; the rest of the tick proceeds and the next tick retries. A
malformed allowlist config, or anything unexpected outside the per-source
loop, propagates — cron surfaces it.

Reddit budget reality (measured on the 2026-07-27 live smoke): the
unauthenticated ``.rss`` listing allows roughly ONE fetch per ~60 s from
this host — each tick typically lands 1-2 subreddits and 429s the rest.
Two mitigations: the subreddit fetch ORDER ROTATES each tick (derived
from the tick's minute, stateless) so a fixed config order can't starve
the later subreddits, and the Reddit fetch does not retry in-call (a
quick retry can never outlast the refill; it only hammers the venue). At
the :03/:18/:33/:48 cadence every subreddit gets fetched roughly
hourly. RSS feeds have no such budget and land every tick.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import structlog

from kq.clients.social import SocialClient, SocialPost, load_social_sources
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.models.social_entities import SocialEntityMatcher
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.social import SocialPostRow, upsert_social_posts

log = structlog.get_logger(__name__)


def _stored_player_names(con: duckdb.DuckDBPyConnection) -> list[tuple[str, str]]:
    """Distinct (player_name, player_id) pairs from the F1a lane. Empty on
    a fresh DB — the matcher then degrades to team-only matching."""
    rows = con.execute("SELECT DISTINCT player_name, player_id FROM nfl_player_game").fetchall()
    return [(str(name), str(player_id)) for name, player_id in rows]


def _rotated(items: tuple[str, ...], minute_of_day: int) -> tuple[str, ...]:
    """Rotate the subreddit order by the tick's minute so Reddit's ~1-fetch
    -per-minute budget is shared across ticks instead of always feeding the
    first config entry. Stateless + deterministic given the clock; at the
    recommended :03/:18/:33/:48 cadence the start index cycles through all
    residues every hour."""
    if not items:
        return items
    offset = minute_of_day % len(items)
    return items[offset:] + items[:offset]


def _to_row(post: SocialPost, matcher: SocialEntityMatcher) -> SocialPostRow:
    match_text = post.title if post.text is None else f"{post.title} {post.text}"
    match = matcher.match(match_text)
    return SocialPostRow(
        source=post.source,
        source_post_id=post.source_post_id,
        subreddit_or_feed=post.subreddit_or_feed,
        author=post.author,
        title=post.title,
        text=post.text,
        url=post.url,
        is_official=post.is_official,
        created_at=post.created_at,
        matched_entity_type=match.entity_type if match else None,
        matched_entity_id=match.entity_id if match else None,
    )


async def ingest_once(
    *,
    db_path: Path | None = None,
    sources_path: Path | None = None,
    social_client: SocialClient | None = None,
) -> int:
    """Fetch every allowlisted source, entity-match, upsert. Returns the
    number of posts upserted (0 when every source failed — logged loudly;
    the next tick retries)."""
    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)
    sources = load_social_sources(sources_path)

    fallback = datetime.now(tz=UTC)
    posts: list[SocialPost] = []
    n_ok = 0
    n_failed = 0
    subreddit_order = _rotated(sources.subreddits, fallback.hour * 60 + fallback.minute)
    client = social_client if social_client is not None else SocialClient()
    async with client:
        for subreddit in subreddit_order:
            try:
                fetched = await client.fetch_subreddit(subreddit, fallback_created_at=fallback)
            except Exception as exc:
                n_failed += 1
                log.warning(
                    "social.source_failed",
                    source=f"r/{subreddit}",
                    error=str(exc),
                    action="skipped; next tick retries",
                )
                continue
            n_ok += 1
            log.info("social.source_fetched", source=f"r/{subreddit}", n_posts=len(fetched))
            posts.extend(fetched)
        for feed in sources.feeds:
            try:
                fetched = await client.fetch_feed(feed, fallback_created_at=fallback)
            except Exception as exc:
                n_failed += 1
                log.warning(
                    "social.source_failed",
                    source=feed.key,
                    url=feed.url,
                    error=str(exc),
                    action="skipped; next tick retries",
                )
                continue
            n_ok += 1
            log.info("social.source_fetched", source=feed.key, n_posts=len(fetched))
            posts.extend(fetched)

    # bootstrap() is idempotent and creates social_post on databases that
    # predate S1 (F1a precedent) — connect only after the network phase so
    # the single-writer lock is held briefly.
    bootstrap(path)
    con = connect(path)
    try:
        matcher = SocialEntityMatcher(_stored_player_names(con))
        rows = [_to_row(p, matcher) for p in posts]
        before_row = con.execute("SELECT count(*) FROM social_post").fetchone()
        n = upsert_social_posts(con, rows)
        after_row = con.execute("SELECT count(*) FROM social_post").fetchone()
    finally:
        con.close()
    n_before = int(before_row[0]) if before_row else 0
    n_after = int(after_row[0]) if after_row else 0
    n_matched = sum(1 for r in rows if r.matched_entity_type is not None)

    log.info(
        "social.ingest_done",
        n_sources_ok=n_ok,
        n_sources_failed=n_failed,
        n_posts=n,
        n_new=n_after - n_before,
        n_matched=n_matched,
        db=str(path),
    )
    return n


def main(*, db_path: Path | None = None, sources_path: Path | None = None) -> int:
    """``python -m kq ingest-social`` entrypoint. Returns posts upserted."""
    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)
    n = asyncio.run(ingest_once(db_path=path, sources_path=sources_path))
    print(f"upserted {n} social posts -> {path}")
    return n


__all__ = ["ingest_once", "main"]
