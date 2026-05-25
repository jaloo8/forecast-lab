"""Tests for the Kalshi NFL-game ticker parser + builder.

NFL's mixed 2-/3-char team codes are the interesting case the NBA parser
doesn't handle; the YES token disambiguates the concatenated team block.
"""

from __future__ import annotations

from datetime import date

import pytest

from kq.clients.kalshi._ticker_parser_nfl import (
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
