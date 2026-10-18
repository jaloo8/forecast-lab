"""Per-vertical bankroll isolation.

THE BUG THIS PINS (measured on the host 2026-08-06): every paper flow computed
``bankroll = starting + settled_pnl_total(con)`` across ALL settled trades. The
weather lane's 443 settled trades (-$1,197.88) drove the shared bankroll to
-$197.88, and ``fractional_kelly_stake`` returns $0.00 for a non-positive
bankroll -- so the freshly-deployed NFL lane would have placed ZERO trades,
silently and indefinitely, while every scheduled job still reported success.

One lane's drawdown must never be able to switch another lane off.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from kq.execution.kelly import fractional_kelly_stake
from kq.storage.duckdb_store import bootstrap
from kq.storage.repositories.paper_trades import (
    VERTICAL_TICKER_PREFIXES,
    settled_pnl_total,
)


def _seed(con: duckdb.DuckDBPyConnection, ticker: str, pnl: float, idx: int) -> None:
    # paper_trade.signal_id is a foreign key into signal.
    con.execute(
        "INSERT INTO signal (signal_id, as_of, ticker, model_prob_yes, model_name) "
        "VALUES (?, ?, ?, 0.6, 'test')",
        [f"s{idx}", datetime(2026, 8, 1, tzinfo=UTC), ticker],
    )
    con.execute(
        "INSERT INTO paper_trade "
        "(trade_id, signal_id, submitted_at, ticker, side, limit_price, qty, "
        " fee_usd, settled_at, pnl_usd) "
        "VALUES (?, ?, ?, ?, 'BUY_YES', 0.5, 1, 0.01, ?, ?)",
        [
            f"t{idx}",
            f"s{idx}",
            datetime(2026, 8, 1, tzinfo=UTC),
            ticker,
            datetime(2026, 8, 2, tzinfo=UTC),
            pnl,
        ],
    )


@pytest.fixture
def con(tmp_path: Path):
    db = tmp_path / "b.duckdb"
    bootstrap(db)
    c = duckdb.connect(str(db))
    try:
        yield c
    finally:
        c.close()


def test_weather_losses_do_not_drain_the_nfl_bankroll(con) -> None:
    """The exact production scenario that would have silently killed NFL."""
    for i in range(10):
        _seed(con, f"KXHIGHLAX-26AUG0{i}-T80", -120.0, i)  # weather: -$1,200
    _seed(con, "KXNFLGAME-26SEP10-KCPHI", +5.0, 99)  # NFL: +$5

    assert settled_pnl_total(con) == pytest.approx(-1195.0)  # portfolio view
    assert settled_pnl_total(con, vertical="weather") == pytest.approx(-1200.0)
    assert settled_pnl_total(con, vertical="nfl") == pytest.approx(5.0)

    # Sizing consequence — the whole point.
    shared = 1000.0 + settled_pnl_total(con)
    nfl_only = 1000.0 + settled_pnl_total(con, vertical="nfl")
    assert shared < 0
    assert nfl_only > 0
    assert fractional_kelly_stake(prob=0.60, price=0.50, bankroll_usd=shared) == 0.0
    assert fractional_kelly_stake(prob=0.60, price=0.50, bankroll_usd=nfl_only) > 0.0


def test_each_vertical_sees_only_its_own_tickers(con) -> None:
    _seed(con, "KXHIGHLAX-26AUG01-T80", -50.0, 1)
    _seed(con, "KXNBAGAME-26NOV01-LALBOS", -7.0, 2)
    _seed(con, "KXNFLGAME-26SEP10-KCPHI", 11.0, 3)
    _seed(con, "KXINX-26AUG01-B5000", 3.0, 4)
    _seed(con, "KXNASDAQ100-26AUG01-B20000", 2.0, 5)

    assert settled_pnl_total(con, vertical="weather") == pytest.approx(-50.0)
    assert settled_pnl_total(con, vertical="nba") == pytest.approx(-7.0)
    assert settled_pnl_total(con, vertical="nfl") == pytest.approx(11.0)
    # The index vertical spans two prefixes.
    assert settled_pnl_total(con, vertical="index") == pytest.approx(5.0)
    # And the unscoped total still reports the whole portfolio.
    assert settled_pnl_total(con) == pytest.approx(-41.0)


def test_unsettled_trades_are_excluded(con) -> None:
    _seed(con, "KXNFLGAME-26SEP10-KCPHI", 11.0, 1)
    con.execute(
        "INSERT INTO signal (signal_id, as_of, ticker, model_prob_yes, model_name) "
        "VALUES ('sopen', ?, 'KXNFLGAME-26SEP17-NYGDAL', 0.6, 'test')",
        [datetime(2026, 8, 1, tzinfo=UTC)],
    )
    con.execute(
        "INSERT INTO paper_trade "
        "(trade_id, signal_id, submitted_at, ticker, side, limit_price, qty, fee_usd) "
        "VALUES ('open', 'sopen', ?, 'KXNFLGAME-26SEP17-NYGDAL', 'BUY_YES', 0.5, 1, 0.01)",
        [datetime(2026, 8, 1, tzinfo=UTC)],
    )
    assert settled_pnl_total(con, vertical="nfl") == pytest.approx(11.0)


def test_unknown_vertical_is_refused_not_silently_zero(con) -> None:
    """A typo must fail loudly; silently returning 0.0 would fabricate a bankroll."""
    with pytest.raises(ValueError, match="unknown vertical"):
        settled_pnl_total(con, vertical="hockey")


def test_every_paper_lane_has_a_vertical() -> None:
    """Guard against adding a lane and forgetting to scope its bankroll."""
    assert set(VERTICAL_TICKER_PREFIXES) >= {"weather", "nba", "nfl", "index"}
    for prefixes in VERTICAL_TICKER_PREFIXES.values():
        assert prefixes and all(p.startswith("KX") for p in prefixes)
