"""Tests for the GEFSv12 reforecast phase 2 ingest flow.

End-to-end test (network-dependent, marked ``integration``) verifies the
real S3 → cfgrib → DuckDB path against a single 2019 c00 file. Skipped by
default per ``pyproject.toml`` ``addopts``; opt in with ``-m integration``.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from pathlib import Path

import pytest

from kq.clients.gefs_reforecast import StationCoord, StationRecord, kelvin_to_fahrenheit
from kq.flows.pull_gefsv12_reforecasts import (
    DAY1_RECORD_NOS,
    MEMBER_INDEX_BY_NAME,
    REFORECAST_MODEL_TAG,
    IngestRow,
    _aggregate_day1_max,
    _build_ingest_rows,
    _insert_ingest_rows,
    _parse_cycle_to_datetime,
    _stations_to_coords,
    pull,
)
from kq.storage.duckdb_store import bootstrap, connect

# --------------------------- pure helpers ---------------------------


def test_parse_cycle_to_datetime_round_trip() -> None:
    """Cycle string YYYYMMDDHH parses to a naive UTC datetime."""
    dt = _parse_cycle_to_datetime("2019010100")
    assert dt == datetime(2019, 1, 1, 0)
    assert dt.tzinfo is None  # weather_forecast convention is naive UTC


def test_stations_to_coords_converts_longitude_to_e() -> None:
    """Station longitudes (West negative) get converted to GEFS 0-360 E."""
    coords = _stations_to_coords()
    assert len(coords) == 6
    by_icao = {c.icao: c for c in coords}
    # KNYC (Central Park since PR-C, audit root cause #4) at -73.9692 → 286.0308
    assert by_icao["KNYC"].longitude_e == pytest.approx(286.0308, abs=0.01)
    # KLAX at -118.4085 → 241.5915
    assert by_icao["KLAX"].longitude_e == pytest.approx(241.5915, abs=0.01)


def test_aggregate_day1_max_picks_largest_per_key() -> None:
    """7 records per (cycle, member, station) → keep the max."""
    records = [
        StationRecord("KAUS", "2019010100", "c00", 9, "24-27", 280.0),
        StationRecord("KAUS", "2019010100", "c00", 10, "27-30", 285.5),  # max
        StationRecord("KAUS", "2019010100", "c00", 11, "30-33", 282.0),
        StationRecord("KJFK", "2019010100", "c00", 9, "24-27", 270.0),
        StationRecord("KJFK", "2019010100", "c00", 10, "27-30", 271.0),
    ]
    result = _aggregate_day1_max(records)
    assert result[("2019010100", "c00", "KAUS")] == pytest.approx(285.5)
    assert result[("2019010100", "c00", "KJFK")] == pytest.approx(271.0)


def test_aggregate_handles_empty_input() -> None:
    assert _aggregate_day1_max([]) == {}


def test_build_ingest_rows_assigns_correct_valid_date() -> None:
    """valid_date = cycle_dt + 1 day (lead-day-1 convention)."""
    aggregated = {
        ("2019010100", "c00", "KAUS"): 295.0,  # 295 K = 71.33 F
    }
    rows = _build_ingest_rows(aggregated)
    assert len(rows) == 1
    r = rows[0]
    assert r.as_of == datetime(2019, 1, 1, 0)
    assert r.valid_date == datetime(2019, 1, 2, 0)
    assert r.member == 0  # c00 → 0
    assert r.station == "KAUS"
    assert r.forecast_high_f == pytest.approx(kelvin_to_fahrenheit(295.0))


def test_build_ingest_rows_unknown_member_dropped() -> None:
    """A member name not in MEMBER_INDEX_BY_NAME is silently dropped (with log)."""
    aggregated = {
        ("2019010100", "p99", "KAUS"): 295.0,  # p99 doesn't exist
        ("2019010100", "c00", "KAUS"): 290.0,
    }
    rows = _build_ingest_rows(aggregated)
    assert len(rows) == 1
    assert rows[0].member == 0  # only c00 survived


def test_member_index_by_name_complete() -> None:
    """All five GEFSv12 reforecast members are mapped."""
    assert MEMBER_INDEX_BY_NAME == {
        "c00": 0,
        "p01": 1,
        "p02": 2,
        "p03": 3,
        "p04": 4,
    }


def test_day1_record_nos_covers_24_to_48_hour_window() -> None:
    """Records 9..16 are the 8 three-hour windows from hour 24 to 48."""
    assert DAY1_RECORD_NOS == (9, 10, 11, 12, 13, 14, 15, 16)
    # Spot-check the count: 8 records of 3 hours = 24-hour daily window.
    assert len(DAY1_RECORD_NOS) == 8


# --------------------------- ingest persistence ---------------------------


def test_insert_ingest_rows_writes_to_weather_forecast(tmp_path: Path) -> None:
    """Rows land in weather_forecast with model='gefsv12_reforecast'."""
    db = tmp_path / "test_gefs.duckdb"
    bootstrap(db)
    rows = [
        IngestRow(
            as_of=datetime(2019, 1, 1, 0),
            run_time=datetime(2019, 1, 1, 0),
            member=0,
            station="KJFK",
            valid_date=datetime(2019, 1, 2, 0),
            forecast_high_f=42.3,
        ),
        IngestRow(
            as_of=datetime(2019, 1, 1, 0),
            run_time=datetime(2019, 1, 1, 0),
            member=1,
            station="KJFK",
            valid_date=datetime(2019, 1, 2, 0),
            forecast_high_f=43.1,
        ),
    ]
    con = connect(db)
    try:
        n = _insert_ingest_rows(con, rows)
        assert n == 2
        # Read back; verify model tag + forecasts.
        result = con.execute(
            """
            SELECT model, member, station, valid_date, forecast_high_f
            FROM weather_forecast
            WHERE model = ?
            ORDER BY member
            """,
            [REFORECAST_MODEL_TAG],
        ).fetchall()
        assert len(result) == 2
        assert result[0][0] == REFORECAST_MODEL_TAG
        assert result[0][1] == 0
        assert result[0][3] == date(2019, 1, 2)
        assert result[0][4] == pytest.approx(42.3)
        assert result[1][1] == 1
    finally:
        con.close()


def test_insert_idempotent_on_pk(tmp_path: Path) -> None:
    """Re-inserting the same (as_of, model, member, station, valid_date) overwrites."""
    db = tmp_path / "idempotent.duckdb"
    bootstrap(db)
    row_a = IngestRow(
        as_of=datetime(2019, 1, 1, 0),
        run_time=datetime(2019, 1, 1, 0),
        member=0,
        station="KAUS",
        valid_date=datetime(2019, 1, 2, 0),
        forecast_high_f=70.0,
    )
    row_b = IngestRow(
        as_of=datetime(2019, 1, 1, 0),
        run_time=datetime(2019, 1, 1, 0),
        member=0,
        station="KAUS",
        valid_date=datetime(2019, 1, 2, 0),
        forecast_high_f=72.5,  # corrected value
    )
    con = connect(db)
    try:
        _insert_ingest_rows(con, [row_a])
        _insert_ingest_rows(con, [row_b])
        result = con.execute(
            "SELECT forecast_high_f FROM weather_forecast WHERE model = ?",
            [REFORECAST_MODEL_TAG],
        ).fetchall()
        assert len(result) == 1
        assert result[0][0] == pytest.approx(72.5)
    finally:
        con.close()


def test_insert_empty_list_returns_zero(tmp_path: Path) -> None:
    db = tmp_path / "empty.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        assert _insert_ingest_rows(con, []) == 0
    finally:
        con.close()


def test_kelvin_to_fahrenheit_known_values() -> None:
    """Sanity check on temperature conversion used by the ingest."""
    assert kelvin_to_fahrenheit(273.15) == pytest.approx(32.0)
    assert kelvin_to_fahrenheit(295.0) == pytest.approx(71.33, abs=0.01)
    assert kelvin_to_fahrenheit(310.928) == pytest.approx(100.0, abs=0.01)


def test_station_coord_dataclass_immutable() -> None:
    sc = StationCoord(icao="KJFK", latitude=40.6413, longitude_e=286.2219)
    with pytest.raises(AttributeError):
        sc.icao = "KLAX"  # type: ignore[misc]


# --------------------------- integration (network-dependent) ---------------------------


@pytest.mark.integration
def test_full_pull_one_day_one_member_smoke(tmp_path: Path) -> None:
    """End-to-end: real S3 fetch + cfgrib parse + DB persist for ONE cycle.

    Skipped by default; opt in with ``pytest -m integration``. Runs in
    ~30 seconds. Validates the entire phase 2 pipeline against the real
    archive without committing the user to a multi-GB pull.
    """
    db = tmp_path / "smoke.duckdb"
    bootstrap(db)
    n_inserted = asyncio.run(
        pull(
            start_year=2019,
            end_year=2019,
            members=("c00",),
            max_days=1,  # single cycle
            max_concurrent=2,
            db_path=db,
        )
    )
    assert n_inserted == 6  # 6 stations from one (cycle, member)

    # Read-back: every station has a row with realistic Tmax values.
    con = connect(db)
    try:
        rows = con.execute(
            """
            SELECT station, forecast_high_f
            FROM weather_forecast
            WHERE model = ?
            ORDER BY station
            """,
            [REFORECAST_MODEL_TAG],
        ).fetchall()
    finally:
        con.close()
    assert len(rows) == 6
    # Sanity: Tmax in early-Jan US ranges roughly -30°F (KMDW winter) to +90°F (KMIA).
    for station, tmax_f in rows:
        assert -50 < tmax_f < 110, (station, tmax_f)
