import pandas as pd
import pytest

from kq.equities.opening_range import underlying_diagnostic


def bars():
    index = pd.date_range("2026-10-15 09:30", periods=390, freq="min", tz="America/New_York")
    f = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}, index=index)
    f.iloc[16, f.columns.get_loc("close")] = 102
    f.iloc[16, f.columns.get_loc("high")] = 102
    f.iloc[18, f.columns.get_loc("open")] = 101
    return f


def test_completed_bar_signal_executes_at_strictly_next_minute_boundary():
    f = bars()
    row = underlying_diagnostic(f).iloc[0]
    assert row.signal_at == f.index[17].tz_convert("UTC")
    assert row.entry_at == f.index[18].tz_convert("UTC")
    assert row.exit_at.hour == 19 and row.exit_at.minute == 30
    assert row.entry_price == 101
    assert row.raw_return == pytest.approx(100 / 101 - 1)
    assert row.net_5bp == pytest.approx(100 * (1 - 0.0005) / (101 * (1 + 0.0005)) - 1)


def test_missing_bar_is_unscored_not_silently_skipped_or_filled():
    row = underlying_diagnostic(bars().drop(bars().index[25])).iloc[0]
    assert row.status == "incomplete_session"
    assert "raw_return" not in row or pd.isna(row.raw_return)


def test_stop_executes_after_completed_close_not_at_invented_stop_price():
    f = bars()
    f.iloc[20, f.columns.get_loc("close")] = 98
    f.iloc[20, f.columns.get_loc("low")] = 98
    f.iloc[22, f.columns.get_loc("open")] = 90
    f.iloc[22, f.columns.get_loc("low")] = 90
    row = underlying_diagnostic(f).iloc[0]
    assert row.exit_at == f.index[22].tz_convert("UTC")
    assert row.exit_price == 90
    assert row.exit_reason == "range_failure"


def test_future_prices_cannot_rewrite_entry_and_duplicates_fail():
    f = bars()
    changed = f.copy()
    changed.iloc[100:] *= 2
    a = underlying_diagnostic(f).iloc[0]
    b = underlying_diagnostic(changed).iloc[0]
    assert a.entry_at == b.entry_at and a.entry_price == b.entry_price
    with pytest.raises(ValueError, match="index"):
        underlying_diagnostic(pd.concat([f, f]))


def test_no_breakout_does_not_generate_a_trade_and_bad_prices_are_unscored():
    f = bars()
    f["close"] = 100
    assert underlying_diagnostic(f).iloc[0].status == "no_signal"
    f.iloc[25, f.columns.get_loc("high")] = 90
    assert underlying_diagnostic(f).iloc[0].status == "invalid_prices"


def test_naive_timestamps_are_rejected():
    f = bars()
    f.index = f.index.tz_localize(None)
    with pytest.raises(ValueError, match="index"):
        underlying_diagnostic(f)


def test_date_with_only_out_of_hours_rows_is_retained_as_incomplete():
    f = bars().iloc[:1].copy()
    f.index = f.index - pd.Timedelta(minutes=1)
    result = underlying_diagnostic(f)
    assert len(result) == 1
    assert result.iloc[0].status == "incomplete_session"
