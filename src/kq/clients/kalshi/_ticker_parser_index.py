"""Parse Kalshi index-brackets market tickers (KXINX / KXNASDAQ100).

Format verified live against prod 2026-07-02 (recorded fixture
``tests/fixtures/kalshi_prod_markets_index.json``):

    KXINX-26JUL02H1300-B7812            -> S&P 500, 2026-07-02 session, between
    KXINX-26JUL01H1600-T7824.9999       -> S&P 500, 2026-07-01 session, tail
    KXNASDAQ100-26JUL01H1600-B31550     -> Nasdaq-100, 2026-07-01, between

The event-date component carries an **hour suffix** ``H<HHMM>`` — the
session's scheduled closing time in US/Eastern. Normal sessions are
``H1600`` (4pm); early-close sessions differ (prod showed ``H1300`` on
Jul 2, 2026, the pre-July-4th 1pm close). Rules text: "the end-of-day
S&P 500 index value on <date>" — the contract settles on the official
end-of-day index print regardless of the hour in the ticker, so
``valid_date`` is the field consumers join on.

Same lesson as weather (PR-B): the ticker TEXT does not carry resolution
semantics. Prod strike fields (verified 2026-07-02):

* ``between``: floor=7800, cap=7824.9999 — YES iff floor <= value <= cap,
  i.e. the real-number bracket [7800, 7825) for 2-decimal index prints.
* ``greater`` (``-T7824.9999``): floor=7824.9999 — YES iff value > floor,
  i.e. >= 7825.00.
* ``less`` (``-T7125``): cap=7125 — YES iff value < cap ("7,124.9999 or
  below").

The cap/floor epsilon DIFFERS per series (S&P caps end in .9999 — gap
1e-4; Nasdaq caps end in .99 — gap 1e-2). ``INDEX_STRIKE_HALF_WIDTH`` is
half the SMALLEST observed gap (5e-5): with 2-decimal settlement prints it
puts every boundary print on the correct side for BOTH series (7825.00
settles the ``greater`` YES, not the ``between`` below it), and it is
measure-zero for continuous pricing. Use it as the ``half_width`` argument
to ``kq.clients.kalshi.strikes.yes_prob`` / ``yes_outcome`` — the weather
default (0.5, for whole-degree-F settlement) would misplace index
boundaries. Consumers MUST still build the :class:`Strike` from the API
fields, never from this parse.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Final, Literal

# Half of the smallest cap->next-floor gap observed on prod (S&P's 1e-4).
# See module docstring for why one value settles both series correctly.
INDEX_STRIKE_HALF_WIDTH: Final = 0.00005

# Kalshi series ticker -> our canonical storage symbol (index_daily.symbol).
INDEX_SERIES_TO_SYMBOL: Final[dict[str, str]] = {
    "KXINX": "SPX",  # S&P 500 range, daily; settles on the EOD S&P 500 print
    "KXNASDAQ100": "NDX",  # Nasdaq-100 range, daily; settles on the EOD NDX print
}

SYMBOL_TO_INDEX_SERIES: Final[dict[str, str]] = {
    symbol: series for series, symbol in INDEX_SERIES_TO_SYMBOL.items()
}

# Venue bracket width in index points (between-market ladder spacing),
# verified on prod 2026-07-02: S&P brackets are 25 wide, Nasdaq 100 wide.
INDEX_BRACKET_WIDTH: Final[dict[str, float]] = {
    "SPX": 25.0,
    "NDX": 100.0,
}

_MONTH_ABBR_TO_NUM: Final[dict[str, int]] = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}  # fmt: skip

# Pattern: <SERIES>-<YY><MMM><DD>H<HHMM>-<T|B><NUMBER>
# NUMBER may carry decimals (tail strikes like T7824.9999).
INDEX_TICKER_RE: Final = re.compile(
    r"^(?P<series>KXINX|KXNASDAQ100)-(?P<yy>\d{2})(?P<mmm>[A-Z]{3})(?P<dd>\d{2})"
    r"H(?P<hhmm>\d{4})-(?P<kind>[TB])(?P<num>\d+(?:\.\d+)?)$"
)


@dataclass(frozen=True, slots=True)
class IndexMarketRef:
    """Parsed identifier for a single Kalshi index-brackets binary contract.

    ``kind`` is the ticker suffix letter: ``"T"`` for tail markets (greater
    OR less — the letter does NOT disambiguate) and ``"B"`` for between
    markets. ``ticker_value`` is the number as written (T: the strike text,
    decimals included; B: Kalshi's bracket label, roughly the bracket
    midpoint rounded down). ``close_hhmm_et`` is the session close hour from
    the event component (1600 normal, 1300 on early-close days). Resolution
    semantics must come from the API strike fields — see
    ``kq.clients.kalshi.strikes``.
    """

    symbol: str  # 'SPX' | 'NDX' (canonical, joins index_daily.symbol)
    series_ticker: str  # 'KXINX' | 'KXNASDAQ100'
    valid_date: date  # the session date AS WRITTEN in the ticker
    close_hhmm_et: str  # scheduled session close, US/Eastern ('1600', '1300', ...)
    ticker_value: float  # the number in the ticker suffix
    raw_ticker: str  # the ticker exactly as Kalshi published it
    kind: Literal["T", "B"] = "T"


def parse_index_market_ticker(ticker: str) -> IndexMarketRef | None:
    """Return an ``IndexMarketRef`` if ``ticker`` matches the index-brackets
    pattern, else None. Never raises — defensive against unknown formats.
    """
    match = INDEX_TICKER_RE.match(ticker.strip())
    if match is None:
        return None
    series = match.group("series")
    symbol = INDEX_SERIES_TO_SYMBOL.get(series)
    month = _MONTH_ABBR_TO_NUM.get(match.group("mmm"))
    if symbol is None or month is None:
        return None
    try:
        year = 2000 + int(match.group("yy"))
        valid_date = date(year, month, int(match.group("dd")))
    except ValueError:
        return None
    try:
        ticker_value = float(match.group("num"))
    except ValueError:  # pragma: no cover — regex guarantees a numeric group
        return None
    kind = match.group("kind")
    return IndexMarketRef(
        symbol=symbol,
        series_ticker=series,
        valid_date=valid_date,
        close_hhmm_et=match.group("hhmm"),
        ticker_value=ticker_value,
        raw_ticker=ticker.strip(),
        kind="T" if kind == "T" else "B",
    )
