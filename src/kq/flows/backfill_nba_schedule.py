"""NBA schedule backfill — pull historical games for an arbitrary date range.

Used to seed the Elo training set with multiple seasons of history before
the live ingest takes over. Per the
[Phase 3 plan doc](../../../docs/research/PHASE-3-NBA-PLAN.md), PR 1's
exit criterion is ≥ 6 seasons of completed games loaded.

Wraps `nba_api.stats.endpoints.leaguegamefinder` via
`kq.clients.nba_schedule.NbaScheduleClient.fetch_games_for_range`. The
underlying endpoint accepts a date range directly so we make one HTTP
call per backfill (vs. one per day in the live ingest).

Idempotent: re-running the same range upserts on `game_id`. Safe for
recovery / re-validation.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import structlog

from kq.clients.nba_schedule import NbaScheduleClient
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.storage.duckdb_store import connect
from kq.storage.repositories.nba import upsert_nba_games

log = structlog.get_logger(__name__)


def main(*, start: str, end: str, db_path: Path | None = None) -> int:
    """`python -m kq backfill-nba-schedule --start ... --end ...` entrypoint.

    Date strings are ISO-8601 (YYYY-MM-DD). Returns rows upserted.
    """
    start_d = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    if end_d < start_d:
        raise SystemExit(f"end {end_d} precedes start {start_d}")

    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)
    return backfill(start=start_d, end=end_d, db_path=path)


def backfill(
    *,
    start: date,
    end: date,
    db_path: Path,
    client: NbaScheduleClient | None = None,
) -> int:
    """Library entry point. Fetches the entire range in one API call,
    then upserts."""
    c = client or NbaScheduleClient()
    rows = c.fetch_games_for_range(start=start, end=end)
    log.info(
        "nba_schedule.backfill_fetched",
        start=start.isoformat(),
        end=end.isoformat(),
        games=len(rows),
    )

    con = connect(db_path)
    try:
        n = upsert_nba_games(con, rows)
    finally:
        con.close()

    log.info(
        "nba_schedule.backfill_done",
        start=start.isoformat(),
        end=end.isoformat(),
        upserted=n,
        db=str(db_path),
    )
    print(f"backfilled {n} NBA game rows ({start} to {end})")
    return n


__all__ = ["backfill", "main"]
