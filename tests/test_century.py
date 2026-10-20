"""Artificial fixtures for dimension migration and the century cash-warmup boundary."""

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from kq.equities import century, long_history

POLICIES = json.loads(Path("docs/research/long-history-registration-2026-10-20.json").read_bytes())[
    "policies"
]
STATIC = [p for p in POLICIES if not p["family"].startswith("CPPI")]


def data(count=30, periods=120):
    rng = np.random.default_rng(1234)
    return century.MonthlyData(
        tuple(map(str, pd.period_range("1926-07", periods=periods, freq="M"))),
        (*[f"S{i:02}" for i in range(count)], "MKT"),
        rng.normal(0.005, 0.03, (periods, count + 1)),
        np.full(periods, 0.001),
    )


@pytest.mark.parametrize("policy", STATIC, ids=lambda p: p["id"])
def test_dimension_adaptation_preserves_frozen_49_asset_formula(policy):
    panel = data(49)
    np.testing.assert_array_equal(
        century.static_target(policy, panel, 80),
        long_history.static_target(policy, panel, 80),
    )


@pytest.mark.parametrize("policy", STATIC, ids=lambda p: p["id"])
def test_30_asset_targets_are_causal_and_funded(policy):
    panel = data()
    expected = century.static_target(policy, panel, 80)
    returns, rf = panel.returns.copy(), panel.rf.copy()
    returns[81:], rf[81:] = 0.9, 0.25
    poisoned = replace(panel, returns=returns, rf=rf)
    np.testing.assert_array_equal(expected, century.static_target(policy, poisoned, 80))
    assert expected.shape == (31,)
    assert expected.min() >= 0 and expected.sum() <= 1 + 1e-12


@pytest.mark.parametrize("policy", [POLICIES[0], POLICIES[-1]], ids=lambda p: p["id"])
def test_cash_warmup_retains_funded_wealth_and_delayed_history(policy):
    panel = data()
    targets = np.zeros_like(panel.returns)
    targets[78:, -1] = 1
    frame, summary = century.simulate_monthly(panel, policy, "1926-07", "1933-12", 25, 2, targets)
    assert frame.warmup.iloc[:78].all()
    assert not frame.warmup.iloc[78:].any()
    assert frame.fee.iloc[:78].sum() == 0
    assert frame.risky_fraction.iloc[:78].sum() == 0
    assert frame.iloc[78].before_nav == pytest.approx(1000 * 1.001**78)
    assert frame.iloc[78].reference_nav == pytest.approx(1000 * 1.001**77)
    assert frame.iloc[78].reference_peak == pytest.approx(1000 * 1.001**77)
    assert summary["warmup_months"] == 78
    assert pd.isna(frame.iloc[0].as_of)
    assert pd.isna(frame.iloc[1].as_of)
    assert frame.iloc[2].as_of == "1926-07-31"


def test_market_control_really_invests_during_1929_crash():
    panel = data()
    returns = np.zeros_like(panel.returns)
    returns[39, -1] = -0.8
    panel = replace(panel, returns=returns, rf=np.zeros(len(panel.months)))
    frame, result = century.simulate_monthly(
        panel, {"id": "CMKT", "family": "control"}, "1926-07", "1933-12", 25, 2
    )
    assert result["warmup_months"] == 0
    assert frame.iloc[39].risky_pnl < -780
    assert result["max_drawdown"] < -0.78
    assert frame.iloc[1:-1].turnover.sum() == 0


def test_century_partial_calendar_years_are_not_full_year_claims():
    panel = data(periods=1200)
    panel = replace(panel, rf=np.full(1200, 0.01))
    _, result = century.simulate_monthly(
        panel, {"id": "CRF", "family": "control"}, "1926-07", "2026-06", 25, 2
    )
    assert result["months"] == 1200
    assert len(result["annual"]) == 99
    assert result["all_years_ge_10pct"]
    assert result["years_ge_10pct"] == 99
    assert set(result["partial_calendar_returns"]) == {"1926", "2026"}
    assert result["partial_calendar_returns"]["1926"] == pytest.approx(1.01**6 - 1)
    assert result["cagr"] == pytest.approx(1.01**12 - 1)


def test_new_account_does_not_inherit_century_cash():
    panel = data()
    frame, result = century.simulate_monthly(panel, POLICIES[-1], "1933-01", "1933-12", 25, 2)
    assert frame.iloc[0].before_nav == 1000
    assert frame.iloc[0].reference_peak == 1000
    assert result["warmup_months"] == 0


def test_all_account_marks_match_old_engine_after_warmup():
    panel = data(49)
    old, old_summary = long_history.simulate_monthly(
        panel, POLICIES[-1], "1933-01", "1935-12", 50, 2
    )
    new, new_summary = century.simulate_monthly(panel, POLICIES[-1], "1933-01", "1935-12", 50, 2)
    pd.testing.assert_frame_equal(old, new.drop(columns="warmup"))
    assert old_summary == {
        k: v
        for k, v in new_summary.items()
        if k not in {"warmup_months", "partial_calendar_returns"}
    }
