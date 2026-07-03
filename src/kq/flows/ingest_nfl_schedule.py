"""NFL schedule + results ingest — The Odds API ``/scores`` endpoint.

One tick pulls upcoming games (with kickoff times, feeding the paper
flow's pre-kickoff guard) AND games completed in the last ``days_from``
days (feeding settlement). No ``nba_api`` analogue exists or is needed —
the design doc's §2 settlement plan, now wired.

Unlike the NBA schedule ingest (nba_api, keyless), this flow needs
``ODDS_API_KEY`` and follows the odds flows' no-op convention when it is
missing: log, print, return 0, exit clean — the cron entry can predate the
key.

**Recommended cron** (UTC; games finish Sun evening through early Tue ET):

    # daily baseline — kickoff times for the coming slate
    30 10 * * *            kq ingest-nfl-schedule
    # post-game sweeps so settlement fires the same night
    0 2,4,6 * * 1,2,5      kq ingest-nfl-schedule   # after Sun/Mon/Thu games

**Quota**: 2 credits per tick with the completed-games lookback (1 without)
— a rounding error next to the odds cadence.

Finality: rows land via the guarded upsert in
:mod:`kq.storage.repositories.nfl` — a completed game is frozen forever;
NULLs never regress stored truth. Rows whose team names we can't map to
the 32-team set are skipped loudly, never stored half-mapped.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from kq.clients.the_odds_api import SPORT_NFL, OddsApiScore, QuotaUsage, TheOddsApiClient
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.models.nfl_crosswalk import NflGameRow, nfl_game_row_from_score
from kq.storage.duckdb_store import connect
from kq.storage.repositories.nfl import upsert_nfl_games

log = structlog.get_logger(__name__)

# Completed-games lookback in days. 3 is the API's maximum and covers a
# full Sun-slate weekend even if the cron missed a couple of ticks.
DEFAULT_DAYS_FROM: int = 3


async def fetch_and_upsert(
    *,
    api_key: str,
    db_path: Path,
    days_from: int = DEFAULT_DAYS_FROM,
) -> int:
    """Pull the /scores window and upsert into ``nfl_game``.

    Returns the count of rows upserted. Errors propagate — cron retries.
    """
    async with TheOddsApiClient(api_key=api_key) as client:
        scores, quota = await client.fetch_scores(SPORT_NFL, days_from=days_from)
    return _persist(scores=scores, quota=quota, db_path=db_path)


def _persist(
    *,
    scores: list[OddsApiScore],
    quota: QuotaUsage,
    db_path: Path,
) -> int:
    """Adapt + upsert score rows. Split out so tests can drive persistence
    with synthetic ``OddsApiScore`` fixtures without the HTTP client."""
    rows: list[NflGameRow] = []
    n_unmappable = 0
    for score in scores:
        row = nfl_game_row_from_score(score)
        if row is None:
            n_unmappable += 1
            log.warning(
                "nfl_schedule.unmappable_team",
                game_id=score.game_id,
                home_team=score.home_team,
                away_team=score.away_team,
            )
            continue
        rows.append(row)

    con = connect(db_path)
    try:
        n = upsert_nfl_games(con, rows)
    finally:
        con.close()
    log.info(
        "nfl_schedule.ingest_done",
        n_games=len(scores),
        n_rows=n,
        n_completed=sum(1 for r in rows if r.completed),
        n_unmappable=n_unmappable,
        remaining=quota.remaining,
        used=quota.used,
        last_cost=quota.last_cost,
        db=str(db_path),
    )
    return n


def main(*, days_from: int = DEFAULT_DAYS_FROM, db_path: Path | None = None) -> int:
    """``python -m kq ingest-nfl-schedule`` entrypoint.

    Returns the count of upserted rows, or 0 (with a logged warning) when
    ``ODDS_API_KEY`` is unset. Never raises on a missing key.
    """
    settings = get_settings()
    api_key = settings.odds_api_key
    if not api_key:
        log.warning(
            "nfl_schedule.skipped",
            reason="ODDS_API_KEY not set; flow no-op until key is provisioned",
        )
        print("ODDS_API_KEY not set -- skipping NFL schedule ingest")
        return 0

    path = db_path or _db_path_from_settings(settings.database_url)
    n = asyncio.run(fetch_and_upsert(api_key=api_key, db_path=path, days_from=days_from))
    print(f"upserted {n} NFL game rows (scores lookback {days_from}d) -> {path}")
    return n


__all__ = ["DEFAULT_DAYS_FROM", "fetch_and_upsert", "main"]
