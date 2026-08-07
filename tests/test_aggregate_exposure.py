"""The aggregate exposure cap: a lane can never commit more than it has.

THE DEFECT (audit 2026-08-07, owner-approved fix). Every submit run sized its
markets against ``starting + settled_pnl`` — open positions were invisible to
sizing, so committed capital compounded across days without bound. Measured
live: 148 open trades holding ~$1,735 of premium against a $1,000 bankroll
(~173%). The per-lane isolation in #128 had also removed the only accidental
brake (the shared bankroll going negative).

THE FIX: sizing uses FREE capital — ``starting + settled P&L - open cost`` —
so Kelly self-limits and stakes hit $0 exactly when the lane is fully
deployed. No new tunable; the bound is the arithmetic of a real account.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from kq.execution.kelly import fractional_kelly_stake
from kq.execution.paper import PaperTradeIntent, make_signal_id
from kq.storage.duckdb_store import bootstrap
from kq.storage.repositories.paper_trades import (
    insert_paper_trade_with_signal,
    open_exposure_usd,
    settled_pnl_total,
    vertical_free_capital_usd,
)


def _insert(
    con: duckdb.DuckDBPyConnection,
    ticker: str,
    *,
    price: float,
    qty: int,
    fee: float,
    settled_pnl: float | None = None,
) -> None:
    intent = PaperTradeIntent(
        signal_id=make_signal_id(model_name="t", ticker=ticker),
        ticker=ticker,
        side="BUY_YES",
        limit_price=price,
        qty=qty,
        fee_usd=fee,
        model_prob_yes=0.60,
        market_yes_bid=price - 0.02,
        market_yes_ask=price,
        edge_bps=700.0,
        model_name="t",
        as_of=datetime(2026, 8, 1, tzinfo=UTC),
    )
    trade_id, was_new = insert_paper_trade_with_signal(con, intent)
    assert was_new
    if settled_pnl is not None:
        con.execute(
            "UPDATE paper_trade SET settled_at = ?, settlement = 'YES', pnl_usd = ? "
            "WHERE trade_id = ?",
            [datetime(2026, 8, 2, tzinfo=UTC), settled_pnl, trade_id],
        )


@pytest.fixture
def con(tmp_path: Path):
    db = tmp_path / "e.duckdb"
    bootstrap(db)
    c = duckdb.connect(str(db))
    try:
        yield c
    finally:
        c.close()


def test_open_positions_reduce_free_capital(con) -> None:
    """The core accounting identity: free = starting + settled P&L - open cost."""
    # Open: $50 premium + $1 fee. Settled: net -$20.
    _insert(con, "KXNFLGAME-26SEP10-KCPHI", price=0.50, qty=100, fee=1.00)
    _insert(con, "KXNFLGAME-26SEP11-NYGDAL", price=0.40, qty=50, fee=0.50, settled_pnl=-20.0)

    assert open_exposure_usd(con, vertical="nfl") == pytest.approx(51.0)
    assert settled_pnl_total(con, vertical="nfl") == pytest.approx(-20.0)
    free = vertical_free_capital_usd(con, vertical="nfl", starting_usd=1000.0)
    assert free == pytest.approx(1000.0 - 20.0 - 51.0)


def test_fully_committed_lane_sizes_to_zero(con) -> None:
    """The 173% scenario cannot recur: at full deployment the stake is $0.00."""
    # Commit ~$1,000 of premium across open positions.
    for i in range(10):
        _insert(con, f"KXHIGHLAX-26AUG{10 + i}-T80", price=0.50, qty=200, fee=1.00)

    free = vertical_free_capital_usd(con, vertical="weather", starting_usd=1000.0)
    assert free < 0  # 10 x ($100 + $1) = $1,010 committed
    assert fractional_kelly_stake(prob=0.60, price=0.50, bankroll_usd=free) == 0.0


def test_settlement_releases_capital(con) -> None:
    """A settled trade stops locking capital; its net P&L takes over."""
    _insert(con, "KXNFLGAME-26SEP10-KCPHI", price=0.50, qty=100, fee=1.00)
    before = vertical_free_capital_usd(con, vertical="nfl", starting_usd=1000.0)
    assert before == pytest.approx(949.0)

    # Settles as a win: payout $100 - cost $50 - fee $1 = net +$49.
    con.execute(
        "UPDATE paper_trade SET settled_at = ?, settlement = 'YES', pnl_usd = 49.0 "
        "WHERE settled_at IS NULL",
        [datetime(2026, 8, 3, tzinfo=UTC)],
    )
    after = vertical_free_capital_usd(con, vertical="nfl", starting_usd=1000.0)
    assert after == pytest.approx(1049.0)  # stake returned + profit


def test_exposure_is_vertical_scoped(con) -> None:
    """Weather's open positions must not shrink the NFL lane's free capital."""
    _insert(con, "KXHIGHLAX-26AUG10-T80", price=0.50, qty=100, fee=1.00)

    assert open_exposure_usd(con, vertical="weather") == pytest.approx(51.0)
    assert open_exposure_usd(con, vertical="nfl") == 0.0
    assert vertical_free_capital_usd(con, vertical="nfl", starting_usd=1000.0) == pytest.approx(
        1000.0
    )
    # Unscoped exposure remains the portfolio view.
    assert open_exposure_usd(con) == pytest.approx(51.0)


def test_unknown_vertical_is_refused(con) -> None:
    with pytest.raises(ValueError, match="unknown vertical"):
        open_exposure_usd(con, vertical="hockey")
