"""Scheduled observed-truth ingest (NWS ACIS daily climate values).

The daily 16:00 UTC settle pass reads ``weather_observed`` — the exact NWS
Daily Climate Report values Kalshi weather markets settle on. Until this
flow, nothing refreshed that table on a schedule, so weather settlement
could never fire (2026-06-11 audit root cause #7). Cron cadence and the
rationale live in ``docs/SCHEDULED-RUNS.md``.

Pulls a trailing window (default: the last 3 days) for ALL stations by
delegating to :func:`kq.flows.backfill_observed.backfill`. Upserts are
idempotent on (station, valid_date), so late-arriving corrections to a
climate report are picked up on the next pass.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog

from kq.flows.backfill_observed import backfill

log = structlog.get_logger(__name__)

DEFAULT_LOOKBACK_DAYS = 3


async def ingest_once(
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    db_path: Path | None = None,
) -> int:
    """Pull ACIS observed truth for every station over the trailing window.

    Window is ``[today_utc - lookback_days, today_utc]`` inclusive — today's
    partial value (if ACIS has one) is harmless because settlement carries
    its own day-completion guard. Returns rows written.
    """
    if lookback_days < 1:
        raise ValueError(f"lookback_days must be >= 1, got {lookback_days}")
    end_date = datetime.now(tz=UTC).date()
    start_date = end_date - timedelta(days=lookback_days)
    n = await backfill(start_date=start_date, end_date=end_date, db_path=db_path)
    log.info(
        "observed.ingest_done",
        rows=n,
        start=start_date.isoformat(),
        end=end_date.isoformat(),
    )
    return n


def main(*, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> None:
    """`python -m kq ingest-observed` entrypoint."""
    total = asyncio.run(ingest_once(lookback_days=lookback_days))
    print(f"ingested {total} observed daily rows (trailing {lookback_days} days)")


if __name__ == "__main__":
    main()
