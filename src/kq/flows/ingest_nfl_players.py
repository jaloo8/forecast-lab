"""NFL player-week stats ingest — nflverse via ``nfl_data_py`` (Fantasy F1a).

One tick pulls, for each requested season: weekly player stat lines
(REG + POST, native standard/PPR fantasy points), snap counts (joined via
the pfr->gsis id crosswalk with a normalized-name fallback), and upserts
merged rows into ``nfl_player_game``. Keyless public data — no API quota.

Default season is the CURRENT NFL season (August flip, same convention as
:func:`kq.models.nfl_crosswalk.nfl_season_start_year`); historical backfill
for model training is explicit: ``kq ingest-nfl-players --season 2022
--season 2023 --season 2024``.

**Recommended cron** (UTC; in-season only, Sep-Feb): nflverse refreshes
weekly stats overnight after games and republishes corrections through the
week, so a Tuesday pass catches the full MNF slate and a Wednesday pass
sweeps corrections:

    0 11 * * 2,3    kq ingest-nfl-players

Failure posture: per-season fetch failures are logged and skipped inside
the client (a not-yet-published season 404s — the cron entry can predate
the season); a snap/id-crosswalk failure degrades to NULL snap columns for
NEW rows while the guarded upsert keeps previously stored snap values
intact. Unexpected errors propagate — cron retries next tick.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import structlog

from kq.clients.nfl_players import (
    fetch_pfr_to_gsis,
    fetch_snap_counts,
    fetch_weekly_stats,
    merge_player_weeks,
)
from kq.config import get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.models.nfl_crosswalk import nfl_season_start_year
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.nfl_players import upsert_player_games

log = structlog.get_logger(__name__)


def run(*, seasons: list[int], db_path: Path) -> int:
    """Fetch + merge + upsert player-week rows. Returns rows upserted."""
    stats = fetch_weekly_stats(seasons)
    if not stats:
        log.warning("nfl_players.no_weekly_rows", seasons=seasons)
        return 0
    snaps = fetch_snap_counts(seasons)
    pfr_to_gsis = fetch_pfr_to_gsis()
    rows = merge_player_weeks(stats, snaps, pfr_to_gsis)

    # bootstrap() is idempotent and creates the F1a tables on databases that
    # predate them (ingest_kalshi precedent) — without it the first host run
    # after this lane lands would crash on a missing table.
    bootstrap(db_path)
    con = connect(db_path)
    try:
        n = upsert_player_games(con, rows)
    finally:
        con.close()

    n_with_snaps = sum(1 for r in rows if r.snaps is not None)
    log.info(
        "nfl_players.ingest_done",
        seasons=seasons,
        n_rows=n,
        n_with_snaps=n_with_snaps,
        n_snap_rows=len(snaps),
        n_id_mappings=len(pfr_to_gsis),
        db=str(db_path),
    )
    return n


def main(*, seasons: list[int] | None = None, db_path: Path | None = None) -> int:
    """``python -m kq ingest-nfl-players`` entrypoint. Returns rows upserted."""
    settings = get_settings()
    path = db_path or _db_path_from_settings(settings.database_url)
    resolved = seasons or [nfl_season_start_year(datetime.now(tz=UTC).date())]
    n = run(seasons=resolved, db_path=path)
    print(f"upserted {n} NFL player-week rows (seasons {resolved}) -> {path}")
    return n


__all__ = ["main", "run"]
