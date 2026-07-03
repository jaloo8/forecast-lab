"""Tests for the Kalshi NFL-game ticker parser + builder.

NFL's mixed 2-/3-char team codes are the interesting case the NBA parser
doesn't handle; the YES token disambiguates the concatenated team block.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from kq.clients.kalshi._parsers import _parse_market
from kq.clients.kalshi._ticker_parser_nfl import (
    NFL_TEAM_ABBRS,
    NflMarketRef,
    build_nfl_market_ticker,
    parse_nfl_market_ticker,
)

# --------------------------- parse ---------------------------


def test_parse_yes_home_three_char_codes() -> None:
    ref = parse_nfl_market_ticker("KXNFLGAME-26JAN04WASPHI-PHI")
    assert ref == NflMarketRef(
        game_date=date(2026, 1, 4),
        away_team_abbr="WAS",
        home_team_abbr="PHI",
        yes_team_abbr="PHI",
        raw_ticker="KXNFLGAME-26JAN04WASPHI-PHI",
    )
    assert ref.yes_is_home is True


def test_parse_yes_away_mixed_length_codes() -> None:
    # LAC @ SF, YES = away (LAC). Block "LACSF" splits via the LAC prefix.
    ref = parse_nfl_market_ticker("KXNFLGAME-26JAN04LACSF-LAC")
    assert ref is not None
    assert ref.away_team_abbr == "LAC"
    assert ref.home_team_abbr == "SF"
    assert ref.yes_team_abbr == "LAC"
    assert ref.yes_is_home is False


def test_parse_two_char_codes_both_sides() -> None:
    # SF @ NE, YES = home (NE). Block "SFNE" splits via the NE suffix.
    ref = parse_nfl_market_ticker("KXNFLGAME-26SEP07SFNE-NE")
    assert ref is not None
    assert ref.away_team_abbr == "SF"
    assert ref.home_team_abbr == "NE"
    assert ref.yes_is_home is True


def test_parse_strips_whitespace() -> None:
    assert parse_nfl_market_ticker("  KXNFLGAME-26JAN04WASPHI-PHI  ") is not None


def test_parse_rejects_unknown_team() -> None:
    assert parse_nfl_market_ticker("KXNFLGAME-26JAN04WASZZ-ZZ") is None


def test_parse_rejects_yes_not_in_matchup() -> None:
    # KC is a real team but not in the WAS/PHI matchup -> no valid split.
    assert parse_nfl_market_ticker("KXNFLGAME-26JAN04WASPHI-KC") is None


def test_parse_rejects_wrong_series() -> None:
    assert parse_nfl_market_ticker("KXNBAGAME-26APR30BOSPHI-PHI") is None


def test_parse_rejects_bad_month() -> None:
    assert parse_nfl_market_ticker("KXNFLGAME-26ZZZ04WASPHI-PHI") is None


def test_parse_rejects_impossible_date() -> None:
    assert parse_nfl_market_ticker("KXNFLGAME-26FEB30WASPHI-PHI") is None


# --------------------------- build (round trip) ---------------------------


def test_build_round_trip_yes_home() -> None:
    ticker = build_nfl_market_ticker(
        game_date=date(2026, 1, 4),
        home_team_abbr="PHI",
        away_team_abbr="WAS",
        yes_team_abbr="PHI",
    )
    assert ticker == "KXNFLGAME-26JAN04WASPHI-PHI"
    assert parse_nfl_market_ticker(ticker) is not None


def test_build_round_trip_two_char() -> None:
    ticker = build_nfl_market_ticker(
        game_date=date(2026, 9, 7),
        home_team_abbr="NE",
        away_team_abbr="SF",
        yes_team_abbr="SF",
    )
    ref = parse_nfl_market_ticker(ticker)
    assert ref is not None
    assert ref.away_team_abbr == "SF"
    assert ref.home_team_abbr == "NE"
    assert ref.yes_is_home is False


def test_build_rejects_unknown_team() -> None:
    with pytest.raises(ValueError, match="unknown NFL team"):
        build_nfl_market_ticker(
            game_date=date(2026, 1, 4),
            home_team_abbr="ZZZ",
            away_team_abbr="WAS",
            yes_team_abbr="WAS",
        )


def test_build_rejects_yes_not_in_matchup() -> None:
    with pytest.raises(ValueError, match="must equal home"):
        build_nfl_market_ticker(
            game_date=date(2026, 1, 4),
            home_team_abbr="PHI",
            away_team_abbr="WAS",
            yes_team_abbr="KC",
        )


# --------------------------- prod verification (2026-07-02) ---------------------------
# The format was UNVERIFIED at design time; on 2026-07-02 live prod listed
# 66 KXNFLGAME markets (33 events) and a page was recorded to
# tests/fixtures/kalshi_prod_markets_nfl.json. These tests pin the parser
# against that recorded reality — including Kalshi's JAC (not ESPN's JAX)
# Jacksonville code and the <AWAY><HOME> ordering confirmed against the
# official 2026 NFL schedule (DAL@NYG and DEN@KC Week 1).

_PROD_FIXTURE = Path(__file__).parent / "fixtures" / "kalshi_prod_markets_nfl.json"


def _prod_markets() -> list[dict[str, object]]:
    payload = json.loads(_PROD_FIXTURE.read_text(encoding="utf-8"))
    markets = payload["markets"]
    assert isinstance(markets, list) and markets
    return markets


def test_every_recorded_prod_ticker_parses() -> None:
    for market in _prod_markets():
        ticker = str(market["ticker"])
        ref = parse_nfl_market_ticker(ticker)
        assert ref is not None, f"prod ticker failed to parse: {ticker}"
        # The YES suffix is always one of the two teams.
        assert ref.yes_team_abbr in (ref.home_team_abbr, ref.away_team_abbr)


def test_prod_tickers_round_trip_through_the_builder() -> None:
    for market in _prod_markets():
        ticker = str(market["ticker"])
        ref = parse_nfl_market_ticker(ticker)
        assert ref is not None
        rebuilt = build_nfl_market_ticker(
            game_date=ref.game_date,
            home_team_abbr=ref.home_team_abbr,
            away_team_abbr=ref.away_team_abbr,
            yes_team_abbr=ref.yes_team_abbr,
        )
        assert rebuilt == ticker


def test_prod_week1_ordering_is_away_then_home() -> None:
    """KXNFLGAME-26SEP13DALNYG is Cowboys AT Giants (Giants host per the
    official 2026 schedule) — pins the <AWAY><HOME> block ordering."""
    ref = parse_nfl_market_ticker("KXNFLGAME-26SEP13DALNYG-NYG")
    assert ref is not None
    assert ref.away_team_abbr == "DAL"
    assert ref.home_team_abbr == "NYG"
    assert ref.game_date == date(2026, 9, 13)
    assert ref.yes_is_home is True


def test_jacksonville_is_jac_not_jax() -> None:
    """Kalshi's Jacksonville code is JAC (observed live 2026-07-02);
    the ESPN-style JAX the parser originally guessed must be rejected."""
    assert "JAC" in NFL_TEAM_ABBRS
    assert "JAX" not in NFL_TEAM_ABBRS
    ref = parse_nfl_market_ticker("KXNFLGAME-26SEP13CLEJAC-JAC")
    assert ref is not None
    assert ref.home_team_abbr == "JAC"
    assert ref.away_team_abbr == "CLE"
    assert parse_nfl_market_ticker("KXNFLGAME-26SEP13CLEJAX-JAX") is None


def test_prod_fixture_prices_parse_through_market_parser() -> None:
    """The recorded prod payload's *_dollars price fields must parse to
    usable [0,1] prices (audit finding #1 class, pinned for NFL)."""
    for raw in _prod_markets():
        market = _parse_market(raw)
        assert market.yes_bid is not None and 0.0 <= market.yes_bid <= 1.0
        assert market.yes_ask is not None and 0.0 <= market.yes_ask <= 1.0
