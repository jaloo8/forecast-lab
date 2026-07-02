"""Tests for Kalshi LST settlement-day arithmetic.

The single-most-important correctness property here is that settlement_day
returns the same calendar date whether or not DST is in effect — Kalshi's
market resolution ignores the local DST shift.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from kq.clients.stations import STATIONS_BY_ICAO
from kq.utils.kalshi_dates import (
    instant_in_settlement_day,
    settlement_day,
    settlement_day_bounds,
)

LAX = STATIONS_BY_ICAO["KLAX"]  # PST, UTC-8
NYC = STATIONS_BY_ICAO["KNYC"]  # EST, UTC-5 (Central Park since PR-C, audit root cause #4)
DEN = STATIONS_BY_ICAO["KDEN"]  # MST, UTC-7


# --------------------------------------------------------------------- shape


def test_settlement_day_requires_aware_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        settlement_day(LAX, datetime(2025, 6, 15, 12, 0))  # naive


def test_settlement_day_accepts_any_aware_zone() -> None:
    pdt = timezone(timedelta(hours=-7))
    instant = datetime(2025, 6, 15, 10, 0, tzinfo=pdt)
    # 2025-06-15 10:00 PDT = 2025-06-15 17:00 UTC = 2025-06-15 09:00 LAX LST
    assert settlement_day(LAX, instant) == date(2025, 6, 15)


def test_settlement_day_bounds_span_24h() -> None:
    start, end = settlement_day_bounds(LAX, date(2025, 6, 15))
    assert end - start == timedelta(hours=24)


# ----------------------------------------------------------------- semantics


def test_noon_utc_maps_to_same_day_lax() -> None:
    # 12:00 UTC = 04:00 PST - still 2025-06-15 locally
    assert settlement_day(LAX, datetime(2025, 6, 15, 12, 0, tzinfo=UTC)) == date(2025, 6, 15)


def test_utc_midnight_is_previous_day_at_west_coast() -> None:
    # 00:00 UTC 2025-06-15 = 16:00 PST 2025-06-14
    assert settlement_day(LAX, datetime(2025, 6, 15, 0, 0, tzinfo=UTC)) == date(2025, 6, 14)


def test_kalshi_day_rolls_at_1am_local_clock_during_dst() -> None:
    """Pass 1 §2f: the Kalshi "day" in DST months runs 01:00-00:59 local-clock
    (equivalently 00:00-23:59 LST).

    So at 00:30 AM local-clock on June 16 PDT we're still inside Kalshi's
    "June 15" day (LST 23:30 June 15). At 01:30 AM local-clock June 16 PDT
    we've crossed into Kalshi's "June 16" (LST 00:30 June 16).
    """
    pdt = timezone(timedelta(hours=-7))

    before_roll = datetime(2025, 6, 16, 0, 30, tzinfo=pdt)
    assert settlement_day(LAX, before_roll) == date(2025, 6, 15)

    after_roll = datetime(2025, 6, 16, 1, 30, tzinfo=pdt)
    assert settlement_day(LAX, after_roll) == date(2025, 6, 16)


def test_lst_boundary_exact_lst_midnight() -> None:
    """At LST midnight, the new Kalshi day starts."""
    pst = timezone(timedelta(hours=-8))
    # 2025-06-15 00:00 PST -> UTC 08:00
    start = datetime(2025, 6, 15, 0, 0, tzinfo=pst)
    assert settlement_day(LAX, start) == date(2025, 6, 15)
    assert settlement_day(LAX, start - timedelta(seconds=1)) == date(2025, 6, 14)


def test_dst_spring_forward_unaffected() -> None:
    """Spring-forward 2025-03-09 in the US. Kalshi uses LST throughout,
    so our function returns the right calendar date on both sides of the
    01:59 -> 03:00 local-clock jump.
    """
    # 2025-03-09 01:30 PST (just before jump) -> 09:30 UTC
    just_before = datetime(2025, 3, 9, 9, 30, tzinfo=UTC)
    # 2025-03-09 03:00 PDT (right after jump) -> 10:00 UTC
    just_after = datetime(2025, 3, 9, 10, 0, tzinfo=UTC)
    assert settlement_day(LAX, just_before) == date(2025, 3, 9)
    assert settlement_day(LAX, just_after) == date(2025, 3, 9)


def test_dst_fall_back_unaffected() -> None:
    """Fall-back 2025-11-02. 01:30 local clock "happens twice" under DST,
    but LST runs straight through, so settlement_day is single-valued.
    """
    # 2025-11-02 08:30 UTC = 01:30 PDT (first) or 00:30 PST (LST)
    instant = datetime(2025, 11, 2, 8, 30, tzinfo=UTC)
    assert settlement_day(LAX, instant) == date(2025, 11, 2)


# -------------------------------------------------------- cross-station sanity


def test_different_stations_at_same_utc_instant() -> None:
    """A single UTC instant can fall in different Kalshi days for different
    stations - e.g., late evening on the east coast is early evening in the
    west, but still the same local date for each.
    """
    instant = datetime(2025, 6, 15, 3, 30, tzinfo=UTC)  # 03:30 UTC
    # LAX (-8 LST): 2025-06-14 19:30 -> 2025-06-14
    # NYC (-5 LST): 2025-06-14 22:30 -> 2025-06-14
    # DEN (-7 LST): 2025-06-14 20:30 -> 2025-06-14
    assert settlement_day(LAX, instant) == date(2025, 6, 14)
    assert settlement_day(NYC, instant) == date(2025, 6, 14)
    assert settlement_day(DEN, instant) == date(2025, 6, 14)

    # Now 14:00 UTC the same day: all stations show 2025-06-15.
    instant2 = datetime(2025, 6, 15, 14, 0, tzinfo=UTC)
    assert settlement_day(LAX, instant2) == date(2025, 6, 15)
    assert settlement_day(NYC, instant2) == date(2025, 6, 15)


# ---------------------------------------------------------------- day bounds


def test_bounds_round_trip() -> None:
    """Every instant inside ``bounds(day)`` maps back to ``day``."""
    day = date(2025, 6, 15)
    start, end = settlement_day_bounds(LAX, day)
    # 25 sample instants spread across the 24h window
    step = (end - start) / 25
    for i in range(25):
        instant = start + step * i
        assert settlement_day(LAX, instant) == day


def test_bounds_end_exclusive() -> None:
    """The ``end`` returned by bounds is the START of the *next* day."""
    _start, end = settlement_day_bounds(LAX, date(2025, 6, 15))
    assert settlement_day(LAX, end) == date(2025, 6, 16)


# -------------------------------------------------- instant_in_settlement_day


def test_instant_in_settlement_day_true_and_false() -> None:
    day = date(2025, 6, 15)
    inside = datetime(2025, 6, 15, 20, 0, tzinfo=UTC)  # 12:00 PST = inside
    outside_past = datetime(2025, 6, 14, 5, 0, tzinfo=UTC)  # 21:00 prior day
    outside_future = datetime(2025, 6, 16, 18, 0, tzinfo=UTC)  # 10:00 next day
    assert instant_in_settlement_day(LAX, inside, day) is True
    assert instant_in_settlement_day(LAX, outside_past, day) is False
    assert instant_in_settlement_day(LAX, outside_future, day) is False


def test_instant_in_settlement_day_requires_aware() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        instant_in_settlement_day(LAX, datetime(2025, 6, 15, 12, 0), date(2025, 6, 15))
