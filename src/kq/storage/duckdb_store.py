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


def bootstrap(db_path: Path) -> None:
    """Create all tables from schemas.sql if they don't exist. Idempotent."""
    con = connect(db_path)
    try:
        con.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    finally:
        con.close()
