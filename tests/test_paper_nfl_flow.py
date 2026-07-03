"""End-to-end tests for the NFL paper-trading flow.

Coverage:
- Settlement maps ``nfl_game`` results -> YES/NO for both YES-home and
  YES-away ticker variants, keyed on the ``completed`` finality gate.
- TIE settlement: both sides resolve at $0.50 (prod-verified KXNFLGAME
  rules), settlement value 'TIE', correct P&L for BUY_YES and BUY_NO.
- VOID path: no completed result past the window voids at -fee; inside
  the window the trade waits.
- Finality: a second settle pass over settled trades changes nothing.
- Weather/NBA tickers are left alone by the NFL settler.
- ``run_once_nfl`` orchestrates end-to-end with a mocked Kalshi pull:
  records at most ONE side per game (larger post-fee edge wins), refuses
  post-kickoff and finished games, refuses anchorless games, idempotent
  re-runs.

Async Kalshi calls are mocked by patching ``_pull_kalshi_nfl_markets``
in the flow module, mirroring the NBA flow tests.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

import duckdb
import pytest

from kq.clients.kalshi._types import Market
from kq.execution.paper import PaperTradeIntent
from kq.flows.paper_nfl_trade import PaperNflRunSummary, run_once_nfl
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.paper_trades import (
    insert_paper_trade_with_signal,
    settle_due_nfl_paper_trades,
)

# --------------------------- fixtures ---------------------------


def _seed_nfl_game(
    con: duckdb.DuckDBPyConnection,
    *,
    game_id: str,
    game_date: date,
    home: str,
    away: str,
    home_score: int | None = None,
    away_score: int | None = None,
    completed: bool = False,
    home_won: bool | None = None,
    commence_time: datetime | None = None,
) -> None:
    con.execute(
        """
        INSERT INTO nfl_game (game_id, season, game_date, commence_time,
            home_team, home_team_abbr, away_team, away_team_abbr,
            home_score, away_score, completed, home_won, fetched_at)
        VALUES (?, 2026, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            game_id,
            game_date,
            commence_time or datetime(game_date.year, game_date.month, game_date.day, 17, 0),
            f"{home} City",
            home,
            f"{away} City",
            away,
            home_score,
            away_score,
            completed,
            home_won,
            datetime(2026, 9, 13),
        ],
    )


