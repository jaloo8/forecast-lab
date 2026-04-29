"""End-to-end test for the weather training flow.

Seeds a tmp DuckDB with synthetic forecast + observed rows for two stations,
runs `train_all`, and checks the manifest + per-station artifacts.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np

from kq.flows.train_weather import (
    DEFAULT_INITIAL_TRAIN,
    DEFAULT_TEST_WINDOW,
    MIN_TRAIN_SAMPLES,
    train_all,
)
from kq.storage.duckdb_store import bootstrap

AS_OF = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _seed_pair(
    con: duckdb.DuckDBPyConnection,
    *,
    station: str,
    start: date,
    n_days: int,
    a: float,
    b: float,
    noise_std: float,
    seed: int,
) -> None:
    """Seed a forecast row + observed row per day with synthetic bias `a + b*x`."""
    rng = np.random.default_rng(seed)
    forecasts = rng.normal(70.0, 10.0, size=n_days)
    observed = a + b * forecasts + rng.normal(0.0, noise_std, size=n_days)
    for i in range(n_days):
        vd = start + timedelta(days=i)
        # Backdate as_of so that lead_days = 1 (forecast pulled the day before).
        as_of_for_row = datetime(vd.year, vd.month, vd.day, 12, 0, tzinfo=UTC) - timedelta(days=1)
        f_hi = float(forecasts[i])
        f_lo = f_hi - 15.0
        con.execute(
            """
            INSERT OR REPLACE INTO weather_forecast
            (as_of, run_time, model, member, station, valid_date,
             forecast_high_f, forecast_low_f)
            VALUES (?, ?, 'gfs_hist', 0, ?, ?, ?, ?)
            """,
            (as_of_for_row, as_of_for_row, station, vd, f_hi, f_lo),
        )
        con.execute(
            """
            INSERT OR REPLACE INTO weather_observed
            (station, valid_date, high_f, low_f, source, fetched_at)
            VALUES (?, ?, ?, ?, 'test', ?)
            """,
            (station, vd, float(observed[i]), float(observed[i] - 15), AS_OF),
        )


def test_train_all_full_path(tmp_path: Path) -> None:
    db = tmp_path / "train.duckdb"
    bootstrap(db)
    con = duckdb.connect(str(db))
    try:
        # 100 days each — well over MIN_TRAIN_SAMPLES + initial_train + test_window
        _seed_pair(
            con,
            station="KAUS",
            start=date(2025, 1, 1),
            n_days=100,
            a=2.0,
            b=1.0,
            noise_std=2.0,
            seed=1,
        )
        _seed_pair(
            con,
            station="KLAX",
            start=date(2025, 1, 1),
            n_days=100,
            a=-1.0,
            b=1.0,
            noise_std=1.5,
            seed=2,
        )
    finally:
        con.close()

    manifest = train_all(db_path=db, output_dir=tmp_path / "models")

    assert manifest["lead_days"] == 1
    assert "KAUS" in manifest["stations"]
    assert "KLAX" in manifest["stations"]

    for station_record in manifest["stations"].values():
        assert station_record["status"] == "fit"
        assert station_record["n_samples"] >= MIN_TRAIN_SAMPLES
        assert station_record["cv"]["n_folds"] > 0
        assert "params" in station_record
        params = station_record["params"]
        assert all(params[k] is not None for k in ("a", "b", "c"))
        assert station_record["pickle"].endswith(".pkl")

    # Pickles + manifest exist on disk
    assert (tmp_path / "models" / "manifest.json").is_file()
    assert (tmp_path / "models" / "weather_ngr_KAUS_lead1.pkl").is_file()
    assert (tmp_path / "models" / "weather_ngr_KLAX_lead1.pkl").is_file()


def test_skips_thin_data(tmp_path: Path) -> None:
    db = tmp_path / "thin.duckdb"
    bootstrap(db)
    con = duckdb.connect(str(db))
    try:
        # Only 5 days — way below MIN_TRAIN_SAMPLES
        _seed_pair(
            con,
            station="KMIA",
            start=date(2025, 1, 1),
            n_days=5,
            a=1.0,
            b=1.0,
            noise_std=1.0,
            seed=3,
        )
    finally:
        con.close()

    manifest = train_all(db_path=db, output_dir=tmp_path / "models")
    assert manifest["stations"]["KMIA"]["status"] == "skipped_thin_data"
    # No pickle should be written for skipped stations
    assert not (tmp_path / "models" / "weather_ngr_KMIA_lead1.pkl").exists()


def test_no_data_writes_no_data_manifest(tmp_path: Path) -> None:
    db = tmp_path / "empty.duckdb"
    bootstrap(db)
    manifest = train_all(db_path=db, output_dir=tmp_path / "models")
    assert manifest["status"] == "no_data"
    assert manifest["stations"] == {}


def test_constants_self_check() -> None:
    """Cheap belt-and-suspenders to keep the manifest defaults coherent."""
    assert MIN_TRAIN_SAMPLES <= DEFAULT_INITIAL_TRAIN
    assert DEFAULT_TEST_WINDOW > 0
