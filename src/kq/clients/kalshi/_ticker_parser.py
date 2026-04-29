"""Parse Kalshi weather-market ticker strings to typed metadata.

Best-guess based on Pass 1 §1a + the demo-environment ticker patterns we
observed for NBA / MLB / tennis (`<EVENT>-<DATE>-<MARKET_SUFFIX>`):

    KXHIGHLAX-26APR30-T75   ->  station=KLAX, valid_date=2026-04-30, threshold=75F
    KXHIGHNY-26MAY01-T80    ->  station=KJFK, valid_date=2026-05-01, threshold=80F

Per Pass 1 §1a Kalshi weather contracts settle on the NWS Daily Climate
Report for an airport using **local standard time** for the calendar day
boundary. We don't try to interpret that here — the parsed `valid_date`
is the date string AS WRITTEN in the ticker. Use `kq.utils.kalshi_dates`
when you need to map UTC observations back to that day.

⚠️ This parser is **unverified against production Kalshi weather markets**
(demo doesn't seed weather markets — see `docs/research/PASS-1-FEASIBILITY.md`).
The patterns are a best guess. When prod access is available, update
`WEATHER_TICKER_RE` + the round-trip test if the actual format differs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Final

# Map the 2-3 letter station code in a Kalshi weather ticker to an ICAO code.
# Matches the Pass 1 weather event-ticker conventions: KXHIGHLAX, KXHIGHNY, etc.
WEATHER_STATION_CODE_TO_ICAO: Final[dict[str, str]] = {
    "LAX": "KLAX",
    "NY": "KJFK",
    "CHI": "KMDW",
    "MIA": "KMIA",
    "DEN": "KDEN",
    "AUS": "KAUS",
}

ICAO_TO_WEATHER_STATION_CODE: Final[dict[str, str]] = {
    icao: code for code, icao in WEATHER_STATION_CODE_TO_ICAO.items()
}

# Three-letter month abbreviations Kalshi uses in YYMMMDD (year is 2-digit).
_MONTH_ABBR_TO_NUM: Final[dict[str, int]] = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}  # fmt: skip

# Pattern: KXHIGH<STATION>-<YY><MMM><DD>-T<INT_F>
WEATHER_TICKER_RE: Final = re.compile(
    r"^KXHIGH(?P<station>[A-Z]+)-(?P<yy>\d{2})(?P<mmm>[A-Z]{3})(?P<dd>\d{2})-T(?P<thr>\d+)$"
)


@dataclass(frozen=True, slots=True)
class WeatherMarketRef:
    """Parsed identifier for a single Kalshi weather binary contract."""

    icao: str  # e.g. 'KLAX' (mapped from the ticker's 2-3 letter station code)
    valid_date: date  # the calendar date AS WRITTEN in the ticker
    threshold_f: int  # the integer Fahrenheit threshold of the >= contract
    raw_ticker: str  # the ticker exactly as Kalshi published it

    @property
    def station_ticker_code(self) -> str:
        """The 2-3 letter station code Kalshi puts in the ticker (LAX/NY/CHI/...)."""
        return ICAO_TO_WEATHER_STATION_CODE[self.icao]


def parse_weather_market_ticker(ticker: str) -> WeatherMarketRef | None:
    """Return a `WeatherMarketRef` if `ticker` matches the weather-market pattern,
    else None. Never raises — defensive against unknown formats.
    """
    match = WEATHER_TICKER_RE.match(ticker.strip())
    if match is None:
        return None
    station_code = match.group("station")
    icao = WEATHER_STATION_CODE_TO_ICAO.get(station_code)
    if icao is None:
        return None
    month = _MONTH_ABBR_TO_NUM.get(match.group("mmm"))
    if month is None:
        return None
    try:
        # Kalshi's 2-digit year: assume 20YY (won't matter for v1 — markets are current-year)
        year = 2000 + int(match.group("yy"))
        day = int(match.group("dd"))
        valid_date = date(year, month, day)
    except ValueError:
        return None
    try:
        threshold = int(match.group("thr"))
    except ValueError:
        return None
    return WeatherMarketRef(
        icao=icao,
        valid_date=valid_date,
        threshold_f=threshold,
        raw_ticker=ticker.strip(),
    )


def build_weather_market_ticker(
    icao: str,
    valid_date: date,
    threshold_f: int,
) -> str:
    """Construct a Kalshi weather ticker string from typed inputs.

    Inverse of `parse_weather_market_ticker`. Used when generating expected
    tickers to query Kalshi for. **Format verified once we have production
    access — until then, treat as best-guess.**
    """
    code = ICAO_TO_WEATHER_STATION_CODE.get(icao)
    if code is None:
        raise ValueError(f"no Kalshi weather ticker code for ICAO {icao!r}")
    yy = f"{valid_date.year % 100:02d}"
    mmm_lookup = {v: k for k, v in _MONTH_ABBR_TO_NUM.items()}
    mmm = mmm_lookup[valid_date.month]
    dd = f"{valid_date.day:02d}"
    return f"KXHIGH{code}-{yy}{mmm}{dd}-T{int(threshold_f)}"