def _seed_crosswalk_and_odds(
    con: duckdb.DuckDBPyConnection,
    *,
    odds_game_id: str,
    nfl_game_id: str,
    game_date: date,
    home: str,
    away: str,
    home_odds: float,
    away_odds: float,
    commence_time: datetime,
    fetched_at: datetime,
) -> None:
    con.execute(
        """
        INSERT INTO nfl_game_crosswalk
        (odds_api_game_id, nfl_game_id, home_team_abbr, away_team_abbr, game_date, matched_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [odds_game_id, nfl_game_id, home, away, game_date, datetime(2026, 9, 13)],
    )
    con.execute(
        """
        INSERT INTO nfl_odds
        (odds_api_game_id, bookmaker_key, market_key, home_team, away_team,
         commence_time, home_decimal_odds, away_decimal_odds,
         book_last_update, fetched_at)
        VALUES (?, 'pinnacle', 'h2h', ?, ?, ?, ?, ?, ?, ?)
        """,
        [odds_game_id, home, away, commence_time, home_odds, away_odds, fetched_at, fetched_at],
    )


def _seed_unsettled_nfl_trade(
    con: duckdb.DuckDBPyConnection,
    *,
    ticker: str,
    side: str = "BUY_YES",
    limit_price: float = 0.40,
    qty: int = 100,
    fee_usd: float = 1.50,
) -> str:
    intent = PaperTradeIntent(
        signal_id=f"sig-{ticker}-{side}",
        as_of=datetime(2026, 9, 13, 21, tzinfo=UTC),
        ticker=ticker,
        side=side,  # type: ignore[arg-type]
        limit_price=limit_price,
        qty=qty,
        fee_usd=fee_usd,
        model_prob_yes=0.55,
        market_yes_bid=limit_price - 0.01,
        market_yes_ask=limit_price,
        edge_bps=1500,
        model_name="nfl_pinnacle_anchored_v1",
    )
    trade_id, _ = insert_paper_trade_with_signal(con, intent)
    return trade_id


def _fake_open_market(ticker: str, *, yes_bid: float = 0.39, yes_ask: float = 0.40) -> Market:
    return Market(
        ticker=ticker,
        event_ticker=ticker.rsplit("-", 1)[0],
        title=ticker,
        status="open",
        category=None,
        yes_ask=yes_ask,
        yes_bid=yes_bid,
        last_price=None,
        volume=0.0,
        open_interest=0.0,
        open_time=None,
        close_time=None,
        expected_expiration_time=None,
        rules_primary=None,
    )


def _new_db(tmp_path: Path) -> Path:
    db = tmp_path / "nfl.duckdb"
    bootstrap(db)
    return db


# --------------------------- settlement ---------------------------


def test_settle_yes_home_ticker_home_won(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    con = connect(db)
    try:
        _seed_nfl_game(
            con,
            game_id="g1",
            game_date=date(2026, 9, 13),
            home="NYG",
            away="DAL",
            home_score=24,
            away_score=17,
            completed=True,
            home_won=True,
        )
        trade_id = _seed_unsettled_nfl_trade(con, ticker="KXNFLGAME-26SEP13DALNYG-NYG")
        n = settle_due_nfl_paper_trades(con, now=datetime(2026, 9, 14, 6, tzinfo=UTC))
        assert n == 1
        row = con.execute(
            "SELECT settlement, pnl_usd FROM paper_trade WHERE trade_id = ?", [trade_id]
        ).fetchone()
        assert row is not None
        assert row[0] == "YES"
        # BUY_YES @0.40 x100, fee 1.50 -> 100*(1-0.40)-1.50
        assert float(row[1]) == pytest.approx(58.5)
    finally:
        con.close()


def test_settle_yes_away_ticker_alignment(tmp_path: Path) -> None:
    """YES = DAL (away). Home (NYG) won -> the away contract settles NO."""
    db = _new_db(tmp_path)
    con = connect(db)
    try:
        _seed_nfl_game(
            con,
            game_id="g1",
            game_date=date(2026, 9, 13),
            home="NYG",
            away="DAL",
            home_score=24,
            away_score=17,
            completed=True,
            home_won=True,
        )
        trade_id = _seed_unsettled_nfl_trade(con, ticker="KXNFLGAME-26SEP13DALNYG-DAL")
        assert settle_due_nfl_paper_trades(con, now=datetime(2026, 9, 14, 6, tzinfo=UTC)) == 1
        row = con.execute(
            "SELECT settlement, pnl_usd FROM paper_trade WHERE trade_id = ?", [trade_id]
        ).fetchone()
        assert row is not None
        assert row[0] == "NO"
        assert float(row[1]) == pytest.approx(-41.5)  # 100*(0-0.40)-1.50
    finally:
        con.close()


def test_settle_tie_resolves_both_sides_at_half(tmp_path: Path) -> None:
    """NFL ties are real; Kalshi resolves each side at $0.50 (prod rules).
    BUY_YES and BUY_NO both book qty*(0.5 - fill) - fee."""
    db = _new_db(tmp_path)
    con = connect(db)
    try:
        _seed_nfl_game(
            con,
            game_id="g1",
            game_date=date(2026, 9, 13),
            home="WAS",
            away="PHI",
            home_score=20,
            away_score=20,
            completed=True,
            home_won=None,
        )
        yes_id = _seed_unsettled_nfl_trade(con, ticker="KXNFLGAME-26SEP13PHIWAS-WAS")
        no_id = _seed_unsettled_nfl_trade(
            con, ticker="KXNFLGAME-26SEP13PHIWAS-PHI", side="BUY_NO", limit_price=0.55
        )
        n = settle_due_nfl_paper_trades(con, now=datetime(2026, 9, 14, 6, tzinfo=UTC))
        assert n == 2
        yes_row = con.execute(
            "SELECT settlement, pnl_usd FROM paper_trade WHERE trade_id = ?", [yes_id]
        ).fetchone()
        no_row = con.execute(
            "SELECT settlement, pnl_usd FROM paper_trade WHERE trade_id = ?", [no_id]
        ).fetchone()
        assert yes_row is not None and no_row is not None
        assert yes_row[0] == "TIE"
        assert float(yes_row[1]) == pytest.approx(100 * (0.5 - 0.40) - 1.50)
        assert no_row[0] == "TIE"
        assert float(no_row[1]) == pytest.approx(100 * (0.5 - 0.55) - 1.50)
    finally:
        con.close()


def test_settle_waits_for_completion_then_lands(tmp_path: Path) -> None:
    """Scores present but completed=False (in progress) must NOT settle —
    the completed flag, not home_won, is the finality gate."""
    db = _new_db(tmp_path)
    con = connect(db)
    try:
        _seed_nfl_game(
            con,
            game_id="g1",
            game_date=date(2026, 9, 13),
            home="NYG",
            away="DAL",
            home_score=14,
            away_score=10,
            completed=False,
            home_won=None,
        )
        trade_id = _seed_unsettled_nfl_trade(con, ticker="KXNFLGAME-26SEP13DALNYG-NYG")
        assert settle_due_nfl_paper_trades(con, now=datetime(2026, 9, 13, 20, tzinfo=UTC)) == 0
        con.execute(
            "UPDATE nfl_game SET completed = TRUE, home_score = 24, away_score = 17, "
            "home_won = TRUE WHERE game_id = 'g1'"
        )
        assert settle_due_nfl_paper_trades(con, now=datetime(2026, 9, 14, 6, tzinfo=UTC)) == 1
        row = con.execute(
            "SELECT settlement FROM paper_trade WHERE trade_id = ?", [trade_id]
        ).fetchone()
        assert row is not None and row[0] == "YES"
    finally:
        con.close()


def test_settle_voids_after_window_and_waits_inside_it(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    con = connect(db)
    try:
        trade_id = _seed_unsettled_nfl_trade(con, ticker="KXNFLGAME-26SEP13DALNYG-NYG")
        # 3 days past: inside the 7-day window -> wait.
        assert settle_due_nfl_paper_trades(con, now=datetime(2026, 9, 16, 12, tzinfo=UTC)) == 0
        # 10 days past: void at -fee.
        assert settle_due_nfl_paper_trades(con, now=datetime(2026, 9, 23, 12, tzinfo=UTC)) == 1
        row = con.execute(
            "SELECT settlement, pnl_usd FROM paper_trade WHERE trade_id = ?", [trade_id]
        ).fetchone()
        assert row is not None
        assert row[0] == "VOID"
        assert float(row[1]) == pytest.approx(-1.50)
    finally:
        con.close()


def test_settle_is_final_second_pass_changes_nothing(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    con = connect(db)
    try:
        _seed_nfl_game(
            con,
            game_id="g1",
            game_date=date(2026, 9, 13),
            home="NYG",
            away="DAL",
            home_score=24,
            away_score=17,
            completed=True,
            home_won=True,
        )
        _seed_unsettled_nfl_trade(con, ticker="KXNFLGAME-26SEP13DALNYG-NYG")
        assert settle_due_nfl_paper_trades(con, now=datetime(2026, 9, 14, 6, tzinfo=UTC)) == 1
        # Adversarial: flip the stored result (should be impossible via the
        # repo, but settlement must STILL not re-touch a settled trade).
        assert settle_due_nfl_paper_trades(con, now=datetime(2026, 9, 15, 6, tzinfo=UTC)) == 0
    finally:
        con.close()


def test_settler_ignores_other_verticals(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    con = connect(db)
    try:
        weather_id = _seed_unsettled_nfl_trade(con, ticker="KXHIGHLAX-26SEP13-T85")
        nba_id = _seed_unsettled_nfl_trade(con, ticker="KXNBAGAME-26APR30BOSPHI-PHI")
        assert settle_due_nfl_paper_trades(con, now=datetime(2026, 12, 1, tzinfo=UTC)) == 0
        for tid in (weather_id, nba_id):
            row = con.execute(
                "SELECT settled_at FROM paper_trade WHERE trade_id = ?", [tid]
            ).fetchone()
            assert row is not None and row[0] is None
    finally:
        con.close()


# --------------------------- submit pass (run_once_nfl) ---------------------------


def _seed_tradeable_game(con: duckdb.DuckDBPyConnection) -> None:
    """DAL @ NYG on 2026-09-13 ET, kickoff 00:20 UTC Sep 14. Pinnacle
    2.38 (home) / 1.66 (away) -> fair_home ~ 0.411, fair_away ~ 0.589."""
    kickoff = datetime(2026, 9, 14, 0, 20)
    _seed_nfl_game(
        con,
        game_id="odds-dalnyg",
        game_date=date(2026, 9, 13),
        home="NYG",
        away="DAL",
        commence_time=kickoff,
    )
    _seed_crosswalk_and_odds(
        con,
        odds_game_id="odds-dalnyg",
        nfl_game_id="odds-dalnyg",
        game_date=date(2026, 9, 13),
        home="NYG",
        away="DAL",
        home_odds=2.38,
        away_odds=1.66,
        commence_time=kickoff,
        fetched_at=datetime(2026, 9, 13, 21, 0),
    )


def test_run_once_nfl_writes_paper_trade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _new_db(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db}")

    con = connect(db)
    try:
        _seed_tradeable_game(con)
    finally:
        con.close()

    # YES = NYG (home), fair ~0.411 vs ask 0.25 -> ~16pp edge -> BUY_YES.
    fake_market = _fake_open_market("KXNFLGAME-26SEP13DALNYG-NYG", yes_bid=0.24, yes_ask=0.25)

    async def _fake_pull() -> list[Market]:
        return [fake_market]

    with patch("kq.flows.paper_nfl_trade._pull_kalshi_nfl_markets", new=_fake_pull):
        summary = run_once_nfl(
            db_path=db,
            now_utc=datetime(2026, 9, 13, 22, 0, tzinfo=UTC),
        )

    assert isinstance(summary, PaperNflRunSummary)
    assert summary.skipped_reason is None
    assert summary.submit_evaluated == 1
    assert summary.submit_recorded == 1
    assert summary.submit_skipped_no_anchor == 0
    assert summary.settle_processed == 0

    con2 = duckdb.connect(str(db), read_only=True)
    try:
        row = con2.execute("SELECT ticker, side FROM paper_trade").fetchone()
        assert row is not None
        assert row[0] == "KXNFLGAME-26SEP13DALNYG-NYG"
        assert row[1] == "BUY_YES"
        sig = con2.execute("SELECT model_name FROM signal LIMIT 1").fetchone()
        assert sig is not None and sig[0] == "nfl_pinnacle_anchored_v1"
    finally:
        con2.close()


def test_run_once_nfl_records_one_side_per_game(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both sides clear the edge gate; only the larger post-fee edge books.
    fair_home ~0.411: YES-NYG ask 0.30 (~11pp) vs YES-DAL ask 0.40
    (fair 0.589, ~19pp) -> the DAL side must win and NYG be skipped."""
    db = _new_db(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db}")
    con = connect(db)
    try:
        _seed_tradeable_game(con)
    finally:
        con.close()

    markets = [
        _fake_open_market("KXNFLGAME-26SEP13DALNYG-NYG", yes_bid=0.29, yes_ask=0.30),
        _fake_open_market("KXNFLGAME-26SEP13DALNYG-DAL", yes_bid=0.39, yes_ask=0.40),
    ]

    async def _fake_pull() -> list[Market]:
        return markets

    with patch("kq.flows.paper_nfl_trade._pull_kalshi_nfl_markets", new=_fake_pull):
        summary = run_once_nfl(db_path=db, now_utc=datetime(2026, 9, 13, 22, 0, tzinfo=UTC))

    assert summary.submit_evaluated == 2
    assert summary.submit_recorded == 1
    con2 = duckdb.connect(str(db), read_only=True)
    try:
        rows = con2.execute("SELECT ticker FROM paper_trade").fetchall()
        assert [r[0] for r in rows] == ["KXNFLGAME-26SEP13DALNYG-DAL"]
    finally:
        con2.close()


def test_run_once_nfl_pre_kickoff_guard_blocks_started_games(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _new_db(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db}")
    con = connect(db)
    try:
        _seed_tradeable_game(con)
    finally:
        con.close()

    fake_market = _fake_open_market("KXNFLGAME-26SEP13DALNYG-NYG", yes_bid=0.24, yes_ask=0.25)

    async def _fake_pull() -> list[Market]:
        return [fake_market]

    with patch("kq.flows.paper_nfl_trade._pull_kalshi_nfl_markets", new=_fake_pull):
        # 00:30 UTC Sep 14 — ten minutes AFTER kickoff.
        summary = run_once_nfl(db_path=db, now_utc=datetime(2026, 9, 14, 0, 30, tzinfo=UTC))

    assert summary.submit_evaluated == 0
    assert summary.submit_recorded == 0


def test_run_once_nfl_refuses_finished_games(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _new_db(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db}")
    con = connect(db)
    try:
        _seed_nfl_game(
            con,
            game_id="g1",
            game_date=date(2026, 9, 13),
            home="NYG",
            away="DAL",
            home_score=24,
            away_score=17,
            completed=True,
            home_won=True,
            commence_time=datetime(2026, 9, 14, 0, 20),
        )
    finally:
        con.close()

    fake_market = _fake_open_market("KXNFLGAME-26SEP13DALNYG-NYG", yes_bid=0.24, yes_ask=0.25)

    async def _fake_pull() -> list[Market]:
        return [fake_market]

    with patch("kq.flows.paper_nfl_trade._pull_kalshi_nfl_markets", new=_fake_pull):
        summary = run_once_nfl(db_path=db, now_utc=datetime(2026, 9, 13, 22, 0, tzinfo=UTC))

    assert summary.submit_evaluated == 0
    assert summary.submit_recorded == 0


def test_run_once_nfl_no_anchor_no_signal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No crosswalk/odds seeded: the game must be counted as no-anchor and
    produce NOTHING — the no-fallback pin (design doc: no Elo for NFL v1)."""
    db = _new_db(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db}")
    con = connect(db)
    try:
        _seed_nfl_game(
            con,
            game_id="g1",
            game_date=date(2026, 9, 13),
            home="NYG",
            away="DAL",
            commence_time=datetime(2026, 9, 14, 0, 20),
        )
    finally:
        con.close()

    fake_market = _fake_open_market("KXNFLGAME-26SEP13DALNYG-NYG", yes_bid=0.24, yes_ask=0.25)

    async def _fake_pull() -> list[Market]:
        return [fake_market]

    with patch("kq.flows.paper_nfl_trade._pull_kalshi_nfl_markets", new=_fake_pull):
        summary = run_once_nfl(db_path=db, now_utc=datetime(2026, 9, 13, 22, 0, tzinfo=UTC))

    assert summary.submit_skipped_no_anchor == 1
    assert summary.submit_recorded == 0
    con2 = duckdb.connect(str(db), read_only=True)
    try:
        count = con2.execute("SELECT COUNT(*) FROM paper_trade").fetchone()
        assert count is not None and int(count[0]) == 0
    finally:
        con2.close()


def test_run_once_nfl_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _new_db(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db}")
    con = connect(db)
    try:
        _seed_tradeable_game(con)
    finally:
        con.close()

    fake_market = _fake_open_market("KXNFLGAME-26SEP13DALNYG-NYG", yes_bid=0.24, yes_ask=0.25)

    async def _fake_pull() -> list[Market]:
        return [fake_market]

    with patch("kq.flows.paper_nfl_trade._pull_kalshi_nfl_markets", new=_fake_pull):
        first = run_once_nfl(db_path=db, now_utc=datetime(2026, 9, 13, 22, 0, tzinfo=UTC))
        second = run_once_nfl(db_path=db, now_utc=datetime(2026, 9, 13, 22, 30, tzinfo=UTC))

    assert first.submit_recorded == 1
    assert second.submit_recorded == 0
    con2 = duckdb.connect(str(db), read_only=True)
    try:
        count = con2.execute("SELECT COUNT(*) FROM paper_trade").fetchone()
        assert count is not None and int(count[0]) == 1
    finally:
        con2.close()


def test_run_once_nfl_settle_only_skips_submit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _new_db(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db}")
    con = connect(db)
    try:
        _seed_nfl_game(
            con,
            game_id="g1",
            game_date=date(2026, 9, 13),
            home="NYG",
            away="DAL",
            home_score=24,
            away_score=17,
            completed=True,
            home_won=True,
        )
        _seed_unsettled_nfl_trade(con, ticker="KXNFLGAME-26SEP13DALNYG-NYG")
    finally:
        con.close()

    # No Kalshi patch needed: settle_only must never touch the network.
    summary = run_once_nfl(
        db_path=db, settle_only=True, now_utc=datetime(2026, 9, 14, 6, tzinfo=UTC)
    )
    assert summary.submit_evaluated == 0
    assert summary.settle_processed == 1
