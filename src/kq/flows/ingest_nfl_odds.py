"""NFL moneyline odds ingest -- pull current Pinnacle quotes from
The Odds API and upsert into ``nfl_odds``.

The NBA twin's disciplines carry over wholesale (see
:mod:`kq.flows.ingest_nba_odds`): quota logging on every pull, structured
no-op when ``ODDS_API_KEY`` is empty, idempotent time-series upserts.

**Cadence (recommended cron).** NFL games cluster on Sunday with Thu/Mon
singles; unlike NBA there is no nightly slate. The strategy panel's W2
entry window is T-60min after official inactives (~90 min pre-kickoff), so
the odds snapshot must be FRESH in that window for the paper flow's anchor
and for honest closing-line capture:

    # hourly baseline, every day (anchor freshness + line history)
    0 * * * *              kq ingest-nfl-odds
    # 15-min cadence through the Sunday slate + Thu/Mon night windows (ET)
    */15 16-23 * * 0       kq ingest-nfl-odds     # Sun afternoon/evening
    */15 0-2 * * 1,2,5     kq ingest-nfl-odds     # Sun/Mon/Thu night finishes (UTC)

**Quota.** One tick = 1 credit (h2h, eu region). Hourly + game-day 15-min
bursts is roughly 800-900 credits/mo in season — over the free 500/mo when
stacked with NBA, so budget the $30/mo tier per CLAUDE.md §11, or drop the
hourly baseline to every 2h off-peak to stay free.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import structlog

from kq.clients.the_odds_api import (
    BOOKMAKER_PINNACLE,
    SPORT_NFL,
    OddsApiGame,
    QuotaUsage,
    TheOddsApiClient,
)
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.storage.duckdb_store import connect
from kq.storage.repositories.nfl_odds import odds_rows_from_games, upsert_nfl_odds_rows

log = structlog.get_logger(__name__)

# Pinnacle is the fair-value anchor for NFL exactly as for NBA (verified
# live 2026-05-24: present via regions=eu, quotes next-season lines early).
DEFAULT_BOOKMAKER_KEYS: tuple[str, ...] = (BOOKMAKER_PINNACLE,)


async def fetch_and_upsert(
    *,
    api_key: str,
    db_path: Path,
    bookmaker_keys: tuple[str, ...] = DEFAULT_BOOKMAKER_KEYS,
    fetched_at: datetime | None = None,
) -> int:
    """Pull current NFL h2h quotes and upsert into ``nfl_odds``.

    Returns the count of (game, book, market) rows upserted. Quota
    counters from the response are logged on the success path.
    Errors propagate -- cron handles the retry.
    """
    when = fetched_at or datetime.now(tz=UTC)
    async with TheOddsApiClient(api_key=api_key) as client:
        games, quota = await client.fetch_h2h(SPORT_NFL, bookmaker_keys=bookmaker_keys)

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
    """Flatten + upsert the games. Split out so tests can drive the
    persistence path with synthetic ``OddsApiGame`` fixtures without the
    HTTP client."""
    rows = odds_rows_from_games(games, fetched_at=fetched_at)
    con = connect(db_path)
    try:
        n = upsert_nfl_odds_rows(con, rows)
    finally:
        con.close()
    log.info(
        "nfl_odds.ingest_done",
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
    """``python -m kq ingest-nfl-odds`` entrypoint.

    Returns the count of upserted rows, or 0 (with a logged warning)
    when ``ODDS_API_KEY`` is unset. Never raises on a missing key --
    the cron entry can be active before the key is provisioned.
    """
    settings = get_settings()
    api_key = settings.odds_api_key
    if not api_key:
        log.warning(
            "nfl_odds.skipped",
            reason="ODDS_API_KEY not set; flow no-op until key is provisioned",
        )
        print("ODDS_API_KEY not set -- skipping NFL odds ingest")
        return 0

    path = db_path or _db_path_from_settings(settings.database_url)
    n = asyncio.run(fetch_and_upsert(api_key=api_key, db_path=path))
    print(f"upserted {n} NFL odds rows -> {path}")
    return n


__all__ = [
    "DEFAULT_BOOKMAKER_KEYS",
    "fetch_and_upsert",
    "main",
]
