"""The Kalshi weather-market settlement stations.

Kalshi daily-high contracts settle on the NWS Daily Climate Report for specific
NWS stations — airports plus Central Park (KNYC). Identifiers match the
METAR/ACIS station network; lat/lon are the official station coordinates used
by NOAA/NWS (ACIS StnMeta).

The original six stations shipped with v1. The 2026-07-02 Phase B expansion
added every OTHER actively-traded KXHIGH* daily series discovered on the prod
public API, after per-series settlement-source verification (the 2026-06-11
Central Park lesson: the settlement station comes from the CONTRACT text —
``rules_secondary`` names the exact NWS CLI product — never from the city
name or the ticker). Notable traps caught by that verification:

* KXHIGHTHOU settles on CLIHOU = Houston **Hobby** (KHOU), not
  Intercontinental/KIAH.
* KXHIGHTDAL settles on CLIDFW = **Dallas/Fort Worth Intl** (KDFW), not
  Love Field, despite the "DAL" in the ticker.
* KXHIGHTDC settles on CLIDCA = Washington-**National** (KDCA), not
  Dulles/BWI.

Every station here was verified against all three data sources before being
added: ACIS StnData resolves the ICAO sid, aviationweather.gov returns live
METARs, and the Open-Meteo ensemble API returns member forecasts at the
station coordinates in the station's fixed LST zone.

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
    # ---- Phase B expansion (2026-07-02): all remaining actively-traded
    # KXHIGH* daily series on prod. Settlement station verified per series
    # from rules_secondary's NWS CLI product (see module docstring); each
    # ICAO verified against ACIS + METAR + Open-Meteo before inclusion.
    Station("KPHX", "Phoenix (Sky Harbor)", "KXHIGHTPHX", 33.4278, -112.0036, -7),  # MST (CLIPHX)
    # CLIHOU = "Houston-Hobby, TX" — Hobby, NOT Intercontinental (KIAH).
    Station("KHOU", "Houston (Hobby)", "KXHIGHTHOU", 29.6459, -95.2821, -6),  # CST (CLIHOU)
    Station("KMSY", "New Orleans", "KXHIGHTNOLA", 29.9976, -90.2777, -6),  # CST (CLIMSY)
    Station("KBOS", "Boston (Logan)", "KXHIGHTBOS", 42.3606, -71.0097, -5),  # EST (CLIBOS)
    # CLIDFW = "Dallas/Fort Worth, TX" — DFW Intl, NOT Love Field (KDAL),
    # despite the "DAL" in the series ticker.
    Station("KDFW", "Dallas/Fort Worth", "KXHIGHTDAL", 32.8974, -97.0220, -6),  # CST (CLIDFW)
    Station("KSAT", "San Antonio", "KXHIGHTSATX", 29.5443, -98.4839, -6),  # CST (CLISAT)
    Station("KSEA", "Seattle-Tacoma", "KXHIGHTSEA", 47.4447, -122.3144, -8),  # PST (CLISEA)
    Station("KOKC", "Oklahoma City (Will Rogers)", "KXHIGHTOKC", 35.3884, -97.6004, -6),  # CST
    Station("KMSP", "Minneapolis-St Paul", "KXHIGHTMIN", 44.8852, -93.2313, -6),  # CST (CLIMSP)
    Station("KPHL", "Philadelphia Intl", "KXHIGHPHIL", 39.8733, -75.2268, -5),  # EST (CLIPHL)
    Station("KLAS", "Las Vegas (Harry Reid)", "KXHIGHTLV", 36.0719, -115.1634, -8),  # PST (CLILAS)
    # CLIDCA = "Washington-National" — Reagan National, NOT Dulles/BWI.
    Station("KDCA", "Washington (Reagan National)", "KXHIGHTDC", 38.8472, -77.0345, -5),  # EST
    Station("KATL", "Atlanta (Hartsfield-Jackson)", "KXHIGHTATL", 33.6297, -84.4422, -5),  # EST
    Station("KSFO", "San Francisco Intl", "KXHIGHTSFO", 37.6196, -122.3656, -8),  # PST (CLISFO)
)


STATIONS_BY_ICAO: dict[str, Station] = {s.icao: s for s in STATIONS}


def lst_timezone_name(station: Station) -> str:
    """IANA fixed-offset zone matching the station's LST, e.g. ``Etc/GMT+8``.

    ``Etc/GMT`` zones use POSIX sign inversion: ``Etc/GMT+8`` is UTC-8.
    They are DST-free, so requesting Open-Meteo ``daily`` aggregation (or
    hourly timestamps) in this zone yields exact Local-Standard-Time
    calendar days — the day definition Kalshi weather contracts settle on
    (2026-06-11 audit, UTC-vs-LST finding). Verified accepted by the
    Open-Meteo APIs (utc_offset_seconds echoes the fixed offset).
    """
    offset = station.lst_offset_hours
    if offset == 0:
        return "Etc/GMT"
    # POSIX inversion: UTC-8 -> "Etc/GMT+8"; UTC+3 -> "Etc/GMT-3".
    return f"Etc/GMT{'+' if offset < 0 else '-'}{abs(offset)}"
