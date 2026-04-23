"""Initialize the DuckDB analytics database from `src/kq/storage/schemas.sql`."""

from __future__ import annotations

from pathlib import Path

from kq.config import get_settings
from kq.storage.duckdb_store import bootstrap


def main() -> None:
    settings = get_settings()
    db_url = settings.database_url
    prefix = "duckdb:///"
    if not db_url.startswith(prefix):
        raise SystemExit(f"Expected database_url to start with {prefix!r}, got {db_url!r}")
    db_path = Path(db_url.removeprefix(prefix))
    bootstrap(db_path)
    print(f"[bootstrap] DuckDB initialized at {db_path}")


if __name__ == "__main__":
    main()
