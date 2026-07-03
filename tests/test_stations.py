"""Pins for the station registry (``kq.clients.stations``).

Each Phase B station (2026-07-02 expansion) is pinned to the settlement
station its Kalshi contract actually names — via rules_secondary's NWS CLI
product, verified live against prod + ACIS + METAR + Open-Meteo on
2026-07-02. The 2026-06-11 Central Park lesson is structural here: the
settlement ICAO comes from the CONTRACT text, never the city name or the
ticker (KXHIGHTHOU -> Hobby not IAH; KXHIGHTDAL -> DFW not Love Field;
KXHIGHTDC -> Reagan National not Dulles).
"""

from __future__ import annotations

import pytest

from kq.clients.stations import STATIONS, STATIONS_BY_ICAO, lst_timezone_name

# (icao, series_ticker, lst_offset) — settlement-source pins, one per station.
_EXPECTED: tuple[tuple[str, str, int], ...] = (
    # v1 six
    ("KLAX", "KXHIGHLAX", -8),
    ("KNYC", "KXHIGHNY", -5),  # Central Park, not JFK (PR-C, audit root cause #4)
    ("KMDW", "KXHIGHCHI", -6),
    ("KMIA", "KXHIGHMIA", -5),
    ("KDEN", "KXHIGHDEN", -7),
    ("KAUS", "KXHIGHAUS", -6),
    # Phase B (2026-07-02) — ICAO is the rules_secondary CLI product's station.
    ("KPHX", "KXHIGHTPHX", -7),  # CLIPHX; AZ has no DST but LST == MST anyway
    ("KHOU", "KXHIGHTHOU", -6),  # CLIHOU — Hobby, NOT Intercontinental (KIAH)
    ("KMSY", "KXHIGHTNOLA", -6),  # CLIMSY
    ("KBOS", "KXHIGHTBOS", -5),  # CLIBOS
    ("KDFW", "KXHIGHTDAL", -6),  # CLIDFW — NOT Love Field despite "DAL" ticker
    ("KSAT", "KXHIGHTSATX", -6),  # CLISAT
    ("KSEA", "KXHIGHTSEA", -8),  # CLISEA
    ("KOKC", "KXHIGHTOKC", -6),  # CLIOKC
    ("KMSP", "KXHIGHTMIN", -6),  # CLIMSP
    ("KPHL", "KXHIGHPHIL", -5),  # CLIPHL — rules name Philadelphia Intl Airport
    ("KLAS", "KXHIGHTLV", -8),  # CLILAS
    ("KDCA", "KXHIGHTDC", -5),  # CLIDCA — Reagan National, NOT Dulles/BWI
    ("KATL", "KXHIGHTATL", -5),  # CLIATL
    ("KSFO", "KXHIGHTSFO", -8),  # CLISFO — the airport, not downtown SF
)


def test_registry_matches_expected_station_set() -> None:
    assert {s.icao for s in STATIONS} == {icao for icao, _, _ in _EXPECTED}
    assert len(STATIONS) == len(_EXPECTED)


@pytest.mark.parametrize(("icao", "series", "lst_offset"), _EXPECTED)
def test_station_pin(icao: str, series: str, lst_offset: int) -> None:
    station = STATIONS_BY_ICAO[icao]
    assert station.kalshi_series_ticker == series
    assert station.lst_offset_hours == lst_offset


def test_series_tickers_unique() -> None:
    tickers = [s.kalshi_series_ticker for s in STATIONS]
    assert len(tickers) == len(set(tickers))


def test_rejected_settlement_stations_absent() -> None:
    """The naive city->airport guesses the contracts do NOT settle on must
    never enter the registry (Central-Park failure class)."""
    for wrong in ("KJFK", "KIAH", "KDAL", "KIAD", "KBWI"):
        assert wrong not in STATIONS_BY_ICAO


def test_coordinates_within_conus() -> None:
    for s in STATIONS:
        assert 24.0 < s.latitude < 49.5, s.icao
        assert -125.0 < s.longitude < -66.0, s.icao


def test_lst_offsets_are_us_standard_zones() -> None:
    """LST offsets are DST-free US standard offsets (EST..PST)."""
    for s in STATIONS:
        assert s.lst_offset_hours in {-5, -6, -7, -8}, s.icao


def test_lst_timezone_name_posix_inversion() -> None:
    for s in STATIONS:
        name = lst_timezone_name(s)
        assert name == f"Etc/GMT+{abs(s.lst_offset_hours)}"
