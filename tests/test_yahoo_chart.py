"""Tests for the Yahoo chart daily-OHLC client (Phase C index lane).

Parse logic is pinned against the recorded 2026-07-02 live payload
(``tests/fixtures/yahoo_chart_index_daily.json``). The endpoint is
unofficial: if the shape drifts, refresh the fixture from a live pull and
update ``_parse_chart_payload`` — never hand-edit the fixture to match the
parser.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from kq.clients.yahoo_chart import (
    IndexDailyBar,
    YahooChartClient,
    YahooChartError,
    _final_session_bars,
    _number_or_none,
    _parse_chart_payload,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "yahoo_chart_index_daily.json"
_FETCHED = datetime(2026, 7, 2, 23, 0, tzinfo=UTC)


def _payload(key: str) -> dict[str, Any]:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))[key]


def test_parse_recorded_sp500_payload() -> None:
    bars = _parse_chart_payload(_payload("sp500"), symbol="SPX", fetched_at=_FETCHED)
    assert bars, "recorded payload produced no bars"
    assert {b.symbol for b in bars} == {"SPX"}
    assert {b.source for b in bars} == {"yahoo_chart"}
    last = bars[-1]
    # Recorded 2026-07-02: ^GSPC closed 7483.24 (matches the live probe).
    assert last.valid_date == date(2026, 7, 2)
    assert last.close == pytest.approx(7483.24, abs=0.01)
    assert last.high is not None and last.low is not None
    assert last.low <= last.close <= last.high
    # Bar timestamps are exchange-local session dates — strictly increasing.
    dates = [b.valid_date for b in bars]
    assert dates == sorted(dates) and len(set(dates)) == len(dates)


def test_parse_recorded_nasdaq_payload() -> None:
    bars = _parse_chart_payload(_payload("nasdaq100"), symbol="NDX", fetched_at=_FETCHED)
    assert bars[-1].close == pytest.approx(29329.21, abs=0.01)


def test_parse_error_body_raises_typed_error() -> None:
    """An HTTP-200 error envelope is an OUTAGE, not zero rows (ACIS lesson)."""
    payload = {"chart": {"result": None, "error": {"code": "Not Found"}}}
    with pytest.raises(YahooChartError, match="Not Found"):
        _parse_chart_payload(payload, symbol="SPX", fetched_at=_FETCHED)


def test_parse_missing_envelope_raises() -> None:
    with pytest.raises(YahooChartError):
        _parse_chart_payload({"nope": 1}, symbol="SPX", fetched_at=_FETCHED)


def test_parse_tolerates_null_quote_entries() -> None:
    payload = _payload("sp500")
    quote = payload["chart"]["result"][0]["indicators"]["quote"][0]
    quote["close"][0] = None  # vendor null (holiday/halt) — bar kept, close=None
    bars = _parse_chart_payload(payload, symbol="SPX", fetched_at=_FETCHED)
    assert bars[0].close is None
    assert bars[1].close is not None


def test_final_session_bars_drops_live_partial_before_close() -> None:
    def bar(d: date) -> IndexDailyBar:
        return IndexDailyBar(
            symbol="SPX",
            valid_date=d,
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            source="yahoo_chart",
            fetched_at=_FETCHED,
        )

    bars = [bar(date(2026, 7, 1)), bar(date(2026, 7, 2))]
    # 15:00 UTC on Jul 2 = 11:00 ET — mid-session: today's bar is a live partial.
    mid_session = datetime(2026, 7, 2, 15, 0, tzinfo=UTC)
    assert [b.valid_date for b in _final_session_bars(bars, now_utc=mid_session)] == [
        date(2026, 7, 1)
    ]
    # 21:00 UTC = 17:00 ET — past the 16:15 settle buffer: bar is final.
    post_close = datetime(2026, 7, 2, 21, 0, tzinfo=UTC)
    assert _final_session_bars(bars, now_utc=post_close) == bars


def test_fetch_daily_validates_inputs_and_round_trips() -> None:
    async def run() -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(200, json=_payload("sp500"))

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = YahooChartClient(http)
            with pytest.raises(ValueError, match="unknown index symbol"):
                await client.fetch_daily(
                    "SPY", start_date=date(2026, 6, 1), end_date=date(2026, 6, 30)
                )
            with pytest.raises(ValueError, match="precedes"):
                await client.fetch_daily(
                    "SPX", start_date=date(2026, 6, 30), end_date=date(2026, 6, 1)
                )
            bars = await client.fetch_daily(
                "SPX", start_date=date(2026, 6, 25), end_date=date(2026, 7, 2)
            )
        assert bars
        assert "%5EGSPC" in seen["url"] or "^GSPC" in seen["url"]
        assert "interval=1d" in seen["url"]

    asyncio.run(run())


def test_number_or_none() -> None:
    assert _number_or_none(7483.24) == pytest.approx(7483.24)
    assert _number_or_none(7483) == pytest.approx(7483.0)
    assert _number_or_none(None) is None
    assert _number_or_none("7483.24") is None  # strings are wire junk here
