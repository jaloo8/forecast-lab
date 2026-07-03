"""Scheduled daily index OHLC ingest (Phase C index-brackets lane).

Pulls a trailing window (default: the last 7 calendar days) of S&P 500 /
Nasdaq-100 daily bars by delegating to :func:`kq.flows.backfill_index.
backfill`. Upserts are idempotent on (symbol, valid_date) and guarded
(NULL never overwrites a stored value), so late vendor corrections are
picked up on the next pass and a degraded payload can't wipe truth. The
current session's live partial bar is excluded until ~16:15 ET by the
client, so a mid-session cron tick can't persist a provisional close.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog

from kq.flows.backfill_index import backfill

log = structlog.get_logger(__name__)

# 7 calendar days ≈ 5 trading sessions: wide enough to heal a long weekend
# plus a vendor correction, small enough to stay one cheap request.
DEFAULT_LOOKBACK_DAYS = 7


async def ingest_once(
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    db_path: Path | None = None,
) -> int:
    """Pull daily OHLC for every index symbol over the trailing window."""
    if lookback_days < 1:
        raise ValueError(f"lookback_days must be >= 1, got {lookback_days}")
    end_date = datetime.now(tz=UTC).date()
    start_date = end_date - timedelta(days=lookback_days)
    n = await backfill(start_date=start_date, end_date=end_date, db_path=db_path)
    log.info(
        "index.ingest_done",
        rows=n,
        start=start_date.isoformat(),
        end=end_date.isoformat(),
    )
    return n


def main(*, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> None:
    """`python -m kq ingest-index` entrypoint."""
    total = asyncio.run(ingest_once(lookback_days=lookback_days))
    print(f"ingested {total} index daily rows (trailing {lookback_days} days)")


if __name__ == "__main__":  # pragma: no cover
    main()
