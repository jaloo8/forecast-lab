import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from kq.equities.sector_study import SECTORS, SYMBOLS, simulate_portfolio


def bars():
    dates = pd.bdate_range("2004-11-01", "2006-03-31")
    frame = pd.MultiIndex.from_product([dates, SYMBOLS], names=["session_date", "symbol"]).to_frame(
        index=False
    )
    return frame.assign(open=100.0, close=100.0)


def run(frame, strategy="spy_hold", cost=0, end="2006-03-31"):
    return simulate_portfolio(frame, strategy, cost, end=end)


def test_fee_roundtrip_and_terminal_audit():
    daily, ledger = run(bars(), cost=50)
    assert daily.iloc[0].nav == pytest.approx(10000 / 1.005)
    assert daily.iloc[-1].nav == pytest.approx(10000 / 1.005 * 0.995)
    assert list(ledger.reason) == ["initial", "terminal"]
    assert pd.isna(ledger.iloc[-1].as_of)
    assert ledger.iloc[-1].cost == pytest.approx(ledger.iloc[-1].turnover * 0.005)
    assert daily.iloc[-1].cash == daily.iloc[-1].nav


def test_skip_recent_month_ranking_and_alphabetical_ties():
    frame = bars()
    frame.loc[
        (frame.session_date == "2005-11-30") & frame.symbol.isin(["XLF", "XLI", "XLV", "XLY"]),
        "close",
    ] = 200
    frame.loc[(frame.session_date == "2005-12-30") & (frame.symbol == "XLE"), "close"] = 1000
    _, ledger = run(frame, "sector_momentum")
    first = ledger.iloc[0]
    assert [s for s in SECTORS if first[f"weight_{s}"] > 0] == ["XLF", "XLI", "XLV"]
    assert first.decision_date == pd.Timestamp("2005-12-30")
    assert first.as_of == pd.Timestamp("2005-12-30 21:00Z")
    assert first.execution_date == pd.Timestamp("2006-01-02")


def test_strict_trend_gate_equality_is_cash():
    for strategy in ["spy_trend", "sector_momentum_trend"]:
        daily, ledger = run(bars(), strategy, 50)
        assert (daily.nav == 10000).all()
        assert ledger.cost.sum() == 0


def test_next_open_and_overnight_carry_before_exit():
    frame = bars()
    frame.loc[(frame.symbol == "SPY") & (frame.session_date == "2005-12-30"), "close"] = 200
    frame.loc[(frame.symbol == "SPY") & (frame.session_date == "2006-01-02"), ["open", "close"]] = (
        200
    )
    frame.loc[(frame.symbol == "SPY") & (frame.session_date == "2006-02-01"), ["open", "close"]] = (
        300
    )
    daily, ledger = run(frame, "spy_trend")
    assert daily.iloc[0].nav == 10000
    exit_row = ledger.loc[ledger.execution_date == "2006-02-01"].iloc[0]
    assert exit_row.decision_date == pd.Timestamp("2006-01-31")
    assert exit_row.pre_nav == 15000
    assert exit_row.weight_SPY == 0
    assert daily.loc[daily.session_date == "2006-02-01", "nav"].iloc[0] == 15000


def test_future_data_cannot_change_past_or_endpoint():
    original = bars()
    changed = original.copy()
    changed.loc[changed.session_date > "2006-02-15", ["open", "close"]] *= 9
    for strategy in ["sector_momentum", "sector_momentum_trend"]:
        before, old_ledger = run(original, strategy, 25)
        after, new_ledger = run(changed, strategy, 25)
        assert_frame_equal(
            before.loc[before.session_date <= "2006-02-15"],
            after.loc[after.session_date <= "2006-02-15"],
        )
        assert_frame_equal(
            old_ledger.loc[old_ledger.execution_date <= "2006-02-15"],
            new_ledger.loc[new_ledger.execution_date <= "2006-02-15"],
        )
        assert_frame_equal(
            run(original, strategy, end="2006-02-15")[0],
            run(changed, strategy, end="2006-02-15")[0],
        )


