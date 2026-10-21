"""The independent checker is exercised with artificial inputs, not market returns."""

import numpy as np
import pandas as pd
import pytest
from scripts.check_bot_study import (
    RULES,
    Audit,
    deviation,
    ema,
    independent_signals,
    reconstructed_metrics,
    replay,
    state_path,
    verify_annual,
)


def bars(count: int = 360) -> dict[str, np.ndarray]:
    time = np.arange(count)
    close = 100 + time / 10 + 4 * np.sin(time / 3)
    return {
        "close": close,
        "open": close * (1 + 0.01 * np.cos(time / 7)),
        "high": close * 1.025,
        "low": close * 0.975,
        "volume": 1_000 + 300 * np.cos(time / 5),
    }


def test_recursive_ema_seed_is_first_observation() -> None:
    assert ema(np.array([1.0, 3.0, 5.0]), 3).tolist() == [1.0, 2.0, 3.5]


def test_population_and_sample_variances_remain_distinct() -> None:
    assert deviation([1.0, 3.0]) == 1.0
    assert deviation([1.0, 3.0], 1) == pytest.approx(2**0.5)


def test_timed_hold_and_no_same_decision_reentry() -> None:
    decisions = state_path(np.ones(8, dtype=bool), np.zeros(8, dtype=bool), 3, 2)
    assert decisions.tolist() == [False, False, True, True, False, True, True, False]


def test_pre_warmup_entry_does_not_leak_latent_position() -> None:
    entries = np.array([True, False, False, False, False])
    assert not state_path(entries, np.zeros(5, dtype=bool), 3).any()


@pytest.mark.parametrize("rule", RULES)
def test_independent_signal_prefix_has_no_future_dependence(rule: str) -> None:
    original = bars()
    prefix = {key: values[:300].copy() for key, values in original.items()}
    shocked = {key: values.copy() for key, values in original.items()}
    for key, values in shocked.items():
        values[300:] *= 2 if key != "volume" else 4
    expected = independent_signals(prefix)[rule]
    assert np.array_equal(independent_signals(shocked)[rule][:300], expected)


def test_all_signals_share_the_252_observation_warmup() -> None:
    results = independent_signals(bars())
    assert tuple(results) == RULES
    assert all(not values[:251].any() for values in results.values())
    assert results["C00"][251]


def test_cash_account_has_no_fictional_return_or_fees() -> None:
    ledger, skipped = replay([10, 20], [15, 50], [False, False], 50)
    result = reconstructed_metrics(
        pd.to_datetime(["2020-01-02", "2020-01-03"]), ledger, [15, 50], skipped
    )
    assert result["ending_cash"] == 1000
    assert result["return"] == result["fees"] == result["trades"] == result["drawdown"] == 0


def test_self_financed_entry_and_terminal_liquidation() -> None:
    ledger, skipped = replay([100], [200], [True], 10)
    assert ledger[0, 2] == pytest.approx(20)
    assert ledger[0, 3] == pytest.approx(9.8 / 1.001)
    assert ledger[0, 5] == pytest.approx(20 + (9.8 / 1.001) * 200 * 0.999)
    assert ledger[0, 6] == 0
    assert skipped == 0


def test_terminal_new_peak_is_seen_before_liquidation_fee() -> None:
    ledger, skipped = replay([100], [200], [True], 10)
    metrics = reconstructed_metrics(pd.to_datetime(["2020-01-02"]), ledger, [200], skipped)
    assert metrics["drawdown"] == pytest.approx(-ledger[0, 10] / ledger[0, 11])


def test_ordinary_dust_skip_is_recorded_then_terminal_dust_swept() -> None:
    ledger, skipped = replay([100, 0.0001], [100, 0.0001], [True, False], 10)
    assert skipped == 1
    assert ledger[1, 7] == 0
    assert ledger[1, 9] < 0
    assert ledger[1, 6] == 0


def test_corrupt_money_rejected_by_audit() -> None:
    with pytest.raises(ValueError, match="dollars"):
        Audit().equal([1000.01], [1000], "dollars")


def test_partial_january_is_not_complete_calendar_year() -> None:
    dates = pd.to_datetime(["2020-01-10", "2020-12-31"])
    calendar = pd.to_datetime(["2020-01-02", "2020-01-10", "2020-12-31"])
    ledger, _ = replay([100, 100], [100, 100], [False, False], 10)
    records = pd.DataFrame(
        [dict(year=2020, return_=0, ending_nav=1000, complete_calendar_year=True)]
    ).rename(columns={"return_": "return"})
    with pytest.raises(ValueError, match="complete-year"):
        verify_annual(Audit(), records, dates, ledger, calendar)
