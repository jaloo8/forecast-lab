"""Tests for the Kalshi NBA-game ticker parser + builder."""

from __future__ import annotations

from datetime import date

import pytest

from kq.clients.kalshi._ticker_parser_nba import (
    NbaMarketRef,
    build_nba_market_ticker,
    parse_nba_market_ticker,
)

# --------------------------- parse_nba_market_ticker ---------------------------


def test_parse_yes_home_ticker() -> None:
    ref = parse_nba_market_ticker("KXNBAGAME-26APR30BOSPHI-PHI")
    assert ref == NbaMarketRef(
        game_date=date(2026, 4, 30),
        away_team_abbr="BOS",
        home_team_abbr="PHI",
        yes_team_abbr="PHI",
        raw_ticker="KXNBAGAME-26APR30BOSPHI-PHI",
    )
    assert ref.yes_is_home is True


def test_parse_yes_away_ticker() -> None:
    ref = parse_nba_market_ticker("KXNBAGAME-26MAY04LALBOS-LAL")
    assert ref is not None
    assert ref.game_date == date(2026, 5, 4)
    assert ref.away_team_abbr == "LAL"
    assert ref.home_team_abbr == "BOS"
    assert ref.yes_team_abbr == "LAL"
    assert ref.yes_is_home is False


def test_parse_strips_surrounding_whitespace() -> None:
    ref = parse_nba_market_ticker("   KXNBAGAME-26APR30BOSPHI-PHI \n")
    assert ref is not None
    assert ref.raw_ticker == "KXNBAGAME-26APR30BOSPHI-PHI"


@pytest.mark.parametrize(
    "ticker",
    [
        "",
        "KXNBAGAME-",
        "KXNBAGAME-INVALID",
        "KXHIGHLAX-26APR30-T75",  # weather, not NBA
        "KXNBAGAME-26ZZZ30BOSPHI-PHI",  # bad month abbr
        "KXNBAGAME-26APR32BOSPHI-PHI",  # invalid day-of-month
        "KXNBAGAME-26APR30BOSPHI-NYK",  # YES side not in matchup
        "KXNBAGAME-26APR30LALLAL-LAL",  # team plays itself
        "KXNBAGAME-26APR30boSPHI-PHI",  # lowercase
        "KXNBAGAME-26APR30BOSPHI",  # missing YES suffix
    ],
)
def test_parse_returns_none_for_malformed(ticker: str) -> None:
    assert parse_nba_market_ticker(ticker) is None


# --------------------------- build_nba_market_ticker ---------------------------


def test_build_yes_home() -> None:
    ticker = build_nba_market_ticker(
        game_date=date(2026, 4, 30),
        home_team_abbr="PHI",
        away_team_abbr="BOS",
        yes_team_abbr="PHI",
    )
    assert ticker == "KXNBAGAME-26APR30BOSPHI-PHI"


def test_build_yes_away() -> None:
    ticker = build_nba_market_ticker(
        game_date=date(2026, 5, 4),
        home_team_abbr="BOS",
        away_team_abbr="LAL",
        yes_team_abbr="LAL",
    )
    assert ticker == "KXNBAGAME-26MAY04LALBOS-LAL"


def test_build_rejects_yes_not_in_matchup() -> None:
    with pytest.raises(ValueError, match="must equal"):
        build_nba_market_ticker(
            game_date=date(2026, 4, 30),
            home_team_abbr="PHI",
            away_team_abbr="BOS",
            yes_team_abbr="NYK",
        )


def test_build_rejects_same_team_both_sides() -> None:
    with pytest.raises(ValueError, match="cannot be the same team"):
        build_nba_market_ticker(
            game_date=date(2026, 4, 30),
            home_team_abbr="LAL",
            away_team_abbr="LAL",
            yes_team_abbr="LAL",
        )


def test_build_rejects_non_3letter_abbr() -> None:
    with pytest.raises(ValueError, match="3 uppercase letters"):
        build_nba_market_ticker(
            game_date=date(2026, 4, 30),
            home_team_abbr="PHI",
            away_team_abbr="bos",  # lowercase
            yes_team_abbr="PHI",
        )


def test_round_trip_all_months() -> None:
    """Sanity: every month value round-trips through build → parse."""
    for month in range(1, 13):
        ticker = build_nba_market_ticker(
            game_date=date(2026, month, 15),
            home_team_abbr="PHI",
            away_team_abbr="BOS",
            yes_team_abbr="PHI",
        )
        parsed = parse_nba_market_ticker(ticker)
        assert parsed is not None
        assert parsed.game_date == date(2026, month, 15)
