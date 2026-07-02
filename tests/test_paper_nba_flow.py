"""End-to-end tests for the NBA paper-trading flow.

Coverage:
- Elo state computed from chronological game history.
- Pinnacle quote join via the crosswalk works on (date, home, away).
- Settlement maps ``nba_game.home_won`` -> YES/NO correctly for both
  YES-home and YES-away ticker variants.
- Unresolved games are skipped (idempotent re-runs land them later).
- Weather tickers are left alone by the NBA settler.
- ``run_once_nba`` orchestrates end-to-end with a mocked Kalshi
  ``list_markets`` call, writes paper_trade + signal rows, and reports
  a correct summary.

Async Kalshi calls are mocked by patching ``_pull_kalshi_nba_markets``
in the flow module; the Kalshi client itself is covered by separate
unit tests.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

import duckdb
import httpx
import pytest

from kq.clients.kalshi import KalshiClient
from kq.clients.kalshi._ticker_parser_nba import parse_nba_market_ticker
from kq.clients.kalshi._types import Market
from kq.execution.paper import DEFAULT_KELLY_FRACTION, DEFAULT_MAX_STAKE_USD, PaperTradeIntent
from kq.execution.paper_nba import NbaSignalDecision, NbaSignalInputs, evaluate_nba_signal
from kq.flows.paper_nba_trade import (
    PaperNbaRunSummary,
    _build_game_context,
    _compute_elo_state,
    _fetch_latest_pinnacle_quote,
    _pull_kalshi_nba_markets,
    run_once_nba,
)
from kq.models.nba_elo import (
    GameContext,
    NbaEloRatings,
    predict_win_prob,
    update_after_game,
)
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.paper_trades import (
    insert_paper_trade_with_signal,
    settle_due_nba_paper_trades,
    settle_due_paper_trades,
)

# --------------------------- fixtures ---------------------------


def _seed_completed_game(
    con: duckdb.DuckDBPyConnection,
    *,
    game_id: str,
    game_date: date,
    home: str,
    away: str,
    home_score: int | None,
    away_score: int | None,
    home_won: bool | None,
) -> None:
    con.execute(
        """
        INSERT INTO nba_game (game_id, season, season_type, game_date,
            home_team_id, home_team_abbr, away_team_id, away_team_abbr,
            home_score, away_score, home_won, fetched_at)
        VALUES (?, '2025-26', 'Regular Season', ?, 1, ?, 2, ?, ?, ?, ?, ?)
        """,
        [game_id, game_date, home, away, home_score, away_score, home_won, datetime(2026, 5, 4)],
    )


def _seed_crosswalk_and_odds(
    con: duckdb.DuckDBPyConnection,
    *,
    odds_game_id: str,
    nba_game_id: str,
    game_date: date,
    home: str,
    away: str,
    home_odds: float,
    away_odds: float,
) -> None:
    con.execute(
        """
        INSERT INTO nba_game_crosswalk
        (odds_api_game_id, nba_game_id, home_team_abbr, away_team_abbr, game_date, matched_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [odds_game_id, nba_game_id, home, away, game_date, datetime(2026, 5, 4)],
    )
    con.execute(
        """
        INSERT INTO nba_odds
        (odds_api_game_id, bookmaker_key, market_key, home_team, away_team,
         commence_time, home_decimal_odds, away_decimal_odds,
         book_last_update, fetched_at)
        VALUES (?, 'pinnacle', 'h2h', ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            odds_game_id,
            home,
            away,
            datetime(game_date.year, game_date.month, game_date.day, 23, 0),
            home_odds,
            away_odds,
            datetime(2026, 5, 4, 22, 0),
            datetime(2026, 5, 4, 22, 30),
        ],
    )


def _seed_unsettled_paper_trade(con: duckdb.DuckDBPyConnection, *, ticker: str) -> str:
    intent = PaperTradeIntent(
        signal_id="sig-test",
        as_of=datetime(2026, 5, 4, 21, tzinfo=UTC),
        ticker=ticker,
        side="BUY_YES",
        limit_price=0.40,
        qty=100,
        fee_usd=1.50,
        model_prob_yes=0.55,
        market_yes_bid=0.39,
        market_yes_ask=0.40,
        edge_bps=1500,
        model_name="nba_pinnacle_anchored_v1",
    )
    trade_id, _ = insert_paper_trade_with_signal(con, intent)
    return trade_id


# --------------------------- _compute_elo_state ---------------------------


def test_compute_elo_state_folds_completed_games(tmp_path: Path) -> None:
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        # LAL beats BOS at home; PHI beats NYK at home. Two independent games.
        _seed_completed_game(
            con,
            game_id="g1",
            game_date=date(2026, 1, 1),
            home="LAL",
            away="BOS",
            home_score=110,
            away_score=100,
            home_won=True,
        )
        _seed_completed_game(
            con,
            game_id="g2",
            game_date=date(2026, 1, 2),
            home="PHI",
            away="NYK",
            home_score=105,
            away_score=95,
            home_won=True,
        )
        elo = _compute_elo_state(con)
    finally:
        con.close()
    # LAL won at home over a fresh 1500-rated team; rating must rise above 1500.
    assert elo.get("LAL") > 1500.0
    # BOS lost; rating must fall.
    assert elo.get("BOS") < 1500.0


def test_compute_elo_state_skips_unfinished(tmp_path: Path) -> None:
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        _seed_completed_game(
            con,
            game_id="g_unresolved",
            game_date=date(2026, 1, 1),
            home="LAL",
            away="BOS",
            home_score=None,
            away_score=None,
            home_won=None,
        )
        elo = _compute_elo_state(con)
    finally:
        con.close()
    # No completed games means no team has moved off the prior. The Elo
    # state may be empty entirely (no teams seen yet) or initialized at
    # the default — either way, no team should have moved.
    assert elo.get("LAL") == pytest.approx(1500.0)
    assert elo.get("BOS") == pytest.approx(1500.0)


# --------------------------- _fetch_latest_pinnacle_quote ---------------------------


def test_fetch_latest_pinnacle_quote_joins_crosswalk(tmp_path: Path) -> None:
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        _seed_crosswalk_and_odds(
            con,
            odds_game_id="odds-1",
            nba_game_id="nba-1",
            game_date=date(2026, 5, 4),
            home="BOS",
            away="LAL",
            home_odds=1.85,
            away_odds=1.95,
        )
        ref = parse_nba_market_ticker("KXNBAGAME-26MAY04LALBOS-BOS")
        assert ref is not None
        home_odds, away_odds = _fetch_latest_pinnacle_quote(con, ref)
    finally:
        con.close()
    assert home_odds == pytest.approx(1.85)
    assert away_odds == pytest.approx(1.95)


def test_fetch_latest_pinnacle_quote_returns_none_when_no_crosswalk(
    tmp_path: Path,
) -> None:
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        ref = parse_nba_market_ticker("KXNBAGAME-26MAY04LALBOS-BOS")
        assert ref is not None
        home_odds, away_odds = _fetch_latest_pinnacle_quote(con, ref)
    finally:
        con.close()
    assert home_odds is None
    assert away_odds is None


# --------------------------- settle_due_nba_paper_trades ---------------------------


def test_settle_nba_yes_home_wins_marks_yes(tmp_path: Path) -> None:
    """YES side = home team; home_won=True -> settlement YES, positive P&L."""
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        _seed_completed_game(
            con,
            game_id="g1",
            game_date=date(2026, 5, 4),
            home="BOS",
            away="LAL",
            home_score=110,
            away_score=105,
            home_won=True,
        )
        # YES=BOS (home); home won -> contract resolves YES.
        trade_id = _seed_unsettled_paper_trade(con, ticker="KXNBAGAME-26MAY04LALBOS-BOS")
        n = settle_due_nba_paper_trades(con)
        assert n == 1
        row = con.execute(
            "SELECT settlement, pnl_usd FROM paper_trade WHERE trade_id = ?",
            [trade_id],
        ).fetchone()
        assert row is not None
        assert row[0] == "YES"
        # BUY_YES at 0.40, qty 100, fee 1.50, outcome YES -> 100*(1-0.40) - 1.50 = 58.50
        assert row[1] == pytest.approx(58.50)
    finally:
        con.close()


def test_settle_nba_yes_away_wins_marks_yes(tmp_path: Path) -> None:
    """YES side = away team; home_won=False (away won) -> contract resolves YES."""
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        _seed_completed_game(
            con,
            game_id="g1",
            game_date=date(2026, 5, 4),
            home="BOS",
            away="LAL",
            home_score=100,
            away_score=110,
            home_won=False,
        )
        # YES=LAL (away); away won -> contract resolves YES.
        trade_id = _seed_unsettled_paper_trade(con, ticker="KXNBAGAME-26MAY04LALBOS-LAL")
        n = settle_due_nba_paper_trades(con)
        assert n == 1
        row = con.execute(
            "SELECT settlement FROM paper_trade WHERE trade_id = ?", [trade_id]
        ).fetchone()
        assert row is not None
        assert row[0] == "YES"
    finally:
        con.close()


def test_settle_nba_yes_home_when_away_wins_marks_no(tmp_path: Path) -> None:
    """YES side = home; away won -> contract resolves NO."""
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        _seed_completed_game(
            con,
            game_id="g1",
            game_date=date(2026, 5, 4),
            home="BOS",
            away="LAL",
            home_score=100,
            away_score=110,
            home_won=False,
        )
        trade_id = _seed_unsettled_paper_trade(con, ticker="KXNBAGAME-26MAY04LALBOS-BOS")
        n = settle_due_nba_paper_trades(con)
        assert n == 1
        row = con.execute(
            "SELECT settlement, pnl_usd FROM paper_trade WHERE trade_id = ?",
            [trade_id],
        ).fetchone()
        assert row is not None
        assert row[0] == "NO"
        # BUY_YES at 0.40, qty 100, fee 1.50, outcome NO -> -100*0.40 - 1.50 = -41.50
        assert row[1] == pytest.approx(-41.50)
    finally:
        con.close()


def test_settle_nba_skips_unresolved_games(tmp_path: Path) -> None:
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        _seed_completed_game(
            con,
            game_id="g1",
            game_date=date(2026, 5, 4),
            home="BOS",
            away="LAL",
            home_score=None,
            away_score=None,
            home_won=None,
        )
        trade_id = _seed_unsettled_paper_trade(con, ticker="KXNBAGAME-26MAY04LALBOS-BOS")
        n = settle_due_nba_paper_trades(con)
        assert n == 0
        row = con.execute(
            "SELECT settled_at FROM paper_trade WHERE trade_id = ?", [trade_id]
        ).fetchone()
        assert row is not None
        assert row[0] is None
    finally:
        con.close()


def test_settle_nba_skips_missing_schedule_row(tmp_path: Path) -> None:
    """If we have a paper trade but no nba_game row yet, settle is a no-op."""
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        trade_id = _seed_unsettled_paper_trade(con, ticker="KXNBAGAME-26MAY04LALBOS-BOS")
        n = settle_due_nba_paper_trades(con)
        assert n == 0
        row = con.execute(
            "SELECT settled_at FROM paper_trade WHERE trade_id = ?", [trade_id]
        ).fetchone()
        assert row is not None
        assert row[0] is None
    finally:
        con.close()


def test_nba_settler_leaves_weather_trades_alone(tmp_path: Path) -> None:
    """A weather ticker must not be touched by the NBA settler."""
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        weather_trade_id = _seed_unsettled_paper_trade(con, ticker="KXHIGHLAX-26APR30-T75")
        n = settle_due_nba_paper_trades(con)
        assert n == 0
        # Weather trade must still be unsettled (left for weather settler).
        row = con.execute(
            "SELECT settled_at FROM paper_trade WHERE trade_id = ?",
            [weather_trade_id],
        ).fetchone()
        assert row is not None
        assert row[0] is None
    finally:
        con.close()


def test_weather_settler_leaves_nba_trades_alone(tmp_path: Path) -> None:
    """Symmetric guarantee: the weather settler skips NBA tickers."""
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        nba_trade_id = _seed_unsettled_paper_trade(con, ticker="KXNBAGAME-26MAY04LALBOS-BOS")
        n = settle_due_paper_trades(con)
        assert n == 0
        row = con.execute(
            "SELECT settled_at FROM paper_trade WHERE trade_id = ?",
            [nba_trade_id],
        ).fetchone()
        assert row is not None
        assert row[0] is None
    finally:
        con.close()


# --------------------------- run_once_nba (end-to-end) ---------------------------


def _fake_open_market(ticker: str, *, yes_bid: int = 39, yes_ask: int = 40) -> Market:
    """Build a Market instance shaped like Kalshi's parsed response."""
    return Market(
        ticker=ticker,
        event_ticker=ticker.rsplit("-", 1)[0],
        title=ticker,
        status="open",
        category=None,
        yes_ask=yes_ask / 100,
        yes_bid=yes_bid / 100,
        last_price=None,
        volume=0.0,
        open_interest=0.0,
        open_time=None,
        close_time=None,
        expected_expiration_time=None,
        rules_primary=None,
    )


def test_run_once_nba_writes_paper_trade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Submit pass with a mocked Kalshi market + Pinnacle data writes a
    paper_trade row; settle pass is a no-op because the game hasn't
    resolved yet."""
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db}")
    monkeypatch.setenv("KQ_KELLY_FRACTION", "0.15")

    con = connect(db)
    try:
        # Crosswalk + Pinnacle data for tomorrow's game. Pinnacle 1.50/2.50
        # -> fair_home ~ 0.625, away ~ 0.375. Booksum 1/1.5 + 1/2.5 = 1.067.
        _seed_crosswalk_and_odds(
            con,
            odds_game_id="odds-1",
            nba_game_id="nba-1",
            game_date=date(2026, 5, 4),
            home="BOS",
            away="LAL",
            home_odds=1.50,
            away_odds=2.50,
        )
        # An upcoming game row (no result yet) so the flow doesn't have to
        # fall back to Elo for the home/away abbr lookup. Pinnacle path is
        # what we expect to be taken.
        _seed_completed_game(
            con,
            game_id="g_future",
            game_date=date(2026, 5, 4),
            home="BOS",
            away="LAL",
            home_score=None,
            away_score=None,
            home_won=None,
        )
    finally:
        con.close()

    # YES = BOS (home). Kalshi yes_ask = 0.40 vs our model_prob ~0.625
    # -> ~22 ppts edge -> BUY_YES.
    fake_market = _fake_open_market("KXNBAGAME-26MAY04LALBOS-BOS", yes_bid=39, yes_ask=40)

    async def _fake_pull() -> list[Market]:
        return [fake_market]

    with patch("kq.flows.paper_nba_trade._pull_kalshi_nba_markets", new=_fake_pull):
        summary = run_once_nba(
            db_path=db,
            starting_bankroll_usd=1000.0,
            kelly_fraction=DEFAULT_KELLY_FRACTION,
            max_stake_usd=DEFAULT_MAX_STAKE_USD,
            now_utc=datetime(2026, 5, 4, 22, tzinfo=UTC),
        )

    assert isinstance(summary, PaperNbaRunSummary)
    assert summary.skipped_reason is None
    assert summary.submit_evaluated == 1
    assert summary.submit_recorded == 1
    assert summary.settle_processed == 0  # game not yet resolved

    # Verify the row landed and references the right ticker + model name.
    con = duckdb.connect(str(db), read_only=True)
    try:
        row = con.execute("SELECT ticker, side, limit_price, qty FROM paper_trade").fetchone()
        assert row is not None
        assert row[0] == "KXNBAGAME-26MAY04LALBOS-BOS"
        assert row[1] == "BUY_YES"
        assert row[2] == pytest.approx(0.40)
        assert int(row[3]) > 0
        sig = con.execute("SELECT model_name FROM signal LIMIT 1").fetchone()
        assert sig is not None
        assert sig[0] == "nba_pinnacle_anchored_v1"
    finally:
        con.close()


def test_run_once_nba_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-running with unchanged inputs doesn't double-insert."""
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db}")

    con = connect(db)
    try:
        _seed_crosswalk_and_odds(
            con,
            odds_game_id="odds-1",
            nba_game_id="nba-1",
            game_date=date(2026, 5, 4),
            home="BOS",
            away="LAL",
            home_odds=1.50,
            away_odds=2.50,
        )
        _seed_completed_game(
            con,
            game_id="g_future",
            game_date=date(2026, 5, 4),
            home="BOS",
            away="LAL",
            home_score=None,
            away_score=None,
            home_won=None,
        )
    finally:
        con.close()

    fake_market = _fake_open_market("KXNBAGAME-26MAY04LALBOS-BOS")

    async def _fake_pull() -> list[Market]:
        return [fake_market]

    with patch("kq.flows.paper_nba_trade._pull_kalshi_nba_markets", new=_fake_pull):
        first = run_once_nba(
            db_path=db,
            now_utc=datetime(2026, 5, 4, 22, tzinfo=UTC),
        )
        second = run_once_nba(
            db_path=db,
            now_utc=datetime(2026, 5, 4, 22, 30, tzinfo=UTC),
        )

    assert first.submit_recorded == 1
    assert second.submit_recorded == 0  # idempotent

    # Exactly one paper_trade row total.
    con = duckdb.connect(str(db), read_only=True)
    try:
        count = con.execute("SELECT COUNT(*) FROM paper_trade").fetchone()
        assert count is not None and int(count[0]) == 1
    finally:
        con.close()


