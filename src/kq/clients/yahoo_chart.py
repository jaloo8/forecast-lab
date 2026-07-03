"""Yahoo Finance v8 chart client — free daily index OHLC (Phase C).

Feeds ``index_daily``, the training/backtest substrate for the HAR-RV
benchmark on Kalshi index brackets (KXINX settles on the end-of-day S&P 500
print, KXNASDAQ100 on the Nasdaq-100 print).

Endpoint: ``https://query1.finance.yahoo.com/v8/finance/chart/<symbol>``
with ``interval=1d`` + ``period1``/``period2`` epoch seconds. No API key,
plain GET; verified live 2026-07-02 (^GSPC and ^NDX, 2y range = 501 bars).
Recorded fixture: ``tests/fixtures/yahoo_chart_index_daily.json``.

Source-selection honesty (venue-reality rule): Stooq's CSV endpoint —
the strategy doc's first suggestion — now sits behind a JavaScript
proof-of-work wall (probed live 2026-07-02: HTTP 200 HTML "This site
requires JavaScript to verify your browser"), unusable from plain httpx.
Yahoo's chart endpoint is UNOFFICIAL and undocumented: fine for personal,
non-commercial research use, but it carries no SLA, may rate-limit or
change shape without notice, and its data must not be redistributed. The
doctor-style mitigation is the recorded fixture + the guarded upsert
(a degraded payload can never wipe stored truth). If the endpoint dies,
the swap point is this module only.

Settlement-truth caveat: Yahoo's ^GSPC/^NDX closes are the standard
published index closes, which is also what Kalshi's rules reference ("the
end-of-day S&P 500 index value", settlement source "e.g. Google Finance").
Small vendor discrepancies (late corrections, rounding) are possible; the
trailing re-fetch window in ``kq ingest-index`` picks up corrections.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Final
from zoneinfo import ZoneInfo

import httpx

from kq.clients._http import default_client, request_json

BASE_URL: Final = "https://query1.finance.yahoo.com/v8/finance/chart"

# Canonical storage symbol -> Yahoo ticker. Canonical ids are venue-neutral
# ('SPX'/'NDX'); the Yahoo-isms stay inside this client.
YAHOO_SYMBOL: Final[dict[str, str]] = {
    "SPX": "^GSPC",
    "NDX": "^NDX",
}

INDEX_SYMBOLS: Final[tuple[str, ...]] = tuple(YAHOO_SYMBOL)

_EASTERN = ZoneInfo("America/New_York")

# A bar for the CURRENT exchange-local session is a live partial (its
# "close" is just the last trade) until the session is over. 16:15 ET
# clears the 16:00 normal close with a settle buffer; early-close days
# (e.g. 13:00 pre-holiday sessions) are simply included a few hours late.
_SESSION_FINAL_ET = time(16, 15)


class YahooChartError(RuntimeError):
    """Yahoo answered but the chart payload reports an error or has no bars."""

    def __init__(self, symbol: str, detail: str) -> None:
        super().__init__(f"Yahoo chart error for {symbol}: {detail}")
        self.symbol = symbol
        self.detail = detail


@dataclass(frozen=True, slots=True)
class IndexDailyBar:
    symbol: str  # canonical ('SPX' | 'NDX')
    valid_date: date  # exchange-local session date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    source: str
    fetched_at: datetime


class YahooChartClient:
    """Async Yahoo Finance daily-OHLC client for the index symbols."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> YahooChartClient:
        if self._client is None:
            self._client = default_client()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_daily(
        self,
        symbol: str,
        *,
        start_date: date,
        end_date: date,
    ) -> list[IndexDailyBar]:
        """Pull daily OHLC bars for a canonical index symbol over a date range.

        The current session's live partial bar is excluded until ~16:15 ET
        (see ``_SESSION_FINAL_ET``) so a mid-session cron can't persist a
        provisional close as if it were the settlement print.
        """
        if symbol not in YAHOO_SYMBOL:
            raise ValueError(f"unknown index symbol {symbol!r}; expected one of {INDEX_SYMBOLS}")
        if end_date < start_date:
            raise ValueError(f"end_date {end_date} precedes start_date {start_date}")
        if self._client is None:
            raise RuntimeError("use `async with YahooChartClient()` or pass a client")

        fetched_at = datetime.now(tz=UTC)
        period1 = int(datetime.combine(start_date, time.min, tzinfo=_EASTERN).timestamp())
        period2 = int(
            datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=_EASTERN).timestamp()
        )
        payload = await request_json(
            self._client,
            f"{BASE_URL}/{YAHOO_SYMBOL[symbol]}",
            params={"interval": "1d", "period1": period1, "period2": period2},
        )
        bars = _parse_chart_payload(payload, symbol=symbol, fetched_at=fetched_at)
        return _final_session_bars(bars, now_utc=fetched_at)


