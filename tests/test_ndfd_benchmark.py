"""Tests for the NDFD benchmark math + lookup loader."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import numpy as np
import pytest

from kq.backtest.ndfd_benchmark import (
    NdfdLookup,
    fit_residual_sigma,
    gaussian_exceedance,
    load_ndfd_lookup,
)
from kq.clients.ndfd import NbmDeterministicForecast
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.ndfd import insert_ndfd_forecasts

# --------------------------- fit_residual_sigma ---------------------------


def test_fit_residual_sigma_known_value() -> None:
    """Residuals = [-1, 0, 1, -1, 0, 1, ...] → sigma ≈ 1 (sample std)."""
    nbm = np.array([76.0, 75.0, 74.0, 76.0, 75.0, 74.0, 76.0, 75.0, 74.0, 76.0, 75.0])
    obs = np.array([75.0, 75.0, 75.0, 75.0, 75.0, 75.0, 75.0, 75.0, 75.0, 75.0, 75.0])
    # residuals = nbm - obs = [1, 0, -1, 1, 0, -1, 1, 0, -1, 1, 0]
    sigma = fit_residual_sigma(nbm, obs, sigma_floor=0.1)
    assert sigma is not None
    expected = float(np.std(nbm - obs, ddof=1))
    assert sigma == pytest.approx(expected)


def test_fit_residual_sigma_returns_none_when_too_few_pairs() -> None:
    nbm = np.array([76.0, np.nan, np.nan, 75.0])
    obs = np.array([75.0, 75.0, 74.0, 75.0])
    # Only 2 valid pairs vs default min_pairs=10.
    assert fit_residual_sigma(nbm, obs) is None


def test_fit_residual_sigma_drops_nan_on_either_side() -> None:
    """NaN in either NBM or observed disqualifies the row."""
    n = 20
    nbm = np.full(n, 75.0)
    obs = np.full(n, 75.0)
    nbm[0] = np.nan
    obs[1] = np.nan
    sigma = fit_residual_sigma(nbm, obs, min_pairs=5, sigma_floor=0.1)
    assert sigma is not None
    # 18 valid pairs all with residual 0 → std = 0, then floored to 0.1.
    assert sigma == pytest.approx(0.1)


def test_fit_residual_sigma_floor_applied() -> None:
    """Floor mirrors engine.py's market_sigma_f handling."""
    nbm = np.full(20, 75.0)
    obs = np.full(20, 75.0)  # all residuals = 0
    sigma = fit_residual_sigma(nbm, obs, sigma_floor=1.0)
    assert sigma == pytest.approx(1.0)


def test_fit_residual_sigma_shape_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="shape mismatch"):
        fit_residual_sigma(np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0]))


def test_fit_residual_sigma_all_nan_returns_none() -> None:
    nbm = np.full(20, np.nan)
    obs = np.full(20, 75.0)
    assert fit_residual_sigma(nbm, obs) is None


# --------------------------- gaussian_exceedance ---------------------------


def test_gaussian_exceedance_at_mean_is_half() -> None:
    assert gaussian_exceedance(mean=75.0, sigma=2.0, threshold=75.0) == pytest.approx(0.5)


def test_gaussian_exceedance_one_sigma_above() -> None:
    """P(X > mean + 1*sigma) approx 0.1587 for a Gaussian (pin to 4 decimals)."""
    p = gaussian_exceedance(mean=75.0, sigma=2.0, threshold=77.0)
    assert p == pytest.approx(0.1587, abs=1e-3)


def test_gaussian_exceedance_one_sigma_below() -> None:
    """P(X > mean - 1*sigma) approx 0.8413 for a Gaussian."""
    p = gaussian_exceedance(mean=75.0, sigma=2.0, threshold=73.0)
    assert p == pytest.approx(0.8413, abs=1e-3)


def test_gaussian_exceedance_clipped_at_high_end() -> None:
    """Threshold far below mean → P → 1, but clipped to 0.99."""
    assert gaussian_exceedance(mean=75.0, sigma=1.0, threshold=50.0) == pytest.approx(0.99)


def test_gaussian_exceedance_clipped_at_low_end() -> None:
    """Threshold far above mean → P → 0, but clipped to 0.01."""
    assert gaussian_exceedance(mean=75.0, sigma=1.0, threshold=100.0) == pytest.approx(0.01)


def test_gaussian_exceedance_rejects_nonpositive_sigma() -> None:
    with pytest.raises(ValueError, match="sigma"):
        gaussian_exceedance(mean=75.0, sigma=0.0, threshold=75.0)
    with pytest.raises(ValueError, match="sigma"):
        gaussian_exceedance(mean=75.0, sigma=-1.0, threshold=75.0)


# --------------------------- NdfdLookup ---------------------------


