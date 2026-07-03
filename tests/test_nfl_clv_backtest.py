"""Tests for the NFL trade-level CLV evaluator + flow.

The metric pin: CLV = (devigged pre-kickoff Pinnacle close of the held
side) - (fee-adjusted Kalshi fill price). Outcome-free — no game result is
seeded anywhere in these tests, and the numbers still come out.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from kq.backtest.nfl_clv import (
    NflCloseQuote,
    NflTradeForClv,
    evaluate_nfl_trades,
    nfl_week_cluster_key,
)
from kq.execution.paper import PaperTradeIntent
from kq.flows.run_nfl_clv_backtest import main as run_nfl_clv_backtest
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.paper_trades import insert_paper_trade_with_signal


def _fair_home(home_odds: float, away_odds: float) -> float:
    """The proportional devig, written out independently so the test pins
    the arithmetic rather than mirroring the implementation."""
    ih, ia = 1.0 / home_odds, 1.0 / away_odds
    return ih / (ih + ia)


def _close(
    game_id: str = "odds-1",
    *,
    home_odds: float = 1.60,
    away_odds: float = 2.60,
    kickoff: datetime = datetime(2026, 9, 14, 0, 20),
    staleness: timedelta = timedelta(minutes=10),
) -> NflCloseQuote:
    return NflCloseQuote(
        odds_api_game_id=game_id,
        home_decimal_odds=home_odds,
        away_decimal_odds=away_odds,
        fetched_at=kickoff - staleness,
        commence_time=kickoff,
    )


def _trade(
    *,
    ticker: str = "KXNFLGAME-26SEP13DALNYG-NYG",
    side: str = "BUY_YES",
    fill_price: float = 0.40,
    qty: int = 100,
    fee_usd: float = 1.00,
    trade_id: str = "t1",
) -> NflTradeForClv:
    return NflTradeForClv(
        trade_id=trade_id,
        ticker=ticker,
        side=side,
        fill_price=fill_price,
        qty=qty,
        fee_usd=fee_usd,
    )


_MATCHUP = {(date(2026, 9, 13), "NYG", "DAL"): "odds-1"}


# --------------------------- metric pins ---------------------------


def test_clv_formula_buy_yes_home_side() -> None:
    summary = evaluate_nfl_trades(
        [_trade()],
        close_by_game={"odds-1": _close()},
        odds_id_by_matchup=_MATCHUP,
    )
    assert summary.n_evaluated == 1
    e = summary.evaluations[0]
    # Entry: fee-adjusted fill = (0.40*100 + 1.00)/100 = 0.41.
    assert e.entry_prob == pytest.approx(0.41)
    # Close: devigged fair home prob of 1.60/2.60.
    expected_close = _fair_home(1.60, 2.60)
    assert e.close_fair_prob == pytest.approx(expected_close)
    assert e.clv == pytest.approx(expected_close - 0.41)
    assert e.held_team_abbr == "NYG"
    assert summary.mean_clv == pytest.approx(expected_close - 0.41)


def test_clv_buy_no_holds_the_opponent() -> None:
    """BUY_NO on the YES-NYG ticker holds DAL: close prob flips."""
    summary = evaluate_nfl_trades(
        [_trade(side="BUY_NO", fill_price=0.55)],
        close_by_game={"odds-1": _close()},
        odds_id_by_matchup=_MATCHUP,
    )
    e = summary.evaluations[0]
    assert e.held_team_abbr == "DAL"
    expected_close = 1.0 - _fair_home(1.60, 2.60)
    assert e.close_fair_prob == pytest.approx(expected_close)
    assert e.entry_prob == pytest.approx(0.56)  # 0.55 + 1.00/100


def test_clv_yes_away_ticker_alignment() -> None:
    """YES = DAL (away side ticker): BUY_YES holds DAL."""
    summary = evaluate_nfl_trades(
        [_trade(ticker="KXNFLGAME-26SEP13DALNYG-DAL")],
        close_by_game={"odds-1": _close()},
        odds_id_by_matchup=_MATCHUP,
    )
    e = summary.evaluations[0]
    assert e.held_team_abbr == "DAL"
    assert e.close_fair_prob == pytest.approx(1.0 - _fair_home(1.60, 2.60))


def test_stale_close_is_excluded_not_used() -> None:
    summary = evaluate_nfl_trades(
        [_trade()],
        close_by_game={"odds-1": _close(staleness=timedelta(minutes=45))},
        odds_id_by_matchup=_MATCHUP,
    )
    assert summary.n_evaluated == 0
    assert summary.n_excluded_stale_close == 1
    assert summary.mean_clv is None


def test_missing_crosswalk_and_close_are_counted() -> None:
    summary = evaluate_nfl_trades(
        [
            _trade(trade_id="t1"),  # crosswalk hit, close missing
            _trade(trade_id="t2", ticker="KXNFLGAME-26SEP13CLEJAC-JAC"),  # no crosswalk
        ],
        close_by_game={},
        odds_id_by_matchup=_MATCHUP,
    )
    assert summary.n_trades == 2
    assert summary.n_excluded_no_close == 1
    assert summary.n_excluded_no_crosswalk == 1


def test_non_nfl_tickers_are_ignored_entirely() -> None:
    summary = evaluate_nfl_trades(
        [_trade(ticker="KXHIGHLAX-26SEP13-T85"), _trade(ticker="KXNBAGAME-26APR30BOSPHI-PHI")],
        close_by_game={},
        odds_id_by_matchup={},
    )
    assert summary.n_trades == 0


# --------------------------- week clustering ---------------------------


def test_week_cluster_groups_thu_through_mon() -> None:
    # 2026-09-10 is a Thursday; 09-13 Sunday; 09-14 Monday; 09-17 next Thu.
    week1 = {
        nfl_week_cluster_key(date(2026, 9, 10)),
        nfl_week_cluster_key(date(2026, 9, 13)),
        nfl_week_cluster_key(date(2026, 9, 14)),
    }
    assert len(week1) == 1
    assert nfl_week_cluster_key(date(2026, 9, 17)) not in week1


def test_clustered_se_needs_two_weeks() -> None:
    matchups = {
        (date(2026, 9, 13), "NYG", "DAL"): "odds-1",
        (date(2026, 9, 20), "NYG", "DAL"): "odds-2",
    }
    closes = {
        "odds-1": _close("odds-1"),
        "odds-2": _close("odds-2", kickoff=datetime(2026, 9, 21, 0, 20)),
    }
    one_week = evaluate_nfl_trades(
        [_trade()],
        close_by_game=closes,
        odds_id_by_matchup=matchups,
    )
    assert one_week.n_week_clusters == 1
    assert one_week.mean_clv_se_week_clustered is None

    two_weeks = evaluate_nfl_trades(
        [
            _trade(trade_id="t1"),
            _trade(trade_id="t2", ticker="KXNFLGAME-26SEP20DALNYG-NYG", fill_price=0.35),
        ],
        close_by_game=closes,
        odds_id_by_matchup=matchups,
    )
    assert two_weeks.n_week_clusters == 2
    assert two_weeks.mean_clv_se_week_clustered is not None
    assert two_weeks.mean_clv_se_week_clustered >= 0.0


# --------------------------- flow end-to-end ---------------------------


def test_flow_end_to_end_writes_manifest(tmp_path: Path) -> None:
    db = tmp_path / "nfl.duckdb"
    manifest = tmp_path / "manifest.json"
    bootstrap(db)
    con = connect(db)
    try:
        kickoff = datetime(2026, 9, 14, 0, 20)
        con.execute(
            """
            INSERT INTO nfl_game_crosswalk
            (odds_api_game_id, nfl_game_id, home_team_abbr, away_team_abbr,
             game_date, matched_at)
            VALUES ('odds-1', 'odds-1', 'NYG', 'DAL', DATE '2026-09-13', TIMESTAMP '2026-09-13')
            """
        )
        # Two snapshots: an early one and the true close 10 min pre-kickoff.
        snapshots = (
            (datetime(2026, 9, 13, 12, 0), 1.70),
            (kickoff - timedelta(minutes=10), 1.60),
        )
        for fetched, home_odds in snapshots:
            con.execute(
                """
                INSERT INTO nfl_odds
                (odds_api_game_id, bookmaker_key, market_key, home_team, away_team,
                 commence_time, home_decimal_odds, away_decimal_odds,
                 book_last_update, fetched_at)
                VALUES ('odds-1', 'pinnacle', 'h2h', 'New York Giants', 'Dallas Cowboys',
                        ?, ?, 2.60, ?, ?)
                """,
                [kickoff, home_odds, fetched, fetched],
            )
        # A post-kickoff (in-play) snapshot that must NOT anchor.
        con.execute(
            """
            INSERT INTO nfl_odds
            (odds_api_game_id, bookmaker_key, market_key, home_team, away_team,
             commence_time, home_decimal_odds, away_decimal_odds,
             book_last_update, fetched_at)
            VALUES ('odds-1', 'pinnacle', 'h2h', 'New York Giants', 'Dallas Cowboys',
                    ?, 1.05, 9.00, ?, ?)
            """,
            [kickoff, kickoff + timedelta(minutes=30), kickoff + timedelta(minutes=30)],
        )
        intent = PaperTradeIntent(
            signal_id="sig-clv",
            as_of=datetime(2026, 9, 13, 22, tzinfo=UTC),
            ticker="KXNFLGAME-26SEP13DALNYG-NYG",
            side="BUY_YES",
            limit_price=0.40,
            qty=100,
            fee_usd=1.00,
            model_prob_yes=0.41,
            market_yes_bid=0.39,
            market_yes_ask=0.40,
            edge_bps=100,
            model_name="nfl_pinnacle_anchored_v1",
        )
        insert_paper_trade_with_signal(con, intent)
    finally:
        con.close()

    n = run_nfl_clv_backtest(db_path=db, manifest_path=manifest)
    assert n == 1
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["n_trades"] == 1
    assert payload["n_evaluated"] == 1
    # Close anchors on the 1.60 pre-kickoff snapshot, never the in-play one.
    ih, ia = 1 / 1.60, 1 / 2.60
    expected = ih / (ih + ia) - 0.41
    assert payload["mean_clv"] == pytest.approx(expected)
    assert payload["close_beat_rate"] in (0.0, 1.0)


def test_flow_is_no_data_safe(tmp_path: Path) -> None:
    db = tmp_path / "nfl.duckdb"
    manifest = tmp_path / "manifest.json"
    bootstrap(db)
    n = run_nfl_clv_backtest(db_path=db, manifest_path=manifest)
    assert n == 0
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["n_trades"] == 0
    assert payload["mean_clv"] is None