def _parse_chart_payload(
    payload: Any,
    *,
    symbol: str,
    fetched_at: datetime,
    source: str = "yahoo_chart",
) -> list[IndexDailyBar]:
    """Flatten the v8 chart response to typed daily bars.

    Raises :class:`YahooChartError` when the payload carries an error body
    or no result — never silently coerced to "zero rows" (the ACIS lesson:
    an outage must be distinguishable from a quiet day).
    """
    if not isinstance(payload, dict):
        raise YahooChartError(symbol, f"non-dict payload: {type(payload).__name__}")
    chart = payload.get("chart")
    if not isinstance(chart, dict):
        raise YahooChartError(symbol, "missing 'chart' envelope")
    error = chart.get("error")
    if error is not None:
        raise YahooChartError(symbol, str(error))
    results = chart.get("result")
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        raise YahooChartError(symbol, "missing chart.result[0]")
    result = results[0]

    meta = result.get("meta")
    tz_name = meta.get("exchangeTimezoneName") if isinstance(meta, dict) else None
    tz = ZoneInfo(tz_name) if isinstance(tz_name, str) and tz_name else _EASTERN

    timestamps = result.get("timestamp")
    if not isinstance(timestamps, list):
        return []  # a valid-but-barless window (e.g. all-holiday range)
    indicators = result.get("indicators")
    quotes = indicators.get("quote") if isinstance(indicators, dict) else None
    quote = quotes[0] if isinstance(quotes, list) and quotes else None
    if not isinstance(quote, dict):
        raise YahooChartError(symbol, "missing indicators.quote[0]")

    opens = _quote_series(quote, "open")
    highs = _quote_series(quote, "high")
    lows = _quote_series(quote, "low")
    closes = _quote_series(quote, "close")

    out: list[IndexDailyBar] = []
    for i, ts in enumerate(timestamps):
        if not isinstance(ts, int | float):
            continue
        valid_date = datetime.fromtimestamp(float(ts), tz=tz).date()
        out.append(
            IndexDailyBar(
                symbol=symbol,
                valid_date=valid_date,
                open=_number_or_none(opens[i] if i < len(opens) else None),
                high=_number_or_none(highs[i] if i < len(highs) else None),
                low=_number_or_none(lows[i] if i < len(lows) else None),
                close=_number_or_none(closes[i] if i < len(closes) else None),
                source=source,
                fetched_at=fetched_at,
            )
        )
    return out


def _quote_series(quote: dict[str, Any], key: str) -> list[Any]:
    values = quote.get(key)
    return values if isinstance(values, list) else []


def _final_session_bars(bars: list[IndexDailyBar], *, now_utc: datetime) -> list[IndexDailyBar]:
    """Drop the current exchange-local session's bar while it is still live.

    Deterministic in ``now_utc`` so tests can pin both sides of the cutoff.
    """
    now_et = now_utc.astimezone(_EASTERN)
    if now_et.time() >= _SESSION_FINAL_ET:
        return bars
    return [b for b in bars if b.valid_date < now_et.date()]


def _number_or_none(raw: Any) -> float | None:
    """Yahoo quote arrays carry nulls for holidays/halts; coerce defensively."""
    if isinstance(raw, int | float):
        return float(raw)
    return None
