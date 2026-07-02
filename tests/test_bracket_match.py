"""Tests for matching generated brackets to live Kalshi market tickers."""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime

import pytest

from kq.backtest.bracket_match import (
    find_matching_market,
    match_brackets,
    parsed_weather_markets,
)
from kq.backtest.brackets import Bracket
from kq.clients.kalshi import Market, build_weather_market_ticker


def _market(
    ticker: str,
    *,
    open_time: datetime | None = None,
) -> Market:
    return Market(
        ticker=ticker,
        event_ticker=ticker.rsplit("-", 1)[0],
        title=f"market {ticker}",
        status="open",
        category=None,
        yes_ask=0.40,
        yes_bid=0.38,
        last_price=0.39,
        volume=100,
        open_interest=50,
        open_time=open_time,
        close_time=None,
        expected_expiration_time=None,
        rules_primary=None,
    )


def test_parsed_weather_markets_filters_non_weather() -> None:
    """Only the weather tickers come through; NBA/MLB/garbage dropped."""
    inputs = [
        _market("KXHIGHLAX-26APR30-T75"),
        _market("KXHIGHLAX-26APR30-T77"),
        _market("KXNBAGAME-26APR30BOSPHI-PHI"),
        _market("KXMLBSPREAD-26APR291507BOSTOR-TOR4"),
        _market("not-a-real-ticker"),
    ]
    out = parsed_weather_markets(inputs)
    assert len(out) == 2
    tickers = {market.ticker for market, _ref, _strike in out}
    assert tickers == {"KXHIGHLAX-26APR30-T75", "KXHIGHLAX-26APR30-T77"}


def test_parsed_weather_markets_admits_all_three_strike_types() -> None:
    """PR-B: greater, less, AND between markets are all tradeable when the
    API strike fields are present and agree with the ticker."""
    greater = dataclasses.replace(
        _market("KXHIGHLAX-26JUN12-T81"), strike_type="greater", floor_strike=81.0
    )
    less = dataclasses.replace(
        _market("KXHIGHLAX-26JUN12-T74"), strike_type="less", cap_strike=74.0
    )
    between = dataclasses.replace(
        _market("KXHIGHLAX-26JUN12-B78.5"),
        strike_type="between",
        floor_strike=78.0,
        cap_strike=79.0,
    )
    # Ticker text disagreeing with API strike fields is refused.
    inconsistent = dataclasses.replace(
        _market("KXHIGHLAX-26JUN12-T81"), strike_type="greater", floor_strike=79.0
    )
    out = parsed_weather_markets([greater, less, between, inconsistent])
    kinds = {strike.kind for _m, _ref, strike in out}
    assert len(out) == 3
    assert kinds == {"greater", "less", "between"}


def test_find_matching_market_simple() -> None:
    markets = [
        _market("KXHIGHLAX-26APR30-T73"),
        _market("KXHIGHLAX-26APR30-T75"),
        _market("KXHIGHLAX-26APR30-T77"),
    ]
    parsed = parsed_weather_markets(markets)
    bracket = Bracket(threshold_f=75.0)
    match = find_matching_market(
        bracket, icao="KLAX", valid_date=date(2026, 4, 30), weather_markets=parsed
    )
    assert match is not None
    assert match.ticker == "KXHIGHLAX-26APR30-T75"


def test_find_matching_market_no_match_returns_none() -> None:
    markets = [_market("KXHIGHLAX-26APR30-T75")]
    parsed = parsed_weather_markets(markets)

    # Wrong threshold
    assert find_matching_market(
        Bracket(threshold_f=80.0),
        icao="KLAX",
        valid_date=date(2026, 4, 30),
        weather_markets=parsed,
    ) is None  # fmt: skip

    # Wrong date
    assert find_matching_market(
        Bracket(threshold_f=75.0),
        icao="KLAX",
        valid_date=date(2026, 5, 1),
        weather_markets=parsed,
    ) is None  # fmt: skip

    # Wrong station
    assert find_matching_market(
        Bracket(threshold_f=75.0),
        icao="KNYC",
        valid_date=date(2026, 4, 30),
        weather_markets=parsed,
    ) is None  # fmt: skip


