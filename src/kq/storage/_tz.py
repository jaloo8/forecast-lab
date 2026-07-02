"""Naive-UTC datetime normalization for DuckDB binds.

DuckDB's TIMESTAMP columns store naive datetimes. When the Python driver is
handed a tz-aware value it converts it to the *host-local* wall clock and
silently drops the tzinfo — corrupting UTC values and mixing conventions in
one DB across hosts with different local timezones (2026-06-11 audit: the
Mac/WSL2 fleet). Every datetime bound into an INSERT/UPSERT must pass
through :func:`to_naive_utc` so the stored value matches the project's
"naive UTC" storage convention regardless of host timezone.
"""

from __future__ import annotations

from datetime import UTC, datetime


def to_naive_utc(dt: datetime) -> datetime:
    """Normalize tz-aware → naive UTC; pass naive through unchanged."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)


def to_naive_utc_optional(dt: datetime | None) -> datetime | None:
    """None-tolerant :func:`to_naive_utc` for nullable timestamp columns."""
    return None if dt is None else to_naive_utc(dt)
