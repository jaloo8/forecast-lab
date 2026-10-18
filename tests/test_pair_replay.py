import numpy as np
import pandas as pd
import pytest

from kq.equities.pair_replay import replay_pair


def prices(values, dates=None):
    if dates is None:
        dates = pd.bdate_range("2020-01-01", periods=len(values))
    return pd.DataFrame(values, index=dates, columns=["KO", "PEP"], dtype=float)


def test_long_short_profit_and_both_leg_costs():
    frame = prices([[100, 100], [110, 90]])
    daily, trades = replay_pair(frame, frame, {0: 1, 1: 0}, 10, 0)
    # $250 long, $250 short; gain $25+$25; fees $.50+$.50.
    assert daily.nav.iloc[-1] == pytest.approx(1049)
    assert trades.net_pnl.sum() == pytest.approx(49)
    assert daily.cost.sum() == pytest.approx(1)
    assert daily.gross.iloc[-1] == 0


def test_short_loss_is_not_clipped_to_premium_or_short_proceeds():
    frame = prices([[100, 100], [100, 300]])
    daily, trades = replay_pair(frame, frame, {0: 1}, 0, 0)
    assert daily.nav.iloc[-1] == pytest.approx(500)
    assert trades.net_pnl.iloc[0] == pytest.approx(-500)


def test_borrow_uses_calendar_days_including_weekend():
    dates = pd.to_datetime(["2020-01-03", "2020-01-06"])
    frame = prices([[100, 100], [100, 100]], dates)
    daily, _ = replay_pair(frame, frame, {0: 1, 1: 0}, 0, 0.365)
    assert daily.borrow.sum() == pytest.approx(250 * 0.365 * 3 / 365)
    assert daily.nav.iloc[-1] == pytest.approx(999.25)


def test_execution_uses_next_open_not_signal_close():
    close = prices([[100, 100], [100, 100], [200, 100]])
    opened = close.copy()
    opened.iloc[1] = [200, 100]
    daily, _ = replay_pair(opened, close, {1: 1}, 0, 0)
    assert daily.nav.iloc[-1] == pytest.approx(1000)
    assert daily.nav.iloc[0] == 1000


def test_signals_are_lagged_and_freeze_the_training_mean():
    ratio = np.array([0, 0.01, -0.01, 0.01, -0.01, 0.2, 0.2, -0.1])
    frame = prices(np.column_stack([100 * np.exp(ratio), np.full(8, 100)]))
    daily, _ = replay_pair(frame, frame, None, 10, 0.03, start=5, lookback=5)
    orders = daily.attrs["orders"]
    assert 5 not in orders
    assert orders[6] == -1


def test_future_changes_cannot_rewrite_prior_signals_or_account_marks():
    rng = np.random.default_rng(15)
    frame = prices(100 * np.exp(np.cumsum(rng.normal(0, 0.03, (450, 2)), axis=0)))
    changed = frame.copy()
    changed.iloc[350:] *= np.array([5, 0.2])
    a, _ = replay_pair(frame, frame, None, 10, 0.03)
    b, _ = replay_pair(changed, changed, None, 10, 0.03)
    first, second = a.attrs.pop("orders"), b.attrs.pop("orders")
    assert {k: v for k, v in first.items() if k < 350} == {
        k: v for k, v in second.items() if k < 350
    }
    pd.testing.assert_frame_equal(a.iloc[:350], b.iloc[:350])


def test_missing_or_misaligned_data_fails_closed():
    frame = prices([[100, 100], [101, 99], [102, 98]])
    with pytest.raises(ValueError, match="align"):
        replay_pair(frame.iloc[:-1], frame, {}, 10, 0.03)
    frame.iloc[1, 0] = np.nan
    with pytest.raises(ValueError, match="price"):
        replay_pair(frame, frame, {0: 1}, 10, 0.03)


def test_exposure_exit_executes_next_open_without_guaranteeing_stop_price():
    frame = prices([[100, 100], [100, 300], [100, 400], [100, 90]])
    daily, trades = replay_pair(frame, frame, {0: 1}, 0, 0)
    assert trades.reason.iloc[0] == "risk"
    assert trades.exit_date.iloc[0] == frame.index[2]
    assert daily.nav.iloc[-1] == pytest.approx(250)


def test_infinite_short_loss_cannot_continue_with_fictitious_positive_bankroll():
    frame = prices([[100, 100], [100, 1000]])
    with pytest.raises(ValueError, match="Insolvent"):
        replay_pair(frame, frame, {0: 1}, 0, 0)


def test_maximum_holding_period_is_lagged_and_closed_trades_reconcile():
    ratio = np.array([0, 0.01, -0.01, 0.01, -0.01, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2])
    frame = prices(np.column_stack([100 * np.exp(ratio), np.full(len(ratio), 100)]))
    daily, trades = replay_pair(frame, frame, None, 25, 0.03, start=5, lookback=5, max_hold=2)
    orders = daily.attrs["orders"]
    assert orders[6] == -1
    assert orders[8] == 0
    assert daily.nav.iloc[-1] == pytest.approx(1000 + trades.net_pnl.sum())
    assert daily.cost.sum() == pytest.approx(trades.cost.sum())
    assert daily.borrow.sum() == pytest.approx(trades.borrow.sum())


def test_forced_exit_resets_strategy_state_for_subsequent_entries():
    ratio = np.array([0, 0.01, -0.01, 0.01, -0.01, 0.2, 0.2, 1.1, 1.1, 2, 2, 2])
    frame = prices(np.column_stack([100 * np.exp(ratio), np.full(len(ratio), 100)]))
    _, trades = replay_pair(frame, frame, None, 10, 0.03, start=5, lookback=5)
    assert trades.reason.iloc[0] == "risk"
    assert frame.index[10] in set(trades.entry_date)
