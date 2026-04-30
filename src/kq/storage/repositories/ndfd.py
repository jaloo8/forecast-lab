"""NDFD/NBM benchmark forecast repository."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date as date_t
from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    from kq.clients.ndfd import NbmDeterministicForecast


_INSERT_SQL = """
INSERT OR REPLACE INTO ndfd_forecast (
    as_of, station, valid_date, lead_days, source,
    forecast_max_f,
    p10_max_f, p25_max_f, p50_max_f, p75_max_f, p90_max_f
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def insert_ndfd_forecasts(
    con: duckdb.DuckDBPyConnection,
    rows: Iterable[NbmDeterministicForecast],
) -> int:
    """Insert NDFD/NBM forecast rows; returns count inserted.

    Idempotent on (as_of, source, station, valid_date). Re-running with the
    same rows overwrites in place — matches the existing `insert_observed`
    pattern so backfill + live ingest can re-run safely.
    """
    batch: list[Sequence[object]] = [
        (
            r.as_of,
            r.station,
            r.valid_date,
            r.lead_days,
            r.source,
            r.forecast_max_f,
            r.p10_max_f,
            r.p25_max_f,
            r.p50_max_f,
            r.p75_max_f,
            r.p90_max_f,
        )
        for r in rows
    ]
    if not batch:
        return 0
    con.executemany(_INSERT_SQL, batch)
    return len(batch)


def fetch_ndfd_forecasts(
    con: duckdb.DuckDBPyConnection,
    *,
    station: str | None = None,
    start_date: date_t | None = None,
    end_date: date_t | None = None,
    lead_days: int | None = 1,
    source: str = "nbm_deterministic_openmeteo",
) -> list[dict[str, object]]:
    """Query NDFD rows, returning a list of dicts (one per row).

    Defaults to ``lead_days=1`` and the v1 deterministic source — the join
    shape PR 2's backtest engine consumes. Pass ``lead_days=None`` to skip
    that filter (e.g., for the operational CLV log).
    """
    where: list[str] = ["source = ?"]
    params: list[object] = [source]
    if station is not None:
        where.append("station = ?")
        params.append(station)
    if start_date is not None:
        where.append("valid_date >= ?")
        params.append(start_date)
    if end_date is not None:
        where.append("valid_date <= ?")
        params.append(end_date)
    if lead_days is not None:
        where.append("lead_days = ?")
        params.append(lead_days)
    sql = f"""
        SELECT as_of, station, valid_date, lead_days, source,
               forecast_max_f, p10_max_f, p25_max_f, p50_max_f, p75_max_f, p90_max_f
        FROM ndfd_forecast
        WHERE {" AND ".join(where)}
        ORDER BY station, valid_date, as_of
    """
    cur = con.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