def test_find_matching_market_threshold_int_round() -> None:
    """Bracket thresholds are floats but must match int Kalshi thresholds."""
    markets = [_market("KXHIGHLAX-26APR30-T75")]
    parsed = parsed_weather_markets(markets)
    # Float 75.0 should match int 75
    assert find_matching_market(
        Bracket(threshold_f=75.0),
        icao="KLAX",
        valid_date=date(2026, 4, 30),
        weather_markets=parsed,
    ) is not None  # fmt: skip
    # Float 75.4 rounds to 75 → match
    assert find_matching_market(
        Bracket(threshold_f=75.4),
        icao="KLAX",
        valid_date=date(2026, 4, 30),
        weather_markets=parsed,
    ) is not None  # fmt: skip
    # Float 75.6 rounds to 76 → no match
    assert find_matching_market(
        Bracket(threshold_f=75.6),
        icao="KLAX",
        valid_date=date(2026, 4, 30),
        weather_markets=parsed,
    ) is None  # fmt: skip


def test_find_matching_market_prefers_recently_opened_on_duplicates() -> None:
    """Defensive: if two markets have the same parsed key, take most-recent open_time."""
    older = _market("KXHIGHLAX-26APR30-T75", open_time=datetime(2026, 4, 1, tzinfo=UTC))
    newer = _market("KXHIGHLAX-26APR30-T75", open_time=datetime(2026, 4, 28, tzinfo=UTC))
    markets = [older, newer]
    parsed = parsed_weather_markets(markets)
    result = find_matching_market(
        Bracket(threshold_f=75.0),
        icao="KLAX",
        valid_date=date(2026, 4, 30),
        weather_markets=parsed,
    )
    assert result is newer


def test_match_brackets_full_set() -> None:
    """End-to-end: 7 brackets, 5 of which have matching markets."""
    brackets = [
        Bracket(threshold_f=70.0),  # match
        Bracket(threshold_f=72.0),  # match
        Bracket(threshold_f=74.0),  # NO match (gap)
        Bracket(threshold_f=76.0),  # match
        Bracket(threshold_f=78.0),  # match
        Bracket(threshold_f=80.0),  # match
        Bracket(threshold_f=82.0),  # NO match
    ]
    markets = [
        _market("KXHIGHLAX-26APR30-T70"),
        _market("KXHIGHLAX-26APR30-T72"),
        _market("KXHIGHLAX-26APR30-T76"),
        _market("KXHIGHLAX-26APR30-T78"),
        _market("KXHIGHLAX-26APR30-T80"),
    ]
    out = match_brackets(
        brackets, icao="KLAX", valid_date=date(2026, 4, 30), kalshi_markets=markets
    )
    assert len(out) == 7
    matched = {b: m for b, m in out.items() if m is not None}
    unmatched = {b for b, m in out.items() if m is None}
    assert {b.threshold_f for b in matched} == {70.0, 72.0, 76.0, 78.0, 80.0}
    assert {b.threshold_f for b in unmatched} == {74.0, 82.0}


def test_match_brackets_with_no_kalshi_data() -> None:
    """All brackets are unmatched when there are no markets to match against."""
    brackets = [Bracket(threshold_f=70.0), Bracket(threshold_f=75.0)]
    out = match_brackets(
        brackets,
        icao="KLAX",
        valid_date=date(2026, 4, 30),
        kalshi_markets=[],
    )
    assert all(v is None for v in out.values())


def test_match_brackets_ignores_non_weather_markets() -> None:
    """NBA/MLB tickers don't accidentally match weather brackets."""
    brackets = [Bracket(threshold_f=75.0)]
    markets = [
        _market("KXNBAGAME-26APR30BOSPHI-PHI"),
        _market("KXMLBSPREAD-26APR291507BOSTOR-TOR4"),
    ]
    out = match_brackets(
        brackets, icao="KLAX", valid_date=date(2026, 4, 30), kalshi_markets=markets
    )
    assert out[brackets[0]] is None


# KNYC not KJFK since PR-C (2026-06-11 audit root cause #4: KXHIGHNY
# settles on Central Park).
@pytest.mark.parametrize("icao", ["KLAX", "KNYC", "KMDW", "KMIA", "KDEN", "KAUS"])
def test_match_works_for_all_six_stations(icao: str) -> None:
    """End-to-end across every station ICAO we support."""
    target_date = date(2026, 6, 15)
    threshold = 80
    market = _market(build_weather_market_ticker(icao, target_date, threshold))
    parsed = parsed_weather_markets([market])
    bracket = Bracket(threshold_f=float(threshold))
    result = find_matching_market(
        bracket, icao=icao, valid_date=target_date, weather_markets=parsed
    )
    assert result is market
