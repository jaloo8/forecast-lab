"""Tests for per-station lead-1 calibration.

The defect being fixed, measured 2026-07-29 on 14,599 true lead-1 station-days:
the raw ensemble mean is systematically COLD (pooled bias +1.78F, every station
but KLAX positive) and its realised spread is 2.55F where the raw pricing path
assumed a flat 3.5F. On 2F-wide Kalshi brackets that displaces almost a whole
bracket of probability mass.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pytest

from kq.models.raw_forecast import RawForecastModel
from kq.models.station_calibration import (
    MIN_PAIRS,
    StationCalibration,
    fit_station_calibrations,
    load_calibrations,
    write_manifest,
)
from kq.storage.duckdb_store import bootstrap


def _seed(db: Path, station: str, *, n_days: int, bias: float, spread: float) -> None:
    """Write n_days of lead-1 forecasts whose error has a known bias/spread."""
    bootstrap(db)
    rng = np.random.default_rng(1234)
    con = duckdb.connect(str(db))
    try:
        start = date(2025, 1, 1)
        for i in range(n_days):
            vd = start + timedelta(days=i)
            fc = 70.0
            obs = fc + bias + float(rng.normal(0.0, spread))
            # Naive UTC, matching how the repo normalises stored timestamps —
            # a tz-aware value shifts CAST(as_of AS DATE) and breaks the
            # exact-lead-1 filter the fitter relies on.
            as_of = datetime(vd.year, vd.month, vd.day, 12, 0) - timedelta(days=1)
            # The LIVE models production prices with, at genuine lead-1.
            # Fitting on the *_prevday1 archive instead made live Brier WORSE
            # (0.1680 -> 0.1902 on 201 settled markets, 2026-07-29): the archive
            # runs ~1.8F cold while the live feed is near-unbiased. See the
            # module header in kq.models.station_calibration.
            for m_idx, model in enumerate(("ecmwf", "gefs")):
                con.execute(
                    "INSERT INTO weather_forecast "
                    "(as_of, run_time, model, member, station, valid_date, "
                    " forecast_high_f, forecast_low_f) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [as_of, as_of, model, m_idx, station, vd, fc, fc - 20.0],
                )
            con.execute(
                "INSERT INTO weather_observed (station, valid_date, high_f, low_f, fetched_at) "
                "VALUES (?, ?, ?, ?, now())",
                [station, vd, obs, obs - 20.0],
            )
    finally:
        con.close()


def test_fit_recovers_a_known_bias(tmp_path: Path) -> None:
    db = tmp_path / "c.duckdb"
    _seed(db, "KATL", n_days=300, bias=3.0, spread=2.0)

    cals, fitted_through = fit_station_calibrations(db)

    assert "KATL" in cals
    cal = cals["KATL"]
    assert cal.usable
    assert cal.n_pairs == 300
    # The whole point: a systematic warm error must be recovered, not averaged away.
    assert cal.bias_f == pytest.approx(3.0, abs=0.35)
    assert cal.sigma_f == pytest.approx(2.0, abs=0.35)
    assert fitted_through is not None


def test_thin_history_is_marked_unusable_not_invented(tmp_path: Path) -> None:
    """Too little evidence must be reported as such, never as a confident number."""
    db = tmp_path / "c.duckdb"
    _seed(db, "KBOS", n_days=MIN_PAIRS - 10, bias=2.0, spread=2.0)

    cals, _ = fit_station_calibrations(db)

    assert cals["KBOS"].usable is False
    # ...and an unusable fit must never reach a consumer.
    path = write_manifest(cals, fitted_through=None, path=tmp_path / "m.json")
    assert load_calibrations(path) == {}


def test_manifest_roundtrip_only_exposes_usable(tmp_path: Path) -> None:
    cals = {
        "KATL": StationCalibration("KATL", 400, 3.0, 2.6, usable=True),
        "KBOS": StationCalibration("KBOS", 5, 9.9, 9.9, usable=False),
    }
    path = write_manifest(cals, fitted_through="2026-07-26", path=tmp_path / "m.json")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["fitted_through"] == "2026-07-26"
    assert payload["n_stations_usable"] == 1
    assert set(payload["stations"]) == {"KATL", "KBOS"}  # both recorded for audit

    loaded = load_calibrations(path)
    assert set(loaded) == {"KATL"}
    assert loaded["KATL"].bias_f == pytest.approx(3.0)


def test_missing_or_corrupt_manifest_degrades_quietly(tmp_path: Path) -> None:
    """A missing manifest must not break the trading path."""
    assert load_calibrations(tmp_path / "nope.json") == {}

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_calibrations(bad) == {}


def test_raw_model_applies_the_bias() -> None:
    """A cold forecast plus a measured warm bias must move the distribution."""
    uncorrected = RawForecastModel(raw_sigma_f=2.5)
    corrected = RawForecastModel(raw_sigma_f=2.5, bias_f=2.0)

    mu_u, sd_u = uncorrected.predict_distribution(70.0)
    mu_c, sd_c = corrected.predict_distribution(70.0)

    assert float(mu_u) == pytest.approx(70.0)
    assert float(mu_c) == pytest.approx(72.0)
    assert float(sd_u) == pytest.approx(float(sd_c))  # bias shifts location only

    # And it must change the traded quantity: P(high > 72) should rise.
    p_u = float(uncorrected.predict_proba(70.0, 72.0))
    p_c = float(corrected.predict_proba(70.0, 72.0))
    assert p_c > p_u


def test_raw_model_defaults_to_no_bias() -> None:
    """Backwards compatibility: every existing caller keeps the old behaviour."""
    assert RawForecastModel(raw_sigma_f=3.5).bias_f == 0.0
    a = RawForecastModel(raw_sigma_f=3.5)
    b = RawForecastModel(raw_sigma_f=3.5, bias_f=0.0)
    assert float(a.predict_proba(70.0, 72.0)) == pytest.approx(float(b.predict_proba(70.0, 72.0)))
