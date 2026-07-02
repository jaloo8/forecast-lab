"""Tests for weather feature engineering + training-set join."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import polars as pl
import pytest

from kq.clients.openmeteo._types import EnsembleForecast
from kq.features.weather import (
    FEATURE_COLUMNS,
    build_ensemble_features,
    build_training_set,
    dedup_one_per_station_day,
)
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.forecasts import insert_forecasts

AS_OF = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)
RUN_TIME = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)


def _ens_row(
    *,
    member: int,
    valid_date: date,
    high: float = 75.0,
    low: float | None = None,
    station: str = "KLAX",
    model: str = "gefs",
    as_of: datetime = AS_OF,
) -> EnsembleForecast:
    return EnsembleForecast(
        as_of=as_of,
        run_time=RUN_TIME,
        model=model,
        member=member,
        station=station,
        valid_date=valid_date,
        forecast_high_f=high,
        forecast_low_f=low if low is not None else high - 15,
    )


def _seed(con: duckdb.DuckDBPyConnection, rows: Sequence[EnsembleForecast]) -> None:
    insert_forecasts(con, rows)


def _seed_observed(
    con: duckdb.DuckDBPyConnection,
    *,
    station: str,
    valid_date: date,
    high_f: float | None,
    low_f: float | None = 60.0,
) -> None:
    con.execute(
        "INSERT INTO weather_observed "
        "(station, valid_date, high_f, low_f, source, fetched_at) "
        "VALUES (?, ?, ?, ?, 'test', ?)",
        (station, valid_date, high_f, low_f, AS_OF),
    )


def test_features_schema_is_stable(tmp_path: Path) -> None:
    db = tmp_path / "f.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        _seed(
            con,
            [
                _ens_row(member=0, valid_date=date(2025, 6, 1), high=74.0),
                _ens_row(member=1, valid_date=date(2025, 6, 1), high=76.0),
            ],
        )
        features = build_ensemble_features(con)
    finally:
        con.close()
    assert list(features.columns) == list(FEATURE_COLUMNS)


def test_features_aggregate_correctly(tmp_path: Path) -> None:
    """Mean / std / min / max / range match hand-computed values."""
    db = tmp_path / "g.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        highs = [70.0, 72.0, 74.0, 76.0, 78.0]  # 5 members
        _seed(
            con,
            [
                _ens_row(member=i, valid_date=date(2025, 6, 1), high=hi)
                for i, hi in enumerate(highs)
            ],
        )
        features = build_ensemble_features(con)
    finally:
        con.close()
    assert features.height == 1
    row = features.row(0, named=True)
    assert row["member_count"] == 5
    assert row["ens_mean_high_f"] == pytest.approx(74.0)
    assert row["ens_min_high_f"] == pytest.approx(70.0)
    assert row["ens_max_high_f"] == pytest.approx(78.0)
    assert row["ens_range_high_f"] == pytest.approx(8.0)
    # Sample stddev of [70,72,74,76,78] = sqrt(10) ≈ 3.162
    assert row["ens_std_high_f"] == pytest.approx(3.162, abs=0.01)
    # Median of 5 values is the middle value
    assert row["ens_q50_high_f"] == pytest.approx(74.0)


def test_deterministic_single_member_std_is_zero(tmp_path: Path) -> None:
    """Historical 'gfs_prevday1' rows have a single member — std must be 0, not None."""
    db = tmp_path / "h.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        _seed(
            con,
            [
                _ens_row(
                    member=0,
                    valid_date=date(2025, 6, 1),
                    high=75.0,
                    model="gfs_prevday1",
                ),
            ],
        )
        features = build_ensemble_features(con)
    finally:
        con.close()
    row = features.row(0, named=True)
    assert row["member_count"] == 1
    assert row["ens_mean_high_f"] == pytest.approx(75.0)
    assert row["ens_std_high_f"] == pytest.approx(0.0)
    assert row["ens_range_high_f"] == pytest.approx(0.0)


def test_filters_by_station_date_model(tmp_path: Path) -> None:
    db = tmp_path / "i.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        _seed(
            con,
            [
                _ens_row(member=0, valid_date=date(2025, 6, 1), station="KLAX"),
                _ens_row(member=0, valid_date=date(2025, 6, 1), station="KJFK"),
                _ens_row(member=0, valid_date=date(2025, 6, 2), station="KLAX"),
                _ens_row(
                    member=0,
                    valid_date=date(2025, 6, 1),
                    station="KLAX",
                    model="ecmwf",
                ),
            ],
        )
        lax_only = build_ensemble_features(con, stations=["KLAX"])
        jun1_only = build_ensemble_features(
            con, start_date=date(2025, 6, 1), end_date=date(2025, 6, 1)
        )
        gefs_only = build_ensemble_features(con, models=["gefs"])
    finally:
        con.close()
    assert lax_only.height == 3  # KLAX: 2 dates + 2 models, KJFK excluded
    assert jun1_only.height == 3  # 3 rows on 2025-06-01 across stations/models
    assert gefs_only.height == 3  # excludes the ecmwf row


def test_members_with_null_highs_not_counted(tmp_path: Path) -> None:
    """`COUNT(forecast_high_f)` treats NULL as not-a-member for aggregation."""
    db = tmp_path / "j.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        _seed(
            con,
            [
                _ens_row(member=0, valid_date=date(2025, 6, 1), high=75.0),
                EnsembleForecast(
                    as_of=AS_OF,
                    run_time=RUN_TIME,
                    model="gefs",
                    member=1,
                    station="KLAX",
                    valid_date=date(2025, 6, 1),
                    forecast_high_f=None,  # non-reporting member
                    forecast_low_f=None,
                ),
            ],
        )
        features = build_ensemble_features(con)
    finally:
        con.close()
    assert features.height == 1
    assert features.row(0, named=True)["member_count"] == 1


def test_training_set_joins_and_computes_residual(tmp_path: Path) -> None:
    db = tmp_path / "k.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        # forecast for 2025-06-01, mean high 74.0
        _seed(
            con,
            [
                _ens_row(
                    member=0,
                    valid_date=date(2025, 6, 1),
                    high=73.0,
                    as_of=datetime(2025, 5, 31, 12, 0, tzinfo=UTC),
                ),
                _ens_row(
                    member=1,
                    valid_date=date(2025, 6, 1),
                    high=75.0,
                    as_of=datetime(2025, 5, 31, 12, 0, tzinfo=UTC),
                ),
            ],
        )
        _seed_observed(con, station="KLAX", valid_date=date(2025, 6, 1), high_f=77.0)

        training = build_training_set(con)
    finally:
        con.close()
    assert training.height == 1
    row = training.row(0, named=True)
    assert row["observed_high_f"] == pytest.approx(77.0)
    assert row["ens_mean_high_f"] == pytest.approx(74.0)
    assert row["residual_high_f"] == pytest.approx(3.0)
    assert row["lead_days"] == 1  # 2025-06-01 vs 2025-05-31


def test_training_set_drops_unobserved_rows(tmp_path: Path) -> None:
    """Forecasts without a matching observation are not in the training set."""
    db = tmp_path / "l.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        _seed(
            con,
            [
                _ens_row(member=0, valid_date=date(2025, 6, 1), high=74.0),
                _ens_row(member=0, valid_date=date(2025, 6, 2), high=70.0),
            ],
        )
        # only observe one of the two days
        _seed_observed(con, station="KLAX", valid_date=date(2025, 6, 1), high_f=77.0)

        training = build_training_set(con)
    finally:
        con.close()
    assert training.height == 1
    assert training.row(0, named=True)["valid_date"] == date(2025, 6, 1)


def test_training_set_empty_when_no_data(tmp_path: Path) -> None:
    db = tmp_path / "m.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        empty = build_training_set(con)
    finally:
        con.close()
    assert empty.is_empty()
    # Must still expose the extra columns for schema stability downstream.
    assert "lead_days" in empty.columns
    assert "observed_high_f" in empty.columns
    assert "residual_high_f" in empty.columns


def test_observations_with_null_high_excluded(tmp_path: Path) -> None:
    """ACIS returns 'M' as None — those rows must not enter the training set."""
    db = tmp_path / "n.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        _seed(
            con,
            [
                _ens_row(member=0, valid_date=date(2025, 6, 1), high=74.0),
                _ens_row(member=0, valid_date=date(2025, 6, 2), high=70.0),
            ],
        )
        _seed_observed(con, station="KLAX", valid_date=date(2025, 6, 1), high_f=77.0)
        _seed_observed(con, station="KLAX", valid_date=date(2025, 6, 2), high_f=None)

        training = build_training_set(con)
    finally:
        con.close()
    assert training.height == 1
    assert training.row(0, named=True)["valid_date"] == date(2025, 6, 1)


def test_lead_days_counts_station_local_standard_days(tmp_path: Path) -> None:
    """PR-F (2026-06-11 audit #8): contracts settle on LST days, so leads
    count LST days. At KLAX (UTC-8), 07:00 UTC on the valid date itself is
    23:00 LST the *evening before* → lead 1. Noon UTC on the valid date is
    04:00 LST the same local day → lead 0. The UTC-date convention would
    call both of these lead 0."""
    db = tmp_path / "lst.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        _seed(
            con,
            [
                # 2025-06-01T07:00Z = 2025-05-31 23:00 LST → lead 1.
                _ens_row(
                    member=0,
                    valid_date=date(2025, 6, 1),
                    as_of=datetime(2025, 6, 1, 7, 0, tzinfo=UTC),
                ),
                # 2025-06-01T12:00Z = 2025-06-01 04:00 LST → lead 0.
                _ens_row(
                    member=0,
                    valid_date=date(2025, 6, 1),
                    model="ecmwf",
                    as_of=datetime(2025, 6, 1, 12, 0, tzinfo=UTC),
                ),
            ],
        )
        _seed_observed(con, station="KLAX", valid_date=date(2025, 6, 1), high_f=77.0)
        training = build_training_set(con)
    finally:
        con.close()
    leads = {row["model"]: row["lead_days"] for row in training.iter_rows(named=True)}
    assert leads["gefs"] == 1
    assert leads["ecmwf"] == 0


def test_lead_days_unknown_station_falls_back_to_utc(tmp_path: Path) -> None:
    """Stations no longer in STATIONS_BY_ICAO (e.g. pre-PR-C KJFK rows in an
    old DB) keep a well-defined UTC-day lead instead of erroring."""
    db = tmp_path / "legacy.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        _seed(
            con,
            [
                _ens_row(
                    member=0,
                    valid_date=date(2025, 6, 1),
                    station="KJFK",
                    as_of=datetime(2025, 5, 31, 23, 0, tzinfo=UTC),
                ),
            ],
        )
        _seed_observed(con, station="KJFK", valid_date=date(2025, 6, 1), high_f=77.0)
        training = build_training_set(con)
    finally:
        con.close()
    assert training.row(0, named=True)["lead_days"] == 1  # UTC-date fallback


# ------------------------------------------------- dedup_one_per_station_day


def _frame(rows: list[dict[str, object]]) -> pl.DataFrame:
    return pl.DataFrame(rows)


def test_dedup_keeps_freshest_as_of_per_station_day() -> None:
    df = _frame(
        [
            {
                "station": "KLAX",
                "valid_date": date(2025, 6, 1),
                "as_of": datetime(2025, 5, 31, 6),
                "model": "gefs",
                "x": 1,
            },
            {
                "station": "KLAX",
                "valid_date": date(2025, 6, 1),
                "as_of": datetime(2025, 5, 31, 18),
                "model": "gefs",
                "x": 2,
            },
            {
                "station": "KLAX",
                "valid_date": date(2025, 6, 2),
                "as_of": datetime(2025, 6, 1, 6),
                "model": "gefs",
                "x": 3,
            },
        ]
    )
    out = dedup_one_per_station_day(df)
    assert out.height == 2
    assert out.filter(pl.col("valid_date") == date(2025, 6, 1))["x"].to_list() == [2]


def test_dedup_tie_breaks_on_model_name_deterministically() -> None:
    df = _frame(
        [
            {
                "station": "KLAX",
                "valid_date": date(2025, 6, 1),
                "as_of": datetime(2025, 5, 31, 12),
                "model": "gefs",
            },
            {
                "station": "KLAX",
                "valid_date": date(2025, 6, 1),
                "as_of": datetime(2025, 5, 31, 12),
                "model": "ecmwf",
            },
        ]
    )
    out = dedup_one_per_station_day(df)
    assert out.height == 1
    assert out["model"].to_list() == ["ecmwf"]  # ascending name tie-break


def test_dedup_preserves_distinct_stations() -> None:
    df = _frame(
        [
            {
                "station": "KLAX",
                "valid_date": date(2025, 6, 1),
                "as_of": datetime(2025, 5, 31, 12),
                "model": "gefs",
            },
            {
                "station": "KMIA",
                "valid_date": date(2025, 6, 1),
                "as_of": datetime(2025, 5, 31, 12),
                "model": "gefs",
            },
        ]
    )
    out = dedup_one_per_station_day(df)
    assert out.height == 2


def test_dedup_requires_key_columns() -> None:
    with pytest.raises(ValueError, match="missing columns"):
        dedup_one_per_station_day(pl.DataFrame({"station": ["KLAX"]}))


def test_training_set_returns_polars_dataframe(tmp_path: Path) -> None:
    db = tmp_path / "o.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        training = build_training_set(con)
    finally:
        con.close()
    assert isinstance(training, pl.DataFrame)
