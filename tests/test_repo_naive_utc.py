"""Naive-UTC normalization round-trips for the 5 high-volume repositories.

2026-06-11 audit (PR-G): DuckDB's TIMESTAMP columns are naive; the Python
driver silently rewrites tz-aware datetimes to the HOST-LOCAL wall clock on
bind, mixing timestamp conventions in one DB across the Mac/WSL2 hosts. The
NBA-era repositories normalized to naive UTC; forecasts/kalshi/metar/ndfd/
observed did not. These tests pin the fix: a tz-aware NON-UTC datetime bound
into each INSERT/UPSERT must round-trip as its UTC wall time, naive,
regardless of the host timezone.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pytest

from kq.clients.acis import DailyClimateObservation
from kq.clients.kalshi import Market, OrderBookSnapshot
from kq.clients.metar import MetarObservation
from kq.clients.ndfd import NbmDeterministicForecast
from kq.clients.openmeteo import EnsembleForecast
from kq.storage._tz import to_naive_utc, to_naive_utc_optional
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.forecasts import insert_forecasts
from kq.storage.repositories.kalshi import insert_kalshi_books, upsert_kalshi_markets
from kq.storage.repositories.metar import insert_metar
from kq.storage.repositories.ndfd import insert_ndfd_forecasts
from kq.storage.repositories.observed import insert_observed

PDT = timezone(timedelta(hours=-7))  # deliberately non-UTC
AWARE = datetime(2026, 6, 11, 9, 30, tzinfo=PDT)
EXPECTED = datetime(2026, 6, 11, 16, 30)  # the same instant as naive UTC
VALID = date(2026, 6, 12)


@pytest.fixture
def con(tmp_path: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    db = tmp_path / "tz.duckdb"
    bootstrap(db)
    connection = connect(db)
    yield connection
    connection.close()


def _stored(con: duckdb.DuckDBPyConnection, sql: str) -> datetime:
    row = con.execute(sql).fetchone()
    assert row is not None and row[0] is not None
    val = row[0]
    assert isinstance(val, datetime)
    assert val.tzinfo is None  # stored per the naive-UTC convention
    return val


# --------------------------------------------------------------- helper


def test_to_naive_utc_converts_and_strips() -> None:
    assert to_naive_utc(AWARE) == EXPECTED
    assert to_naive_utc(EXPECTED) == EXPECTED  # naive passes through
    assert to_naive_utc_optional(None) is None
    assert to_naive_utc_optional(AWARE) == EXPECTED


# ----------------------------------------------------------- forecasts


def test_forecasts_round_trip_utc(con: duckdb.DuckDBPyConnection) -> None:
    n = insert_forecasts(
        con,
        [
            EnsembleForecast(
                as_of=AWARE,
                run_time=AWARE,
                model="gefs",
                member=0,
                station="KLAX",
                valid_date=VALID,
                forecast_high_f=75.0,
                forecast_low_f=60.0,
            )
        ],
    )
    assert n == 1
    assert _stored(con, "SELECT as_of FROM weather_forecast") == EXPECTED
    assert _stored(con, "SELECT run_time FROM weather_forecast") == EXPECTED


# -------------------------------------------------------------- kalshi


def test_kalshi_markets_round_trip_utc(con: duckdb.DuckDBPyConnection) -> None:
    market = Market(
        ticker="KXHIGHLAX-26JUN12-B74.5",
        event_ticker="KXHIGHLAX-26JUN12",
        title="74-75",
        status="active",
        category="WEATHER",
        yes_ask=0.5,
        yes_bid=0.4,
        last_price=None,
        volume=None,
        open_interest=None,
        open_time=AWARE,
        close_time=AWARE + timedelta(days=1),
        expected_expiration_time=None,
        rules_primary=None,
        strike_type="between",
        floor_strike=74.0,
        cap_strike=75.0,
    )
    assert upsert_kalshi_markets(con, [market]) == 1
    assert _stored(con, "SELECT opens_at FROM kalshi_market") == EXPECTED
    assert _stored(con, "SELECT closes_at FROM kalshi_market") == EXPECTED + timedelta(days=1)


def test_kalshi_books_round_trip_utc(con: duckdb.DuckDBPyConnection) -> None:
    snap = OrderBookSnapshot(
        snap_time=AWARE,
        ticker="KXHIGHLAX-26JUN12-B74.5",
        yes_bid=0.4,
        yes_ask=0.5,
        yes_bid_size=10.0,
        yes_ask_size=12.0,
        yes_bids=(),
        yes_asks=(),
    )
    assert insert_kalshi_books(con, [snap]) == 1
    assert _stored(con, "SELECT snap_time FROM kalshi_book_snap") == EXPECTED


# --------------------------------------------------------------- metar


def test_metar_round_trip_utc(con: duckdb.DuckDBPyConnection) -> None:
    obs = MetarObservation(
        obs_time=AWARE,
        station="KLAX",
        temp_f=71.0,
        dewpoint_f=55.0,
        wind_kt=8.0,
        pressure_mb=1015.0,
    )
    assert insert_metar(con, [obs]) == 1
    assert _stored(con, "SELECT obs_time FROM metar_obs") == EXPECTED


# ---------------------------------------------------------------- ndfd


def test_ndfd_round_trip_utc(con: duckdb.DuckDBPyConnection) -> None:
    row = NbmDeterministicForecast(
        as_of=AWARE,
        station="KLAX",
        valid_date=VALID,
        lead_days=1,
        forecast_max_f=76.0,
    )
    assert insert_ndfd_forecasts(con, [row]) == 1
    assert _stored(con, "SELECT as_of FROM ndfd_forecast") == EXPECTED


# ------------------------------------------------------------ observed


def test_observed_round_trip_utc(con: duckdb.DuckDBPyConnection) -> None:
    row = DailyClimateObservation(
        station="KLAX",
        valid_date=VALID,
        high_f=77.0,
        low_f=61.0,
        source="nws_acis",
        fetched_at=AWARE,
    )
    assert insert_observed(con, [row]) == 1
    assert _stored(con, "SELECT fetched_at FROM weather_observed") == EXPECTED
