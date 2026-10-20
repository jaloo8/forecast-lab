"""Artificial runner, selection and inference boundaries; no market runs."""

import json
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scripts import run_long_history as runner

from kq.equities.long_history import MonthlyData, max_mean_bootstrap


def guarded_fixture(tmp_path, monkeypatch, policies=None):
    registration = json.loads(Path(runner.REGISTRATION).read_bytes())
    source = tmp_path / "synthetic-source"
    source.mkdir()
    rows = []
    for name in ("industries", "factors"):
        archive, member = source / f"{name}.zip", source / f"{name}.csv"
        archive.write_bytes(b"artificial archive bytes; never opened")
        member.write_text("artificial source bytes; never parsed", encoding="utf-8")
        rows.append(
            {
                "file": archive.name,
                "sha256": runner.digest(archive),
                "member": member.name,
                "member_sha256": runner.digest(member),
            }
        )
    acquired = source / "acquisition.json"
    acquired.write_text(json.dumps({"files": rows}), encoding="utf-8")
    registration["inputs"]["raw_manifest_sha256"] = runner.digest(acquired)
    if policies is not None:
        registration["policies"] = policies
    path = tmp_path / "registration.json"
    path.write_text(json.dumps(registration), encoding="utf-8")
    monkeypatch.setattr(runner, "REGISTRATION", path)
    monkeypatch.setattr(runner, "EXPECTED_REGISTRATION", runner.digest(path))
    code_files = []
    for name in ("engine.py", "runner.py", "checker.py"):
        code = tmp_path / name
        code.write_text("# Artificial hash fixture; never imported\n", encoding="utf-8")
        code_files.append(str(code))
    monkeypatch.setattr(runner, "SOURCE_FILES", tuple(code_files))
    review_value = {
        "status": "PASS",
        "registration_sha256": runner.EXPECTED_REGISTRATION,
        "source_sha256": {name: runner.digest(Path(name)) for name in code_files},
    }
    review = tmp_path / "review.json"
    review.write_text(json.dumps(review_value), encoding="utf-8")
    return source, tmp_path / "new-run", review, review_value


@pytest.mark.parametrize(
    "failure",
    [
        "missing_review",
        "invalid_json",
        "array_receipt",
        "failed_status",
        "registration_receipt",
        "source_receipt",
        "missing_source_hash",
        "changed_source_code",
        "changed_registration",
        "acquisition_manifest",
        "zip_bytes",
        "csv_bytes",
    ],
)
def test_guard_failures_precede_loading_signals_or_performance(tmp_path, monkeypatch, failure):
    source, output, review, value = guarded_fixture(tmp_path, monkeypatch)

    def forbidden(*_args, **_kwargs):
        pytest.fail("An invalid registration/review/input reached performance setup")

    monkeypatch.setattr(runner, "load_monthly", forbidden)
    monkeypatch.setattr(runner, "simulate_monthly", forbidden)
    if failure == "missing_review":
        review.unlink()
    elif failure == "invalid_json":
        review.write_text("{unfinished", encoding="utf-8")
    elif failure == "array_receipt":
        review.write_text("[]", encoding="utf-8")
    elif failure in {
        "failed_status",
        "registration_receipt",
        "source_receipt",
        "missing_source_hash",
    }:
        if failure == "failed_status":
            value["status"] = "FAIL"
        elif failure == "registration_receipt":
            value["registration_sha256"] = "0" * 64
        elif failure == "source_receipt":
            value["source_sha256"][runner.SOURCE_FILES[0]] = "0" * 64
        else:
            value["source_sha256"].pop(runner.SOURCE_FILES[0])
        review.write_text(json.dumps(value), encoding="utf-8")
    else:
        changed = {
            "changed_source_code": Path(runner.SOURCE_FILES[0]),
            "changed_registration": Path(runner.REGISTRATION),
            "acquisition_manifest": source / "acquisition.json",
            "zip_bytes": source / "industries.zip",
            "csv_bytes": source / "industries.csv",
        }[failure]
        changed.write_bytes(changed.read_bytes() + b"\n")
    error = FileNotFoundError if failure == "missing_review" else ValueError
    with pytest.raises(error):
        runner.run(source, output, review)
    assert not output.exists()