def test_rebalance_costs_actual_notional_and_conserves_wealth():
    frame = bars()
    frame.loc[(frame.symbol == "XLB") & (frame.session_date >= "2006-02-01"), ["open", "close"]] = (
        200
    )
    _, ledger = run(frame, "equal_sectors", 25)
    previous_units = {s: 0.0 for s in SYMBOLS}
    for _, row in ledger.iterrows():
        turnover = sum(
            abs(row[f"units_{s}"] - previous_units[s]) * row[f"price_{s}"] for s in SYMBOLS
        )
        assert row.turnover == pytest.approx(turnover)
        assert row.cost == pytest.approx(turnover * 0.0025)
        assert row.post_nav == pytest.approx(row.pre_nav - row.cost)
        previous_units = {s: row[f"units_{s}"] for s in SYMBOLS}
    assert ledger.iloc[1].turnover > 0
    assert ledger.iloc[2].turnover == pytest.approx(0, abs=1e-8)


@pytest.mark.parametrize("defect", ["missing", "duplicate", "zero", "nan", "warmup", "month_gap"])
def test_rejects_invalid_or_incomplete_prices(defect):
    frame = bars()
    if defect == "missing":
        frame = frame.drop(frame.index[100])
    elif defect == "duplicate":
        frame = pd.concat([frame, frame.iloc[[100]]])
    elif defect in ["zero", "nan"]:
        frame.loc[100, "open"] = 0 if defect == "zero" else np.nan
    elif defect == "warmup":
        frame = frame.loc[frame.session_date >= "2005-08-01"]
    else:
        frame = frame.loc[frame.session_date.dt.month != 5]
    with pytest.raises(ValueError):
        run(frame, "sector_momentum")


def test_momentum_denominator_is_twelve_months_before_decision():
    frame = bars()
    frame.loc[(frame.session_date == "2004-12-31") & (frame.symbol == "XLV"), "close"] = 50
    frame.loc[(frame.session_date == "2005-01-31") & (frame.symbol == "XLY"), "close"] = 1
    _, ledger = run(frame, "sector_momentum")
    assert [s for s in SECTORS if ledger.iloc[0][f"weight_{s}"] > 0] == ["XLB", "XLE", "XLV"]


def test_gate_uses_exactly_ten_months_and_decision_timestamp_observes_dst():
    frame = bars()
    frame.loc[(frame.session_date == "2005-03-31") & (frame.symbol == "SPY"), "close"] = 1000
    frame.loc[(frame.session_date == "2005-12-30") & (frame.symbol == "SPY"), "close"] = 101
    assert run(frame, "spy_trend")[1].iloc[0].weight_SPY == 0
    frame.loc[(frame.session_date == "2005-03-31") & (frame.symbol == "SPY"), "close"] = 100
    frame.loc[(frame.session_date == "2005-02-28") & (frame.symbol == "SPY"), "close"] = 1000
    assert run(frame, "spy_trend")[1].iloc[0].weight_SPY == 1
    _, ledger = simulate_portfolio(frame, "equal_sectors", 0, start="2005-11-01", end="2006-03-31")
    assert ledger.iloc[0].as_of == pd.Timestamp("2005-10-31 21:00Z")
    _, ledger = simulate_portfolio(frame, "equal_sectors", 0, start="2005-10-01", end="2006-03-31")
    assert ledger.iloc[0].as_of == pd.Timestamp("2005-09-30 20:00Z")


@pytest.mark.parametrize(
    "strategy,cost",
    [("unknown", 0), ("spy_hold", -1), ("spy_hold", float("inf")), ("spy_hold", 10000)],
)
def test_rejects_unknown_rule_or_invalid_cost(strategy, cost):
    with pytest.raises(ValueError):
        run(bars(), strategy, cost)
