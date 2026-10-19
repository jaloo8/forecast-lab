import numpy as np
import pandas as pd
import pytest
from scripts.plan_options_extension import cost_sample, definition_ranges, provisional_pair, regimes


def test_regimes_do_not_see_current_or_future_close():
    index = pd.date_range("2023-01-01", periods=100, freq="B", tz="UTC")
    close = pd.Series(100 * np.exp(np.arange(100) * 0.001), index=index)
    before = regimes(close)
    close.iloc[75:] *= 2
    after = regimes(close)
    pd.testing.assert_frame_equal(before.iloc[:76], after.iloc[:76])
    assert before.iloc[:60].trend.eq("warmup").all()
    assert before.iloc[60:].trend.eq("above_60d").all()
    assert before.iloc[21:].volatility.eq("low").all()
    assert before.iloc[75].regime_as_of < index[75]


def test_missing_close_is_not_forward_filled():
    index = pd.date_range("2023-01-01", periods=100, freq="B", tz="UTC")
    close = pd.Series(np.arange(100) + 100.0, index=index)
    close.iloc[70] = np.nan
    result = regimes(close)
    assert result.iloc[71:92].volatility.eq("warmup").all()
    with pytest.raises(ValueError):
        regimes(close.iloc[::-1])


def test_cost_sample_is_independent_of_outcome_and_row_order():
    rows = pd.DataFrame(
        {
            "session": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
            "year": [2024] * 4,
            "volatility": ["low"] * 4,
            "trend": ["above_60d"] * 4,
            "net_5bp": [-1, 2, 3, 4],
        }
    )
    expected = cost_sample(rows)
    rows.net_5bp *= -100
    assert cost_sample(rows.iloc[::-1]).session.tolist() == expected.session.tolist()
    assert expected.session.tolist() == ["2024-01-01", "2024-01-04"]


def test_provisional_symbols_are_not_chain_eligibility_and_ties_go_lower():
    assert provisional_pair("2024-07-03", 550.5) == [
        "SPY   240704C00550000",
        "SPY   240704C00551000",
    ]  # Holiday expiry deliberately stays provisional; never changed to July 5.
    with pytest.raises(ValueError):
        provisional_pair("2024-07-03", float("nan"))


def test_definition_ranges_do_not_buy_gap_dates():
    result = definition_ranges(["2024-07-09", "2024-07-05", "2024-07-08", "2024-07-08"])
    assert [(str(a.date()), str(b.date())) for a, b in result] == [
        ("2024-07-05", "2024-07-06"),
        ("2024-07-08", "2024-07-10"),
    ]
    assert definition_ranges([]) == []
