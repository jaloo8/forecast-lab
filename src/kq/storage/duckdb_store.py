"""DuckDB connection factory and schema bootstrap.

Domain-specific inserters live under `kq.storage.repositories.*`. Keeping
this module small makes ownership obvious: connect/bootstrap is shared
infrastructure, repositories own their tables.
"""

from __future__ import annotations

import time
from pathlib import Path

import duckdb

SCHEMA_PATH = Path(__file__).parent / "schemas.sql"

# DuckDB holds a single-writer file lock. Two cron flows landing on the same
# tick (e.g. the every-minute Kalshi ingest vs the daily paper pass) collide
# transiently — a couple of short retries absorbs that without masking a
# genuinely wedged writer.
LOCK_RETRIES: int = 3
LOCK_BACKOFF_S: float = 0.25


def is_lock_conflict(exc: BaseException) -> bool:
    """True when ``exc`` is DuckDB's file-lock conflict (another process holds
    the lock) — the transient "busy, retry next tick" class, distinct from a
    missing or corrupt database file."""
    return isinstance(exc, duckdb.IOException) and "lock" in str(exc).lower()


def connect(
    db_path: Path,
    *,
    read_only: bool = False,
    lock_retries: int = LOCK_RETRIES,
    lock_backoff_s: float = LOCK_BACKOFF_S,
) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection at `db_path`.

    ``read_only=True`` opens with ``duckdb.connect(..., read_only=True)`` and
    NEVER creates a database: a nonexistent path raises instead of silently
    materializing an empty file (the 2026-07-01 audit's doctor finding —
    read-only consumers like `kq doctor`, `kq health-check`, and the dashboard
    must observe, not create). Read-only connections also don't block the
    cron writers.

    Lock conflicts (another process mid-write) are retried ``lock_retries``
    times with a short linear backoff before the ``duckdb.IOException``
    propagates; callers that want "busy" semantics can test the final error
    with :func:`is_lock_conflict`.
    """
    if not read_only:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    attempts = max(1, lock_retries)
    for attempt in range(attempts):
        try:
            return duckdb.connect(str(db_path), read_only=read_only)
        except duckdb.IOException as exc:
            if not is_lock_conflict(exc) or attempt == attempts - 1:
                raise
            time.sleep(lock_backoff_s * (attempt + 1))
    raise AssertionError("unreachable")  # pragma: no cover


# Idempotent column-type migrations for databases created before a schema
# change. CREATE TABLE IF NOT EXISTS never alters existing tables, so a
# re-run of bootstrap is the documented upgrade path; each statement here
# must be a no-op when the column already has the target type.
_MIGRATIONS: tuple[str, ...] = (
    # 2026-06-11 PR-A: Kalshi prod has fractional trading -- orderbook sizes
    # like 4985.18 are real. INTEGER columns would round them silently.
    "ALTER TABLE kalshi_book_snap ALTER COLUMN yes_bid_size SET DATA TYPE DOUBLE",
    "ALTER TABLE kalshi_book_snap ALTER COLUMN yes_ask_size SET DATA TYPE DOUBLE",
    # 2026-06-11 PR-A: persist prod strike semantics so settlement (PR-B)
    # reads point-in-time contract terms from the DB, never ticker text.
    "ALTER TABLE kalshi_market ADD COLUMN IF NOT EXISTS strike_type VARCHAR",
    "ALTER TABLE kalshi_market ADD COLUMN IF NOT EXISTS floor_strike DOUBLE",
    "ALTER TABLE kalshi_market ADD COLUMN IF NOT EXISTS cap_strike DOUBLE",
    # 2026-07-01 PR-B: capture strike semantics on the trade itself at submit
    # time — settlement must never re-derive contract terms from ticker text.
    "ALTER TABLE paper_trade ADD COLUMN IF NOT EXISTS strike_type VARCHAR",
    "ALTER TABLE paper_trade ADD COLUMN IF NOT EXISTS floor_strike DOUBLE",
    "ALTER TABLE paper_trade ADD COLUMN IF NOT EXISTS cap_strike DOUBLE",
    # 2026-07-01 P1: deterministic (HRRR/GFS) rows use member = -1 sentinel;
    # PK forbids NULL, so the old "NULL for deterministic" was unimplementable.
    "ALTER TABLE weather_forecast ALTER COLUMN member SET DEFAULT -1",
    # 2026-07-02 Phase B (NFL lane): nfl_game / nfl_odds / nfl_game_crosswalk
    # are NEW tables — their idempotent migration IS the CREATE TABLE IF NOT
    # EXISTS in schemas.sql, which bootstrap() re-runs on every call (same
    # path the NBA tables took). No ALTER entries needed here.
    # 2026-07-02 Phase C (index-brackets lane): index_daily is a NEW table —
    # same CREATE TABLE IF NOT EXISTS migration path. No ALTER entries needed.
    # 2026-07-27 Fantasy F1a: nfl_player_game / nfl_player_projection are NEW
    # tables — same CREATE TABLE IF NOT EXISTS migration path. No ALTER
    # entries needed.
)


def bootstrap(db_path: Path) -> None:
    """Create all tables from schemas.sql if they don't exist, then apply
    idempotent column migrations for pre-existing databases."""
    con = connect(db_path)
    try:
        con.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
        for stmt in _MIGRATIONS:
            con.execute(stmt)
    finally:
        con.close()
