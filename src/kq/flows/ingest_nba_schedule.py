"""NBA schedule ingest — daily pull of yesterday + today's games.

Runs once per cron tick. Pulls today's scoreboard and yesterday's, with
"today" anchored to the US/Eastern calendar date (the repo's fixed -5h
convention) — ``nba_game.game_date`` is an ET date, and a 00:00-05:00
UTC cron tick is still the previous evening in ET, so a UTC-anchored
window never swept the finals of games that ended late the prior ET
evening (2026-07-01 audit, Tier 2). Idempotent — re-running re-upserts
and bumps `fetched_at`.

Designed for the operational cadence per CLAUDE.md §5 Phase 3:
  * Hourly during the season — score updates as games finish.
  * 15-min cadence in the final 3h before tipoff (see `nba_injuries`
    flow when that lands; this scheduling lives in cron, not here).

Phase 3 PR 1 of [`docs/research/PHASE-3-NBA-PLAN.md`](../../../docs/research/PHASE-3-NBA-PLAN.md).
NBA is gated behind Phase 2 ship per CLAUDE.md §2; the flow lands as a
ready-to-run starter so cron entries can reference it once the gate
clears.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import structlog

from kq.clients.nba_schedule import NbaScheduleClient
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.models.nba_crosswalk import US_EASTERN_OFFSET_HOURS
from kq.storage.duckdb_store import connect
from kq.storage.repositories.nba import upsert_nba_games

log = structlog.get_logger(__name__)

# Default lookback: pull yesterday + today's games (US/Eastern days).
# Yesterday catches late games that finished after the prior cron run;
# today catches scheduled tipoffs + early finishes.
DEFAULT_LOOKBACK_DAYS: int = 1


def main(
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    db_path: Path | None = None,
    client: NbaScheduleClient | None = None,
    now_utc: datetime | None = None,
) -> int:
    """`python -m kq ingest-nba-schedule` entrypoint.

    The day window is anchored to the US/Eastern calendar date (fixed
    -5h, no DST — the same convention as
    ``kq.models.nba_crosswalk.odds_api_to_us_eastern_date`` and
    ``nba_game.game_date``), NOT the UTC date: at a 00:00-05:00 UTC cron
    tick the UTC date is already tomorrow in ET terms, so a UTC-anchored
    ``[today - lookback, today]`` window skipped the ET day on which the
    previous evening's games actually finished (2026-07-01 audit, Tier 2).

    ``client`` / ``now_utc`` are injectable for tests.

    Returns the number of (game_id) rows upserted.
    """
    path = db_path or _db_path_from_settings(get_settings().database_url)
    now = now_utc or datetime.now(tz=UTC)
    today_et = (now.astimezone(UTC) + timedelta(hours=US_EASTERN_OFFSET_HOURS)).date()
    start = today_et - timedelta(days=lookback_days)
    return ingest_range(start=start, end=today_et, db_path=path, client=client)


def ingest_range(
    *,
    start: date,
    end: date,
    db_path: Path,
    client: NbaScheduleClient | None = None,
) -> int:
    """Pull every day in [start, end]; upsert each into nba_game.

    Library entry point. Tests can pass an `NbaScheduleClient` mock to
    avoid hitting the real `nba_api`.
    """
    if end < start:
        raise ValueError(f"end {end} precedes start {start}")
    c = client or NbaScheduleClient()

    total_inserted = 0
    con = connect(db_path)
    try:
        # Iterate one day at a time so a single bad day doesn't take down
        # the whole window. We log per-day counts for cron visibility.
        current = start
        while current <= end:
            rows = c.fetch_games_for_date(current)
            n = upsert_nba_games(con, rows)
            total_inserted += n
            log.info(
                "nba_schedule.day_done",
                date=current.isoformat(),
                games=n,
            )
            current += timedelta(days=1)
    finally:
        con.close()

    log.info(
        "nba_schedule.ingest_done",
        start=start.isoformat(),
        end=end.isoformat(),
        total_inserted=total_inserted,
        db=str(db_path),
    )
    print(f"upserted {total_inserted} NBA game rows ({start} to {end})")
    return total_inserted


__all__ = ["DEFAULT_LOOKBACK_DAYS", "ingest_range", "main"]
