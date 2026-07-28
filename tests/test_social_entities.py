"""Tests for conservative social-post entity matching (Phase S1).

Titles used in the happy paths are the REAL post titles from the recorded
2026-07-27 fixtures (tests/fixtures/social/) — the matcher must work on
what the venues actually publish, punctuation and all.
"""

from __future__ import annotations

from kq.models.social_entities import (
    ENTITY_NBA_TEAM,
    ENTITY_NFL_PLAYER,
    ENTITY_NFL_TEAM,
    SocialEntityMatcher,
    normalize_match_text,
)

PLAYERS = [
    ("Alec Pierce", "00-0037247"),
    ("Patrick Mahomes", "00-0033873"),
    ("D.J. Williams", "00-0099999"),
    ("Marvin Harrison Jr.", "00-0039918"),
]


def test_player_match_on_real_reddit_title() -> None:
    matcher = SocialEntityMatcher(PLAYERS)
    m = matcher.match(
        "[Schefter] Colts placed WR Alec Pierce on the Active/Physically Unable to Perform list"
    )
    assert m is not None
    assert m.entity_type == ENTITY_NFL_PLAYER
    assert m.entity_id == "00-0037247"


def test_player_match_survives_punctuated_names() -> None:
    """'D.J. Williams' — periods removed on BOTH sides, so the needle 'dj
    williams' hits the real '[Highlight] Broncos LB D.J. Williams said...'
    title."""
    matcher = SocialEntityMatcher(PLAYERS)
    m = matcher.match("[Highlight] Broncos LB D.J. Williams said that Chargers FB Lorenzo Neal...")
    assert m is not None
    assert m.entity_id == "00-0099999"


def test_player_match_suffix_stripped_both_ways() -> None:
    matcher = SocialEntityMatcher(PLAYERS)
    for title in (
        "Marvin Harrison Jr. limited in practice",
        "Marvin Harrison limited in practice",
    ):
        m = matcher.match(title)
        assert m is not None and m.entity_id == "00-0039918"


def test_no_fuzzy_matching_word_boundaries_hold() -> None:
    matcher = SocialEntityMatcher(PLAYERS)
    assert matcher.match("Alec Piercee had a great day") is None
    assert matcher.match("Alec") is None


def test_normalized_name_collision_refuses_both() -> None:
    matcher = SocialEntityMatcher([("Michael Thomas", "id_a"), ("Michael Thomas", "id_b")])
    assert matcher.match("Michael Thomas questionable") is None


def test_same_name_same_id_is_not_a_collision() -> None:
    matcher = SocialEntityMatcher([("Odell Beckham Jr.", "id_x"), ("Odell Beckham", "id_x")])
    m = matcher.match("Odell Beckham to work out")
    assert m is not None and m.entity_id == "id_x"


def test_single_token_names_are_dropped() -> None:
    matcher = SocialEntityMatcher([("Cher", "id_c")])
    assert matcher.match("Cher announces tour") is None


def test_nfl_team_full_name_matches_real_title() -> None:
    matcher = SocialEntityMatcher()
    m = matcher.match(
        "The Miami Dolphins announced today that they have signed former #4 overall "
        "pick Clelin Ferrell"
    )
    assert m is not None
    assert m.entity_type == ENTITY_NFL_TEAM
    assert m.entity_id == "MIA"


def test_team_nicknames_alone_do_not_match() -> None:
    """v0 policy: nickname-only mentions ('Colts', 'Heat', 'Jazz') stay
    unmatched — several NBA nicknames are ordinary words. Documented gap."""
    matcher = SocialEntityMatcher()
    assert matcher.match("Colts open training camp") is None
    assert matcher.match("Heat wave hits the midwest") is None


def test_nba_team_full_name_and_alternate_spelling() -> None:
    matcher = SocialEntityMatcher()
    m1 = matcher.match("Los Angeles Lakers acquire a second-round pick")
    assert m1 is not None and (m1.entity_type, m1.entity_id) == (ENTITY_NBA_TEAM, "LAL")
    m2 = matcher.match("LA Clippers waive two players")
    assert m2 is not None and m2.entity_id == "LAC"


def test_player_beats_team_priority() -> None:
    matcher = SocialEntityMatcher(PLAYERS)
    m = matcher.match("Kansas City Chiefs restructure Patrick Mahomes deal")
    assert m is not None
    assert m.entity_type == ENTITY_NFL_PLAYER
    assert m.entity_id == "00-0033873"


def test_earliest_mention_wins_within_a_tier() -> None:
    matcher = SocialEntityMatcher(PLAYERS)
    m = matcher.match("Patrick Mahomes finds Alec Pierce impressive")
    assert m is not None and m.entity_id == "00-0033873"
    m2 = matcher.match("Alec Pierce impresses Patrick Mahomes")
    assert m2 is not None and m2.entity_id == "00-0037247"


def test_unmatched_text_returns_none() -> None:
    matcher = SocialEntityMatcher(PLAYERS)
    assert matcher.match("League announces new TV deal") is None


def test_empty_player_pool_degrades_to_team_matching() -> None:
    matcher = SocialEntityMatcher([])
    m = matcher.match("Philadelphia Eagles sign a kicker")
    assert m is not None and m.entity_id == "PHI"


def test_normalize_match_text_conventions() -> None:
    assert normalize_match_text("D.J.  Moore's  55-yard TD!") == " dj moores 55 yard td "
    # curly apostrophe U+2019 (real Yahoo/CBS payloads carry them)
    assert normalize_match_text("the couple’s home") == " the couples home "  # noqa: RUF001
