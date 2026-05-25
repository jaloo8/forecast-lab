"""Tests for the Kalshi PGA (golf) tournament-winner ticker parser + builder.

The event layer (tournament code + year) is the reliable part; the per-player
slug is unverified and treated as an opaque trailing segment. These tests pin
current behavior — they are NOT a claim the prod format matches.
"""

from __future__ import annotations

import pytest

from kq.clients.kalshi._ticker_parser_pga import (
    PgaMarketRef,
    build_pga_market_ticker,
    parse_pga_market_ticker,
)

# --------------------------- parse ---------------------------


def test_parse_event_level_ticker() -> None:
    ref = parse_pga_market_ticker("KXPGATOUR-PGC26")
    assert ref == PgaMarketRef(
        event_code="PGC26",
        tournament_code="PGC",
        year=2026,
        player_slug=None,
        raw_ticker="KXPGATOUR-PGC26",
    )
    assert ref.tournament_name == "PGA Championship"
    assert ref.is_player_contract is False


def test_parse_player_contract_ticker() -> None:
    ref = parse_pga_market_ticker("KXPGATOUR-USO26-SCHEFFLER")
    assert ref is not None
    assert ref.tournament_code == "USO"
    assert ref.year == 2026
    assert ref.player_slug == "SCHEFFLER"
    assert ref.is_player_contract is True
    assert ref.tournament_name == "US Open"


def test_parse_unknown_tournament_code_still_parses() -> None:
    ref = parse_pga_market_ticker("KXPGATOUR-XYZ27")
    assert ref is not None
    assert ref.tournament_code == "XYZ"
    assert ref.year == 2027
    assert ref.tournament_name is None


def test_parse_strips_whitespace() -> None:
    assert parse_pga_market_ticker("  KXPGATOUR-PGC26  ") is not None


def test_parse_rejects_wrong_series() -> None:
    assert parse_pga_market_ticker("KXNBAGAME-26APR30BOSPHI-PHI") is None


def test_parse_rejects_missing_year() -> None:
    assert parse_pga_market_ticker("KXPGATOUR-PGC") is None


def test_parse_rejects_bare_prefix() -> None:
    assert parse_pga_market_ticker("KXPGATOUR-") is None


# --------------------------- build (round trip) ---------------------------


def test_build_event_level_round_trip() -> None:
    ticker = build_pga_market_ticker(tournament_code="PGC", year=2026)
    assert ticker == "KXPGATOUR-PGC26"
    assert parse_pga_market_ticker(ticker) == PgaMarketRef(
        event_code="PGC26",
        tournament_code="PGC",
        year=2026,
        player_slug=None,
        raw_ticker="KXPGATOUR-PGC26",
    )


def test_build_player_round_trip() -> None:
    ticker = build_pga_market_ticker(tournament_code="USO", year=2026, player_slug="SCHEFFLER")
    assert ticker == "KXPGATOUR-USO26-SCHEFFLER"
    ref = parse_pga_market_ticker(ticker)
    assert ref is not None
    assert ref.player_slug == "SCHEFFLER"


def test_build_rejects_lowercase_code() -> None:
    with pytest.raises(ValueError, match="tournament_code"):
        build_pga_market_ticker(tournament_code="pgc", year=2026)


def test_build_rejects_bad_player_slug() -> None:
    with pytest.raises(ValueError, match="player_slug"):
        build_pga_market_ticker(tournament_code="PGC", year=2026, player_slug="scheffler!")
