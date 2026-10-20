"""Artificial checker fixtures, including deliberate ledger corruption."""

import itertools

import numpy as np
import pandas as pd
import pytest
from scripts.check_allocation_accounting import (
    Reconciliation,
    check_covariance_target,
    check_target,
    check_trial,
    independently_measure,
    insurance_reference,
    monthly_references,
)

SYMBOLS = ("SPY", "EFA", "IEF", "VNQ", "GLD", "BIL")


def test_independent_insurance_floor_and_target_oracles():
    floor, fraction, weights = insurance_reference("I01", 1000, 1000)
    assert floor == 800
    assert fraction == pytest.approx(0.6)
    np.testing.assert_allclose(weights, [0.588, 0, 0, 0, 0, 0.392])
    floor, fraction, weights = insurance_reference("I04", 1000, 1200)
    assert floor == 960
    assert fraction == pytest.approx(0.12)
    np.testing.assert_allclose(weights[:5], np.full(5, 0.02352))
    assert weights[5] == pytest.approx(0.8624)
    assert insurance_reference("I03", 700, 1000)[1] == 0
    assert insurance_reference("I02", 1800, 1800)[1] == 1


def test_monthly_signal_reference_initial_uniform_and_one_update():
    dates = pd.to_datetime(["2007-05-30", "2007-05-31", "2007-06-29", "2007-07-02"])
    values = np.full((4, 6), 100.0)
    values[2, 0] = 200
    refs = monthly_references(dates, values)
    np.testing.assert_allclose(refs[dates[1]]["O01"], np.full(6, 0.98 / 6))
    np.testing.assert_allclose(refs[dates[1]]["O02"], np.full(6, 0.98 / 6))
    grid = np.array([w for w in itertools.product(range(5), repeat=6) if sum(w) == 4]) / 4
    gains = 1 + grid[:, 0]
    expected = np.array([sum(gains * grid[:, j]) / sum(gains) for j in range(6)]) * 0.98
    np.testing.assert_allclose(refs[dates[2]]["O01"], expected)
    odds = np.exp(0.05 / (7 / 6))
    assert refs[dates[2]]["O02"][0] / refs[dates[2]]["O02"][1] == pytest.approx(odds)


def test_monthly_reference_future_prices_do_not_revise_previous_signals():
    dates = pd.bdate_range("2007-05-30", "2007-10-31")
    values = np.exp(np.arange(len(dates))[:, None] * np.arange(1, 7)[None, :] / 2000) * 100
    expected = monthly_references(dates, values)
    cut = dates.get_loc("2007-08-15")
    values[cut:] *= 100
    altered = monthly_references(dates, values)
    for day in expected:
        if day < dates[cut]:
            for policy in ("O01", "O02"):
                np.testing.assert_array_equal(expected[day][policy], altered[day][policy])


def covariance_history():
    times = np.arange(126)
    returns = np.array([0.01 * np.cos(2 * np.pi * times * k / 126) for k in range(1, 6)]).T
    return np.vstack([np.ones(5), np.cumprod(1 + returns, axis=0)]) * 100


@pytest.mark.parametrize("policy", ["A01", "A02"])
def test_covariance_optimality_accepts_known_equal_variance_solution(policy):
    check = Reconciliation()
    check_covariance_target(policy, np.r_[np.full(5, 0.98 / 5), 0.0], covariance_history(), check)
    assert sum(check.checks.values()) > 0


@pytest.mark.parametrize("policy", ["A01", "A02"])
def test_covariance_optimality_rejects_wrong_allocation(policy):
    with pytest.raises(ValueError):
        check_covariance_target(
            policy,
            np.r_[np.array([0.3, 0.1, 0.2, 0.2, 0.2]) * 0.98, 0],
            covariance_history(),
            Reconciliation(),
        )


