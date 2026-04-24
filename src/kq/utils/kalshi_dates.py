"""Kalshi weather-market settlement-day arithmetic.

Per Pass 1 §2f and Kalshi's own help text, weather markets settle on the
**Local Standard Time** calendar day. That's the same as local clock time
in winter, but during DST the "day" runs 01:00-24:59 on the local wall clock
(because LST is 1 hour behind DST-local).

Two entry points:

- ``settlement_day(station, instant)``: which LST-day contains this UTC
  instant? Use this when you need to assign a METAR observation, a fill,
  or any UTC-stamped event to its Kalshi settlement date.

- ``settlement_day_bounds(station, day)``: the UTC start (inclusive) and
  end (exclusive) of a given Kalshi settlement day. Use this to filter a
  stream of METAR observations to "the ones that belong to today's
  high".

Both are pure functions — no network, no state.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

from kq.clients.stations import Station


def _lst_tz(station: Station) -> timezone:
    """Station's fixed LST timezone (DST-free)."""
    return timezone(timedelta(hours=station.lst_offset_hours))


def settlement_day(station: Station, instant: datetime) -> date:
    """Return the Kalshi-settlement calendar date that contains ``instant``.

    Raises ValueError if ``instant`` is naive (no tzinfo) — we refuse to
    guess a timezone here because silent conversion is exactly how these
    bugs happen.
    """
    if instant.tzinfo is None:
        raise ValueError(
            "settlement_day() requires a timezone-aware datetime; "
            "pass `datetime.now(tz=UTC)` or similar."
        )
    return instant.astimezone(_lst_tz(station)).date()


def settlement_day_bounds(station: Station, day: date) -> tuple[datetime, datetime]:
    """Return ``(start_utc, end_utc)`` for a given Kalshi settlement day.

    ``start_utc`` is inclusive; ``end_utc`` is exclusive. Together they
    span exactly 24 hours.
    """
    tz = _lst_tz(station)
    start_lst = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=tz)
    end_lst = start_lst + timedelta(days=1)
    return start_lst.astimezone(UTC), end_lst.astimezone(UTC)


def instant_in_settlement_day(station: Station, instant: datetime, day: date) -> bool:
    """Convenience: does ``instant`` fall inside the ``day`` settlement window?"""
    start, end = settlement_day_bounds(station, day)
    if instant.tzinfo is None:
        raise ValueError("instant_in_settlement_day() requires a timezone-aware datetime.")
    return start <= instant.astimezone(UTC) < end
