"""The 6 Kalshi weather-market settlement stations.

Kalshi daily-high contracts settle on the NWS Daily Climate Report for specific
NWS stations — five airports plus Central Park (KNYC). Identifiers match the
METAR/ACIS station network; lat/lon are the official station coordinates used
by NOAA/NWS.

LST (Local Standard Time) offsets are the UTC offset **without DST**. Kalshi
weather markets settle on the LST calendar day — during DST, that means the
"day" runs from 01:00-24:59 local-clock time, not midnight-midnight. See
`kq.utils.kalshi_dates` for the settlement-day math and `docs/research/PASS-1`
§2f for the original reference.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Station:
    icao: str  # e.g. "KLAX" - used as the primary key across the system
    city: str
    # Kalshi SERIES ticker, e.g. "KXHIGHLAX". Daily markets live under dated
    # EVENT tickers (`KXHIGHLAX-26MAY31`) whose market tickers prefix-match this
    # (`KXHIGHLAX-26MAY31-T75`). Query Kalshi with `series_ticker=`, NOT
    # `event_ticker=` (the latter wants the dated event and returns nothing here).
    kalshi_series_ticker: str
    latitude: float
    longitude: float
    lst_offset_hours: int  # UTC offset in Local Standard Time (DST-free)


STATIONS: tuple[Station, ...] = (
    # (icao, city, kalshi_series_ticker, latitude, longitude, lst_offset_hours)
    Station("KLAX", "Los Angeles", "KXHIGHLAX", 33.9416, -118.4085, -8),  # PST
    # 2026-06-11 audit root cause #4: KXHIGHNY settles on the Central Park
    # NWS station (KNYC), NOT JFK — the two differ by several °F on
    # sea-breeze/marine-layer days. KJFK was removed in PR-C; historical
    # KJFK rows remain in the DB but nothing models JFK anymore.
    Station("KNYC", "New York (Central Park)", "KXHIGHNY", 40.7789, -73.9692, -5),  # EST
    Station("KMDW", "Chicago Midway", "KXHIGHCHI", 41.7868, -87.7522, -6),  # CST
    Station("KMIA", "Miami", "KXHIGHMIA", 25.7932, -80.2906, -5),  # EST
    Station("KDEN", "Denver", "KXHIGHDEN", 39.8561, -104.6737, -7),  # MST
    Station("KAUS", "Austin", "KXHIGHAUS", 30.1945, -97.6699, -6),  # CST
)


STATIONS_BY_ICAO: dict[str, Station] = {s.icao: s for s in STATIONS}
