"""Tests for Kalshi weather-market ticker parsing.

The parser is best-guess against unverified production format. These tests
lock down the contract of the format we currently assume; if Kalshi's actual
production weather tickers differ, update WEATHER_TICKER_RE and refresh
these expectations together.
"""

from __future__ import annotations

from datetime import date

import pytest

from kq.clients.kalshi._ticker_parser import (
    ICAO_TO_WEATHER_STATION_CODE,
    WEATHER_STATION_CODE_TO_ICAO,
    WeatherMarketRef,
    build_weather_market_ticker,
    parse_weather_market_ticker,
)

# --------------------------------------------------- station code mapping


def test_station_code_mapping_is_bijection() -> None:
    """Every ICAO maps to a unique 2-3 letter Kalshi station code, and back."""
    assert len(WEATHER_STATION_CODE_TO_ICAO) == len(ICAO_TO_WEATHER_STATION_CODE)
    for code, icao in WEATHER_STATION_CODE_TO_ICAO.items():
        assert ICAO_TO_WEATHER_STATION_CODE[icao] == code


def test_station_code_mapping_covers_all_six_stations() -> None:
    """All 6 v1 stations have a Kalshi ticker code."""
    expected_icaos = {"KLAX", "KJFK", "KMDW", "KMIA", "KDEN", "KAUS"}
    assert set(ICAO_TO_WEATHER_STATION_CODE.keys()) == expected_icaos


# ----------------------------------------------------- happy-path parsing


def test_parse_lax_basic() -> None:
    ref = parse_weather_market_ticker("KXHIGHLAX-26APR30-T75")
    assert ref is not None
    assert ref.icao == "KLAX"
    assert ref.valid_date == date(2026, 4, 30)
    assert ref.threshold_f == 75
    assert ref.raw_ticker == "KXHIGHLAX-26APR30-T75"
    assert ref.station_ticker_code == "LAX"


def test_parse_jfk_uses_ny_code() -> None:
    """JFK in our station list maps to 'NY' in the Kalshi ticker."""
    ref = parse_weather_market_ticker("KXHIGHNY-26MAY01-T80")
    assert ref is not None
    assert ref.icao == "KJFK"
    assert ref.station_ticker_code == "NY"


def test_parse_chicago_uses_chi_code() -> None:
    ref = parse_weather_market_ticker("KXHIGHCHI-26JUL04-T95")
    assert ref is not None
    assert ref.icao == "KMDW"
    assert ref.valid_date == date(2026, 7, 4)


def test_parse_all_six_stations_round_trip() -> None:
    """Every ICAO can build a ticker and parse back to the same ICAO."""
    target_date = date(2026, 6, 15)
    for icao in ("KLAX", "KJFK", "KMDW", "KMIA", "KDEN", "KAUS"):
        ticker = build_weather_market_ticker(icao, target_date, 80)
        ref = parse_weather_market_ticker(ticker)
        assert ref is not None
        assert ref.icao == icao
        assert ref.valid_date == target_date
        assert ref.threshold_f == 80


def test_parse_three_digit_threshold() -> None:
    """Tail thresholds (>= 100F) are integers with 3 digits."""
    ref = parse_weather_market_ticker("KXHIGHAUS-26AUG15-T105")
    assert ref is not None
    assert ref.threshold_f == 105


def test_parse_strips_surrounding_whitespace() -> None:
    ref = parse_weather_market_ticker("  KXHIGHLAX-26APR30-T75  ")
    assert ref is not None
    assert ref.icao == "KLAX"


# ----------------------------------------------------- defensive parsing


@pytest.mark.parametrize(
    "bad_ticker",
    [
        "",
        "not-a-kalshi-ticker",
        "KXHIGHLAX",  # missing date + threshold
        "KXHIGHLAX-26APR30",  # missing threshold
        "KXHIGHLAX-26APR30-X75",  # threshold prefix isn't 'T'
        "KXHIGHLAX-2026APR30-T75",  # 4-digit year
        "KXHIGHZZZ-26APR30-T75",  # unknown station code
        "KXHIGHLAX-26FOO30-T75",  # non-month abbreviation
        "KXHIGHLAX-26APR30-Tabc",  # non-numeric threshold
        "KXNBAGAME-26APR30BOSPHI-PHI",  # NBA ticker (not weather)
        "KXMLBSPREAD-26APR291507BOSTOR-TOR4",  # MLB ticker
    ],
)
def test_parse_returns_none_on_bad_input(bad_ticker: str) -> None:
    assert parse_weather_market_ticker(bad_ticker) is None


def test_parse_returns_none_on_invalid_date() -> None:
    """Feb 30 doesn't exist; parser must reject."""
    assert parse_weather_market_ticker("KXHIGHLAX-26FEB30-T75") is None


def test_parse_does_not_raise_on_garbage() -> None:
    """Property: parser must NEVER raise. Returns None on any nonsense input."""
    for s in ["", "\n", "\x00\x01\x02", "🦄🌈", "a" * 1000, "123-456-789"]:
        assert parse_weather_market_ticker(s) is None


# ----------------------------------------------------- builder


def test_build_round_trip_idempotent() -> None:
    """Build then parse returns the same fields."""
    ticker = build_weather_market_ticker("KMIA", date(2026, 12, 25), 78)
    assert ticker == "KXHIGHMIA-26DEC25-T78"
    ref = parse_weather_market_ticker(ticker)
    assert ref is not None
    assert ref.icao == "KMIA"
    assert ref.valid_date == date(2026, 12, 25)
    assert ref.threshold_f == 78


def test_build_rejects_unknown_icao() -> None:
    with pytest.raises(ValueError, match="no Kalshi weather ticker code"):
        build_weather_market_ticker("KZZZ", date(2026, 4, 30), 75)


def test_build_pads_single_digit_day() -> None:
    """Day 1-9 must be zero-padded to two digits (matches Kalshi convention)."""
    ticker = build_weather_market_ticker("KLAX", date(2026, 4, 5), 70)
    assert ticker == "KXHIGHLAX-26APR05-T70"


def test_weather_market_ref_immutable() -> None:
    """Frozen dataclass — assignment after construction must fail."""
    ref = WeatherMarketRef(
        icao="KLAX",
        valid_date=date(2026, 4, 30),
        threshold_f=75,
        raw_ticker="KXHIGHLAX-26APR30-T75",
    )
    with pytest.raises((AttributeError, TypeError)):
        ref.threshold_f = 80  # type: ignore[misc]
