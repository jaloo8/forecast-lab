"""Archive adaptation preserves actual provenance and discloses full-grid selection."""

import json
from pathlib import Path

import pandas as pd
import pytest

from kq.equities.strategy_lab import archive


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    history = tmp_path / "broad-history-2026-09-28"
    history.mkdir()
    (tmp_path / "universe").mkdir()
    (tmp_path / "universe/manifest.json").write_text("{}")
    days = ["2026-09-24T00:00:00Z", "2026-09-25T00:00:00Z"]
    bars = [
        dict(
            begins_at=d,
            open_price="10",
            high_price="12",
            low_price="9",
            close_price="11",
            volume=100,
            session="reg",
        )
        for d in days
    ]

    def series(symbol: str) -> dict:
        return dict(symbol=symbol, interval="day", bounds="regular", bars=bars)

    for name, rows in [("benchmark.json", [series("SPY")]), ("batch.json", [series("AAA")])]:
        (history / name).write_text(
            json.dumps({"captured_at": "2026-09-28T01:00:00Z", "data": {"results": rows}})
        )
    monkeypatch.setattr(
        archive,
        "scan_captures",
        lambda *args: (
            pd.DataFrame(),
            pd.DataFrame({"symbol": ["AAA", "BBB"], "coverage_status": ["ranked", "not_found"]}),
        ),
    )
    return history


def test_actual_retrieval_separate_from_simulated_as_of(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fixture(tmp_path, monkeypatch)
    bars, metadata = archive.load_archive(tmp_path)
    assert bars.as_of.max().date().isoformat() == "2026-09-25"
    assert metadata["captured_at"] == "2026-09-28T01:00:00Z"
    assert metadata["stock_count"] == 1 and metadata["candidate_count"] == 2
    assert metadata["excluded"] == {"BBB": "not_found"}
    assert len(metadata["input_sha256"]) == 2
    assert metadata["input_captured_at"]["batch.json"] == "2026-09-28T01:00:00Z"
    assert any("observed SPY" in value for value in metadata["limitations"])


def test_duplicate_source_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    history = _fixture(tmp_path, monkeypatch)
    (history / "duplicate.json").write_bytes((history / "batch.json").read_bytes())
    with pytest.raises(ValueError, match="Duplicate"):
        archive.load_archive(tmp_path)


def test_invalid_ohlc_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    history = _fixture(tmp_path, monkeypatch)
    j = json.loads((history / "batch.json").read_text())
    j["data"]["results"][0]["bars"][0]["high_price"] = "8"
    (history / "batch.json").write_text(json.dumps(j))
    with pytest.raises(ValueError, match="inconsistent OHLC"):
        archive.load_archive(tmp_path)


@pytest.mark.parametrize("filename", ["benchmark.json", "batch.json"])
def test_explicit_non_split_result_adjustment_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filename: str
) -> None:
    history = _fixture(tmp_path, monkeypatch)
    path = history / filename
    value = json.loads(path.read_text())
    value["data"]["results"][0]["adjustment_type"] = "none"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="adjustment"):
        archive.load_archive(tmp_path)
