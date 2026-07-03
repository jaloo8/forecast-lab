"""Tests for the Kalshi index-brackets ticker parser + strike discipline.

Pinned against the recorded 2026-07-02 prod payload
(``tests/fixtures/kalshi_prod_markets_index.json``): if Kalshi changes the
KXINX / KXNASDAQ100 format, update ``_ticker_parser_index.py`` AND refresh
the fixture from prod — never adjust the parser to unverified guesses.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from kq.clients.kalshi._parsers import _parse_market
from kq.clients.kalshi._ticker_parser_index import (
    INDEX_SERIES_TO_SYMBOL,
    INDEX_STRIKE_HALF_WIDTH,
    parse_index_market_ticker,
)
from kq.clients.kalshi.strikes import Strike, strike_from_market, yes_outcome, yes_prob

_FIXTURE = Path(__file__).parent / "fixtures" / "kalshi_prod_markets_index.json"


def _fixture() -> dict[str, Any]:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _fixture_markets(key: str) -> list[dict[str, Any]]:
    markets = _fixture()[key]["markets"]
    assert isinstance(markets, list) and markets
    return markets


# --------------------------- parsing ---------------------------


def test_parse_between_ticker_normal_close() -> None:
    ref = parse_index_market_ticker("KXINX-26JUL01H1600-B7337")
    assert ref is not None
    assert ref.symbol == "SPX"
    assert ref.series_ticker == "KXINX"
    assert ref.valid_date == date(2026, 7, 1)
    assert ref.close_hhmm_et == "1600"
    assert ref.kind == "B"
    assert ref.ticker_value == pytest.approx(7337.0)


def test_parse_tail_ticker_early_close_with_decimals() -> None:
    """Jul 2, 2026 was a 1pm-ET early close (pre-July-4th) — the hour
    component is session-dependent, and tail strikes carry decimals."""
    ref = parse_index_market_ticker("KXINX-26JUL02H1300-T7824.9999")
    assert ref is not None
    assert ref.valid_date == date(2026, 7, 2)
    assert ref.close_hhmm_et == "1300"
    assert ref.kind == "T"
    assert ref.ticker_value == pytest.approx(7824.9999)


def test_parse_nasdaq_ticker() -> None:
    ref = parse_index_market_ticker("KXNASDAQ100-26JUL01H1600-B31550")
    assert ref is not None
    assert ref.symbol == "NDX"
    assert ref.series_ticker == "KXNASDAQ100"


@pytest.mark.parametrize(
    "ticker",
    [
        "KXHIGHLAX-26APR30-T75",  # weather, no hour component
        "KXINXU-26JUL02H1200-T7800",  # hourly above/below series — different lane
        "KXINX-26JUL02-B7812",  # missing hour component
        "KXINX-26XXX02H1600-B7812",  # bad month
        "KXINX-26JUL02H1600-Z7812",  # unknown kind letter
        "",
    ],
)
def test_parse_rejects_non_index_formats(ticker: str) -> None:
    assert parse_index_market_ticker(ticker) is None


def test_parse_rejects_impossible_calendar_date() -> None:
    assert parse_index_market_ticker("KXINX-26FEB30H1600-B7812") is None


@pytest.mark.parametrize("key", ["sp500", "nasdaq100"])
def test_every_recorded_prod_ticker_parses(key: str) -> None:
    markets = _fixture_markets(key)
    for m in markets:
        ref = parse_index_market_ticker(str(m["ticker"]))
        assert ref is not None, f"prod ticker failed to parse: {m['ticker']}"
        assert ref.series_ticker in INDEX_SERIES_TO_SYMBOL
        assert ref.valid_date.year == 2026


# --------------------------- strike semantics from API fields ---------------------------


@pytest.mark.parametrize("key", ["sp500", "nasdaq100"])
def test_strike_builds_from_recorded_api_fields(key: str) -> None:
    """Strike is unit-agnostic: the same API-fields path weather uses must
    accept index-point strikes (ref=None: the WeatherMarketRef cross-check
    doesn't apply to this lane)."""
    for raw in _fixture_markets(key):
        market = _parse_market(raw)
        strike = strike_from_market(market, None)
        assert strike is not None, f"ineligible strike for {market.ticker}"
        assert strike.kind in ("greater", "less", "between")


def test_recorded_between_market_has_venue_cap_encoding() -> None:
    """The .9999-style cap (floor of the NEXT bracket minus epsilon) is the
    venue's boundary encoding — pin it so drift is loud."""
    betweens = [
        _parse_market(m) for m in _fixture_markets("sp500") if m.get("strike_type") == "between"
    ]
    assert betweens
    m = betweens[0]
    assert m.floor_strike is not None and m.cap_strike is not None
    width = 25.0
    assert m.cap_strike == pytest.approx(m.floor_strike + width - 0.0001)


# ----------------------- half-boundary discipline (index half-width) -----------------------

_SP_BETWEEN = Strike(kind="between", floor=7800.0, cap=7824.9999)
_SP_GREATER = Strike(kind="greater", floor=7824.9999, cap=None)
_SP_LESS = Strike(kind="less", floor=None, cap=7125.0)
_NDX_BETWEEN = Strike(kind="between", floor=31500.0, cap=31599.99)
_NDX_GREATER = Strike(kind="greater", floor=31599.99, cap=None)


@pytest.mark.parametrize(
    ("strike", "observed", "expected"),
    [
        # S&P between [7800, 7825): boundary prints land on the right side
        (_SP_BETWEEN, 7800.00, True),
        (_SP_BETWEEN, 7824.99, True),
        (_SP_BETWEEN, 7825.00, False),
        (_SP_BETWEEN, 7799.99, False),
        # S&P greater ("7,825 or above")
        (_SP_GREATER, 7825.00, True),
        (_SP_GREATER, 7824.99, False),
        # S&P less ("7,124.9999 or below")
        (_SP_LESS, 7124.99, True),
        (_SP_LESS, 7125.00, False),
        # Nasdaq's coarser .99 cap encoding settles with the SAME half-width
        (_NDX_BETWEEN, 31599.99, True),
        (_NDX_BETWEEN, 31600.00, False),
        (_NDX_GREATER, 31600.00, True),
        (_NDX_GREATER, 31599.99, False),
    ],
)
def test_index_half_width_settles_boundary_prints(
    strike: Strike, observed: float, expected: bool
) -> None:
    assert yes_outcome(strike, observed, half_width=INDEX_STRIKE_HALF_WIDTH) is expected


def test_weather_default_half_width_would_misplace_index_boundaries() -> None:
    """The regression this lane exists to prevent: pricing/settling index
    strikes with the weather 0.5° half-width puts a 7825.00 print in the
    WRONG bracket (both the between below it and the greater above it)."""
    assert yes_outcome(_SP_BETWEEN, 7825.00) is True  # wrong under weather default
    assert yes_outcome(_SP_GREATER, 7825.00) is False  # wrong under weather default
    # ... and exactly-one-YES holds only under the index half-width:
    hits = [
        yes_outcome(s, 7825.00, half_width=INDEX_STRIKE_HALF_WIDTH)
        for s in (_SP_BETWEEN, _SP_GREATER)
    ]
    assert hits == [False, True]


def test_yes_prob_uses_half_width_boundaries() -> None:
    """A point-mass-free continuous CDF must price the between bracket as
    CDF(cap+h) - CDF(floor-h); with a step exceedance function centered
    inside the bracket the probability is 1 (both boundaries clip at 0.99)."""

    def prob_gt(x: float) -> float:
        return 1.0 if x < 7810.0 else 0.0

    p = yes_prob(_SP_BETWEEN, prob_gt, half_width=INDEX_STRIKE_HALF_WIDTH)
    assert p == pytest.approx(0.99)  # clipped per project convention
    p_tail = yes_prob(_SP_GREATER, prob_gt, half_width=INDEX_STRIKE_HALF_WIDTH)
    assert p_tail == pytest.approx(0.01)
