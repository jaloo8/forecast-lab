"""Tests for the NBA backtest CLV evaluator (price-based, per the 2026-06-11 audit).

Coverage:
- Single-game eval: side pick vs the devigged entry quote, entry price,
  devigged close, per-game CLV arithmetic.
- CLV is OUTCOME-FREE: flipping the realized winner cannot move it
  (the retired mean_signed_clv flipped sign -- these tests fail under
  the old definition).
- A zero-skill favorite-leaning model gets ~0 CLV on static vig-free
  lines (the old metric rewarded it with |edge|*(2p-1) > 0).
- Skip paths: missing odds, missing crosswalk, unusable quotes, and the
  no-pre-tipoff-close exclusion counter.
- Empty evaluation set returns sensible Nones, not crashes.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from kq.backtest.nba_clv import (
    BacktestNbaClvSummary,
    FinishedGame,
    GameQuotes,
    PinnacleQuote,
    evaluate_games,
)
from kq.models.nba_crosswalk import CrosswalkPair
from kq.models.nba_elo import GameContext, NbaEloRatings


def _crosswalk(
    nba_game_id: str,
    odds_api_game_id: str,
    home_abbr: str = "LAL",
    away_abbr: str = "BOS",
) -> CrosswalkPair:
    return CrosswalkPair(
        odds_api_game_id=odds_api_game_id,
        nba_game_id=nba_game_id,
        home_team_abbr=home_abbr,
        away_team_abbr=away_abbr,
        game_date=date(2026, 5, 4),
    )


def _gq(
    oid: str,
    home: float,
    away: float,
    *,
    close_home: float | None = None,
    close_away: float | None = None,
) -> GameQuotes:
    """Entry quote (home, away); close defaults to the entry (static line)."""
    return GameQuotes(
        odds_api_game_id=oid,
        entry=PinnacleQuote(odds_api_game_id=oid, home_decimal_odds=home, away_decimal_odds=away),
        close=PinnacleQuote(
            odds_api_game_id=oid,
            home_decimal_odds=close_home if close_home is not None else home,
            away_decimal_odds=close_away if close_away is not None else away,
        ),
    )


def _game(
    game_id: str = "0022500001",
    home: str = "LAL",
    away: str = "BOS",
    home_score: int = 110,
    away_score: int = 100,
) -> FinishedGame:
    return FinishedGame(
        nba_game_id=game_id,
        home_team_abbr=home,
        away_team_abbr=away,
        home_score=home_score,
        away_score=away_score,
    )


# --------------------------- single-game eval ---------------------------


def test_single_game_eval_with_aligned_quotes() -> None:
    """One game, Pinnacle at 1.91/1.91 (fair 0.5), Elo at parity leans
    home (~0.64) -> we buy home at the vigged price 1/1.91 and the
    static close nets CLV = 0.5 - 1/1.91 (we paid the vig)."""
    summary = evaluate_games(
        games=[_game()],
        quotes_by_odds_id={"abc-123": _gq("abc-123", 1.91, 1.91)},
        crosswalk=[_crosswalk("0022500001", "abc-123")],
        elo=NbaEloRatings(),
    )
    assert summary.n_evaluated == 1
    assert summary.n_picked == 1
    assert summary.n_skipped_no_odds == 0
    assert summary.n_skipped_no_crosswalk == 0
    assert summary.n_skipped_no_pinnacle == 0
    assert summary.n_excluded_no_pretipoff_close == 0
    eval_ = summary.evaluations[0]
    assert eval_.nba_game_id == "0022500001"
    assert eval_.entry_fair_prob_home == pytest.approx(0.5, abs=1e-3)
    assert eval_.close_fair_prob_home == pytest.approx(0.5, abs=1e-3)
    assert eval_.our_prob_home > 0.5
    assert eval_.edge > 0
    assert eval_.side == "home"
    assert eval_.entry_price == pytest.approx(1 / 1.91)
    assert eval_.close_fair_prob_side == pytest.approx(0.5)
    assert eval_.clv == pytest.approx(0.5 - 1 / 1.91)
    assert eval_.clv is not None and eval_.clv < 0  # static line: we pay the vig
    assert eval_.realized_home_won is True
    assert eval_.correct_side is True


def test_side_picks_away_when_entry_fair_exceeds_model() -> None:
    """Entry fair_home ~0.755 (1.30/4.00) > Elo parity ~0.64 -> buy away
    at the vigged away price 0.25."""
    summary = evaluate_games(
        games=[_game(home_score=95, away_score=110)],
        quotes_by_odds_id={"abc-123": _gq("abc-123", 1.30, 4.00)},
        crosswalk=[_crosswalk("0022500001", "abc-123")],
        elo=NbaEloRatings(),
    )
    eval_ = summary.evaluations[0]
    assert eval_.entry_fair_prob_home > 0.7
    assert eval_.edge < 0
    assert eval_.side == "away"
    assert eval_.entry_price == pytest.approx(1 / 4.00)
    assert eval_.close_fair_prob_side == pytest.approx(1.0 - eval_.close_fair_prob_home)
    assert eval_.clv == pytest.approx((1.0 - eval_.close_fair_prob_home) - 0.25)
    assert eval_.correct_side is True  # away won


def test_clv_positive_when_line_moves_toward_us() -> None:
    """Enter home at vig-free 2.0/2.0 (price 0.5); the pre-tipoff close
    steams to 1.6 / (8/3) (fair 0.625/0.375). CLV = 0.625 - 0.5 = +0.125."""
    summary = evaluate_games(
        games=[_game()],
        quotes_by_odds_id={"abc-123": _gq("abc-123", 2.0, 2.0, close_home=1.6, close_away=8 / 3)},
        crosswalk=[_crosswalk("0022500001", "abc-123")],
        elo=NbaEloRatings(),  # parity -> ~0.64 home -> buys home
    )
    eval_ = summary.evaluations[0]
    assert eval_.side == "home"
    assert eval_.entry_price == pytest.approx(0.5)
    assert eval_.close_fair_prob_side == pytest.approx(0.625)
    assert eval_.clv == pytest.approx(0.125)
    assert summary.mean_clv == pytest.approx(0.125)


# --------------------------- outcome independence (the audit fix) ---------------------------


def test_clv_is_outcome_free() -> None:
    """THE load-bearing property: the realized winner must not move CLV.

    The retired mean_signed_clv was mean(+|edge| if picked side won else
    -|edge|) -- it flipped sign with the outcome, so this test FAILS
    under the old definition.
    """
    quotes = {"abc-123": _gq("abc-123", 1.91, 1.91)}
    crosswalk = [_crosswalk("0022500001", "abc-123")]
    won = evaluate_games(
        games=[_game(home_score=110, away_score=100)],
        quotes_by_odds_id=quotes,
        crosswalk=crosswalk,
        elo=NbaEloRatings(),
    )
    lost = evaluate_games(
        games=[_game(home_score=95, away_score=110)],
        quotes_by_odds_id=quotes,
        crosswalk=crosswalk,
        elo=NbaEloRatings(),
    )
    assert won.evaluations[0].side == lost.evaluations[0].side == "home"
    assert won.evaluations[0].correct_side != lost.evaluations[0].correct_side
    assert won.evaluations[0].clv == pytest.approx(lost.evaluations[0].clv)
    assert won.mean_clv == pytest.approx(lost.mean_clv)


def test_zero_skill_favorite_leaning_model_has_zero_clv() -> None:
    """A zero-skill model that just leans toward home favorites earns
    EXACTLY 0 CLV on static vig-free lines -- while the retired
    outcome-conditioned metric on the very same inputs is |edge|*(2p-1)
    > +0.01 and would have PASSED the Phase 5 #5 gate.
    """
    pairs = [("LAL", "BOS"), ("MIA", "NYK"), ("DEN", "GSW"), ("PHX", "DAL")]
    # Home favorites win 3 of 4 -- outcomes consistent with p = 0.75.
    outcomes = [(110, 100), (110, 100), (110, 100), (95, 110)]
    games = [
        _game(game_id=f"g{i}", home=h, away=a, home_score=hs, away_score=aws)
        for i, ((h, a), (hs, aws)) in enumerate(zip(pairs, outcomes, strict=True))
    ]
    crosswalk = [_crosswalk(f"g{i}", f"oid-{i}", h, a) for i, (h, a) in enumerate(pairs)]
    # Static, vig-free coin-flip quotes: entry == close, booksum == 1.0.
    quotes = {f"oid-{i}": _gq(f"oid-{i}", 2.0, 2.0) for i in range(len(pairs))}
    # The "model": every home team rated 200 points above the away team.
    ratings = {h: 1700.0 for h, _ in pairs} | {a: 1500.0 for _, a in pairs}
    summary = evaluate_games(
        games=games,
        quotes_by_odds_id=quotes,
        crosswalk=crosswalk,
        elo=NbaEloRatings(ratings=ratings),
    )
    assert summary.n_evaluated == 4
    assert summary.n_picked == 4
    assert all(e.side == "home" for e in summary.evaluations)
    # New metric: dead flat zero. No vig, no line movement, no outcome term.
    assert summary.mean_clv == pytest.approx(0.0, abs=1e-12)
    assert summary.mean_clv is not None and not summary.mean_clv >= 0.01
    # The retired metric on the same evaluations would have cleared the bar.
    old_signed = sum(
        (abs(e.edge) if e.correct_side else -abs(e.edge)) for e in summary.evaluations
    ) / len(summary.evaluations)
    assert old_signed > 0.01
    # And the descriptive win rate is above 0.5 -- which is exactly why it
    # must never gate anything.
    assert summary.win_rate_when_picked is not None and summary.win_rate_when_picked > 0.5


# --------------------------- skip / exclusion paths ---------------------------


def test_skip_when_no_crosswalk_for_game() -> None:
    summary = evaluate_games(
        games=[_game()],
        quotes_by_odds_id={},
        crosswalk=[],
        elo=NbaEloRatings(),
    )
    assert summary.n_evaluated == 0
    assert summary.n_skipped_no_crosswalk == 1
    assert summary.n_skipped_no_odds == 0


def test_skip_when_crosswalk_exists_but_no_odds_quote() -> None:
    summary = evaluate_games(
        games=[_game()],
        quotes_by_odds_id={},
        crosswalk=[_crosswalk("0022500001", "abc-123")],
        elo=NbaEloRatings(),
    )
    assert summary.n_evaluated == 0
    assert summary.n_skipped_no_odds == 1
    assert summary.n_skipped_no_crosswalk == 0
    assert summary.n_excluded_no_pretipoff_close == 0


def test_excluded_when_only_inplay_quotes_exist() -> None:
    """A game whose only Pinnacle rows are in-play must be EXCLUDED and
    counted -- never scored (the in-play quote embeds the outcome) and
    never silently lumped into the generic no-odds skip."""
    summary = evaluate_games(
        games=[_game()],
        quotes_by_odds_id={},  # the pre-tipoff fetch found nothing
        crosswalk=[_crosswalk("0022500001", "abc-123")],
        elo=NbaEloRatings(),
        inplay_only_odds_ids={"abc-123"},
    )
    assert summary.n_evaluated == 0
    assert summary.n_excluded_no_pretipoff_close == 1
    assert summary.n_skipped_no_odds == 0


def test_skip_when_decimal_odds_are_unusable() -> None:
    """A 1.0 odds is invalid (no payout). The evaluator should drop
    rather than crash."""
    summary = evaluate_games(
        games=[_game()],
        quotes_by_odds_id={"abc-123": _gq("abc-123", 1.0, 2.0)},
        crosswalk=[_crosswalk("0022500001", "abc-123")],
        elo=NbaEloRatings(),
    )
    assert summary.n_evaluated == 0
    assert summary.n_skipped_no_pinnacle == 1


def test_skip_when_close_quote_is_unusable_even_if_entry_is_fine() -> None:
    """Both snapshots must devig cleanly; a bad CLOSE quote (out-of-band
    booksum) invalidates the CLV anchor, so the game is skipped."""
    summary = evaluate_games(
        games=[_game()],
        quotes_by_odds_id={"abc-123": _gq("abc-123", 1.91, 1.91, close_home=3.0, close_away=3.0)},
        crosswalk=[_crosswalk("0022500001", "abc-123")],
        elo=NbaEloRatings(),
    )
    assert summary.n_evaluated == 0
    assert summary.n_skipped_no_pinnacle == 1


def test_skip_when_booksum_out_of_band() -> None:
    """Booksum below MIN_BOOKSUM (~0.99) -> stale data, skip."""
    summary = evaluate_games(
        games=[_game()],
        quotes_by_odds_id={"abc-123": _gq("abc-123", 3.0, 3.0)},
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
    assert summary.n_picked == 0
    assert summary.brier_model is None
    assert summary.brier_pinnacle is None
    assert summary.mean_clv is None
    assert summary.mean_edge_vs_close is None
    assert summary.win_rate_when_picked is None


def test_aggregate_brier_lower_for_better_predictor() -> None:
    """Two games. Construct so our model is RIGHT on both and Pinnacle
    is at parity -- our Brier should be lower."""
    games = [
        _game(game_id="g1", home="LAL", away="BOS", home_score=110, away_score=100),
        _game(game_id="g2", home="MIA", away="NYK", home_score=95, away_score=110),
    ]
    quotes = {f"oid-{i}": _gq(f"oid-{i}", 1.91, 1.91) for i in (1, 2)}
    crosswalk = [
        _crosswalk("g1", "oid-1", "LAL", "BOS"),
        _crosswalk("g2", "oid-2", "MIA", "NYK"),
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
    # mean_edge_vs_close is the unconditional model-minus-close mean.
    expected_edge = sum(e.our_prob_home - e.close_fair_prob_home for e in summary.evaluations) / 2
    assert summary.mean_edge_vs_close == pytest.approx(expected_edge)


def test_contexts_propagate_to_per_game_predictions() -> None:
    """A B2B context should drop the home win prob compared to the
    no-context baseline. Verifies that ``contexts`` is honored."""
    games = [_game(game_id="g1")]
    quotes = {"oid-1": _gq("oid-1", 1.91, 1.91)}
    crosswalk = [_crosswalk("g1", "oid-1")]
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
        "n_picked": summary.n_picked,
        "n_excluded_no_pretipoff_close": summary.n_excluded_no_pretipoff_close,
        "brier_model": summary.brier_model,
        "brier_pinnacle": summary.brier_pinnacle,
        "mean_clv": summary.mean_clv,
        "mean_edge_vs_close": summary.mean_edge_vs_close,
        "win_rate_when_picked": summary.win_rate_when_picked,
    }
    json.dumps(payload)  # raises if anything's not JSON-safe
