"""Artificial accounting and chronology fixtures, never investment evidence."""

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scripts import run_long_history as runner

from kq.equities.long_history import (
    MonthlyData,
    causal_regimes,
    insurance_target,
    max_mean_bootstrap,
    read_first_monthly,
    rebalance_values,
    simulate_monthly,
    static_target,
)

REGISTERED = json.loads(
    Path("docs/research/long-history-registration-2026-10-20.json").read_bytes()
)["policies"]
STATIC = [p for p in REGISTERED if not p["family"].startswith("CPPI")]


@pytest.fixture
def panel() -> MonthlyData:
    rng = np.random.default_rng(109)
    return MonthlyData(
        tuple(map(str, pd.period_range("1969-07", periods=120, freq="M"))),
        (*[f"S{x:02}" for x in range(49)], "MKT"),
        rng.normal(0.005, 0.04, (120, 50)),
        np.full(120, 0.001),
    )


@pytest.mark.parametrize("policy", STATIC, ids=lambda p: p["id"])
def test_every_static_rule_is_prefix_invariant(panel, policy):
    weights = static_target(policy, panel, 80)
    poisoned = panel.returns.copy()
    poisoned[81:] = 0.75
    future_rf = panel.rf.copy()
    future_rf[81:] = 0.30
    altered = replace(panel, returns=poisoned, rf=future_rf)
    np.testing.assert_array_equal(weights, static_target(policy, altered, 80))
    assert np.isfinite(weights).all() and weights.min() >= 0
    assert weights.sum() <= 1 + 1e-12


def test_momentum_and_reversal_choose_opposite_known_assets(panel):
    returns = np.zeros((120, 50))
    returns[:, :49] = np.arange(49) / 10000
    data = replace(panel, returns=returns)
    momentum = static_target({"family": "MOM", "lookback": 6, "top_k": 5}, data, 80)
    reversal = static_target({"family": "SHORTREV", "lookback": 1, "top_k": 5}, data, 80)
    assert set(np.flatnonzero(momentum)) == set(range(44, 49))
    assert set(np.flatnonzero(reversal)) == set(range(5))


def test_equal_rank_ties_follow_symbol_name(panel):
    data = replace(panel, returns=np.zeros((120, 50)))
    weights = static_target({"family": "MOM", "lookback": 6, "top_k": 5}, data, 80)
    np.testing.assert_array_equal(np.flatnonzero(weights), np.arange(5))


def test_absolute_momentum_defends_against_rf_not_zero(panel):
    data = replace(panel, returns=np.full((120, 50), 0.0005))
    weights = static_target({"family": "ABSMOM", "lookback": 12}, data, 80)
    assert weights.sum() == 0


def test_fee_solver_is_funded_for_rotation():
    old = np.array([700.0, 0.0])
    weights = np.array([0.0, 0.98])
    values, cash, turnover, fee = rebalance_values(old, 300, weights, 0.005)
    expected_nav = (1000 - 0.005 * 700) / (1 + 0.005 * 0.98)
    np.testing.assert_allclose(values, [0, 0.98 * expected_nav], rtol=1e-12)
    assert fee == pytest.approx(0.005 * turnover)
    assert cash + values.sum() + fee == pytest.approx(1000)
    assert cash >= 0


@pytest.mark.parametrize("weights", [[-0.1, 0.9], [0.8, 0.8], [float("nan"), 0]])
def test_invalid_targets_rejected(weights):
    with pytest.raises(ValueError):
        rebalance_values(np.zeros(2), 1000, np.array(weights), 0.0025)


def test_market_control_closed_form_and_final_peak_drawdown(panel):
    data = replace(panel, returns=np.full((120, 50), 0.10), rf=np.zeros(120))
    frame, summary = simulate_monthly(
        data, {"id": "CMKT", "family": "control"}, "1976-01", "1976-12", 50, 2
    )
    after_entry = 1000 / (1 + 0.005 * 0.98)
    stock_end = after_entry * 0.98 * 1.1**12
    expected = stock_end * 0.995 + after_entry * 0.02
    assert summary["ending_nav"] == pytest.approx(expected)
    terminal_dd = -frame.iloc[-1].terminal_fee / frame.iloc[-1].ending_before_terminal
    assert summary["max_drawdown"] == pytest.approx(terminal_dd)
    assert frame.attrs["risky_after_cost"].shape == (12, 50)
    assert summary["trade_legs"] == 2


