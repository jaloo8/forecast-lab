"""Tests for the NDFD/NBM forecast repository."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from kq.clients.ndfd import DETERMINISTIC_SOURCE, NbmDeterministicForecast
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.ndfd import fetch_ndfd_forecasts, insert_ndfd_forecasts


def _row(
    *,
    as_of: datetime = datetime(2026, 4, 28),
    station: str = "KJFK",
    valid_date: date = date(2026, 4, 29),
    lead_days: int = 1,
    forecast_max_f: float = 60.0,
    source: str = DETERMINISTIC_SOURCE,
    p10: float | None = None,
    p50: float | None = None,
    p90: float | None = None,
) -> NbmDeterministicForecast:
    return NbmDeterministicForecast(
        as_of=as_of,
        station=station,
        valid_date=valid_date,
        lead_days=lead_days,
        forecast_max_f=forecast_max_f,
        source=source,
        p10_max_f=p10,
        p50_max_f=p50,
        p90_max_f=p90,
    )


def _setup_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "ndfd.duckdb"
    bootstrap(db_path)
    return db_path


def test_insert_returns_count(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    con = connect(db_path)
    try:
        n = insert_ndfd_forecasts(
            con,
            [
                _row(),
                _row(station="KLAX", valid_date=date(2026, 4, 30)),
            ],
        )
        assert n == 2
    finally:
        con.close()


def test_insert_idempotent_on_pk(tmp_path: Path) -> None:
    """Re-inserting the same (as_of, source, station, valid_date) overwrites."""
    db_path = _setup_db(tmp_path)
    con = connect(db_path)
    try:
        insert_ndfd_forecasts(con, [_row(forecast_max_f=60.0)])
        # Re-insert with same PK but updated forecast — should not duplicate.
        insert_ndfd_forecasts(con, [_row(forecast_max_f=62.5)])
        rows = fetch_ndfd_forecasts(con)
        assert len(rows) == 1
        assert rows[0]["forecast_max_f"] == 62.5
    finally:
        con.close()


def test_deterministic_and_qmd_rows_coexist(tmp_path: Path) -> None:
    """`source` is part of the PK so the qmd upgrade lands without conflict."""
    db_path = _setup_db(tmp_path)
    con = connect(db_path)
    try:
        # Same (as_of, station, valid_date) but different `source` → both rows kept.
        insert_ndfd_forecasts(
            con,
            [
                _row(source="nbm_deterministic_openmeteo", forecast_max_f=60.0),
                _row(
                    source="nbm_qmd_s3",
                    forecast_max_f=60.5,
                    p10=55.0,
                    p50=60.5,
                    p90=66.0,
                ),
            ],
        )
        det = fetch_ndfd_forecasts(con, source="nbm_deterministic_openmeteo")
        qmd = fetch_ndfd_forecasts(con, source="nbm_qmd_s3")
        assert len(det) == 1 and det[0]["p10_max_f"] is None
        assert len(qmd) == 1 and qmd[0]["p10_max_f"] == 55.0
    finally:
        con.close()


def test_fetch_filters_by_station_and_dates(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    con = connect(db_path)
    try:
        insert_ndfd_forecasts(
            con,
            [
                _row(station="KJFK", valid_date=date(2026, 4, 28)),
                _row(station="KJFK", valid_date=date(2026, 4, 29)),
                _row(station="KJFK", valid_date=date(2026, 4, 30)),
                _row(station="KLAX", valid_date=date(2026, 4, 29)),
            ],
        )
        # station filter
        jfk = fetch_ndfd_forecasts(con, station="KJFK")
        assert {r["station"] for r in jfk} == {"KJFK"}
        assert len(jfk) == 3
        # date window
        narrow = fetch_ndfd_forecasts(
            con,
            station="KJFK",
            start_date=date(2026, 4, 29),
            end_date=date(2026, 4, 29),
        )
        assert len(narrow) == 1
        assert narrow[0]["valid_date"] == date(2026, 4, 29)
    finally:
        con.close()


def test_fetch_lead_days_default_filters_to_one(tmp_path: Path) -> None:
    """The default ``lead_days=1`` is the operational backtest join shape."""
    db_path = _setup_db(tmp_path)
    con = connect(db_path)
    try:
        insert_ndfd_forecasts(
            con,
            [
                _row(lead_days=0, valid_date=date(2026, 4, 28)),
                _row(lead_days=1, valid_date=date(2026, 4, 29)),
                _row(lead_days=2, valid_date=date(2026, 4, 30)),
            ],
        )
        defaulted = fetch_ndfd_forecasts(con)
        assert len(defaulted) == 1
        assert defaulted[0]["lead_days"] == 1

        all_leads = fetch_ndfd_forecasts(con, lead_days=None)
        assert len(all_leads) == 3
    finally:
        con.close()
