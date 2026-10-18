"""Frozen prospective portfolio variants share one validated capture."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from kq.equities.ledger import update_ledger
from kq.equities.portfolios import portfolio_research, portfolio_specs
from kq.equities.research import daily_bars


def _series(symbol: str, prices: list[float], *, volume: int = 1_000_000) -> dict[str, object]:
    days = pd.bdate_range("2026-07-03", periods=len(prices))
    return {
        "symbol": symbol,
        "interval": "day",
        "bounds": "regular",
        "bars": [
            {
                "begins_at": day.strftime("%Y-%m-%dT00:00:00Z"),
                "open_price": str(price),
                "close_price": str(price),
                "high_price": str(price),
                "low_price": str(price),
                "volume": volume,
                "session": "reg",
            }
            for day, price in zip(days, prices, strict=True)
        ],
    }


def _earn(symbol: str, actual: str | None = "1.20") -> dict[str, object]:
    return {
        "symbol": symbol,
        "year": 2026,
        "quarter": 3,
        "eps": {"estimate": "1.00", "actual": actual},
        "report": {"date": "2026-09-23", "verified": True},
    }


def _snapshot() -> dict[str, object]:
    prices = [100.0] * 41 + [120.0] * 10 + [110.0] * 10
    return {
        "captured_at": "2026-09-28T05:00:00Z",
        "benchmark": "SPY",
        "adjustment_type": "split",
        "universe": ["AAA", "BBB", "CCC", "DDD"],
        "bars": [
            _series("SPY", [100.0] * 61),
            _series("AAA", [100.0 + i for i in range(61)]),
            _series("BBB", prices),
            _series("CCC", [100.0 + i / 2 for i in range(61)]),
            _series("DDD", [100.0 + i for i in range(61)], volume=100),
        ],
        "earnings": [_earn("AAA"), _earn("BBB", None), _earn("CCC"), _earn("DDD")],
    }


def _spec(family: str, hold: int, lookback: int):
    return next(
        spec
        for spec in portfolio_specs()
        if (spec.family, spec.holding_sessions, spec.lookback) == (family, hold, lookback)
    )


def test_nine_frozen_specs_and_method_ids() -> None:
    specs = portfolio_specs()
    assert len(specs) == 9
    assert len({s.portfolio_id for s in specs}) == 9
    assert len({s.protocol_id for s in specs}) == 9
    assert {(s.family, s.holding_sessions, s.lookback) for s in specs} == {
        (family, hold, lookback)
        for family, hold in (("momentum", 5), ("momentum", 20), ("earnings", 20))
        for lookback in (10, 20, 60)
    }
    with pytest.raises(FrozenInstanceError):
        specs[0].lookback = 99


def test_matching_momentum_holds_select_same_names_and_reversal() -> None:
    snapshot = _snapshot()
    for lookback in (10, 20, 60):
        short = portfolio_research(snapshot, _spec("momentum", 5, lookback))
        long = portfolio_research(snapshot, _spec("momentum", 20, lookback))
        assert (
            short.loc[short.selected, "symbol"].tolist()
            == long.loc[long.selected, "symbol"].tolist()
        )
    ten = portfolio_research(snapshot, _spec("momentum", 5, 10)).set_index("symbol")
    twenty = portfolio_research(snapshot, _spec("momentum", 5, 20)).set_index("symbol")
    assert ten.at["BBB", "excess_momentum"] < 0
    assert twenty.at["BBB", "excess_momentum"] > 0
    assert ten.at["BBB", "status"] == "excluded"
    assert twenty.at["BBB", "status"] == "ranked"
    assert twenty.at["BBB", "selected"] == True  # noqa: E712


def test_earnings_gate_and_liquidity_survive_recomputed_momentum() -> None:
    snapshot = _snapshot()
    momentum = portfolio_research(snapshot, _spec("momentum", 20, 20)).set_index("symbol")
    earnings = portfolio_research(snapshot, _spec("earnings", 20, 20)).set_index("symbol")
    assert momentum.at["BBB", "selected"] == True  # noqa: E712
    assert earnings.at["BBB", "selected"] == False  # noqa: E712
    assert earnings.at["BBB", "reason"] == "unreported_eps"
    assert momentum.at["DDD", "reason"] == "illiquid"
    assert earnings.at["DDD", "reason"] == "illiquid"


def test_sixty_session_history_requires_all_aligned_real_positive_volume_bars() -> None:
    snapshot = _snapshot()
    bars = snapshot["bars"]
    assert isinstance(bars, list)
    bars[2]["bars"] = bars[2]["bars"][-40:]
    bars[3]["bars"][5]["synthetic"] = True
    frame = portfolio_research(snapshot, _spec("momentum", 5, 60)).set_index("symbol")
    assert frame.at["BBB", "reason"] == "missing_history"
    assert frame.at["CCC", "reason"] == "missing_history"
    assert frame.at["AAA", "status"] == "ranked"


def test_output_has_ledger_schema_and_never_uses_future_bar() -> None:
    snapshot = _snapshot()
    bars = snapshot["bars"]
    assert isinstance(bars, list)
    bars[1]["bars"].append(
        {
            **bars[1]["bars"][-1],
            "begins_at": "2026-09-28T00:00:00Z",
            "close_price": "9999",
            "high_price": "9999",
        }
    )
    frame = portfolio_research(snapshot, _spec("momentum", 5, 10))
    assert {
        "symbol",
        "horizon_sessions",
        "as_of",
        "session_date",
        "excess_momentum",
        "status",
        "selected",
        "reason",
        "reasons",
        "rank",
    }.issubset(frame.columns)
    assert str(frame.as_of.dt.tz) == "UTC"
    assert all(isinstance(value, date) for value in frame.session_date)
    assert frame.session_date.max() < date(2026, 9, 28)
    assert frame.set_index("symbol").at["AAA", "close"] != 9999


def test_empty_event_selection_keeps_typed_schema() -> None:
    snapshot = _snapshot()
    snapshot["earnings"] = []
    frame = portfolio_research(snapshot, _spec("earnings", 20, 20))
    assert frame.empty
    assert str(frame.as_of.dt.tz) == "UTC"
    assert "excess_momentum" in frame.columns


def test_missing_history_still_exposes_price_liquidity_and_eps_guards() -> None:
    snapshot = _snapshot()
    bars = snapshot["bars"]
    assert isinstance(bars, list)
    bars[2]["bars"] = bars[2]["bars"][-20:]
    bars[2]["bars"][-1]["close_price"] = "4"
    bars[2]["bars"][-1]["open_price"] = "4"
    bars[2]["bars"][-1]["high_price"] = "4"
    bars[2]["bars"][-1]["low_price"] = "4"
    bars[2]["bars"] = [dict(bar, volume=100) for bar in bars[2]["bars"]]
    frame = portfolio_research(snapshot, _spec("earnings", 20, 60)).set_index("symbol")
    assert frame.at["BBB", "reasons"] == ("missing_history;low_price;illiquid;unreported_eps")


def test_missing_symbol_bar_is_excluded_with_valid_ledger_date() -> None:
    snapshot = _snapshot()
    bars = snapshot["bars"]
    assert isinstance(bars, list)
    bars.pop(1)
    frame = portfolio_research(snapshot, _spec("momentum", 5, 10)).set_index("symbol")
    assert frame.at["AAA", "reason"] == "missing_history"
    assert isinstance(frame.at["AAA", "session_date"], date)


def test_ten_day_gain_does_not_hide_twenty_day_reversal() -> None:
    snapshot = _snapshot()
    snapshot["universe"].append("EEE")
    snapshot["bars"].append(_series("EEE", [100.0] * 40 + [120.0] + [100.0] * 10 + [110.0] * 10))
    snapshot["earnings"].append(_earn("EEE"))
    ten = portfolio_research(snapshot, _spec("momentum", 5, 10)).set_index("symbol")
    twenty = portfolio_research(snapshot, _spec("momentum", 5, 20)).set_index("symbol")
    assert ten.at["EEE", "excess_momentum"] > 0
    assert twenty.at["EEE", "excess_momentum"] < 0
    assert twenty.at["EEE", "reason"] == "nonpositive_excess"


def test_zero_volume_session_excludes_even_with_sixty_dates() -> None:
    snapshot = _snapshot()
    snapshot["bars"][1]["bars"][2]["volume"] = 0
    frame = portfolio_research(snapshot, _spec("momentum", 5, 60)).set_index("symbol")
    assert frame.at["AAA", "reason"] == "missing_history"


def test_excluded_missing_history_and_price_rows_feed_ledger(tmp_path: Path) -> None:
    snapshot = _snapshot()
    snapshot["bars"].pop(1)
    snapshot["bars"][1]["bars"] = snapshot["bars"][1]["bars"][-40:]
    spec = _spec("momentum", 5, 60)
    frame = portfolio_research(snapshot, spec)
    assert frame.set_index("symbol").at["AAA", "reason"] == "missing_history"
    assert frame.set_index("symbol").at["BBB", "reason"] == "missing_history"
    result = update_ledger(
        tmp_path / "paper.sqlite",
        frame,
        daily_bars(snapshot),
        snapshot_hash="fixture",
        as_of=datetime(2026, 9, 28, 5, tzinfo=UTC),
        holding_sessions=spec.holding_sessions,
        protocol_id=spec.protocol_id,
    )
    assert result["pending_count"] >= 0
