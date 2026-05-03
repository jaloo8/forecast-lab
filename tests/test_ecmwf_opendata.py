"""Tests for the Phase 1 ECMWF Open Data scaffolding.

Mirrors the GEFSv12 reforecast tests: unit-test only the pure URL +
file-layout primitives. The cfgrib-touching path (``fetch_grib2_bytes``,
``extract_station_tmax``) is exercised via the future Phase 2 ingest
flow, the same way ``gefs_reforecast.extract_station_values`` is.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from kq.clients.ecmwf_opendata import (
    CYCLE_HOURS,
    DISSEMINATION_BASE,
    LEAD_1_STEPS_HOURS,
    OpenDataFile,
    StationCoord,
    files_for_lead_1,
    kelvin_to_fahrenheit,
    make_cycle_dt,
)

# --------------------------- URL builder ---------------------------


def test_url_well_formed_oper_fc() -> None:
    """URL matches the ECMWF Open Data path verified live (2026-05-02)."""
    cycle = datetime(2026, 5, 2, 0, tzinfo=UTC)
    f = OpenDataFile(cycle=cycle, stream="oper", type="fc", step_hours=3)
    assert f.url == (
        f"{DISSEMINATION_BASE}/20260502/00z/ifs/0p25/oper/20260502000000-3h-oper-fc.grib2"
    )


def test_url_well_formed_enfo_ef() -> None:
    """ENS combined file naming."""
    cycle = datetime(2026, 5, 2, 12, tzinfo=UTC)
    f = OpenDataFile(cycle=cycle, stream="enfo", type="ef", step_hours=24)
    assert f.url == (
        f"{DISSEMINATION_BASE}/20260502/12z/ifs/0p25/enfo/20260502120000-24h-enfo-ef.grib2"
    )


def test_filename_uses_cycle_timestamp_not_just_date() -> None:
    """Filename includes hhmmss so 06z and 18z don't collide on the same day."""
    cycle = datetime(2026, 5, 2, 18, tzinfo=UTC)
    f = OpenDataFile(cycle=cycle, stream="oper", type="fc", step_hours=6)
    assert f.filename == "20260502180000-6h-oper-fc.grib2"


def test_resolution_is_overridable() -> None:
    cycle = datetime(2026, 5, 2, 0, tzinfo=UTC)
    f = OpenDataFile(cycle=cycle, stream="oper", type="fc", step_hours=3, resolution="0p4-beta")
    assert "0p4-beta" in f.url
    assert f.resolution == "0p4-beta"


# --------------------------- cycle validation ---------------------------


def test_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        OpenDataFile(
            cycle=datetime(2026, 5, 2, 0),
            stream="oper",
            type="fc",
            step_hours=3,
        )


def test_rejects_non_utc_datetime() -> None:
    cet = timezone(timedelta(hours=2))
    with pytest.raises(ValueError, match="UTC"):
        OpenDataFile(
            cycle=datetime(2026, 5, 2, 0, tzinfo=cet),
            stream="oper",
            type="fc",
            step_hours=3,
        )


def test_rejects_unsupported_cycle_hour() -> None:
    with pytest.raises(ValueError, match="not in"):
        OpenDataFile(
            cycle=datetime(2026, 5, 2, 3, tzinfo=UTC),
            stream="oper",
            type="fc",
            step_hours=3,
        )


def test_rejects_negative_step_hours() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        OpenDataFile(
            cycle=datetime(2026, 5, 2, 0, tzinfo=UTC),
            stream="oper",
            type="fc",
            step_hours=-3,
        )


def test_make_cycle_dt_accepts_published_cycles() -> None:
    """All four published cycles produce UTC-aware datetimes."""
    for hour in CYCLE_HOURS:
        cycle = make_cycle_dt(date(2026, 5, 2), hour=hour)
        assert cycle.tzinfo == UTC
        assert cycle.hour == hour


def test_make_cycle_dt_rejects_unpublished_hour() -> None:
    with pytest.raises(ValueError, match="not in published cycles"):
        make_cycle_dt(date(2026, 5, 2), hour=3)


# --------------------------- lead-1 file set ---------------------------


def test_files_for_lead_1_oper_uses_fc_type() -> None:
    cycle = datetime(2026, 5, 2, 0, tzinfo=UTC)
    files = files_for_lead_1(cycle=cycle, stream="oper")
    assert len(files) == len(LEAD_1_STEPS_HOURS)
    assert all(f.type == "fc" for f in files)
    assert [f.step_hours for f in files] == list(LEAD_1_STEPS_HOURS)


def test_files_for_lead_1_enfo_uses_ef_type() -> None:
    cycle = datetime(2026, 5, 2, 12, tzinfo=UTC)
    files = files_for_lead_1(cycle=cycle, stream="enfo")
    assert all(f.type == "ef" for f in files)


def test_files_for_lead_1_steps_cover_all_lst_zones() -> None:
    """Lead-1 step set must reach far enough that the latest-LST station
    (KLAX, lst_offset_hours=-8) sees a full local-day worth of samples
    after a 00z init. With 00z init, KLAX local midnight is at 08z --
    so we need at minimum step_hours >= 32 for a 24-hour window. The
    default tuple goes through 48h, which clears that comfortably."""
    assert max(LEAD_1_STEPS_HOURS) >= 32


# --------------------------- StationCoord ---------------------------


def test_longitude_e_wraps_west_negative_to_east_positive() -> None:
    """KLAX is at -118.4 degrees west; ECMWF grid is east-positive in [0, 360]."""
    klax = StationCoord(icao="KLAX", latitude=33.94, longitude=-118.4085)
    assert klax.longitude_e == pytest.approx(360.0 - 118.4085)


def test_longitude_e_passthrough_for_east_positive_input() -> None:
    """Already-east-positive longitudes pass through unchanged."""
    east = StationCoord(icao="UTAA", latitude=0.0, longitude=120.0)
    assert east.longitude_e == 120.0


def test_longitude_e_handles_360() -> None:
    """360 wraps to 0 (Greenwich). The exact-360 boundary is rare in
    practice but the modulus must not produce 360.0."""
    p = StationCoord(icao="EGLL", latitude=51.5, longitude=360.0)
    assert p.longitude_e == 0.0


# --------------------------- temperature math ---------------------------


def test_kelvin_to_fahrenheit_freezing_point() -> None:
    assert kelvin_to_fahrenheit(273.15) == pytest.approx(32.0)


def test_kelvin_to_fahrenheit_boiling_point() -> None:
    assert kelvin_to_fahrenheit(373.15) == pytest.approx(212.0)


def test_kelvin_to_fahrenheit_negative_celsius() -> None:
    """-40 Celsius = -40 Fahrenheit (the well-known crossover)."""
    assert kelvin_to_fahrenheit(233.15) == pytest.approx(-40.0)
