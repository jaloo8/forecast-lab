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
