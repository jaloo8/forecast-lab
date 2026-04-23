"""The 6 Kalshi weather-market airport stations.

Kalshi daily-high contracts settle on the NWS Daily Climate Report for specific
airport stations. ICAO codes match the METAR network; lat/lon are the official
station coordinates used by NOAA/NWS.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Station:
    icao: str  # e.g. "KLAX" — used as the primary key across the system
    city: str
    kalshi_event_ticker: str  # e.g. "KXHIGHLAX"
    latitude: float
    longitude: float


STATIONS: tuple[Station, ...] = (
    Station("KLAX", "Los Angeles", "KXHIGHLAX", 33.9416, -118.4085),
    Station("KJFK", "New York (JFK)", "KXHIGHNY", 40.6413, -73.7781),
    Station("KMDW", "Chicago Midway", "KXHIGHCHI", 41.7868, -87.7522),
    Station("KMIA", "Miami", "KXHIGHMIA", 25.7932, -80.2906),
    Station("KDEN", "Denver", "KXHIGHDEN", 39.8561, -104.6737),
    Station("KAUS", "Austin", "KXHIGHAUS", 30.1945, -97.6699),
)


STATIONS_BY_ICAO: dict[str, Station] = {s.icao: s for s in STATIONS}
