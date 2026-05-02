"""Tests for `kq router-summary`. Operates entirely on synthesized manifests
in a tmp dir — no DB, no network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from kq.flows.router_summary import (
    BRIER_VS_NDFD_BAR_PCT,
    render_human,
    run,
    summarize,
)


def _write_manifest(
    models_dir: Path,
    fname: str,
    *,
    stations: dict[str, dict[str, Any]],
) -> None:
    """Write a minimal backtest manifest with the given station rows."""
    payload = {"stations": stations}
    (models_dir / fname).write_text(json.dumps(payload))


def _write_router_config(
    models_dir: Path,
    *,
    decisions: dict[str, dict[str, Any]],
    mode: str = "ndfd_aware",
    threshold: float = 1.0,
    generated_at: str = "2026-05-02T00:00:00+00:00",
) -> None:
    payload = {
        "generated_at": generated_at,
        "mode": mode,
        "decision_threshold_pct": threshold,
        "decisions": decisions,
    }
    (models_dir / "router_config.json").write_text(json.dumps(payload))


def _models_dir(tmp_path: Path) -> Path:
    md = tmp_path / "models"
    md.mkdir()
    return md


def _row(brier_vs_ndfd: float | None = None, passes_calib: bool | None = None) -> dict[str, Any]:
    """One manifest row for one station."""
    out: dict[str, Any] = {}
    if brier_vs_ndfd is not None:
        out["brier_improvement_vs_ndfd_pct"] = brier_vs_ndfd
    if passes_calib is not None:
        out["reliability_summary"] = {"passes_bar": passes_calib}
    return out


# ----------------------------------------------------------- summarize


def test_empty_models_dir_returns_empty_summary(tmp_path: Path) -> None:
    md = _models_dir(tmp_path)
    s = summarize(md)
    assert s.n_stations == 0
    assert s.n_stations_ngr == 0
    assert s.n_stations_raw == 0
    assert s.n_passes_brier_bar == 0
    assert s.phase5_passes_brier_bar is False
    assert s.stations == []


def test_router_decisions_drive_strategy_count(tmp_path: Path) -> None:
    md = _models_dir(tmp_path)
    _write_router_config(
        md,
        decisions={
            "KAUS": {"strategy": "raw", "reason": "raw better"},
            "KDEN": {"strategy": "ngr", "reason": "ngr clears bar"},
            "KJFK": {"strategy": "ngr", "reason": "ngr clears bar"},
            "KLAX": {"strategy": "raw", "reason": "raw better"},
        },
    )
    s = summarize(md)
    assert s.n_stations == 4
    assert s.n_stations_ngr == 2
    assert s.n_stations_raw == 2
    assert s.n_stations_other == 0
    assert s.router_mode == "ndfd_aware"
    assert s.decision_threshold_pct == pytest.approx(1.0)


def test_brier_bar_aggregates_from_router_v1_manifest(tmp_path: Path) -> None:
    """Active strategy is `weather_router_v1`; brier bar is computed off
    that manifest, NOT off `weather_v1` or `weather_all_raw_v1`."""
    md = _models_dir(tmp_path)
    _write_router_config(md, decisions={"KAUS": {"strategy": "raw"}, "KDEN": {"strategy": "ngr"}})
    # Construct a clear contrast: v1 looks great, router_v1 looks bad.
    _write_manifest(
        md,
        "backtest_manifest.json",
        stations={"KAUS": _row(brier_vs_ndfd=20.0), "KDEN": _row(brier_vs_ndfd=20.0)},
    )
    _write_manifest(
        md,
        "backtest_router_manifest.json",
        stations={"KAUS": _row(brier_vs_ndfd=-5.0), "KDEN": _row(brier_vs_ndfd=-5.0)},
    )
    s = summarize(md)
    assert s.n_passes_brier_bar == 0  # router_v1 fails both


def test_brier_bar_passes_only_when_router_v1_clears_threshold(tmp_path: Path) -> None:
    md = _models_dir(tmp_path)
    _write_router_config(
        md,
        decisions={
            "KAUS": {"strategy": "raw"},
            "KDEN": {"strategy": "ngr"},
            "KJFK": {"strategy": "ngr"},
            "KLAX": {"strategy": "raw"},
            "KMDW": {"strategy": "raw"},
            "KMIA": {"strategy": "raw"},
        },
    )
    _write_manifest(
        md,
        "backtest_router_manifest.json",
        stations={
            "KAUS": _row(brier_vs_ndfd=BRIER_VS_NDFD_BAR_PCT - 0.01),  # just below
            "KDEN": _row(brier_vs_ndfd=BRIER_VS_NDFD_BAR_PCT),  # exactly at
            "KJFK": _row(brier_vs_ndfd=20.0),
            "KLAX": _row(brier_vs_ndfd=10.0),
            "KMDW": _row(brier_vs_ndfd=-50.0),
            "KMIA": _row(brier_vs_ndfd=5.0),
        },
    )
    s = summarize(md)
    # KAUS just-below fails; KDEN exactly-at passes (>=); the other three
    # are clear: KJFK + KLAX + KMIA pass, KMDW fails. Total: 4 pass.
    assert s.n_passes_brier_bar == 4
    assert s.phase5_passes_brier_bar is True  # exactly at the >= 4 gate


def test_calibration_bar_uses_router_v1_reliability_summary(tmp_path: Path) -> None:
    md = _models_dir(tmp_path)
    _write_router_config(md, decisions={"KAUS": {"strategy": "raw"}, "KDEN": {"strategy": "ngr"}})
    _write_manifest(
        md,
        "backtest_router_manifest.json",
        stations={
            "KAUS": _row(brier_vs_ndfd=10.0, passes_calib=True),
            "KDEN": _row(brier_vs_ndfd=10.0, passes_calib=False),
        },
    )
    s = summarize(md)
    assert s.n_passes_calibration == 1
    by = {v.station: v for v in s.stations}
    assert by["KAUS"].active_passes_calibration is True
    assert by["KDEN"].active_passes_calibration is False


def test_per_strategy_columns_populate_for_each_station(tmp_path: Path) -> None:
    """Each station's view exposes brier/calibration cells for all 4 strategies."""
    md = _models_dir(tmp_path)
    _write_router_config(md, decisions={"KAUS": {"strategy": "raw"}})
    _write_manifest(
        md,
        "backtest_manifest.json",
        stations={"KAUS": _row(brier_vs_ndfd=10.0, passes_calib=False)},
    )
    _write_manifest(
        md,
        "backtest_router_manifest.json",
        stations={"KAUS": _row(brier_vs_ndfd=11.0, passes_calib=False)},
    )
    _write_manifest(
        md,
        "backtest_all_raw_manifest.json",
        stations={"KAUS": _row(brier_vs_ndfd=12.0, passes_calib=False)},
    )
    _write_manifest(
        md,
        "backtest_reforecast_manifest.json",
        stations={"KAUS": _row(brier_vs_ndfd=13.0, passes_calib=True)},
    )
    s = summarize(md)
    assert len(s.stations) == 1
    sv = s.stations[0]
    assert sv.brier_vs_ndfd_pct_by_strategy["v1"] == pytest.approx(10.0)
    assert sv.brier_vs_ndfd_pct_by_strategy["router_v1"] == pytest.approx(11.0)
    assert sv.brier_vs_ndfd_pct_by_strategy["all_raw_v1"] == pytest.approx(12.0)
    assert sv.brier_vs_ndfd_pct_by_strategy["reforecast_v1"] == pytest.approx(13.0)
    assert sv.calibration_passes_by_strategy["reforecast_v1"] is True
    assert sv.calibration_passes_by_strategy["router_v1"] is False


