"""Parse Kalshi weather-market ticker strings to typed metadata.

Best-guess based on Pass 1 §1a + the demo-environment ticker patterns we
observed for NBA / MLB / tennis (`<EVENT>-<DATE>-<MARKET_SUFFIX>`):

    KXHIGHLAX-26APR30-T75   ->  station=KLAX, valid_date=2026-04-30, threshold=75F
    KXHIGHNY-26MAY01-T80    ->  station=KNYC, valid_date=2026-05-01, threshold=80F

Per Pass 1 §1a Kalshi weather contracts settle on the NWS Daily Climate
Report for an airport using **local standard time** for the calendar day
boundary. We don't try to interpret that here — the parsed `valid_date`
is the date string AS WRITTEN in the ticker. Use `kq.utils.kalshi_dates`
when you need to map UTC observations back to that day.

⚠️ VERIFIED against prod 2026-06-11 — with a critical caveat: the ticker
TEXT does not carry resolution semantics. Prod low-tail `-T<n>` tickers are
`strike_type='less'` (YES iff value < cap_strike) and 4 of 6 brackets per
event are `-B<x>.5` between-markets (parsed since PR-B with `kind="B"`).
The parsed `threshold_f` is just the number in the ticker; the
authoritative contract semantics live in `Market.strike_type` /
`floor_strike` / `cap_strike` (see `_types.py`). Consumers MUST price and
settle via `kq.clients.kalshi.strikes` (PR-B), which builds a typed
`Strike` from the API fields and cross-checks them against the ticker.
Recorded prod payloads: `tests/fixtures/kalshi_prod_markets_weather.json`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Final, Literal

# Map the 2-5 letter station code in a Kalshi weather ticker to an ICAO code.
# The code is whatever follows "KXHIGH" in the series ticker (KXHIGHLAX ->
# "LAX", KXHIGHTPHX -> "TPHX"). Each mapping's ICAO is the settlement station
# named by the CONTRACT (rules_secondary's NWS CLI product), verified live
# 2026-07-02 — never inferred from the city name (Central Park lesson).
WEATHER_STATION_CODE_TO_ICAO: Final[dict[str, str]] = {
    "LAX": "KLAX",
    # 2026-06-11 audit root cause #4 (PR-C): KXHIGHNY settles on Central
    # Park (KNYC), not JFK — "NY" must never map back to KJFK.
    "NY": "KNYC",
    "CHI": "KMDW",
    "MIA": "KMIA",
    "DEN": "KDEN",
    "AUS": "KAUS",
    # ---- Phase B expansion (2026-07-02), settlement station per CLI product:
    "TPHX": "KPHX",  # CLIPHX — Phoenix Sky Harbor
    # CLIHOU = Houston-Hobby: "THOU" must never map to KIAH (Intercontinental).
    "THOU": "KHOU",
    "TNOLA": "KMSY",  # CLIMSY — New Orleans Louis Armstrong Intl
    "TBOS": "KBOS",  # CLIBOS — Boston Logan
    # CLIDFW = Dallas/Fort Worth Intl: "TDAL" must never map to Love Field (KDAL).
    "TDAL": "KDFW",
    "TSATX": "KSAT",  # CLISAT — San Antonio Intl
    "TSEA": "KSEA",  # CLISEA — Seattle-Tacoma Intl
    "TOKC": "KOKC",  # CLIOKC — Oklahoma City Will Rogers
    "TMIN": "KMSP",  # CLIMSP — Minneapolis-St Paul Intl
    "PHIL": "KPHL",  # CLIPHL — rules_primary names "Philadelphia International Airport"
    "TLV": "KLAS",  # CLILAS — Las Vegas Harry Reid Intl
    # CLIDCA = Washington-National: "TDC" must never map to Dulles (KIAD) or BWI.
    "TDC": "KDCA",
    "TATL": "KATL",  # CLIATL — Atlanta Hartsfield-Jackson
    "TSFO": "KSFO",  # CLISFO — San Francisco Intl (airport, not downtown SF)
}

ICAO_TO_WEATHER_STATION_CODE: Final[dict[str, str]] = {
    icao: code for code, icao in WEATHER_STATION_CODE_TO_ICAO.items()
}

# Three-letter month abbreviations Kalshi uses in YYMMMDD (year is 2-digit).
_MONTH_ABBR_TO_NUM: Final[dict[str, int]] = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}  # fmt: skip

# Pattern: KXHIGH<STATION>-<YY><MMM><DD>-T<INT_F>  (tail greater/less markets)
#      or: KXHIGH<STATION>-<YY><MMM><DD>-B<F>.5    (between markets, half-degree midpoint)
WEATHER_TICKER_RE: Final = re.compile(
    r"^KXHIGH(?P<station>[A-Z]+)-(?P<yy>\d{2})(?P<mmm>[A-Z]{3})(?P<dd>\d{2})"
    r"-(?P<kind>[TB])(?P<thr>\d+(?:\.\d+)?)$"
)


@dataclass(frozen=True, slots=True)
class WeatherMarketRef:
    """Parsed identifier for a single Kalshi weather binary contract.

    ``kind`` is the ticker suffix letter: ``"T"`` for tail markets (greater
    OR less — the letter does NOT disambiguate; see module docstring) and
    ``"B"`` for between markets. ``threshold_f`` is the number as written:
    the tail threshold for T-markets, the bracket midpoint (e.g. ``74.5``
    for "74-75°") for B-markets. Resolution semantics must come from the
    API strike fields — see ``kq.clients.kalshi.strikes``.
    """

    icao: str  # e.g. 'KLAX' (mapped from the ticker's 2-3 letter station code)
    valid_date: date  # the calendar date AS WRITTEN in the ticker
    threshold_f: float  # the number in the ticker suffix (T: integer; B: x.5 midpoint)
    raw_ticker: str  # the ticker exactly as Kalshi published it
    kind: Literal["T", "B"] = "T"

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
    month = _MONTH_ABBR_TO_NUM.get(match.group("mmm"))
    if icao is None or month is None:
        return None
    try:
        # Kalshi's 2-digit year: assume 20YY (won't matter for v1 — markets are current-year)
        year = 2000 + int(match.group("yy"))
        day = int(match.group("dd"))
        valid_date = date(year, month, day)
    except ValueError:
        return None
    try:
        threshold = float(match.group("thr"))
    except ValueError:
        return None
    kind = match.group("kind")
    if kind == "T" and not threshold.is_integer():
        return None  # tail thresholds are whole degrees; refuse odd formats
    return WeatherMarketRef(
        icao=icao,
        valid_date=valid_date,
        threshold_f=threshold,
        raw_ticker=ticker.strip(),
        kind="T" if kind == "T" else "B",
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
