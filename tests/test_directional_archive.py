import hashlib
import json
import zipfile

import pandas as pd
import pytest
from scripts import run_directional_study as runner


def frozen_zip(tmp_path, monkeypatch, fault=""):
    members = {}
    data = {}
    for pointer, symbols in zip(runner.POINTERS, [("SPY",), runner.STOCKS], strict=True):
        snapshot = pointer.removesuffix("latest.json") + "raw/frozen"
        files = {}
        for symbol in symbols:
            if fault == "missing_spy" and symbol == "SPY":
                continue
            name = "../escape.csv" if fault == "traversal" else symbol + ".csv"
            price = "0" if fault == "zero_close" else "20"
            raw = (
                "Date,Open,High,Low,Close,Adj Close\n"
                f"2006-01-03,20,21,19,{price},10\n"
                "2026-01-02,20,21,19,20,10\n"
            ).encode()
            member = "Tester/" + snapshot + "/" + name
            members[member] = raw + (b"\n" if fault == "price_hash" else b"")
            files[symbol] = {
                "file": name,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "retrieved_utc": "2026-10-07T00:00:00Z",
            }
        manifest = json.dumps(
            {"files": files, "retrieved_utc": "2026-10-07T00:00:00Z", "not_point_in_time": True}
        ).encode()
        members["Tester/" + snapshot + "/manifest.json"] = manifest
        raw_pointer = json.dumps({"snapshot": snapshot}).encode()
        members["Tester/" + pointer] = raw_pointer
        data[pointer] = {
            "snapshot": snapshot,
            "pointer_sha256": hashlib.sha256(raw_pointer).hexdigest(),
            "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
        }
    if fault in {"pointer_hash", "manifest_hash"}:
        member = (
            "Tester/" + runner.POINTERS[0]
            if fault == "pointer_hash"
            else "Tester/" + data[runner.POINTERS[0]]["snapshot"] + "/manifest.json"
        )
        members[member] += b" "
    provenance = json.dumps({"data": data, "source_sha256": {"old.py": "frozen"}}).encode()
    members[runner.PROVENANCE] = provenance
    monkeypatch.setattr(runner, "PROVENANCE_SHA256", hashlib.sha256(provenance).hexdigest())
    if fault == "provenance_hash":
        members[runner.PROVENANCE] += b" "
    archive = tmp_path / "fixture.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        for name, raw in members.items():
            zipped.writestr(name, raw)
    return archive


@pytest.mark.parametrize(
    "fault",
    [
        "provenance_hash",
        "pointer_hash",
        "manifest_hash",
        "price_hash",
        "traversal",
        "missing_spy",
        "zero_close",
    ],
)
def test_archive_rejects_invalid_sources(tmp_path, monkeypatch, fault):
    archive = frozen_zip(tmp_path, monkeypatch, fault)
    with pytest.raises(ValueError):
        runner.load_archive(archive)


def test_adjustment_date_cutoff_and_provenance(tmp_path, monkeypatch):
    bars, metadata = runner.load_archive(frozen_zip(tmp_path, monkeypatch))
    assert set(bars.symbol) == {*runner.STOCKS, "SPY"}
    assert bars.open.eq(10).all() and bars.close.eq(10).all()
    assert bars.session_date.max() == pd.Timestamp("2006-01-03")
    assert metadata["provenance_sha256"] == runner.PROVENANCE_SHA256
    assert metadata["sources"][0]["retrieved_utc"] == "2026-10-07T00:00:00Z"


def test_existing_output_refused_before_archive_open(tmp_path):
    with pytest.raises(FileExistsError):
        runner.run_study(tmp_path / "absent.zip", tmp_path)


def sample_cohorts():
    return pd.DataFrame(
        [
            (
                "S20",
                "5s",
                -1,
                status,
                status,
                pd.Timestamp("2012-12-28"),
                pd.Timestamp("2013-01-08") if status != "pending" else pd.NaT,
                net,
                excess,
                hit,
                hit,
            )
            for status, net, excess, hit in [
                ("complete", -0.1, -0.02, True),
                ("unavailable", float("nan"), float("nan"), None),
                ("pending", float("nan"), float("nan"), None),
            ]
        ],
        columns=[
            "rule",
            "horizon",
            "signal",
            "status",
            "reason",
            "decision_date",
            "exit_date",
            "net_return",
            "excess_vs_spy",
            "absolute_hit",
            "relative_hit",
        ],
    )


def test_summary_retains_missing_outcomes_and_bearish_long_returns():
    rows = runner.summarize(sample_cohorts(), 10)
    overall = next(row for row in rows if row["epoch"] == "overall" and row["count"])
    assert overall["count"] == 3 and overall["unavailable"] == 1 and overall["pending"] == 1
    assert overall["mean_net_long_return"] == -0.1
    assert overall["absolute_hit_rate"] == 1
    assert not overall["qualified"]
    cross = next(row for row in rows if row["epoch"] == "cross_boundary" and row["count"])
    assert cross["count"] == 2
    assert any(row["signal"] == 0 and row["count"] == 0 for row in rows)
    assert all(row["count"] == 0 for row in rows if row["epoch"] in runner.EPOCHS)
    encoded = json.dumps(rows, allow_nan=False)
    assert "NaN" not in encoded and "Infinity" not in encoded


def test_unscored_history_not_combined_with_genuine_neutral():
    cohorts = sample_cohorts().iloc[:2].copy()
    cohorts["signal"] = 0
    cohorts.loc[1, "status"] = "excluded"
    rows = runner.summarize(cohorts, 10)
    rows = [
        row
        for row in rows
        if row["epoch"] == "overall" and row["rule"] == "S20" and row["horizon"] == "5s"
    ]
    assert next(row for row in rows if row["signal_class"] == "neutral")["count"] == 1
    assert next(row for row in rows if row["signal_class"] == "unscored")["excluded"] == 1


def test_synthetic_cli_outputs_strict_json_and_all_costs(tmp_path, monkeypatch):
    archive = frozen_zip(tmp_path, monkeypatch)
    output = tmp_path / "new"
    runner.run_study(archive, output)
    report = json.loads(
        (output / "summary.json").read_text(),
        parse_constant=lambda value: pytest.fail(f"Invalid JSON: {value}"),
    )
    assert {row["cost_bps"] for row in report["groups"]} == {10, 25, 50}
    assert len(report["metadata"]["code_protocol_sha256"]) == 3
    assert len(report["metadata"]["cohort_sha256"]) == 3
    assert len(report["metadata"]["untested_arms"]) == 3
    assert "LONG cohort" in (output / "summary.md").read_text()