@pytest.mark.parametrize("policy", ["A01", "A02"])
def test_covariance_optimality_rejects_zero_covariance(policy):
    with pytest.raises(ValueError, match="Degenerate"):
        check_covariance_target(
            policy, np.r_[np.full(5, 0.196), 0], np.ones((130, 5)), Reconciliation()
        )


@pytest.mark.parametrize(
    ("policy", "weights"),
    [
        ("C01", [0, 0, 0, 0, 0, 0]),
        ("C02", [0, 0, 0, 0, 0, 0.98]),
        ("C03", [0.98, 0, 0, 0, 0, 0]),
        ("C04", [0.196, 0.196, 0.196, 0.196, 0.196, 0]),
    ],
)
def test_control_target_exact_registration(policy, weights):
    check_target(
        {},
        policy,
        pd.DatetimeIndex([]),
        np.empty((0, 6)),
        np.array(weights),
        1000,
        1000,
        {},
        Reconciliation(),
    )
    wrong = np.array(weights, dtype=float)
    wrong[0] += 0.001
    with pytest.raises(ValueError, match="registered_target"):
        check_target(
            {},
            policy,
            pd.DatetimeIndex([]),
            np.empty((0, 6)),
            wrong,
            1000,
            1000,
            {},
            Reconciliation(),
        )


def direct_rebalance(units, cash, prices, weights, rate):
    """Piecewise closed-form funding oracle; no engine or bisection imports."""
    current = units * prices
    before = cash + sum(current)
    for signs_tuple in itertools.product((-1, 1), repeat=6):
        signs = np.asarray(signs_tuple)
        after = (before + rate * sum(signs * current)) / (1 + rate * sum(signs * weights))
        delta_value = weights * after - current
        if (signs * delta_value >= -1e-10).all():
            new = weights * after / prices
            cost = sum(abs(delta_value)) * rate
            return new, before - sum(new * prices) - cost, cost
    raise AssertionError("No self-financing region")


def fixture_trial(path, policy="I03"):
    dates = pd.to_datetime(["2007-12-31", "2008-01-02", "2008-01-03", "2008-01-04"])
    opened = np.full((4, 6), 100.0)
    closed = opened.copy()
    opened[2, 0], closed[2, 0] = 120, 130
    opened[3, 0], closed[3, 0] = 70, 75
    cash, previous, peak, rate = 1000.0, 1000.0, 1000.0, 0.0025
    units = np.zeros(6)
    daily, ledger = [], []
    for i in range(1, 4):
        day_cost = 0
        floor, fraction, weights = insurance_reference(policy, previous, peak)
        state = {
            "reference_nav": previous,
            "reference_peak": peak,
            "floor": floor,
            "risky_fraction": fraction,
        }
        open_before = cash + sum(units * opened[i])
        for at_close in (False, True):
            if at_close and i != 3:
                continue
            prices = closed[i] if at_close else opened[i]
            target = np.zeros(6) if at_close else weights
            old = units.copy()
            before = cash + sum(units * prices)
            units, cash, fee = direct_rebalance(units, cash, prices, target, rate)
            day_cost += fee
            ledger.append(
                {
                    "decision_date": dates[i - 1],
                    "execution_date": dates[i],
                    "as_of": (dates[i - 1] + pd.Timedelta(hours=16))
                    .tz_localize("America/New_York")
                    .tz_convert("UTC"),
                    "reason": "terminal_prescheduled_close"
                    if at_close
                    else "initial"
                    if i == 1
                    else "rebalance",
                    "pre_nav": before,
                    "post_nav": cash + sum(units * prices),
                    "cash": cash,
                    "turnover": sum(abs((units - old) * prices)),
                    "cost": fee,
                    **{f"units_{s}": units[k] for k, s in enumerate(SYMBOLS)},
                    **{f"delta_{s}": units[k] - old[k] for k, s in enumerate(SYMBOLS)},
                    **{f"weight_{s}": target[k] for k, s in enumerate(SYMBOLS)},
                    **{f"price_{s}": prices[k] for k, s in enumerate(SYMBOLS)},
                    **state,
                }
            )
            if not at_close:
                open_after = cash + sum(units * opened[i])
                close_before = cash + sum(units * closed[i])
        measured = {
            "session_date": dates[i],
            "open_before": open_before,
            "open_after": open_after,
            "close_before": close_before,
            "nav": cash + sum(units * closed[i]),
            "cash": cash,
            "cost": day_cost,
            **state,
        }
        measured.update(
            {
                f"floor_breached_{k}": measured[k] < floor
                for k in ("open_before", "open_after", "close_before", "nav")
            }
        )
        daily.append(measured)
        previous = measured["nav"]
        peak = max(peak, previous)
    saved = independently_measure(daily, dates[1:])
    saved.update(
        policy=policy,
        cost_bps=25,
        window="full",
        sessions=3,
        turnover=sum(e["turnover"] for e in ledger),
        portfolio_trade_events=sum(e["cost"] > 0 for e in ledger),
        trade_count=sum(abs(e[f"delta_{s}"]) > 1e-12 for e in ledger for s in SYMBOLS),
    )
    registration = {
        "inputs": {"symbols": list(SYMBOLS)},
        "policies": [{"id": policy, "schedule": "daily"}],
        "windows": {"full": ["2008-01-01", "2008-12-31"]},
    }
    pd.DataFrame(daily).to_csv(path / "test_daily.csv.gz", index=False)
    pd.DataFrame(ledger).to_csv(path / "test_ledger.csv.gz", index=False)
    return saved, registration, (dates, opened, closed, {})


