"""Regression checks for the broad historical study's source assembly."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_broad_stock_study.py"


def _module() -> object:
    spec = importlib.util.spec_from_file_location("run_broad_stock_study", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_output_must_be_study_json_in_data_dir(tmp_path: Path) -> None:
    module = _module()
    data = tmp_path / "equities"
    data.mkdir()
    history = data / "broad-history-2026-09-28"
    history.mkdir()
    assert module._output_path(data, data / "broad-historical-study-rerun.json") == (
        data / "broad-historical-study-rerun.json"
    )
    for bad in (history / "batch-1.json", data / "universe" / "manifest.json",
                data / "arbitrary.json", tmp_path / "broad-historical-study.json"):
        with pytest.raises(ValueError, match="output"):
            module._output_path(data, bad)


def test_source_selects_only_complete_ranked_real_grids(tmp_path: Path) -> None:
    module = _module()
    data = tmp_path / "equities"
    history = data / "broad-history-2026-09-28"
    universe = data / "universe"
    history.mkdir(parents=True)
    universe.mkdir()
    (universe / "manifest.json").write_text('{}', encoding="utf-8")
    def bars(days: list[str], *, synthetic: bool = False) -> list[dict[str, object]]:
        return [{"begins_at": day, "volume": 10, "synthetic": synthetic} for day in days]
    days = ["2026-09-24T00:00:00Z", "2026-09-25T00:00:00Z"]
    captured = "2026-09-28T12:00:00Z"
    (history / "benchmark.json").write_text(json.dumps({"captured_at": captured,
        "data": {"results": [{"symbol": "SPY", "bars": bars(days)}]}}), encoding="utf-8")
    (history / "batch.json").write_text(json.dumps({"captured_at": captured,
        "data": {"results": [{"symbol": "AAA", "bars": bars(days)},
                              {"symbol": "BBB", "bars": bars(days, synthetic=True)},
                              {"symbol": "CCC", "bars": bars(days[:1])}]}}), encoding="utf-8")
    coverage = pd.DataFrame({"symbol": ["AAA", "BBB", "CCC", "DDD"],
                             "coverage_status": ["ranked", "ranked", "ranked", "not_found"]})
    source, stocks, exclusions = module._assemble_source(data, coverage)
    assert stocks == ("AAA",)
    assert [item["symbol"] for item in source["bars"]] == ["SPY", "AAA"]
    assert exclusions == {"DDD": "not_found", "BBB": "incomplete_real_positive_volume_grid",
                          "CCC": "incomplete_real_positive_volume_grid"}
    assert set(source["input_hashes"]) == {"benchmark.json", "batch.json"}
