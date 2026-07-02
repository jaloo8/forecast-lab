"""Tests for the weather CLV backtest flow (manifest writer + no-data path)."""

from __future__ import annotations

import json
from pathlib import Path

from kq.backtest.weather_clv import StationClvSummary, WeatherClvSummary
from kq.flows.run_weather_clv_backtest import main, write_manifest
from kq.storage.duckdb_store import bootstrap


def _new_db(tmp_path: Path) -> Path:
    db = tmp_path / "weather_clv.duckdb"
    bootstrap(db)
    return db


def test_write_manifest_roundtrips(tmp_path: Path) -> None:
    summary = WeatherClvSummary(
        n_evaluated=3,
        n_skipped_no_ndfd=1,
        n_skipped_no_model=0,
        brier_model=0.18,
        brier_ndfd=0.2675,
        mean_edge_vs_ndfd=0.017,
        win_rate_when_picked=0.667,
        per_station={
            "KJFK": StationClvSummary(
                station="KJFK",
                n=2,
                brier_model=0.09,
                brier_ndfd=0.25,
                mean_edge_vs_ndfd=0.0,
                win_rate_when_picked=1.0,
            )
        },
    )
    out = tmp_path / "wclv.json"
    write_manifest(summary, strategy="weather_router_v1", out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["strategy"] == "weather_router_v1"
    assert payload["n_evaluated"] == 3
    assert payload["brier_model"] == 0.18
    assert payload["mean_edge_vs_ndfd"] == 0.017
    assert payload["per_station"]["KJFK"]["n"] == 2
    assert payload["per_station"]["KJFK"]["mean_edge_vs_ndfd"] == 0.0
    assert payload["per_station"]["KJFK"]["win_rate_when_picked"] == 1.0
    assert isinstance(payload["honest_caveats"], list) and payload["honest_caveats"]
    # The outcome-conditioned key is gone -- not null, GONE.
    assert "mean_signed_edge_vs_ndfd" not in payload
    assert "mean_signed_edge_vs_ndfd" not in payload["per_station"]["KJFK"]


def test_main_empty_db_is_no_data_safe(tmp_path: Path) -> None:
    db = _new_db(tmp_path)
    out = tmp_path / "wclv.json"
    # weather_v1 avoids the router_config.json dependency.
    n = main(db_path=db, strategy="weather_v1", manifest_path=out)
    assert n == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["n_evaluated"] == 0
    assert payload["brier_model"] is None
    assert payload["per_station"] == {}
