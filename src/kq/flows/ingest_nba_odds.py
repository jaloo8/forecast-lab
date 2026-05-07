"""NBA moneyline odds ingest -- pull current Pinnacle quotes from
The Odds API and upsert into ``nba_odds``.

Designed for the Phase 3 cron cadence (CLAUDE.md §5):
  * Hourly during the regular season + playoffs.
  * 15-min cadence in the final 3h before tipoff (cron schedule, not
    a flag here -- this module is one tick).

**Quota discipline.** The Odds API free tier ships 500 credits/mo and,
empirically (verified 2026-05-06) returns Pinnacle when the request
specifies ``regions=eu``. One tick = one credit; an hourly cadence
during a peak NBA month uses ~120-300 credits, comfortably under the
free quota. The paid $30/mo tier (20 k credits/mo) is only needed if
you start polling minute-by-minute or layer in multiple sports. The
flow logs ``remaining`` on every successful pull -- cron alerting
should fire when that drops below 50 (10 % of the free bucket).

**No-key behavior.** When ``ODDS_API_KEY`` is empty (the v1 default
in ``.env.example``), the flow logs a structured ``odds_api.skipped``
event and returns 0 without raising. This means we can land the cron
entry today, before the user signs up, and the pipeline stays
idempotent + green.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import structlog

from kq.clients.the_odds_api import (
    BOOKMAKER_PINNACLE,
    OddsApiGame,
    QuotaUsage,
    TheOddsApiClient,
)
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.storage.duckdb_store import connect
from kq.storage.repositories.nba_odds import odds_rows_from_games, upsert_odds_rows

log = structlog.get_logger(__name__)

# Default bookmaker filter. Pinnacle is the fair-value anchor; the
# fallback list (BetMGM, DraftKings, FanDuel) is requested via the
# CLI when we want the broader US-book view.
DEFAULT_BOOKMAKER_KEYS: tuple[str, ...] = (BOOKMAKER_PINNACLE,)


async def fetch_and_upsert(
    *,
    api_key: str,
    db_path: Path,
    bookmaker_keys: tuple[str, ...] = DEFAULT_BOOKMAKER_KEYS,
    fetched_at: datetime | None = None,
) -> int:
    """Pull current NBA h2h quotes and upsert into ``nba_odds``.

    Returns the count of (game, book, market) rows upserted. Quota
    counters from the response are logged on the success path.
    Errors propagate -- cron handles the retry.
    """
    when = fetched_at or datetime.now(tz=UTC)
    async with TheOddsApiClient(api_key=api_key) as client:
        games, quota = await client.fetch_nba_h2h(bookmaker_keys=bookmaker_keys)

    return _persist(
        games=games,
        quota=quota,
        db_path=db_path,
        bookmaker_keys=bookmaker_keys,
        fetched_at=when,
    )


def _persist(
    *,
    games: list[OddsApiGame],
    quota: QuotaUsage,
    db_path: Path,
    bookmaker_keys: tuple[str, ...],
    fetched_at: datetime,
) -> int:
    """Flatten + upsert the games in a single transaction. Split out so
    tests can call the persistence path with synthetic ``OddsApiGame``
    fixtures without going through the HTTP client."""
    rows = odds_rows_from_games(games, fetched_at=fetched_at)
    con = connect(db_path)
    try:
        n = upsert_odds_rows(con, rows)
    finally:
        con.close()
    log.info(
        "odds_api.ingest_done",
        n_games=len(games),
        n_rows=n,
        bookmakers=bookmaker_keys,
        remaining=quota.remaining,
        used=quota.used,
        last_cost=quota.last_cost,
        db=str(db_path),
    )
    return n


def main(*, db_path: Path | None = None) -> int:
    """``python -m kq ingest-nba-odds`` entrypoint.

    Returns the count of upserted rows, or 0 (with a logged warning)
    when ``ODDS_API_KEY`` is unset. Never raises on a missing key --
    the cron entry can be active before the user signs up.
    """
    settings = get_settings()
    api_key = settings.odds_api_key
    if not api_key:
        log.warning(
            "odds_api.skipped",
            reason="ODDS_API_KEY not set; flow no-op until key is provisioned",
        )
        print("ODDS_API_KEY not set -- skipping NBA odds ingest")
        return 0

    path = db_path or _db_path_from_settings(settings.database_url)
    n = asyncio.run(fetch_and_upsert(api_key=api_key, db_path=path))
    print(f"upserted {n} NBA odds rows -> {path}")
    return n


__all__ = [
    "DEFAULT_BOOKMAKER_KEYS",
    "fetch_and_upsert",
    "main",
]