@pytest.mark.parametrize("policy", ["I01", "I02", "I03", "I04"])
def test_independent_full_account_oracle_accepts_valid_fixture(tmp_path, policy):
    saved, registration, inputs = fixture_trial(tmp_path, policy)
    receipt = check_trial(tmp_path, saved, "test", registration, inputs, {}, Reconciliation())
    assert receipt["status"] == "PASS"
    assert receipt["daily_rows"] == 3
    assert receipt["ledger_rows"] == 4


@pytest.mark.parametrize(
    ("file", "row", "field", "difference"),
    [
        ("ledger", 1, "reference_nav", 10),
        ("ledger", 1, "reference_peak", 10),
        ("ledger", 1, "floor", 10),
        ("ledger", 1, "risky_fraction", 0.02),
        ("ledger", 1, "weight_SPY", 0.01),
        ("ledger", 1, "cost", 1),
        ("ledger", 1, "cash", 1),
        ("ledger", 1, "units_SPY", 0.01),
        ("ledger", 1, "price_SPY", 1),
        ("daily", 1, "nav", 1),
        ("daily", 1, "reference_nav", 1),
    ],
)
def test_checker_rejects_corrupted_account(tmp_path, file, row, field, difference):
    saved, registration, inputs = fixture_trial(tmp_path)
    path = tmp_path / f"test_{file}.csv.gz"
    frame = pd.read_csv(path)
    frame.loc[row, field] += difference
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError):
        check_trial(tmp_path, saved, "test", registration, inputs, {}, Reconciliation())


def test_checker_rejects_current_session_decision(tmp_path):
    saved, registration, inputs = fixture_trial(tmp_path)
    path = tmp_path / "test_ledger.csv.gz"
    frame = pd.read_csv(path)
    frame.loc[1, "decision_date"] = frame.loc[1, "execution_date"]
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match="Wrong decision"):
        check_trial(tmp_path, saved, "test", registration, inputs, {}, Reconciliation())


def test_checker_rejects_missing_daily_rebalance(tmp_path):
    saved, registration, inputs = fixture_trial(tmp_path)
    path = tmp_path / "test_ledger.csv.gz"
    frame = pd.read_csv(path).drop(index=1)
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError):
        check_trial(tmp_path, saved, "test", registration, inputs, {}, Reconciliation())