def test_run_once_nba_no_open_markets_returns_clean_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When Kalshi has zero NBA markets, the flow exits cleanly with a
    zeroed summary -- no exception, no skipped_reason."""
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db}")

    async def _fake_pull() -> list[Market]:
        return []

    with patch("kq.flows.paper_nba_trade._pull_kalshi_nba_markets", new=_fake_pull):
        summary = run_once_nba(db_path=db)

    assert summary.submit_evaluated == 0
    assert summary.submit_recorded == 0
    assert summary.skipped_reason is None


# --------------------------- market discovery (audit #5) ---------------------------


async def test_pull_kalshi_nba_markets_queries_series_ticker(
    rsa_private_key_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flow must ask for `series_ticker=KXNBAGAME` (mirroring the weather
    PR #97 fix) — NOT an unfiltered status-open page, whose first page on
    prod contains zero NBA markets (2026-06-11 audit #5)."""
    urls: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(request.url)
        return httpx.Response(200, json={"markets": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        kc = KalshiClient(
            api_key_id="id", private_key_path=rsa_private_key_file, env="prod", client=http
        )
        monkeypatch.setattr(
            "kq.flows.paper_nba_trade.KalshiClient.from_settings",
            staticmethod(lambda settings=None, *, client=None: kc),
        )
        markets = await _pull_kalshi_nba_markets()

    assert markets == []
    assert len(urls) == 1
    assert urls[0].params.get("series_ticker") == "KXNBAGAME"
    assert urls[0].params.get("status") == "open"


# --------------------------- one side per game (audit #6) ---------------------------


def test_run_once_nba_records_at_most_one_side_per_game(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kalshi lists a YES-home AND a YES-away market per game. Even when BOTH
    sides show a tradable edge, exactly ONE paper trade lands — the side with
    the larger post-fee edge (2026-06-11 audit #6: trading both doubled
    Kelly exposure and double-counted settles)."""
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db}")

    con = connect(db)
    try:
        # Pinnacle 1.50/2.50 -> vig-stripped fair_home ~0.625, fair_away ~0.375.
        _seed_crosswalk_and_odds(
            con,
            odds_game_id="odds-1",
            nba_game_id="nba-1",
            game_date=date(2026, 5, 4),
            home="BOS",
            away="LAL",
            home_odds=1.50,
            away_odds=2.50,
        )
        _seed_completed_game(
            con,
            game_id="g_future",
            game_date=date(2026, 5, 4),
            home="BOS",
            away="LAL",
            home_score=None,
            away_score=None,
            home_won=None,
        )
    finally:
        con.close()

    # YES-home at ask 0.40 -> edge ~0.225; YES-away at ask 0.20 -> edge ~0.175.
    # Both clear the min-edge gate; the home side has the larger post-fee edge.
    home_side = _fake_open_market("KXNBAGAME-26MAY04LALBOS-BOS", yes_bid=39, yes_ask=40)
    away_side = _fake_open_market("KXNBAGAME-26MAY04LALBOS-LAL", yes_bid=19, yes_ask=20)

    async def _fake_pull() -> list[Market]:
        return [away_side, home_side]

    with patch("kq.flows.paper_nba_trade._pull_kalshi_nba_markets", new=_fake_pull):
        summary = run_once_nba(
            db_path=db,
            now_utc=datetime(2026, 5, 4, 22, tzinfo=UTC),
        )

    assert summary.submit_evaluated == 2  # both sides were evaluated
    assert summary.submit_recorded == 1  # but only one trade landed

    con2 = duckdb.connect(str(db), read_only=True)
    try:
        rows = con2.execute("SELECT ticker FROM paper_trade").fetchall()
    finally:
        con2.close()
    assert [r[0] for r in rows] == ["KXNBAGAME-26MAY04LALBOS-BOS"]


# --------------------------- pre-tipoff guard ---------------------------


def test_run_once_nba_skips_game_after_tipoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Once `nba_odds.commence_time` has passed, no trade may be submitted
    for the game — even though the market still shows an edge."""
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db}")

    con = connect(db)
    try:
        # commence_time is seeded at 23:00 UTC on the game date.
        _seed_crosswalk_and_odds(
            con,
            odds_game_id="odds-1",
            nba_game_id="nba-1",
            game_date=date(2026, 5, 4),
            home="BOS",
            away="LAL",
            home_odds=1.50,
            away_odds=2.50,
        )
    finally:
        con.close()

    fake_market = _fake_open_market("KXNBAGAME-26MAY04LALBOS-BOS")

    async def _fake_pull() -> list[Market]:
        return [fake_market]

    with patch("kq.flows.paper_nba_trade._pull_kalshi_nba_markets", new=_fake_pull):
        summary = run_once_nba(
            db_path=db,
            now_utc=datetime(2026, 5, 4, 23, 30, tzinfo=UTC),  # 30 min after tipoff
        )

    assert summary.submit_evaluated == 0
    assert summary.submit_recorded == 0
    con2 = duckdb.connect(str(db), read_only=True)
    try:
        count = con2.execute("SELECT COUNT(*) FROM paper_trade").fetchone()
    finally:
        con2.close()
    assert count is not None and int(count[0]) == 0


def test_run_once_nba_skips_past_date_game_without_tipoff_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fallback guard: with no odds row (no commence_time known), a game
    whose US/Eastern date already passed is refused conservatively."""
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db}")

    # Game dated 2026-05-03; "now" is 2026-05-04 22:00 UTC (May 4 in ET).
    fake_market = _fake_open_market("KXNBAGAME-26MAY03LALBOS-BOS")

    async def _fake_pull() -> list[Market]:
        return [fake_market]

    with patch("kq.flows.paper_nba_trade._pull_kalshi_nba_markets", new=_fake_pull):
        summary = run_once_nba(
            db_path=db,
            now_utc=datetime(2026, 5, 4, 22, tzinfo=UTC),
        )

    assert summary.submit_evaluated == 0
    assert summary.submit_recorded == 0


def test_run_once_nba_skips_finished_game(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A game whose result already landed in nba_game must never be traded,
    even same-day (a market can linger 'open' after the final buzzer)."""
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db}")

    con = connect(db)
    try:
        _seed_completed_game(
            con,
            game_id="g_done",
            game_date=date(2026, 5, 4),
            home="BOS",
            away="LAL",
            home_score=110,
            away_score=100,
            home_won=True,
        )
    finally:
        con.close()

    fake_market = _fake_open_market("KXNBAGAME-26MAY04LALBOS-BOS")

    async def _fake_pull() -> list[Market]:
        return [fake_market]

    with patch("kq.flows.paper_nba_trade._pull_kalshi_nba_markets", new=_fake_pull):
        summary = run_once_nba(
            db_path=db,
            now_utc=datetime(2026, 5, 4, 22, tzinfo=UTC),  # same ET day
        )

    assert summary.submit_evaluated == 0
    assert summary.submit_recorded == 0


# --------------------------- GameContext wiring ---------------------------


def test_build_game_context_flags_back_to_backs(tmp_path: Path) -> None:
    """Both teams played (and finished) a game the previous day -> both
    back-to-back flags set; travel stays at the neutral 0.0 default."""
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        _seed_completed_game(
            con,
            game_id="g_prev_home",
            game_date=date(2026, 5, 3),
            home="BOS",
            away="MIA",
            home_score=110,
            away_score=100,
            home_won=True,
        )
        _seed_completed_game(
            con,
            game_id="g_prev_away",
            game_date=date(2026, 5, 3),
            home="DEN",
            away="LAL",
            home_score=105,
            away_score=95,
            home_won=True,
        )
        ref = parse_nba_market_ticker("KXNBAGAME-26MAY04LALBOS-BOS")
        assert ref is not None
        ctx = _build_game_context(con, ref)
    finally:
        con.close()
    assert ctx == GameContext(home_back_to_back=True, away_back_to_back=True)


def test_build_game_context_neutral_without_prior_day_games(tmp_path: Path) -> None:
    """No prior-day games -> neutral context. An UNFINISHED prior-day row
    (e.g. a postponed listing) doesn't count as a played game."""
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        _seed_completed_game(
            con,
            game_id="g_postponed",
            game_date=date(2026, 5, 3),
            home="BOS",
            away="MIA",
            home_score=None,
            away_score=None,
            home_won=None,
        )
        ref = parse_nba_market_ticker("KXNBAGAME-26MAY04LALBOS-BOS")
        assert ref is not None
        ctx = _build_game_context(con, ref)
    finally:
        con.close()
    assert ctx == GameContext()


def test_run_once_nba_wires_game_context_into_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression for the audit's `elo_context=None` finding: the live flow
    must hand the evaluator a schedule-derived GameContext, and the Elo
    probability must actually move when the context does (B2B penalty)."""
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db}")

    con = connect(db)
    try:
        # BOS finished a home game yesterday -> tonight BOS is on a B2B.
        _seed_completed_game(
            con,
            game_id="g_yesterday",
            game_date=date(2026, 5, 3),
            home="BOS",
            away="MIA",
            home_score=110,
            away_score=100,
            home_won=True,
        )
    finally:
        con.close()

    # No odds/crosswalk seeded -> the evaluator falls back to Elo, where the
    # context adjustment is observable in model_prob_home.
    fake_market = _fake_open_market("KXNBAGAME-26MAY04LALBOS-BOS")

    async def _fake_pull() -> list[Market]:
        return [fake_market]

    calls: list[tuple[NbaSignalInputs, NbaSignalDecision]] = []

    def _spy(inputs: NbaSignalInputs, **kwargs: float) -> NbaSignalDecision:
        decision = evaluate_nba_signal(inputs, **kwargs)  # type: ignore[arg-type]
        calls.append((inputs, decision))
        return decision

    with (
        patch("kq.flows.paper_nba_trade._pull_kalshi_nba_markets", new=_fake_pull),
        patch("kq.flows.paper_nba_trade.evaluate_nba_signal", new=_spy),
    ):
        run_once_nba(
            db_path=db,
            now_utc=datetime(2026, 5, 4, 22, tzinfo=UTC),
        )

    assert len(calls) == 1
    inputs, decision = calls[0]
    expected_ctx = GameContext(home_back_to_back=True, away_back_to_back=False)
    assert inputs.elo_context == expected_ctx

    # Reproduce the flow's Elo state (yesterday's game folded in) and verify
    # the recorded probability is the WITH-context one, not the neutral one.
    elo = NbaEloRatings()
    update_after_game(
        elo,
        home_team_abbr="BOS",
        away_team_abbr="MIA",
        home_score=110,
        away_score=100,
        ctx=None,
    )
    prob_with_b2b = predict_win_prob(
        home_rating=elo.get("BOS"),
        away_rating=elo.get("LAL"),
        home_team_abbr="BOS",
        ctx=expected_ctx,
    )
    prob_neutral = predict_win_prob(
        home_rating=elo.get("BOS"),
        away_rating=elo.get("LAL"),
        home_team_abbr="BOS",
        ctx=None,
    )
    assert decision.model_prob_home == pytest.approx(prob_with_b2b)
    assert prob_with_b2b != pytest.approx(prob_neutral)


# --------------------------- season-boundary Elo regression ---------------------------


def test_compute_elo_state_regresses_between_seasons(tmp_path: Path) -> None:
    """Crossing a season boundary pulls every rating 1/4 toward 1505 —
    even for teams that haven't played yet in the new season."""
    db = tmp_path / "nba.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        # Season 2025-26 finale (April) ...
        _seed_completed_game(
            con,
            game_id="g_spring",
            game_date=date(2026, 4, 10),
            home="LAL",
            away="BOS",
            home_score=110,
            away_score=100,
            home_won=True,
        )
        # ... then a season 2026-27 game (November) between OTHER teams.
        _seed_completed_game(
            con,
            game_id="g_fall",
            game_date=date(2026, 11, 1),
            home="MIA",
            away="NYK",
            home_score=105,
            away_score=95,
            home_won=True,
        )
        elo = _compute_elo_state(con)
    finally:
        con.close()

    expected = NbaEloRatings()
    update_after_game(
        expected,
        home_team_abbr="LAL",
        away_team_abbr="BOS",
        home_score=110,
        away_score=100,
        ctx=None,
    )
    lal_unregressed = expected.get("LAL")
    expected.regress_to_baseline()

    assert elo.get("LAL") == pytest.approx(expected.get("LAL"))
    assert elo.get("BOS") == pytest.approx(expected.get("BOS"))
    assert elo.get("LAL") != pytest.approx(lal_unregressed)
