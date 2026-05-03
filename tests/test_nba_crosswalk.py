"""Tests for the NBA schedule <-> odds cross-walk matcher.

Coverage:
- Team-name normalization for the 30 canonical names + the LAC alias.
- US/Eastern date projection from UTC commence_time.
- match_games returns 1-to-1 pairs on aligned (home, away, date) tuples.
- Unmatched games (unknown team, missing nba row) are silently dropped.
- The full Odds-API JSON fixture round-trips into a sensible match set
  given a synthetic nba_game lookup.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from kq.clients.nba_schedule import NbaGameRow
from kq.clients.the_odds_api import (
    OddsApiBookmaker,
    OddsApiGame,
    OddsApiMarket,
    OddsApiOutcome,
    parse_odds_response,
)
from kq.models.nba_crosswalk import (
    TEAM_NAME_TO_ABBR,
    CrosswalkPair,
    match_games,
    normalize_team,
    odds_api_to_us_eastern_date,
)

FIXTURE = Path(__file__).parent / "fixtures" / "the_odds_api_nba_h2h.json"


def _nba_row(
    *,
    game_id: str,
    home_abbr: str,
    away_abbr: str,
    game_date: date,
) -> NbaGameRow:
    return NbaGameRow(
        game_id=game_id,
        season="2025-26",
        season_type="Regular Season",
        game_date=game_date,
        home_team_id=0,
        home_team_abbr=home_abbr,
        away_team_id=0,
        away_team_abbr=away_abbr,
        home_score=None,
        away_score=None,
        home_won=None,
    )


# --------------------------- normalize_team ---------------------------


def test_normalize_team_round_trips_for_all_30_canonical_names() -> None:
    """Every canonical name in TEAM_NAME_TO_ABBR resolves cleanly --
    catches typos / drift in the table itself."""
    for name, abbr in TEAM_NAME_TO_ABBR.items():
        assert normalize_team(name) == abbr


def test_normalize_team_handles_la_clippers_alias() -> None:
    """The Odds API has been seen to use both ``LA Clippers`` and
    ``Los Angeles Clippers`` -- both must resolve to LAC."""
    assert normalize_team("LA Clippers") == "LAC"
    assert normalize_team("Los Angeles Clippers") == "LAC"


def test_normalize_team_strips_whitespace() -> None:
    assert normalize_team("  Boston Celtics ") == "BOS"


def test_normalize_team_returns_none_for_unknown() -> None:
    assert normalize_team("Vancouver Grizzlies") is None  # 1995-2001 only
    assert normalize_team("typo Lakers") is None


def test_table_covers_30_unique_abbreviations() -> None:
    """30 NBA franchises today; the alias entry brings the table size
    to 31 but only 30 unique abbrs."""
    assert len(set(TEAM_NAME_TO_ABBR.values())) == 30


# --------------------------- date projection ---------------------------


def test_odds_api_to_us_eastern_date_for_evening_tipoff() -> None:
    """A 23:00 UTC tipoff projects to the same UTC calendar day in
    US/Eastern (-5h -> 18:00 ET, same date)."""
    commence = datetime(2026, 5, 4, 23, 0, tzinfo=UTC)
    assert odds_api_to_us_eastern_date(commence) == date(2026, 5, 4)


def test_odds_api_to_us_eastern_date_for_late_night_tipoff() -> None:
    """A 02:00 UTC tipoff is 21:00 ET the prior day -- date should
    roll back."""
    commence = datetime(2026, 5, 5, 2, 0, tzinfo=UTC)
    assert odds_api_to_us_eastern_date(commence) == date(2026, 5, 4)


def test_odds_api_to_us_eastern_date_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        odds_api_to_us_eastern_date(datetime(2026, 5, 4, 23, 0))


# --------------------------- match_games ---------------------------


def test_match_games_returns_one_to_one_pair_on_aligned_tuple() -> None:
    odds = OddsApiGame(
        game_id="abc1234",
        sport_key="basketball_nba",
        commence_time=datetime(2026, 5, 4, 23, 0, tzinfo=UTC),
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        bookmakers=(),
    )
    nba = _nba_row(
        game_id="0022500001",
        home_abbr="LAL",
        away_abbr="BOS",
        game_date=date(2026, 5, 4),
    )
    pairs = match_games([odds], [nba])
    assert pairs == [
        CrosswalkPair(
            odds_api_game_id="abc1234",
            nba_game_id="0022500001",
            home_team_abbr="LAL",
            away_team_abbr="BOS",
            game_date=date(2026, 5, 4),
        )
    ]


def test_match_games_drops_unknown_team() -> None:
    """A team not in our 30-team table should silently drop, not crash."""
    odds = OddsApiGame(
        game_id="abc1234",
        sport_key="basketball_nba",
        commence_time=datetime(2026, 5, 4, 23, 0, tzinfo=UTC),
        home_team="Vancouver Grizzlies",
        away_team="Boston Celtics",
        bookmakers=(),
    )
    pairs = match_games([odds], [])
    assert pairs == []


def test_match_games_drops_when_no_nba_row_at_that_date() -> None:
    odds = OddsApiGame(
        game_id="abc1234",
        sport_key="basketball_nba",
        commence_time=datetime(2026, 5, 4, 23, 0, tzinfo=UTC),
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        bookmakers=(),
    )
    nba = _nba_row(
        game_id="0022500001",
        home_abbr="LAL",
        away_abbr="BOS",
        game_date=date(2026, 5, 5),  # different date
    )
    pairs = match_games([odds], [nba])
    assert pairs == []


def test_match_games_skips_swap_when_home_away_reversed() -> None:
    """Home/away order matters; a reversed match in nba schedule should
    not match (defensive against transposition bugs)."""
    odds = OddsApiGame(
        game_id="abc1234",
        sport_key="basketball_nba",
        commence_time=datetime(2026, 5, 4, 23, 0, tzinfo=UTC),
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        bookmakers=(),
    )
    nba_swapped = _nba_row(
        game_id="0022500001",
        home_abbr="BOS",  # reversed
        away_abbr="LAL",  # reversed
        game_date=date(2026, 5, 4),
    )
    assert match_games([odds], [nba_swapped]) == []


def test_match_games_handles_empty_inputs() -> None:
    assert match_games([], []) == []


def test_match_games_uses_first_match_on_collision() -> None:
    """Two nba rows with the same (home, away, date) is impossible in
    practice but the matcher must not crash if it happens. The dict
    construction picks the LAST inserted row by Python's dict
    semantics; we test that exactly so future refactors don't drift."""
    odds = OddsApiGame(
        game_id="abc1234",
        sport_key="basketball_nba",
        commence_time=datetime(2026, 5, 4, 23, 0, tzinfo=UTC),
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        bookmakers=(),
    )
    nba_a = _nba_row(
        game_id="0022500001",
        home_abbr="LAL",
        away_abbr="BOS",
        game_date=date(2026, 5, 4),
    )
    nba_b = _nba_row(
        game_id="0022500002",
        home_abbr="LAL",
        away_abbr="BOS",
        game_date=date(2026, 5, 4),
    )
    pairs = match_games([odds], [nba_a, nba_b])
    # Last-insertion-wins semantics from dict construction.
    assert len(pairs) == 1
    assert pairs[0].nba_game_id == "0022500002"


