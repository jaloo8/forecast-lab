"""Social-post repository (Phase S1) — the event lane's storage.

Upsert contract (schema rationale in schemas.sql, pinned in
tests/test_idempotency.py): keyed on (source, source_post_id); re-fetching
the same post is a no-op; an upstream EDIT may update title/text/url/author
and a later, better entity match may fill matched_entity_*; the
FIRST-SIGHTING stamps — ``as_of`` (our clock) and ``created_at`` (source
clock) — NEVER move once stored, so the latency ledger can trust them
(publishers bump pubDate on edits, which would otherwise fake freshness).
``fetched_at`` always advances to the latest touch. ``is_official`` keeps
the value the row was ingested under (point-in-time allowlist config, not
retroactive).

Corroboration is computed at READ time (:func:`corroboration_level`), never
stored — stored fields stay raw facts, not judgments.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

import duckdb

from kq.storage._tz import to_naive_utc

CORROBORATION_RED: Final = "red"
CORROBORATION_YELLOW: Final = "yellow"

_COLUMNS: Final[tuple[str, ...]] = (
    "source",
    "source_post_id",
    "subreddit_or_feed",
    "author",
    "title",
    "text",
    "url",
    "is_official",
    "created_at",
    "fetched_at",
    "as_of",
    "matched_entity_type",
    "matched_entity_id",
)


@dataclass(frozen=True, slots=True)
class SocialPostRow:
    """Storage-shaped row — ``social_post`` minus the repo-stamped
    ``fetched_at``/``as_of``."""

    source: str
    source_post_id: str
    subreddit_or_feed: str
    author: str | None
    title: str
    text: str | None
    url: str | None
    is_official: bool
    created_at: datetime
    matched_entity_type: str | None
    matched_entity_id: str | None


def upsert_social_posts(
    con: duckdb.DuckDBPyConnection,
    rows: Iterable[SocialPostRow],
    *,
    as_of: datetime | None = None,
) -> int:
    """Upsert posts; returns the count of input rows.

    Idempotent on (source, source_post_id). On conflict: title always takes
    the incoming value (edits flow); text/url/author and the matched-entity
    pair take the incoming value only when non-NULL (a degraded re-parse
    never blanks stored data; matched_entity_type/-id are always set or
    unset together by the flow, so per-column COALESCE cannot mix pairs);
    ``fetched_at`` moves to this batch's stamp. ``created_at``, ``as_of``,
    and ``is_official`` are deliberately ABSENT from the update — first
    sighting wins, forever.
    """
    stamp = to_naive_utc(as_of) if as_of is not None else datetime.now(tz=UTC).replace(tzinfo=None)
    batch: list[Sequence[object]] = [
        (
            r.source,
            r.source_post_id,
            r.subreddit_or_feed,
            r.author,
            r.title,
            r.text,
            r.url,
            r.is_official,
            to_naive_utc(r.created_at),
            stamp,
            stamp,
            r.matched_entity_type,
            r.matched_entity_id,
        )
        for r in rows
    ]
    if not batch:
        return 0
    con.executemany(
        f"""
        INSERT INTO social_post ({", ".join(_COLUMNS)})
        VALUES ({", ".join("?" for _ in _COLUMNS)})
        ON CONFLICT (source, source_post_id) DO UPDATE SET
            subreddit_or_feed = EXCLUDED.subreddit_or_feed,
            author = COALESCE(EXCLUDED.author, social_post.author),
            title = EXCLUDED.title,
            text = COALESCE(EXCLUDED.text, social_post.text),
            url = COALESCE(EXCLUDED.url, social_post.url),
            matched_entity_type =
                COALESCE(EXCLUDED.matched_entity_type, social_post.matched_entity_type),
            matched_entity_id =
                COALESCE(EXCLUDED.matched_entity_id, social_post.matched_entity_id),
            fetched_at = EXCLUDED.fetched_at
        """,
        batch,
    )
    return len(batch)


def fetch_social_posts(
    con: duckdb.DuckDBPyConnection,
    *,
    source: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    since: datetime | None = None,
) -> list[dict[str, object]]:
    """Read posts as dicts, ordered for reproducible consumption. ``since``
    filters on ``as_of`` (when WE first knew), the honest cut for any
    latency or corroboration question."""
    where_clauses: list[str] = []
    params: list[object] = []
    if source is not None:
        where_clauses.append("source = ?")
        params.append(source)
    if entity_type is not None:
        where_clauses.append("matched_entity_type = ?")
        params.append(entity_type)
    if entity_id is not None:
        where_clauses.append("matched_entity_id = ?")
        params.append(entity_id)
    if since is not None:
        where_clauses.append("as_of >= ?")
        params.append(to_naive_utc(since))
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    rows = con.execute(
        f"""
        SELECT {", ".join(_COLUMNS)}
        FROM social_post
        {where_sql}
        ORDER BY as_of, source, source_post_id
        """,
        params,
    ).fetchall()
    return [dict(zip(_COLUMNS, row, strict=True)) for row in rows]


def corroboration_level(posts: Sequence[Mapping[str, object]]) -> str | None:
    """Read-time corroboration over posts the caller already filtered to
    one entity + time window (e.g. via :func:`fetch_social_posts`):

    * ``'red'`` — any post from an ``is_official`` source, OR >= 2 distinct
      feeds/subreddits carried it (design: one official post or two
      independent allowlisted sources may trigger an input re-evaluation);
    * ``'yellow'`` — a single unofficial sighting (surface only);
    * ``None`` — no posts.

    Honest v0 caveats: "distinct feeds" approximates independence — Yahoo
    syndicates PFT/SB Nation content and one publisher can appear under
    several feed keys, so two feeds can carry the SAME underlying report.
    Nothing acts on this signal in S1 (surfacing only); tighten the
    independence definition before any consumer does.
    """
    if not posts:
        return None
    if any(bool(p["is_official"]) for p in posts):
        return CORROBORATION_RED
    if len({str(p["subreddit_or_feed"]) for p in posts}) >= 2:
        return CORROBORATION_RED
    return CORROBORATION_YELLOW


__all__ = [
    "CORROBORATION_RED",
    "CORROBORATION_YELLOW",
    "SocialPostRow",
    "corroboration_level",
    "fetch_social_posts",
    "upsert_social_posts",
]
