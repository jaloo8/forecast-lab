"""NBA injury ingest flow.

v1: imports from a CSV file. The actual scraping / API ingest is
gated on a CLAUDE.md §9 dep decision (see
:mod:`kq.clients.nba_injuries` for the menu of options). This flow
no-ops with a structured warning when ``--csv`` isn't passed, so the
cron entry can land before the source decision is made.
"""

from __future__ import annotations

from pathlib import Path

import structlog

from kq.clients.nba_injuries import parse_csv_file
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.storage.duckdb_store import connect
from kq.storage.repositories.nba_injuries import upsert_injuries

log = structlog.get_logger(__name__)


def main(*, csv_path: Path | None = None, db_path: Path | None = None) -> int:
    """``python -m kq ingest-nba-injuries`` entrypoint.

    Returns the count of rows upserted. 0 (with a structured warning)
    when no source is configured -- the cron entry stays clean.
    """
    if csv_path is None:
        log.warning(
            "nba_injuries.skipped",
            reason=(
                "no CSV source configured; pass --csv FILE to ingest. "
                "Live scraping deferred per CLAUDE.md §9 (new dep needs signoff)."
            ),
        )
        print(
            "nba_injuries: --csv not provided; skipping. "
            "See `kq.clients.nba_injuries` docstring for the data-source menu."
        )
        return 0

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    rows = parse_csv_file(csv_path)
    if not rows:
        log.warning("nba_injuries.empty_csv", csv=str(csv_path))
        print(f"nba_injuries: CSV at {csv_path} parsed to 0 rows; nothing to upsert.")
        return 0

    settings = get_settings()
    db = db_path or _db_path_from_settings(settings.database_url)
    con = connect(db)
    try:
        n = upsert_injuries(con, rows)
    finally:
        con.close()

    log.info(
        "nba_injuries.ingest_done",
        n_rows=n,
        csv=str(csv_path),
        db=str(db),
    )
    print(f"nba_injuries: upserted {n} rows from {csv_path} -> {db}")
    return n


__all__ = ["main"]