def test_actual_runner_preserves_existing_directory(tmp_path, monkeypatch):
    source, output, review, _ = guarded_fixture(tmp_path, monkeypatch)
    output.mkdir()
    original = output / "original.bin"
    original.write_bytes(b"keep these exact bytes")
    with pytest.raises(FileExistsError):
        runner.run(source, output, review)
    assert list(output.iterdir()) == [original]
    assert original.read_bytes() == b"keep these exact bytes"


def test_parser_setup_error_keeps_started_and_error_receipts(tmp_path, monkeypatch):
    source, output, review, _ = guarded_fixture(tmp_path, monkeypatch)

    def broken_source(_source):
        raise ValueError("Synthetic parser refusal")

    monkeypatch.setattr(runner, "load_monthly", broken_source)
    with pytest.raises(ValueError, match="Synthetic parser refusal"):
        runner.run(source, output, review)
    assert (output / "started.json").is_file()
    failure = json.loads((output / "run-error.json").read_bytes())
    assert failure["type"] == "ValueError"
    assert failure["message"] == "Synthetic parser refusal"
    assert not (output / "manifest.json").exists()


def test_partial_execution_retains_every_failure_and_success(tmp_path, monkeypatch):
    policies = [
        {"id": name, "family": "CPPIFIXED", "multiplier": 1, "floor_fraction": 0.8}
        for name in ("PASS", "FAIL")
    ]
    source, output, review, _ = guarded_fixture(tmp_path, monkeypatch, policies)
    monkeypatch.setattr(runner, "CONTROLS", ())
    fake = MonthlyData(
        ("1975-11", "1975-12", "1976-01"),
        (*[f"S{i}" for i in range(49)], "MKT"),
        np.zeros((3, 50)),
        np.zeros(3),
    )
    monkeypatch.setattr(runner, "load_monthly", lambda _source: fake)
    calls = []

    def simulate_stub(_data, policy, start, _end, cost, lag, _targets):
        calls.append((policy["id"], start, cost, lag))
        if policy["id"] == "FAIL":
            raise ValueError("Synthetic account failure")
        frame = pd.DataFrame({"month": ["1976-01"], "ending_nav": [1000.0]})
        frame.attrs["risky_after_cost"] = np.zeros((1, 50))
        return frame, {"cagr": 0.0, "max_drawdown": 0.0}

    monkeypatch.setattr(runner, "simulate_monthly", simulate_stub)
    with pytest.raises(RuntimeError, match="Incomplete study"):
        runner.run(source, output, review)
    assert len(calls) == 12
    assert len(json.loads((output / "results-partial.json").read_bytes())) == 6
    failures = json.loads((output / "failures.json").read_bytes())
    assert len(failures) == 6
    assert all(row["account"].startswith("FAIL_") for row in failures)
    assert all("Synthetic account failure" in row["error"] for row in failures)
    assert len(list(output.glob("PASS_*.csv.gz"))) == 6
    assert len(list(output.glob("PASS_*.positions.npz"))) == 6
    assert (output / "run-error.json").is_file()
    assert not (output / "selection.json").exists()
    assert not (output / "manifest.json").exists()


def selection_rows():
    names = ("MOM_01", "MOM_02", "MOM_03", "MOM_04", "MOM_05", "MOM_06")
    rows = [
        {
            "policy": name,
            "window": "training",
            "cost_bps": 25,
            "lag": 2,
            "cagr": 0.12,
            "max_drawdown": -0.2,
        }
        for name in (*names, *runner.CONTROLS)
    ]
    next(row for row in rows if row["policy"] == "CMKT")["max_drawdown"] = -0.4
    return rows


