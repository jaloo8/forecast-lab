"""DuckDB connection factory and schema bootstrap.

Domain-specific inserters live under `kq.storage.repositories.*`. Keeping
this module small makes ownership obvious: connect/bootstrap is shared
infrastructure, repositories own their tables.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

SCHEMA_PATH = Path(__file__).parent / "schemas.sql"


def connect(db_path: Path) -> duckdb.DuckDBPyConnection:
    """Open (or create) a DuckDB connection at `db_path`."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


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