def test_missing_manifest_yields_none_cells(tmp_path: Path) -> None:
    """A station present in router_config but missing from a manifest must
    show None in that strategy's cell, not raise."""
    md = _models_dir(tmp_path)
    _write_router_config(md, decisions={"KAUS": {"strategy": "raw"}})
    # Don't write any manifests at all
    s = summarize(md)
    assert len(s.stations) == 1
    sv = s.stations[0]
    for short in ("v1", "router_v1", "all_raw_v1", "reforecast_v1"):
        assert sv.brier_vs_ndfd_pct_by_strategy[short] is None
        assert sv.calibration_passes_by_strategy[short] is None


def test_malformed_manifest_is_logged_and_treated_as_missing(tmp_path: Path) -> None:
    md = _models_dir(tmp_path)
    _write_router_config(md, decisions={"KAUS": {"strategy": "raw"}})
    (md / "backtest_router_manifest.json").write_text("not valid JSON")
    s = summarize(md)
    sv = s.stations[0]
    assert sv.brier_vs_ndfd_pct_by_strategy["router_v1"] is None


def test_unknown_active_strategy_counts_as_other(tmp_path: Path) -> None:
    """A future router that emits ``strategy=reforecast`` must be tallied
    under `n_stations_other` (not `n_stations_ngr` or `_raw`)."""
    md = _models_dir(tmp_path)
    _write_router_config(
        md,
        decisions={
            "KAUS": {"strategy": "raw"},
            "KDEN": {"strategy": "reforecast"},  # forward-compat
            "KJFK": {"strategy": "ngr"},
        },
    )
    s = summarize(md)
    assert s.n_stations == 3
    assert s.n_stations_raw == 1
    assert s.n_stations_ngr == 1
    assert s.n_stations_other == 1


# ----------------------------------------------------------- render


def test_render_human_includes_per_strategy_grid(tmp_path: Path) -> None:
    md = _models_dir(tmp_path)
    _write_router_config(md, decisions={"KAUS": {"strategy": "raw", "reason": "test reason"}})
    _write_manifest(
        md,
        "backtest_router_manifest.json",
        stations={"KAUS": _row(brier_vs_ndfd=5.0, passes_calib=True)},
    )
    s = summarize(md)
    out = render_human(s)
    assert "KAUS" in out
    assert "RAW" in out
    assert "test reason" in out
    assert "brier-vs-ndfd" in out
    assert "calibration" in out
    # The Phase 5 #2 verdict line must be present + show a clear PASS or FAIL.
    assert "Phase 5 #2" in out


def test_render_handles_empty_summary(tmp_path: Path) -> None:
    md = _models_dir(tmp_path)
    s = summarize(md)
    out = render_human(s)
    assert "no stations" in out


def test_run_returns_json_when_requested(tmp_path: Path) -> None:
    md = _models_dir(tmp_path)
    _write_router_config(md, decisions={"KAUS": {"strategy": "raw"}})
    _, rendered = run(models_dir=md, json_output=True)
    parsed = json.loads(rendered)
    assert parsed["n_stations"] == 1
    assert parsed["n_stations_raw"] == 1
    # Round-trip safety — caller can rely on the fields being JSON-native.
    assert "phase5_passes_brier_bar" in parsed