def test_cash_control_and_rf_are_distinct(panel):
    _, zero = simulate_monthly(
        panel, {"id": "CZERO", "family": "control"}, "1976-01", "1976-12", 25, 2
    )
    _, rf = simulate_monthly(panel, {"id": "CRF", "family": "control"}, "1976-01", "1976-12", 25, 2)
    assert zero["ending_nav"] == 1000 and zero["fees"] == 0
    assert rf["ending_nav"] == pytest.approx(1000 * 1.001**12)


def test_insurance_exposure_uses_delayed_account_state(panel):
    data = replace(panel, returns=np.zeros((120, 50)), rf=np.zeros(120))
    shocked = data.returns.copy()
    shocked[78, -1] = -0.5
    data = replace(data, returns=shocked)
    policy = {"id": "CPPIFIXED_01", "family": "CPPIFIXED", "multiplier": 3, "floor_fraction": 0.8}
    frame, _ = simulate_monthly(data, policy, "1976-01", "1976-12", 25, 2)
    assert frame.iloc[0].reference_nav == 1000
    assert frame.iloc[1].reference_nav == 1000
    assert frame.iloc[2].reference_nav == pytest.approx(frame.iloc[0].ending_nav)
    assert frame.iloc[2].risky_fraction == 0
    np.testing.assert_allclose(frame.risky_fraction.iloc[:2], [0.588, 0.588])
    assert frame.iloc[0].as_of == "1975-11-30"


def test_insurance_floor_rule_is_not_a_guarantee():
    rule = {"family": "CPPIFIXED", "multiplier": 3, "floor_fraction": 0.8}
    assert insurance_target(rule, 700, 1000).sum() == 0
    assert insurance_target(rule, 2000, 2000).sum() == 1
    rule["family"] = "CPPIRATCHET"
    assert insurance_target(rule, 1000, 1400).sum() == 0


def test_regime_labels_are_prefix_invariant(panel):
    a = causal_regimes(panel, 2)
    future = panel.returns.copy()
    future[90:] = 0.9
    b = causal_regimes(replace(panel, returns=future), 2)
    for i in range(13, 92):
        assert a[panel.months[i]] == b[panel.months[i]]


def test_bootstrap_preserves_shared_column_dependence_and_adjustment():
    rng = np.random.default_rng(52)
    series = rng.normal(0.001, 0.02, 48)
    data = np.column_stack((series, series, series - 0.1))
    result = max_mean_bootstrap(data, repeats=99)
    assert result == max_mean_bootstrap(data, repeats=99)
    assert result["familywise_p"][0] == result["familywise_p"][1]
    assert result["familywise_p"][2] == 1
    assert all(a >= b for a, b in zip(result["familywise_p"], result["unadjusted_p"], strict=True))


def test_month_parser_rejects_duplicate_date(tmp_path):
    path = tmp_path / "example.csv"
    path.write_text("header\n,A,B\n197601,1,2\n197601,3,4\n\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        read_first_monthly(path)


def test_parser_ignores_later_annual_and_other_sections(tmp_path):
    path = tmp_path / "example.csv"
    path.write_text(
        "header\n,A,B\n197601,1,2\n197602,3,4\n\nAnnual\n1976,99,99\n", encoding="utf-8"
    )
    result = read_first_monthly(path)
    assert result.shape == (2, 2)
    assert result.iloc[-1, -1] == 4


def test_failure_receipt_keeps_setup_error_and_partial_outputs(tmp_path, monkeypatch):
    output = tmp_path / "run"

    def fail(_source, dest, _review):
        dest.mkdir()
        (dest / "started.json").write_text("{}")
        raise ValueError("bad input")

    monkeypatch.setattr(runner, "_run", fail)
    with pytest.raises(ValueError):
        runner.run(tmp_path, output, tmp_path / "review.json")
    assert json.loads((output / "run-error.json").read_bytes())["message"] == "bad input"
    assert (output / "started.json").exists()


def test_refused_existing_run_does_not_mutate_it(tmp_path, monkeypatch):
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "frozen"
    marker.write_bytes(b"unchanged")

    def fail(*_args):
        raise FileExistsError("refuse overwrite")

    monkeypatch.setattr(runner, "_run", fail)
    with pytest.raises(FileExistsError):
        runner.run(tmp_path, output, tmp_path / "review.json")
    assert list(output.iterdir()) == [marker] and marker.read_bytes() == b"unchanged"
