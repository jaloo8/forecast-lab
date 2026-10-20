"""Synthetic input-integrity, selection and aggregation checks; no market run."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scripts import run_allocation_study as runner


def source_fixture(tmp_path, change=None):
    source = tmp_path / "source"
    source.mkdir()
    available = pd.bdate_range("2007-05-30", "2025-12-31")
    positions = np.linspace(0, len(available) - 1, 4679, dtype=int)
    dates = available[positions].append(pd.DatetimeIndex(["2026-01-02"]))
    manifest = {"files": {}}
    hashes = {}
    for symbol in runner.SYMBOLS:
        frame = pd.DataFrame(
            {
                "Date": dates,
                "Open": 100.0,
                "High": 115.0,
                "Low": 90.0,
                "Close": 110.0,
                "Adj Close": 55.0,
            }
        )
        frame.loc[frame.index[-1], ["Open", "High", "Low", "Close", "Adj Close"]] = 250.0
        if change is not None:
            frame = change(symbol, frame)
        path = source / f"{symbol}.csv"
        frame.to_csv(path, index=False)
        value = runner.digest(path)
        hashes[path.name] = value
        manifest["files"][symbol] = {"file": path.name, "sha256": value}
    manifest_path = source / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    registration = {
        "inputs": {
            "manifest_sha256": runner.digest(manifest_path),
            "file_sha256": hashes,
            "common_start": "2007-05-30",
            "truncate_at": "2025-12-31",
        }
    }
    return source, registration


def test_source_shape_price_adjustment_and_future_exclusion(tmp_path):
    source, registration = source_fixture(tmp_path)
    prices, receipt = runner.load_inputs(source, registration)
    assert tuple(prices.closed.columns) == runner.SYMBOLS
    assert prices.closed.shape == prices.opened.shape == (4679, 6)
    assert prices.closed.index.equals(prices.opened.index)
    assert prices.closed.index[0] == pd.Timestamp("2007-05-30")
    assert prices.closed.index[-1] == pd.Timestamp("2025-12-31")
    assert (prices.opened.to_numpy() == 50.0).all()
    assert (prices.closed.to_numpy() == 55.0).all()
    assert receipt["sessions"] == 4679
    assert receipt["after_2025_excluded"] is True
    assert receipt["file_sha256"] == registration["inputs"]["file_sha256"]


@pytest.mark.parametrize("member", ["manifest.json", "SPY.csv"])
def test_source_rejects_bytes_changed_after_registration(tmp_path, member):
    source, registration = source_fixture(tmp_path)
    path = source / member
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match=r"manifest differs|hash differs"):
        runner.load_inputs(source, registration)


def test_source_rejects_second_registered_member_hash_mismatch(tmp_path):
    source, registration = source_fixture(tmp_path)
    registration["inputs"]["file_sha256"]["SPY.csv"] = "0" * 64
    with pytest.raises(ValueError, match="Source hash differs: SPY"):
        runner.load_inputs(source, registration)


def test_source_rejects_calendar_gap_even_when_all_hashes_match(tmp_path):
    def remove_one(symbol, frame):
        return frame.drop(index=30) if symbol == "EFA" else frame

    source, registration = source_fixture(tmp_path, remove_one)
    with pytest.raises(ValueError, match="Missing or mismatched observed session: EFA"):
        runner.load_inputs(source, registration)


@pytest.mark.parametrize("failure", ["duplicate", "nonpositive", "bad_high", "unordered"])
def test_source_rejects_invalid_dates_or_prices_with_matching_hashes(tmp_path, failure):
    def change(symbol, frame):
        if symbol == "SPY":
            if failure == "duplicate":
                frame.loc[1, "Date"] = frame.loc[0, "Date"]
            elif failure == "nonpositive":
                frame.loc[1, "Adj Close"] = 0
            elif failure == "bad_high":
                frame.loc[1, "High"] = 95
            else:
                frame = frame.iloc[::-1]
        return frame

    source, registration = source_fixture(tmp_path, change)
    with pytest.raises(ValueError, match="Invalid source dates/prices: SPY"):
        runner.load_inputs(source, registration)


def selection_fixture():
    eligible = ["A01", "A02", "I01", "I02", "I03", "I04", "O01", "O02"]
    registration = {"selection": {"eligible": eligible}}
    rows = [
        {
            "policy": policy,
            "window": "training",
            "cost_bps": 25,
            "worst_year": -0.1,
            "cagr": 0.1,
            "max_drawdown": -0.2,
        }
        for policy in eligible
    ]
    return registration, rows


def test_selection_uses_training_primary_cost_and_registered_tie_breaks_only():
    registration, rows = selection_fixture()
    ignored = [
        {**rows[0], "window": "evaluation", "worst_year": 99},
        {**rows[0], "window": "full", "worst_year": 99},
        {**rows[0], "cost_bps": 10, "worst_year": 99},
        {**rows[0], "cost_bps": 50, "worst_year": 99},
        {**rows[0], "policy": "C03", "worst_year": 99},
    ]
    assert runner.select_training(rows + ignored, registration)["selected_policy"] == "A01"
    rows[-1]["max_drawdown"] = -0.15
    assert runner.select_training(rows + ignored, registration)["selected_policy"] == "O02"
    rows[-2]["cagr"] = 0.11
    assert runner.select_training(rows + ignored, registration)["selected_policy"] == "O01"
    rows[2]["worst_year"] = -0.09
    selected = runner.select_training(rows + ignored, registration)
    assert selected["selected_policy"] == "I01"
    assert len(selected["ranked_training"]) == 8
    assert all(row["window"] == "training" for row in selected["ranked_training"])
    assert all(row["cost_bps"] == 25 for row in selected["ranked_training"])


@pytest.mark.parametrize("failure", ["missing", "duplicate_extra", "duplicate_replacement"])
def test_selection_rejects_missing_and_duplicate_candidates(failure):
    registration, rows = selection_fixture()
    if failure == "missing":
        rows.pop()
    elif failure == "duplicate_extra":
        rows.append(rows[0])
    else:
        rows[-1] = rows[0]
    with pytest.raises(ValueError, match="Incomplete training selection"):
        runner.select_training(rows, registration)


def metric_fixture():
    daily = pd.DataFrame(
        {
            "session_date": pd.to_datetime(["2019-12-31", "2020-12-31"]),
            "open_before": [1000.0, 1050.0],
            "open_after": [999.0, 1048.0],
            "close_before": [1100.0, 1000.0],
            "nav": [1100.0, 999.0],
            "cash": [20.0, 999.0],
            "cost": [1.0, 2.0],
            "floor": [800.0, 1100.0],
            "floor_breached_open_before": [False, True],
            "floor_breached_open_after": [False, True],
            "floor_breached_close_before": [False, True],
            "floor_breached_nav": [False, True],
        }
    )
    ledger = pd.DataFrame({"cost": [1.0, 2.0]})
    for symbol in runner.SYMBOLS:
        ledger[f"delta_{symbol}"] = 0.0
        ledger[f"price_{symbol}"] = 100.0
    ledger.loc[0, "delta_SPY"] = 0.005
    ledger.loc[1, "delta_SPY"] = -0.005
    ledger.loc[0, "delta_EFA"] = 0.01
    ledger.loc[1, "delta_EFA"] = -0.02
    ledger.loc[1, "delta_IEF"] = 1e-16
    return daily, ledger


def test_metrics_count_tickets_and_breach_sessions_without_double_counting():
    daily, ledger = metric_fixture()
    result = runner.metrics(daily, ledger, "I03", 25, "evaluation")
    assert result["trade_count"] == 4
    assert result["sub_dollar_traded_legs"] == 2
    assert result["smallest_positive_traded_leg_usd"] == 0.5
    assert result["turnover"] == pytest.approx(4.0)
    assert result["floor_breach_sessions"] == 1
    assert result["minimum_nav_minus_floor"] == -101
    assert result["portfolio_trade_events"] == 2
    assert set(result["annual"]) == {"2019", "2020"}


def test_metrics_cash_case_keeps_zero_trades_and_no_insurance_claim():
    daily, ledger = metric_fixture()
    for symbol in runner.SYMBOLS:
        ledger[f"delta_{symbol}"] = 0.0
    ledger["cost"] = 0.0
    result = runner.metrics(daily, ledger, "C01", 25, "evaluation")
    assert result["trade_count"] == result["sub_dollar_traded_legs"] == 0
    assert result["smallest_positive_traded_leg_usd"] is None
    assert result["turnover"] == result["portfolio_trade_events"] == 0
    assert "floor_breach_sessions" not in result


def review_fixture(tmp_path):
    root = Path(runner.__file__).resolve().parents[1]
    value = {
        "status": "PASS",
        "registration_sha256": runner.REGISTRATION_SHA256,
        "code_sha256": {name: runner.digest(root / name) for name in runner.SOURCE_FILES},
    }
    path = tmp_path / "review.json"
    return path, value


@pytest.mark.parametrize("failure", ["missing", "failed", "registration", "source", "absent_hash"])
def test_review_must_match_before_any_input_loading_or_performance(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(runner, "read_registration", lambda: {})

    def forbidden(*args, **kwargs):
        pytest.fail("Unapproved run reached source loading or performance")

    monkeypatch.setattr(runner, "load_inputs", forbidden)
    monkeypatch.setattr(runner, "build_signals", forbidden)
    monkeypatch.setattr(runner, "simulate", forbidden)
    review, value = review_fixture(tmp_path)
    if failure == "failed":
        value["status"] = "FAIL"
    elif failure == "registration":
        value["registration_sha256"] = "0" * 64
    elif failure == "source":
        value["code_sha256"][runner.SOURCE_FILES[0]] = "0" * 64
    elif failure == "absent_hash":
        value["code_sha256"].pop(runner.SOURCE_FILES[0])
    if failure != "missing":
        review.write_text(json.dumps(value), encoding="utf-8")
    output = tmp_path / "run"
    expected = FileNotFoundError if failure == "missing" else ValueError
    with pytest.raises(expected):
        runner.run_study(tmp_path / "missing-source", output, review)
    assert not output.exists()


def test_existing_run_is_preserved_before_review_or_input_access(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "read_registration", lambda: {})
    output = tmp_path / "run"
    output.mkdir()
    receipt = output / "original.txt"
    receipt.write_text("original evidence", encoding="utf-8")
    with pytest.raises(FileExistsError, match="prior results are preserved"):
        runner.run_study(tmp_path / "source", output, tmp_path / "missing-review.json")
    assert receipt.read_text(encoding="utf-8") == "original evidence"
