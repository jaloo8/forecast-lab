"""Tests for the NBA backtest CLV evaluator.

Coverage:
- Single-game eval: edge sign, correct-side flag, Brier scores.
- Multi-game aggregate: mean_clv, mean_signed_clv, win_rate_when_picked.
- Skip paths: missing odds, missing crosswalk, missing Pinnacle quote.
- Out-of-band booksum / unusable decimal odds gracefully skipped.
- Empty evaluation set returns sensible Nones, not crashes.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from kq.backtest.nba_clv import (
    BacktestNbaClvSummary,
    FinishedGame,
    PinnacleQuote,
    evaluate_games,
)
from kq.models.nba_crosswalk import CrosswalkPair
from kq.models.nba_elo import GameContext, NbaEloRatings


def _crosswalk(nba_game_id: str, odds_api_game_id: str) -> CrosswalkPair:
    return CrosswalkPair(
        odds_api_game_id=odds_api_game_id,
        nba_game_id=nba_game_id,
        home_team_abbr="LAL",
        away_team_abbr="BOS",
        game_date=date(2026, 5, 4),
    )


# --------------------------- single-game eval ---------------------------


def test_single_game_eval_with_aligned_quotes() -> None:
    """One game, our Elo agrees with Pinnacle close to parity, home
    won. Verify the per-game evaluation has the right shape and the
    aggregate produces sensible numbers."""
    games = [
        FinishedGame(
            nba_game_id="0022500001",
            home_team_abbr="LAL",
            away_team_abbr="BOS",
            home_score=110,
            away_score=100,
        )
    ]
    quotes = {
        "abc-123": PinnacleQuote(
            odds_api_game_id="abc-123",
            home_decimal_odds=1.91,
            away_decimal_odds=1.91,
        )
    }
    crosswalk = [_crosswalk("0022500001", "abc-123")]
    elo = NbaEloRatings()  # both at INITIAL_RATING -> Elo predicts ~0.64 home
    summary = evaluate_games(
        games=games,
        quotes_by_odds_id=quotes,
        crosswalk=crosswalk,
        elo=elo,
    )
    assert summary.n_evaluated == 1
    assert summary.n_skipped_no_odds == 0
    assert summary.n_skipped_no_crosswalk == 0
    assert summary.n_skipped_no_pinnacle == 0
    eval_ = summary.evaluations[0]
    assert eval_.nba_game_id == "0022500001"
    # Pinnacle 1.91/1.91 strips to fair_home == 0.5; Elo at parity ~ 0.64.
    assert eval_.pinnacle_prob_home == pytest.approx(0.5, abs=1e-3)
    assert eval_.our_prob_home > 0.5
    assert eval_.edge > 0  # we're more bullish on home
    assert eval_.realized_home_won is True
    assert eval_.correct_side is True


def test_single_game_eval_with_wrong_pick() -> None:
    """Same setup but home loses -- correct_side flips to False."""
    games = [
        FinishedGame(
            nba_game_id="0022500001",
            home_team_abbr="LAL",
            away_team_abbr="BOS",
            home_score=95,
            away_score=110,
        )
    ]
    quotes = {
        "abc-123": PinnacleQuote(
            odds_api_game_id="abc-123",
            home_decimal_odds=1.91,
            away_decimal_odds=1.91,
        )
    }
    crosswalk = [_crosswalk("0022500001", "abc-123")]
    summary = evaluate_games(
        games=games,
        quotes_by_odds_id=quotes,
        crosswalk=crosswalk,
        elo=NbaEloRatings(),
    )
    eval_ = summary.evaluations[0]
    assert eval_.realized_home_won is False
    # Edge > 0 (we picked home) but home lost -> wrong side.
    assert eval_.edge > 0
    assert eval_.correct_side is False


def test_edge_sign_picks_away_when_pinnacle_favors_home_more_than_us() -> None:
    """When Pinnacle's vig-stripped fair_home > our_p_home, edge < 0
    -> we'd pick the away team. Verify with a heavily-home-favored
    Pinnacle line (1.30/4.0 -> fair_home ~0.75)."""
    games = [
        FinishedGame(
            nba_game_id="0022500001",
            home_team_abbr="LAL",
            away_team_abbr="BOS",
            home_score=95,
            away_score=110,  # away won
        )
    ]
    quotes = {
        "abc-123": PinnacleQuote(
            odds_api_game_id="abc-123",
            home_decimal_odds=1.30,
            away_decimal_odds=4.00,
        )
    }
    crosswalk = [_crosswalk("0022500001", "abc-123")]
    summary = evaluate_games(
        games=games,
        quotes_by_odds_id=quotes,
        crosswalk=crosswalk,
        elo=NbaEloRatings(),  # Elo says ~0.64 home; Pinnacle says ~0.75
    )
    eval_ = summary.evaluations[0]
    assert eval_.pinnacle_prob_home > 0.7
    assert eval_.our_prob_home < eval_.pinnacle_prob_home
    assert eval_.edge < 0  # we'd pick away
    # Away won -> correct side.
    assert eval_.correct_side is True


# --------------------------- skip paths ---------------------------


def test_skip_when_no_crosswalk_for_game() -> None:
    games = [
        FinishedGame(
            nba_game_id="0022500001",
            home_team_abbr="LAL",
            away_team_abbr="BOS",
            home_score=110,
            away_score=100,
        )
    ]
    summary = evaluate_games(
        games=games,
        quotes_by_odds_id={},
        crosswalk=[],
        elo=NbaEloRatings(),
    )
    assert summary.n_evaluated == 0
    assert summary.n_skipped_no_crosswalk == 1
    assert summary.n_skipped_no_odds == 0


def test_skip_when_crosswalk_exists_but_no_odds_quote() -> None:
    games = [
        FinishedGame(
            nba_game_id="0022500001",
            home_team_abbr="LAL",
            away_team_abbr="BOS",
            home_score=110,
            away_score=100,
        )
    ]
    summary = evaluate_games(
        games=games,
        quotes_by_odds_id={},
        crosswalk=[_crosswalk("0022500001", "abc-123")],
        elo=NbaEloRatings(),
    )
    assert summary.n_evaluated == 0
    assert summary.n_skipped_no_odds == 1
    assert summary.n_skipped_no_crosswalk == 0


def test_skip_when_decimal_odds_are_unusable() -> None:
    """A 1.0 odds is invalid (no payout). The evaluator should drop
    rather than crash."""
    games = [
        FinishedGame(
            nba_game_id="0022500001",
            home_team_abbr="LAL",
            away_team_abbr="BOS",
            home_score=110,
            away_score=100,
        )
    ]
    quotes = {
        "abc-123": PinnacleQuote(
            odds_api_game_id="abc-123",
            home_decimal_odds=1.0,  # invalid
            away_decimal_odds=2.0,
        )
    }
    summary = evaluate_games(
        games=games,
        quotes_by_odds_id=quotes,
        crosswalk=[_crosswalk("0022500001", "abc-123")],
        elo=NbaEloRatings(),
    )
    assert summary.n_evaluated == 0
    assert summary.n_skipped_no_pinnacle == 1


def test_skip_when_booksum_out_of_band() -> None:
    """Booksum below MIN_BOOKSUM (~0.99) -> stale data, skip."""
    games = [
        FinishedGame(
            nba_game_id="0022500001",
            home_team_abbr="LAL",
            away_team_abbr="BOS",
            home_score=110,
            away_score=100,
        )
    ]
    # 3.0 / 3.0 -> raw probs sum to 0.667, below MIN_BOOKSUM.
    quotes = {
        "abc-123": PinnacleQuote(
            odds_api_game_id="abc-123",
            home_decimal_odds=3.0,
            away_decimal_odds=3.0,
        )
    }
    summary = evaluate_games(
        games=games,
        quotes_by_odds_id=quotes,
        crosswalk=[_crosswalk("0022500001", "abc-123")],
        elo=NbaEloRatings(),
    )
    assert summary.n_evaluated == 0
    assert summary.n_skipped_no_pinnacle == 1


# --------------------------- aggregate ---------------------------


def test_empty_evaluation_returns_none_not_crash() -> None:
    summary = evaluate_games(
        games=[],
        quotes_by_odds_id={},
        crosswalk=[],
        elo=NbaEloRatings(),
    )
    assert summary.n_evaluated == 0
    assert summary.brier_model is None
    assert summary.brier_pinnacle is None
    assert summary.mean_clv_vs_pinnacle is None
    assert summary.mean_signed_clv is None
    assert summary.win_rate_when_picked is None


def test_aggregate_brier_lower_for_better_predictor() -> None:
    """Two games. Construct so our model is RIGHT on both and Pinnacle
    is at parity -- our Brier should be lower."""
    games = [
        FinishedGame(
            nba_game_id="g1",
            home_team_abbr="LAL",
            away_team_abbr="BOS",
            home_score=110,
            away_score=100,
        ),
        FinishedGame(
            nba_game_id="g2",
            home_team_abbr="MIA",
            away_team_abbr="NYK",
            home_score=95,
            away_score=110,
        ),
    ]
    # Pinnacle is 1.91/1.91 on both -> fair_home == 0.5 on both.
    quotes = {
        f"oid-{i}": PinnacleQuote(
            odds_api_game_id=f"oid-{i}",
            home_decimal_odds=1.91,
            away_decimal_odds=1.91,
        )
        for i in (1, 2)
    }
    crosswalk = [
        CrosswalkPair(
            odds_api_game_id="oid-1",
            nba_game_id="g1",
            home_team_abbr="LAL",
            away_team_abbr="BOS",
            game_date=date(2026, 5, 4),
        ),
        CrosswalkPair(
            odds_api_game_id="oid-2",
            nba_game_id="g2",
            home_team_abbr="MIA",
            away_team_abbr="NYK",
            game_date=date(2026, 5, 4),
        ),
    ]
    # Spike our Elo so we predict 0.95 on game 1 (LAL) and 0.05 on
    # game 2 (we'd say MIA loses badly). Both predictions match
    # realized outcomes.
    elo = NbaEloRatings(ratings={"LAL": 1900.0, "BOS": 1300.0, "MIA": 1200.0, "NYK": 1800.0})
    summary = evaluate_games(
        games=games,
        quotes_by_odds_id=quotes,
        crosswalk=crosswalk,
        elo=elo,
    )
    assert summary.n_evaluated == 2
    assert summary.brier_model is not None and summary.brier_pinnacle is not None
    assert summary.brier_model < summary.brier_pinnacle
    assert summary.win_rate_when_picked == 1.0


def test_aggregate_mean_signed_clv_positive_when_picks_correct() -> None:
    """Same right-on-both setup: mean_signed_clv should be positive
    (we picked correctly + had a real edge)."""
    games = [
        FinishedGame(
            nba_game_id="g1",
            home_team_abbr="LAL",
            away_team_abbr="BOS",
            home_score=110,
            away_score=100,
        ),
    ]
    quotes = {
        "oid-1": PinnacleQuote(
            odds_api_game_id="oid-1",
            home_decimal_odds=1.91,
            away_decimal_odds=1.91,
        )
    }
    crosswalk = [
        CrosswalkPair(
            odds_api_game_id="oid-1",
            nba_game_id="g1",
            home_team_abbr="LAL",
            away_team_abbr="BOS",
            game_date=date(2026, 5, 4),
        ),
    ]
    elo = NbaEloRatings(ratings={"LAL": 1700.0, "BOS": 1500.0})
    summary = evaluate_games(games=games, quotes_by_odds_id=quotes, crosswalk=crosswalk, elo=elo)
    assert summary.mean_signed_clv is not None and summary.mean_signed_clv > 0
    assert summary.win_rate_when_picked == 1.0


def test_aggregate_mean_signed_clv_negative_when_picks_wrong() -> None:
    """Elo rates LAL high; LAL loses; mean_signed_clv goes negative."""
    games = [
        FinishedGame(
            nba_game_id="g1",
            home_team_abbr="LAL",
            away_team_abbr="BOS",
            home_score=95,
            away_score=110,
        ),
    ]
    quotes = {
        "oid-1": PinnacleQuote(
            odds_api_game_id="oid-1",
            home_decimal_odds=1.91,
            away_decimal_odds=1.91,
        )
    }
    crosswalk = [
        CrosswalkPair(
            odds_api_game_id="oid-1",
            nba_game_id="g1",
            home_team_abbr="LAL",
            away_team_abbr="BOS",
            game_date=date(2026, 5, 4),
        ),
    ]
    elo = NbaEloRatings(ratings={"LAL": 1700.0, "BOS": 1500.0})
    summary = evaluate_games(games=games, quotes_by_odds_id=quotes, crosswalk=crosswalk, elo=elo)
    assert summary.mean_signed_clv is not None and summary.mean_signed_clv < 0
    assert summary.win_rate_when_picked == 0.0


def test_contexts_propagate_to_per_game_predictions() -> None:
    """A B2B context should drop the home win prob compared to the
    no-context baseline. Verifies that ``contexts`` is honored."""
    games = [
        FinishedGame(
            nba_game_id="g1",
            home_team_abbr="LAL",
            away_team_abbr="BOS",
            home_score=110,
            away_score=100,
        ),
    ]
    quotes = {
        "oid-1": PinnacleQuote(
            odds_api_game_id="oid-1",
            home_decimal_odds=1.91,
            away_decimal_odds=1.91,
        )
    }
    crosswalk = [
        CrosswalkPair(
            odds_api_game_id="oid-1",
            nba_game_id="g1",
            home_team_abbr="LAL",
            away_team_abbr="BOS",
            game_date=date(2026, 5, 4),
        ),
    ]
    elo = NbaEloRatings()  # parity
    s_baseline = evaluate_games(games=games, quotes_by_odds_id=quotes, crosswalk=crosswalk, elo=elo)
    s_b2b = evaluate_games(
        games=games,
        quotes_by_odds_id=quotes,
        crosswalk=crosswalk,
        elo=elo,
        contexts={"g1": GameContext(home_back_to_back=True)},
    )
    assert s_b2b.evaluations[0].our_prob_home < s_baseline.evaluations[0].our_prob_home


# --------------------------- type sanity ---------------------------


def test_summary_fields_are_json_safe() -> None:
    """Empty case: every aggregate field is None or int (no NaN, no
    datetime, no numpy scalar that would choke json.dumps)."""
    summary = evaluate_games(
        games=[],
        quotes_by_odds_id={},
        crosswalk=[],
        elo=NbaEloRatings(),
    )
    assert isinstance(summary, BacktestNbaClvSummary)
    payload = {
        "n_evaluated": summary.n_evaluated,
        "brier_model": summary.brier_model,
        "brier_pinnacle": summary.brier_pinnacle,
        "mean_clv_vs_pinnacle": summary.mean_clv_vs_pinnacle,
        "mean_signed_clv": summary.mean_signed_clv,
        "win_rate_when_picked": summary.win_rate_when_picked,
    }
    json.dumps(payload)  # raises if anything's not JSON-safe