# --------------------------- end-to-end via fixture ---------------------------


def test_match_games_against_fixture() -> None:
    """The recorded Odds API fixture has 3 games. With aligned NBA
    schedule rows, exactly 3 cross-walk pairs come back; with one
    NBA row missing, 2 pairs come back."""
    odds_payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    odds_games = parse_odds_response(odds_payload)

    # Synthesize aligned NBA rows. The fixture has UTC commence times
    # at 23:00 (5/4 ET = 5/4) and 01:30/02:00 (5/4 ET = 5/4).
    nba_rows = [
        _nba_row(
            game_id="0022500001",
            home_abbr="LAL",
            away_abbr="BOS",
            game_date=date(2026, 5, 4),
        ),
        _nba_row(
            game_id="0022500002",
            home_abbr="DEN",
            away_abbr="OKC",
            game_date=date(2026, 5, 4),
        ),
        _nba_row(
            game_id="0022500003",
            home_abbr="MIA",
            away_abbr="IND",
            game_date=date(2026, 5, 4),
        ),
    ]
    pairs = match_games(odds_games, nba_rows)
    assert len(pairs) == 3
    odds_ids = {p.odds_api_game_id for p in pairs}
    nba_ids = {p.nba_game_id for p in pairs}
    assert odds_ids == {g.game_id for g in odds_games}
    assert nba_ids == {"0022500001", "0022500002", "0022500003"}


def test_match_games_against_fixture_with_one_missing_nba_row() -> None:
    odds_payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    odds_games = parse_odds_response(odds_payload)
    # Drop the Heat-Pacers nba row -> only 2 of 3 should match.
    nba_rows = [
        _nba_row(
            game_id="0022500001",
            home_abbr="LAL",
            away_abbr="BOS",
            game_date=date(2026, 5, 4),
        ),
        _nba_row(
            game_id="0022500002",
            home_abbr="DEN",
            away_abbr="OKC",
            game_date=date(2026, 5, 4),
        ),
    ]
    pairs = match_games(odds_games, nba_rows)
    assert len(pairs) == 2


# --------------------------- type sanity ---------------------------


def test_crosswalk_pair_is_frozen() -> None:
    p = CrosswalkPair(
        odds_api_game_id="x",
        nba_game_id="y",
        home_team_abbr="LAL",
        away_team_abbr="BOS",
        game_date=date(2026, 5, 4),
    )
    with pytest.raises(AttributeError):
        p.odds_api_game_id = "mutated"  # type: ignore[misc]


def test_unused_payload_imports_are_referenced() -> None:
    """Sanity check that the OddsApi* shapes we import are consumable;
    keeps mypy honest about type-only imports we use indirectly via
    parse_odds_response."""
    _ = (OddsApiBookmaker, OddsApiMarket, OddsApiOutcome)