def test_training_selection_ignores_later_windows_costs_and_lags_and_resolves_ties():
    rows = selection_rows()
    expected = [f"MOM_{i:02}" for i in range(1, 6)]
    extras = [
        {**rows[-1], "policy": "POISON", "window": window, "cagr": 9, "max_drawdown": 0}
        for window in ("evaluation", "full")
    ] + [
        {**rows[0], "cost_bps": 10, "cagr": 9, "max_drawdown": 0},
        {**rows[0], "lag": 1, "cagr": 9, "max_drawdown": 0},
    ]
    result = runner.select_training(list(reversed(rows + extras)))
    assert result["stable"] == result["growth10"] == expected
    assert result["growth25"] == []
    rows[5]["cagr"] = 0.25
    rows[4]["max_drawdown"] = -0.1
    result = runner.select_training(rows)
    assert result["stable"][:2] == ["MOM_05", "MOM_06"]
    assert result["growth10"][0] == result["growth25"][0] == "MOM_06"


def test_training_empty_groups_stay_empty_and_stability_requires_strict_improvement():
    rows = selection_rows()
    for row in rows:
        if row["policy"] not in runner.CONTROLS:
            row.update(cagr=0.0, max_drawdown=-0.1)
    result = runner.select_training(rows)
    assert result["stable"] == result["growth10"] == result["growth25"] == []
    rows[0].update(cagr=0.05, max_drawdown=-0.4)
    assert runner.select_training(rows)["stable"] == []
    rows[0]["max_drawdown"] = -0.399
    assert runner.select_training(rows)["stable"] == ["MOM_01"]


@pytest.mark.parametrize(
    "failure", ["empty", "missing_market", "duplicate_market", "duplicate_policy"]
)
def test_training_rejects_missing_or_duplicated_primary_records(failure):
    rows = selection_rows()
    if failure == "empty":
        rows = []
    elif failure == "missing_market":
        rows = [row for row in rows if row["policy"] != "CMKT"]
    elif failure == "duplicate_market":
        rows.append(next(row for row in rows if row["policy"] == "CMKT"))
    else:
        rows.append(rows[0])
    with pytest.raises(ValueError):
        runner.select_training(rows)


def classification_rows():
    return [
        {
            "policy": name,
            "family": "MOM" if name != "CMKT" else "control",
            "window": window,
            "cost_bps": cost,
            "lag": lag,
            "cagr": 0.12,
            "max_drawdown": -0.2 if name != "CMKT" else -0.4,
        }
        for name, window, cost, lag in product(
            ("MOM_01", "MOM_02", "CMKT"), ("full", "evaluation"), (10, 25, 50), (1, 2)
        )
    ]


def test_classification_checks_all_twelve_matching_benchmarks_and_overlapping_counts():
    rows = classification_rows()
    # Only this matched scenario has a smaller benchmark drawdown.
    market = next(
        row
        for row in rows
        if (row["policy"], row["window"], row["cost_bps"], row["lag"])
        == ("CMKT", "evaluation", 50, 1)
    )
    market["max_drawdown"] = -0.1
    for row in rows:
        if row["policy"] == "MOM_02":
            row.update(cagr=0.25, max_drawdown=-0.05)
    report = runner.classify(rows, ["MOM_01", "MOM_02"])
    by_name = {row["policy"]: row for row in report["rows"]}
    assert by_name["MOM_01"]["positive_all12"]
    assert not by_name["MOM_01"]["stable_all12"]
    assert by_name["MOM_02"]["stable_all12"]
    assert report["counts"]["growth10_primary_both"] == 2
    assert report["counts"]["growth25_primary_both"] == 1
    assert report["counts"]["stable_all12"] == 1
    assert report["unique_qualifying_configurations"] == 2


