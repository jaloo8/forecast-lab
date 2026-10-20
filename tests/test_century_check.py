"""Artificial independent-checker fixtures; no historical performance is computed."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scripts.check_century import (
    Audit,
    Inputs,
    audit_account,
    bootstrap_reference,
    classification_reference,
    compare_summary,
    cppi_reference,
    funded_rebalance,
    measure,
    read_section,
    regimes_reference,
    selection_reference,
    target_reference,
)

from kq.equities.century import (
    MonthlyData,
    causal_regimes,
    max_mean_bootstrap,
    simulate_monthly,
    static_target,
)

REGISTRATION = json.loads(Path("docs/research/century-registration-2026-10-20.json").read_bytes())
STATIC = [policy for policy in REGISTRATION["policies"] if not policy["family"].startswith("CPPI")]


def synthetic():
    generator = np.random.default_rng(7531)
    months = tuple(str(m) for m in pd.period_range("1926-07", periods=120, freq="M"))
    symbols = (*(f"X{i:02}" for i in range(30)), "MKT")
    returns = generator.normal(0.006, 0.03, (120, 31))
    rf = np.full(120, 0.001)
    independent = Inputs(months, symbols, returns, rf)
    original = MonthlyData(months, symbols, returns, rf)
    return independent, original


@pytest.mark.parametrize("policy", STATIC, ids=[policy["id"] for policy in STATIC])
def test_all_registered_static_configurations_on_artificial_history(policy):
    independent, original = synthetic()
    expected = target_reference(policy, independent, 76)
    np.testing.assert_allclose(static_target(policy, original, 76), expected, atol=1e-12)
    poisoned = independent.returns.copy()
    poisoned[77:] = 100
    altered = Inputs(independent.months, independent.symbols, poisoned, independent.rf)
    np.testing.assert_array_equal(target_reference(policy, altered, 76), expected)
    assert expected.min() >= 0 and expected.sum() <= 1 + 1e-12


def test_rank_ties_are_alphabetical_and_skip_excludes_last_cutoff_month():
    independent, _ = synthetic()
    values = np.zeros_like(independent.returns)
    values[76, 1] = 0.5
    data = Inputs(independent.months, independent.symbols, values, independent.rf)
    policy = {"id": "MOM", "family": "MOM", "lookback": 6, "top_k": 1}
    assert target_reference(policy, data, 76)[1] == 1
    policy["family"] = "SKIPMOM"
    assert target_reference(policy, data, 76)[0] == 1


def test_fixed_and_ratchet_reference_use_funded_wealth_and_clipping():
    policy = {"family": "CPPIFIXED", "floor_fraction": 0.8, "multiplier": 3}
    weights, floor = cppi_reference(policy, 1000, 1200, 30)
    assert floor == 800
    assert weights[-1] == pytest.approx(0.588)
    policy["family"] = "CPPIRATCHET"
    weights, floor = cppi_reference(policy, 1000, 1200, 30)
    assert floor == 960
    assert weights[-1] == pytest.approx(0.1176)
    assert cppi_reference(policy, 900, 1200, 30)[0][-1] == 0


def test_bracket_fee_solver_matches_closed_form_purchase_and_complete_rotation():
    target = np.array([0.98, 0.0])
    positions, cash, fee = funded_rebalance(np.zeros(2), 1000, target, 0.005)
    nav = 1000 / (1 + 0.98 * 0.005)
    np.testing.assert_allclose(positions, [nav * 0.98, 0])
    assert cash == pytest.approx(nav * 0.02)
    assert fee == pytest.approx(1000 - nav)
    positions, cash, fee = funded_rebalance(np.array([980.0, 0.0]), 20, target[::-1], 0.005)
    nav = (1000 - 980 * 0.005) / (1 + 0.98 * 0.005)
    np.testing.assert_allclose(positions, [0, nav * 0.98])
    assert cash + positions.sum() == pytest.approx(nav)
    assert fee == pytest.approx((980 + positions.sum()) * 0.005)


@pytest.mark.parametrize("lag", [1, 2])
@pytest.mark.parametrize(
    "identity",
    ["CZERO", "CRF", "CMKT", "CEQ", "MOM_01", "INVERSEVOL_01", "CPPIFIXED_01", "CPPIRATCHET_01"],
)
def test_full_artificial_account_reconciles_assets_cash_fees_and_summary(identity, lag):
    independent, original = synthetic()
    policy = next(
        (p for p in REGISTRATION["policies"] if p["id"] == identity),
        {"id": identity, "family": "control"},
    )
    targets = None
    if identity not in ("CZERO", "CRF", "CMKT", "CEQ") and not identity.startswith("CPPI"):
        targets = np.zeros_like(independent.returns)
        for pos in range(78, 90):
            targets[pos] = target_reference(policy, independent, pos - lag)
    frame, summary = simulate_monthly(original, policy, "1933-01", "1933-12", 50, lag, targets)
    audit = Audit()
    verified = audit_account(
        frame,
        independent,
        policy,
        "1933-01",
        "1933-12",
        50,
        lag,
        targets,
        audit,
        {"risky_after_cost": frame.attrs["risky_after_cost"]},
    )
    compare_summary(summary, verified["metrics"], audit)
    assert audit.checks["asset_risky_after_cost"] == len(frame) * len(original.symbols)
    assert audit.checks["account_conservation"] == len(frame)


@pytest.mark.parametrize(
    "field",
    [
        "before_nav",
        "after_cost_nav",
        "ending_nav",
        "ending_before_terminal",
        "cash_after_cost",
        "fee",
        "terminal_fee",
        "turnover",
        "risky_pnl",
        "cash_pnl",
        "risky_fraction",
        "reference_nav",
        "reference_peak",
        "trade_legs",
        "sub_dollar_legs",
    ],
)
def test_account_corruption_is_detected(field):
    independent, original = synthetic()
    policy = {
        "id": "CPPIRATCHET_01",
        "family": "CPPIRATCHET",
        "floor_fraction": 0.8,
        "multiplier": 3,
    }
    frame, _ = simulate_monthly(original, policy, "1933-01", "1933-12", 25, 2)
    frame.loc[4, field] += 1
    with pytest.raises(ValueError, match="account_" + field):
        audit_account(frame, independent, policy, "1933-01", "1933-12", 25, 2, None, Audit())


def test_asset_corruption_and_future_timestamp_are_detected():
    independent, original = synthetic()
    policy = {"id": "CEQ", "family": "control"}
    frame, _ = simulate_monthly(original, policy, "1933-01", "1933-12", 25, 2)
    holdings = frame.attrs["risky_after_cost"].copy()
    holdings[3, 5] += 0.1
    with pytest.raises(ValueError, match="asset_risky_after_cost"):
        audit_account(
            frame,
            independent,
            policy,
            "1933-01",
            "1933-12",
            25,
            2,
            None,
            Audit(),
            {"risky_after_cost": holdings},
        )
    frame.loc[3, "as_of"] = "1933-04-30"
    with pytest.raises(ValueError, match="as_of"):
        audit_account(frame, independent, policy, "1933-01", "1933-12", 25, 2, None, Audit())


def test_final_pre_liquidation_peak_counts_in_drawdown():
    independent, original = synthetic()
    returns = np.full_like(independent.returns, 0.05)
    original = MonthlyData(original.months, original.symbols, returns, original.rf)
    frame, summary = simulate_monthly(
        original, {"id": "CMKT", "family": "control"}, "1933-01", "1933-12", 50, 2
    )
    expected = measure(frame)
    last = frame.iloc[-1]
    assert expected["max_drawdown"] == pytest.approx(
        last.ending_nav / last.ending_before_terminal - 1
    )
    assert summary["max_drawdown"] == pytest.approx(expected["max_drawdown"])


def test_rf_and_zero_cash_are_distinct_controls():
    _, original = synthetic()
    zero, _ = simulate_monthly(
        original, {"id": "CZERO", "family": "control"}, "1933-01", "1933-12", 25, 2
    )
    cash, _ = simulate_monthly(
        original, {"id": "CRF", "family": "control"}, "1933-01", "1933-12", 25, 2
    )
    assert zero.ending_nav.iloc[-1] == 1000
    assert cash.ending_nav.iloc[-1] == pytest.approx(1000 * 1.001**12)
    assert cash.turnover.sum() == cash.fee.sum() == 0


def test_csv_parser_uses_named_monthly_section_and_rejects_duplicate_dates(tmp_path):
    path = tmp_path / "source.csv"
    path.write_text(
        "metadata\nAverage Value Weighted Returns -- Monthly\n,A,B\n"
        "200001,1,2\n200002,3,4\n\nAverage Equal Weighted Returns -- Monthly\n,A,B\n200001,99,99\n",
        encoding="utf-8",
    )
    values = read_section(path, "Average Value Weighted Returns -- Monthly")
    np.testing.assert_array_equal(values.to_numpy(), [[1, 2], [3, 4]])
    path.write_text(",A\n200001,1\n200001,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        read_section(path)


def test_causal_regime_reference_matches_and_ignores_future_returns():
    independent, original = synthetic()
    labels = regimes_reference(independent, 2)
    assert labels == causal_regimes(original, 2)
    values = independent.returns.copy()
    values[90:] *= -5
    altered = regimes_reference(
        Inputs(independent.months, independent.symbols, values, independent.rf), 2
    )
    for month in independent.months[:92]:
        if month in labels:
            assert altered[month] == labels[month]


def test_bootstrap_joint_maximum_matches_artificial_matrix():
    values = np.random.default_rng(44).normal(0, 0.03, (36, 7))
    expected = bootstrap_reference(values, repeats=60)
    original = max_mean_bootstrap(values, repeats=60)
    for name, result in expected.items():
        np.testing.assert_allclose(result, original[name], atol=1e-15)
    assert np.all(expected["familywise_p"] >= expected["unadjusted_p"])


def test_bootstrap_constant_columns_have_known_null_probabilities():
    values = np.column_stack((np.zeros(12), np.ones(12), -np.ones(12)))
    result = bootstrap_reference(values, repeats=19)
    np.testing.assert_array_equal(result["familywise_p"], [1, 0.05, 1])


def study_records():
    records = []
    for identity in ("CMKT", "A", "B"):
        for window in ("training", "evaluation", "full"):
            for cost in (10, 25, 50):
                for lag in (1, 2):
                    records.append(
                        {
                            "policy": identity,
                            "family": identity,
                            "window": window,
                            "cost_bps": cost,
                            "lag": lag,
                            "cagr": {"CMKT": 0.12, "A": 0.15, "B": 0.30}[identity],
                            "max_drawdown": {"CMKT": -0.4, "A": -0.15, "B": -0.3}[identity],
                        }
                    )
    return records


def test_training_selection_does_not_use_later_performance_and_keeps_empty_groups():
    records = study_records()
    expected = selection_reference(records)
    assert expected == {"stable": ["A", "B"], "growth10": ["B", "A"], "growth25": ["B"]}
    for row in records:
        if row["window"] != "training":
            row["cagr"] = -0.9
    assert selection_reference(records) == expected
    for row in records:
        row["cagr"] = -0.01
    assert selection_reference(records) == {"stable": [], "growth10": [], "growth25": []}


def test_stable_screen_requires_strictly_lower_drawdown_and_all_twelve_cases():
    records = study_records()
    result = classification_reference(records, ["A", "B"])
    assert result["counts"]["stable_all12"] == 2
    next(
        r
        for r in records
        if (r["policy"], r["window"], r["cost_bps"], r["lag"]) == ("A", "full", 50, 1)
    )["max_drawdown"] = -0.4
    next(
        r
        for r in records
        if (r["policy"], r["window"], r["cost_bps"], r["lag"]) == ("B", "evaluation", 50, 2)
    )["cagr"] = -0.01
    result = classification_reference(records, ["A", "B"])
    assert result["counts"]["stable_all12"] == 0
    assert result["counts"]["positive_all12"] == 1
    assert result["counts"]["growth10_primary_both"] == 2
    assert result["counts"]["growth25_primary_both"] == 1


@pytest.mark.parametrize("lag", [1, 2])
@pytest.mark.parametrize(
    "identity",
    ["CZERO", "CRF", "CMKT", "CEQ", "MOM_01", "INVERSEVOL_01", "CPPIFIXED_01", "CPPIRATCHET_01"],
)
def test_century_cash_warmup_partial_years_and_activation_reconcile(identity, lag, tmp_path):
    independent, original = synthetic()
    policy = next(
        (p for p in REGISTRATION["policies"] if p["id"] == identity),
        {"id": identity, "family": "control"},
    )
    targets = None
    candidate = identity not in ("CZERO", "CRF", "CMKT", "CEQ")
    if candidate and not identity.startswith("CPPI"):
        targets = np.zeros_like(independent.returns)
        for pos in range(78, 84):
            targets[pos] = target_reference(policy, independent, pos - lag)
    frame, summary = simulate_monthly(original, policy, "1926-07", "1933-06", 25, lag, targets)
    ledger = {"risky_after_cost": frame.attrs["risky_after_cost"]}
    path = tmp_path / "roundtrip.csv"
    frame.to_csv(path, index=False)
    roundtrip = pd.read_csv(path, float_precision="round_trip")
    audit = Audit()
    verified = audit_account(
        roundtrip, independent, policy, "1926-07", "1933-06", 25, lag, targets, audit, ledger
    )
    compare_summary(summary, verified["metrics"], audit)
    assert set(summary["annual"]) == {str(y) for y in range(1927, 1933)}
    assert set(summary["partial_calendar_returns"]) == {"1926", "1933"}
    assert summary["warmup_months"] == (78 if candidate else 0)
    assert roundtrip.as_of.iloc[:lag].isna().all()
    if candidate:
        assert frame.iloc[:78].fee.sum() == 0
        assert np.count_nonzero(ledger["risky_after_cost"][:78]) == 0
        assert frame.ending_nav.iloc[77] == pytest.approx(1000 * 1.001**78)
        assert frame.reference_nav.iloc[78] == pytest.approx(1000 * 1.001 ** (79 - lag))
    elif identity in ("CMKT", "CEQ"):
        assert frame.risky_fraction.iloc[0] > 0


def test_fabricated_pre_source_asof_and_false_warmup_are_rejected():
    independent, original = synthetic()
    policy = {"id": "CPPIFIXED_01", "family": "CPPIFIXED", "floor_fraction": 0.8, "multiplier": 3}
    frame, _ = simulate_monthly(original, policy, "1926-07", "1933-06", 25, 2)
    frame.loc[0, "as_of"] = "1926-06-30"
    with pytest.raises(ValueError, match="as_of"):
        audit_account(frame, independent, policy, "1926-07", "1933-06", 25, 2, None, Audit())
    frame.loc[0, "as_of"] = None
    frame.loc[77, "warmup"] = False
    with pytest.raises(ValueError, match="warmup"):
        audit_account(frame, independent, policy, "1926-07", "1933-06", 25, 2, None, Audit())


def test_partial_year_only_does_not_pass_annual_floor_vacuously():
    _, original = synthetic()
    frame, summary = simulate_monthly(
        original, {"id": "CRF", "family": "control"}, "1926-07", "1926-12", 25, 2
    )
    independent = measure(frame)
    compare_summary(summary, independent, Audit())
    assert independent["annual"] == {}
    assert independent["all_years_ge_10pct"] is False
    assert independent["partial_calendar_returns"]["1926"] == pytest.approx(1.001**6 - 1)


def test_century_secondary_classification_keeps_distinct_cash_warmup_history():
    records = study_records()
    century = [{**r, "window": "century", "cagr": -0.02} for r in records if r["window"] == "full"]
    combined = records + century
    primary = classification_reference(combined, ["A", "B"])
    secondary_inputs = [
        {**r, "window": "full" if r["window"] == "century" else "evaluation"}
        for r in combined
        if r["window"] in {"century", "evaluation"}
    ]
    secondary = classification_reference(secondary_inputs, ["A", "B"])
    assert primary["counts"]["growth10_primary_both"] == 2
    assert secondary["counts"]["positive_all12"] == 0