def test_ndfd_lookup_returns_empty_dict_for_missing_station() -> None:
    lookup = NdfdLookup(by_station={"KJFK": {date(2026, 4, 30): 60.0}})
    assert lookup.for_station("KJFK") == {date(2026, 4, 30): 60.0}
    # Missing station → empty dict, not KeyError.
    assert lookup.for_station("KZZZ") == {}


def test_ndfd_lookup_default_construction() -> None:
    lookup = NdfdLookup()
    assert lookup.for_station("KJFK") == {}


# --------------------------- load_ndfd_lookup ---------------------------


def _row(
    *,
    station: str,
    valid_date: date,
    forecast_max_f: float,
    as_of: datetime = datetime(2026, 4, 28),
    source: str = "nbm_deterministic_openmeteo",
    lead_days: int = 1,
) -> NbmDeterministicForecast:
    return NbmDeterministicForecast(
        as_of=as_of,
        station=station,
        valid_date=valid_date,
        lead_days=lead_days,
        forecast_max_f=forecast_max_f,
        source=source,
    )


def _setup_db(tmp_path: Path) -> Path:
    p = tmp_path / "ndfd_lookup.duckdb"
    bootstrap(p)
    return p


def test_load_ndfd_lookup_empty_db(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    con = connect(db)
    try:
        lookup = load_ndfd_lookup(con)
    finally:
        con.close()
    assert lookup.by_station == {}


def test_load_ndfd_lookup_groups_by_station(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    con = connect(db)
    try:
        insert_ndfd_forecasts(
            con,
            [
                _row(station="KJFK", valid_date=date(2025, 4, 1), forecast_max_f=58.0),
                _row(station="KJFK", valid_date=date(2025, 4, 2), forecast_max_f=60.0),
                _row(station="KLAX", valid_date=date(2025, 4, 1), forecast_max_f=70.0),
            ],
        )
        lookup = load_ndfd_lookup(con)
    finally:
        con.close()

    assert lookup.for_station("KJFK") == {
        date(2025, 4, 1): 58.0,
        date(2025, 4, 2): 60.0,
    }
    assert lookup.for_station("KLAX") == {date(2025, 4, 1): 70.0}


def test_load_ndfd_lookup_filters_source_and_lead(tmp_path: Path) -> None:
    """Lead-1 and lead-2 rows naturally have different ``as_of`` (different cycles).

    The schema's PK is ``(as_of, source, station, valid_date)`` so lead-1 from
    cycle (vd - 1) and lead-2 from cycle (vd - 2) coexist without conflict —
    that's the realistic shape live ingest produces.
    """
    db = _setup_db(tmp_path)
    con = connect(db)
    try:
        vd = date(2025, 4, 3)
        insert_ndfd_forecasts(
            con,
            [
                _row(
                    station="KJFK",
                    valid_date=vd,
                    forecast_max_f=58.0,
                    as_of=datetime(2025, 4, 2),  # cycle vd-1 → lead 1
                    lead_days=1,
                ),
                _row(
                    station="KJFK",
                    valid_date=vd,
                    forecast_max_f=99.0,
                    as_of=datetime(2025, 4, 1),  # cycle vd-2 → lead 2
                    lead_days=2,
                ),
                _row(
                    station="KJFK",
                    valid_date=vd,
                    forecast_max_f=88.0,
                    as_of=datetime(2025, 4, 2),  # same as_of as lead-1 row but different source
                    source="nbm_qmd_s3",
                ),
            ],
        )
        # Default: deterministic + lead=1.
        lookup_default = load_ndfd_lookup(con)
        assert lookup_default.for_station("KJFK") == {vd: 58.0}
        # Override: same date, different lead.
        lookup_lead2 = load_ndfd_lookup(con, lead_days=2)
        assert lookup_lead2.for_station("KJFK") == {vd: 99.0}
        # Override: different source.
        lookup_qmd = load_ndfd_lookup(con, source="nbm_qmd_s3")
        assert lookup_qmd.for_station("KJFK") == {vd: 88.0}
    finally:
        con.close()


def test_load_ndfd_lookup_keeps_freshest_as_of(tmp_path: Path) -> None:
    """Multiple ``as_of`` rows for the same (station, valid_date): freshest wins."""
    db = _setup_db(tmp_path)
    con = connect(db)
    try:
        insert_ndfd_forecasts(
            con,
            [
                _row(
                    station="KJFK",
                    valid_date=date(2025, 4, 1),
                    forecast_max_f=58.0,
                    as_of=datetime(2025, 3, 31, 6),  # earlier
                ),
                _row(
                    station="KJFK",
                    valid_date=date(2025, 4, 1),
                    forecast_max_f=60.5,
                    as_of=datetime(2025, 3, 31, 18),  # later — should win
                ),
            ],
        )
        lookup = load_ndfd_lookup(con)
    finally:
        con.close()
    assert lookup.for_station("KJFK") == {date(2025, 4, 1): 60.5}