def test_one_nonprimary_zero_or_equal_drawdown_fails_the_robust_screen():
    rows = classification_rows()
    changed = next(
        row
        for row in rows
        if (row["policy"], row["window"], row["cost_bps"], row["lag"]) == ("MOM_01", "full", 10, 1)
    )
    changed["cagr"] = 0
    result = runner.classify(rows, ["MOM_01"])["rows"][0]
    assert result["positive_primary_both"] and result["growth10_primary_both"]
    assert not result["positive_all12"] and not result["stable_all12"]
    changed.update(cagr=0.12, max_drawdown=-0.4)
    result = runner.classify(rows, ["MOM_01"])["rows"][0]
    assert result["positive_all12"] and not result["stable_all12"]


@pytest.mark.parametrize("failure", ["duplicate_result", "duplicate_identity"])
def test_classification_does_not_silently_double_count_or_overwrite(failure):
    rows, identities = classification_rows(), ["MOM_01", "MOM_02"]
    if failure == "duplicate_result":
        rows.append(rows[0])
    else:
        identities.append(identities[0])
    with pytest.raises(ValueError):
        runner.classify(rows, identities)


def test_bootstrap_known_shared_resamples_have_exact_maximum_adjustment(monkeypatch):
    class FixedDraws:
        def __init__(self):
            self.indices = iter([0] * 12 + [4] * 12 + [9] * 12)

        def integers(self, count):
            assert count == 12
            return next(self.indices)

        def random(self):
            return 0.0

    def factory(seed):
        assert seed == 20261020
        return FixedDraws()

    monkeypatch.setattr(np.random, "default_rng", factory)
    x = np.arange(-6, 6) / 8
    values = np.column_stack((x, -x + 0.125, np.full(12, 0.03125), np.full(12, 0.5)))
    result = max_mean_bootstrap(values, repeats=3)
    # Three shared null maxima are exactly .6875, .1875 and .4375.
    assert result["mean_monthly_excess"] == [-0.0625, 0.1875, 0.03125, 0.5]
    assert result["familywise_p"] == [1, 1, 1, 0.5]
    assert result["unadjusted_p"] == [0.5, 0.75, 0.25, 0.25]


@pytest.mark.parametrize("repeats", [0, -1, 1.5, True])
def test_bootstrap_rejects_nonpositive_or_noninteger_draw_counts(repeats):
    with pytest.raises(ValueError):
        max_mean_bootstrap(np.zeros((12, 2)), repeats=repeats)


def test_bootstrap_rejects_empty_candidate_axis():
    with pytest.raises(ValueError):
        max_mean_bootstrap(np.zeros((12, 0)), repeats=3)


def test_diagnostics_use_compounded_returns_and_calendar_stress_boundaries():
    months = tuple(map(str, pd.period_range("1976-01", "2025-12", freq="M")))
    frame = pd.DataFrame(
        {
            "month": months,
            "ending_nav": 1000 * np.cumprod(np.full(600, 1.01)),
            "risky_fraction": np.full(600, 0.8),
            "cash_pnl": np.full(600, 1.0),
            "risky_pnl": np.full(600, 2.0),
            "fee": np.full(600, 0.5),
        }
    )
    labels = {month: ("up_low_vol" if i % 2 else "down_high_vol") for i, month in enumerate(months)}
    result = runner.diagnostics(frame, labels)
    assert len(result["decade_cagr"]) == 5
    for number in result["decade_cagr"].values():
        assert number == pytest.approx(1.01**12 - 1)
    for state in result["causal_states"].values():
        assert state["months"] == 300
        assert state["mean_net_monthly_return"] == pytest.approx(0.01)
        assert state["sum_cash_pnl_usd"] == 300
        assert state["sum_risky_pnl_usd"] == 600
        assert state["sum_fees_usd"] == 150
    for period, count in {
        "1987-10:1987-10": 1,
        "2000-03:2002-10": 32,
        "2007-10:2009-03": 18,
        "2020-02:2020-04": 3,
        "2022-01:2022-12": 12,
    }.items():
        assert result["stress_total_return"][period] == pytest.approx(1.01**count - 1)
