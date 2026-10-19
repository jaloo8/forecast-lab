import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from scripts.run_inverse_vol_study import paired, summarize

from kq.equities.sector_study import SECTORS, SYMBOLS, _target, simulate_portfolio


def history():
    returns = np.tile([-0.01, 0.02], 6)[:, None] * np.arange(1, 11)
    return pd.DataFrame(
        100 * np.vstack([np.ones(10), np.cumprod(1 + returns, axis=0)]), columns=SYMBOLS
    )


@pytest.mark.parametrize("base", ["equal_sectors", "sector_momentum", "sector_momentum_trend"])
def test_normalized_inverse_sample_volatility_keeps_selection(base):
    frame = history()
    selected = _target(frame, base) > 0
    assert selected.any()
    vol = frame.pct_change(fill_method=None).iloc[1:].std(ddof=1).to_numpy()
    expected = np.zeros(10)
    expected[selected] = (1 / vol[selected]) / (1 / vol[selected]).sum()
    actual = _target(frame, base + "_invvol")
    np.testing.assert_allclose(actual, expected, rtol=1e-13)
    assert actual.sum() == pytest.approx(1)
    assert (actual >= 0).all() and actual[0] == 0


def test_exact_window_and_inclusion_of_latest_completed_return():
    frame = history()
    original = _target(frame, "equal_sectors_invvol")
    older = pd.concat([frame.iloc[[0]] * 99, frame], ignore_index=True)
    np.testing.assert_array_equal(original, _target(older, "equal_sectors_invvol"))
    frame.loc[12, "XLB"] *= 2
    assert _target(frame, "equal_sectors_invvol")[1] < original[1]


@pytest.mark.parametrize("defect", ["short", "zero_vol", "missing", "infinite", "zero_close"])
def test_invalid_volatility_fails_closed(defect):
    frame = history()
    if defect == "short":
        frame = frame.iloc[1:]
    elif defect == "zero_vol":
        frame["XLB"] = 100
    else:
        frame.loc[5, "XLB"] = {"missing": np.nan, "infinite": np.inf, "zero_close": 0}[defect]
    with pytest.raises(ValueError, match=r"warmup|volatility"):
        _target(frame, "equal_sectors_invvol")


def test_trend_equality_stays_cash():
    frame = history()
    frame["SPY"] = 100
    np.testing.assert_array_equal(_target(frame, "sector_momentum_trend_invvol"), np.zeros(10))


def test_next_session_execution_no_future_leakage_and_cost_accounting():
    dates = pd.bdate_range("2004-12-01", "2006-03-31")
    frame = pd.MultiIndex.from_product([dates, SYMBOLS], names=["session_date", "symbol"]).to_frame(
        index=False
    )
    month = (frame.session_date.dt.year - 2004) * 12 + frame.session_date.dt.month
    scale = frame.symbol.map({s: i + 1 for i, s in enumerate(SYMBOLS)})
    frame = frame.assign(open=100 + month * scale + (month % 2) * scale, close=lambda x: x.open)
    for base in ["equal_sectors", "sector_momentum", "sector_momentum_trend"]:
        daily, ledger = simulate_portfolio(frame, base + "_invvol", 25, end="2006-03-31")
        first = ledger.iloc[0]
        assert first.decision_date == pd.Timestamp("2005-12-30")
        assert first.execution_date == pd.Timestamp("2006-01-02")
        assert first.as_of == pd.Timestamp("2005-12-30 21:00Z")
        original = simulate_portfolio(frame, base, 25, end="2006-03-31")[1]
        columns = [f"weight_{s}" for s in SECTORS]
        np.testing.assert_array_equal(ledger[columns] > 0, original[columns] > 0)
        np.testing.assert_allclose(ledger.cost, ledger.turnover * 0.0025)
        np.testing.assert_allclose(ledger.post_nav, ledger.pre_nav - ledger.cost)
        changed = frame.copy()
        changed.loc[changed.session_date > "2006-02-15", ["open", "close"]] *= 9
        later, later_ledger = simulate_portfolio(changed, base + "_invvol", 25, end="2006-03-31")
        assert_frame_equal(
            daily[daily.session_date <= "2006-02-15"], later[later.session_date <= "2006-02-15"]
        )
        assert_frame_equal(
            ledger[ledger.execution_date <= "2006-02-15"],
            later_ledger[later_ledger.execution_date <= "2006-02-15"],
        )


def test_report_risk_and_turnover_include_initial_capital():
    daily = pd.DataFrame(
        {
            "session_date": pd.to_datetime(["2006-01-03", "2006-01-04", "2006-01-05"]),
            "nav": [11000, 9900, 11880],
        }
    )
    ledger = pd.DataFrame({"cost": [25, 50], "turnover": [10000, 20000], "pre_nav": [10000, 20000]})
    result = summarize(daily, ledger)
    assert result["sharpe_zero_rf"] == pytest.approx(
        np.mean([0.1, -0.1, 0.2]) / np.std([0.1, -0.1, 0.2], ddof=1) * np.sqrt(252)
    )
    assert result["total_fees"] == 75
    assert result["turnover_nav"] == 2
    assert result["annual_turnover_nav"] == 0.1


def test_pairing_matches_cost_period_and_direction():
    rows = pd.DataFrame(
        {
            "strategy": ["equal_sectors", "equal_sectors_invvol"] * 2,
            "cost_bps": [10, 10, 25, 25],
            "year": [2006] * 4,
            "return": [0.1, 0.2, 0.08, 0.15],
        }
    )
    result = paired(rows, ["cost_bps", "year"], "return")
    np.testing.assert_allclose(result.delta, [0.1, 0.07])
