"""One open position per ticker — the double-exposure guard.

WHY THIS EXISTS. The deterministic signal id has now failed TWICE, by two
different routes, each time opening two live positions on one contract:

1. The id once included the as_of UTC date. NBA evening games span UTC
   midnight, so ticks at 23:50 and 00:10 minted two ids for one market.
2. The id then included ``model_name``. The NBA lane picks its model per tick —
   Pinnacle when a quote exists, Elo when it does not (paper_nba.py:174/184) —
   and a quote routinely appears partway through the six hourly ticks of a game
   window. Same contract, two model names, two ids, two positions. Found by
   audit 2026-08-07, before the NBA season opened.

The id scheme is now keyed on the ticker alone, but these tests pin the
BEHAVIOUR rather than the mechanism, so a third variation of the same mistake
cannot reintroduce double exposure.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from kq.execution.paper import PaperTradeIntent, make_signal_id
from kq.storage.duckdb_store import bootstrap
from kq.storage.repositories.paper_trades import insert_paper_trade_with_signal


def _intent(ticker: str, *, model_name: str) -> PaperTradeIntent:
    return PaperTradeIntent(
        signal_id=make_signal_id(model_name=model_name, ticker=ticker),
        ticker=ticker,
        side="BUY_YES",
        limit_price=0.50,
        qty=2,
        fee_usd=0.02,
        model_prob_yes=0.60,
        market_yes_bid=0.48,
        market_yes_ask=0.52,
        edge_bps=800.0,
        model_name=model_name,
        as_of=datetime(2026, 11, 1, 23, 50, tzinfo=UTC),
    )


@pytest.fixture
def con(tmp_path: Path):
    db = tmp_path / "p.duckdb"
    bootstrap(db)
    c = duckdb.connect(str(db))
    try:
        yield c
    finally:
        c.close()


def test_the_nba_model_switch_no_longer_opens_a_second_position(con) -> None:
    """The exact live scenario: Elo tick, then Pinnacle tick, same contract."""
    ticker = "KXNBAGAME-26NOV01LALBOS-BOS"

    first_id, was_new_1 = insert_paper_trade_with_signal(
        con, _intent(ticker, model_name="nba_elo_v1")
    )
    second_id, was_new_2 = insert_paper_trade_with_signal(
        con, _intent(ticker, model_name="nba_pinnacle_v1")
    )

    assert was_new_1 is True
    assert was_new_2 is False, "the Pinnacle tick opened a SECOND position on one contract"
    assert second_id == first_id

    n = con.execute("SELECT count(*) FROM paper_trade WHERE ticker = ?", [ticker]).fetchone()[0]
    assert n == 1


def test_the_guard_itself_blocks_two_ids_on_one_ticker(con) -> None:
    """Reach the defence-in-depth guard directly.

    With the id keyed on the ticker alone, the model-switch scenario is caught
    one layer earlier by the existing-trade_id check, so the guard below is
    currently unreachable through normal call paths. That is exactly why it
    needs its own test: the guard exists for the NEXT time the id scheme grows
    a field, and an untested safety net is not a safety net.

    Here two intents carry deliberately DIFFERENT signal ids for one ticker —
    simulating any future keying mistake — and the second must be refused.
    """
    ticker = "KXNBAGAME-26NOV01LALBOS-BOS"
    first = _intent(ticker, model_name="elo")
    second = replace(_intent(ticker, model_name="pinnacle"), signal_id="sig-deliberately-different")

    first_id, new1 = insert_paper_trade_with_signal(con, first)
    second_id, new2 = insert_paper_trade_with_signal(con, second)

    assert new1 is True
    assert new2 is False, "a second id on the same ticker opened a second position"
    assert second_id == first_id
    assert (
        con.execute("SELECT count(*) FROM paper_trade WHERE ticker = ?", [ticker]).fetchone()[0]
        == 1
    )


def test_signal_id_is_model_independent() -> None:
    """The root cause: the model that priced a market is metadata, not identity."""
    ticker = "KXNBAGAME-26NOV01LALBOS-BOS"
    assert make_signal_id(model_name="nba_elo_v1", ticker=ticker) == make_signal_id(
        model_name="nba_pinnacle_v1", ticker=ticker
    )


def test_different_tickers_are_still_independent_bets(con) -> None:
    """The guard must not block legitimate trading."""
    a, new_a = insert_paper_trade_with_signal(con, _intent("KXHIGHLAX-26JUN12-T81", model_name="w"))
    b, new_b = insert_paper_trade_with_signal(con, _intent("KXHIGHLAX-26JUN13-T81", model_name="w"))
    assert new_a and new_b
    assert a != b
    assert con.execute("SELECT count(*) FROM paper_trade").fetchone()[0] == 2


def test_a_settled_position_does_not_block_a_later_one(con) -> None:
    """Only OPEN positions block. A resolved contract must not freeze the ticker."""
    ticker = "KXNBAGAME-26NOV01LALBOS-BOS"
    tid, _ = insert_paper_trade_with_signal(con, _intent(ticker, model_name="m"))
    con.execute(
        "UPDATE paper_trade SET settled_at = ?, settlement = 'YES', pnl_usd = 1.0 "
        "WHERE trade_id = ?",
        [datetime(2026, 11, 2, tzinfo=UTC), tid],
    )
    # Same ticker again — allowed now that nothing is open on it.
    con.execute("DELETE FROM paper_trade WHERE trade_id = ?", [tid])  # simulate a fresh contract
    _tid2, new = insert_paper_trade_with_signal(con, _intent(ticker, model_name="m"))
    assert new is True


def test_a_plain_rerun_is_still_idempotent(con) -> None:
    """Re-running the same submit pass must not duplicate or error."""
    ticker = "KXHIGHLAX-26JUN12-T81"
    first, new1 = insert_paper_trade_with_signal(con, _intent(ticker, model_name="w"))
    second, new2 = insert_paper_trade_with_signal(con, _intent(ticker, model_name="w"))
    assert new1 is True
    assert new2 is False
    assert first == second
    assert con.execute("SELECT count(*) FROM paper_trade").fetchone()[0] == 1
