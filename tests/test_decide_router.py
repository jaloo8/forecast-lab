"""Tests for the decide-router flow's winner's-curse guard (2026-07-01 audit).

The router used to SELECT each station's strategy on the same window it then
reported — in-sample selection presented as OOS skill. The guard splits every
manifest's per-month NDFD diagnostics in half: selection runs on the first
half, and the chosen strategy's second-half number is reported as the honest
OOS figure in the reason string + the ``selection_protocol`` block of
``router_config.json``. Full nested CV is documented as out of scope.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from kq.flows import decide_router
from kq.flows.decide_router import (
    SplitWindowStats,
    _selection_manifest,
    _station_split_stats,
)
from kq.models.router import StrategyRouterConfig

# ------------------------------------------------------------- fixtures


def _month_row(month: str, brier_model: float, brier_ndfd: float, n: int = 50) -> dict[str, Any]:
    return {
        "month": month,
        "n_with_ndfd": n,
        "brier_model_subset": brier_model,
        "brier_ndfd": brier_ndfd,
        "brier_improvement_vs_ndfd_pct": round(
            (brier_ndfd - brier_model) / brier_ndfd * 100.0, 2
        ),
        "mean_clv_pp": 0.0,
    }


def _station_summary(
    *,
    full_window_vs_ndfd: float | None,
    per_month: list[dict[str, Any]] | None,
    brier_improvement_pct: float = 5.0,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "brier_improvement_pct": brier_improvement_pct,
        "brier_improvement_vs_ndfd_pct": full_window_vs_ndfd,
        "n_evaluated": 700,
        "reliability_summary": {},
    }
    if per_month is not None:
        summary["diagnostics"] = {"per_month": per_month}
    return summary


def _write(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(json.dumps(manifest), encoding="utf-8")


def _patch_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point every module-level manifest path at tmp_path; return config path."""
    config = tmp_path / "router_config.json"
    monkeypatch.setattr(decide_router, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(decide_router, "TRAINING_MANIFEST", tmp_path / "manifest.json")
    monkeypatch.setattr(decide_router, "BACKTEST_MANIFEST", tmp_path / "backtest_manifest.json")
    monkeypatch.setattr(
        decide_router, "ALL_RAW_BACKTEST_MANIFEST", tmp_path / "backtest_all_raw_manifest.json"
    )
    monkeypatch.setattr(
        decide_router,
        "REFORECAST_BACKTEST_MANIFEST",
        tmp_path / "backtest_reforecast_manifest.json",
    )
    monkeypatch.setattr(decide_router, "ROUTER_CONFIG", config)
    return config


# NGR: bad first half (-5%), great second half (+25%); full window +10%.
_NGR_MONTHS = [
    _month_row("2025-01", 0.21, 0.20),
    _month_row("2025-02", 0.21, 0.20),
    _month_row("2025-03", 0.15, 0.20),
    _month_row("2025-04", 0.15, 0.20),
]
# RAW: good first half (+5%), flat second half (0%); full window +2.5%.
_RAW_MONTHS = [
    _month_row("2025-01", 0.19, 0.20),
    _month_row("2025-02", 0.19, 0.20),
    _month_row("2025-03", 0.20, 0.20),
    _month_row("2025-04", 0.20, 0.20),
]


# --------------------------------------------------------- split-stat units


def test_station_split_stats_halves_chronologically() -> None:
    stats = _station_split_stats(
        _station_summary(full_window_vs_ndfd=10.0, per_month=_NGR_MONTHS)
    )
    assert stats is not None
    assert stats.first_half_months == "2025-01..2025-02"
    assert stats.second_half_months == "2025-03..2025-04"
    assert stats.n_first == 100
    assert stats.n_second == 100
    assert stats.first_half_vs_ndfd_pct == pytest.approx(-5.0)
    assert stats.second_half_vs_ndfd_pct == pytest.approx(25.0)


def test_station_split_stats_requires_two_ndfd_months() -> None:
    one_month = _station_summary(
        full_window_vs_ndfd=10.0, per_month=[_month_row("2025-01", 0.19, 0.20)]
    )
    assert _station_split_stats(one_month) is None
    assert _station_split_stats(_station_summary(full_window_vs_ndfd=10.0, per_month=None)) is None


def test_station_split_stats_odd_month_count_puts_extra_in_first_half() -> None:
    months = [
        _month_row("2025-01", 0.19, 0.20),
        _month_row("2025-02", 0.19, 0.20),
        _month_row("2025-03", 0.15, 0.20),
    ]
    stats = _station_split_stats(_station_summary(full_window_vs_ndfd=0.0, per_month=months))
    assert stats is not None
    assert stats.first_half_months == "2025-01..2025-02"
    assert stats.second_half_months == "2025-03..2025-03"


def test_selection_manifest_overrides_only_split_stations() -> None:
    manifest = {
        "stations": {
            "KAUS": _station_summary(full_window_vs_ndfd=10.0, per_month=_NGR_MONTHS),
            "KMIA": _station_summary(full_window_vs_ndfd=7.0, per_month=None),
        }
    }
    split = {
        "KAUS": SplitWindowStats(
            first_half_vs_ndfd_pct=-5.0,
            second_half_vs_ndfd_pct=25.0,
            first_half_months="2025-01..2025-02",
            second_half_months="2025-03..2025-04",
            n_first=100,
            n_second=100,
        )
    }
    selection = _selection_manifest(manifest, split)
    assert selection["stations"]["KAUS"]["brier_improvement_vs_ndfd_pct"] == pytest.approx(-5.0)
    # No split → full-window value untouched; original manifest not mutated.
    assert selection["stations"]["KMIA"]["brier_improvement_vs_ndfd_pct"] == 7.0
    assert manifest["stations"]["KAUS"]["brier_improvement_vs_ndfd_pct"] == 10.0


# --------------------------------------------------------- end-to-end flow


def test_decide_router_selects_on_first_half_not_full_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The winner's-curse core assertion. Full-window numbers say NGR (+10 vs
    +2.5); the FIRST half says RAW (+5 vs -5). The router must pick RAW —
    this test fails on the old same-window selection."""
    config_path = _patch_paths(monkeypatch, tmp_path)
    _write(
        tmp_path / "backtest_manifest.json",
        {"stations": {"KAUS": _station_summary(full_window_vs_ndfd=10.0, per_month=_NGR_MONTHS)}},
    )
    _write(
        tmp_path / "backtest_all_raw_manifest.json",
        {"stations": {"KAUS": _station_summary(full_window_vs_ndfd=2.5, per_month=_RAW_MONTHS)}},
    )

    decide_router.main(mode="ndfd_aware")

    data = json.loads(config_path.read_text(encoding="utf-8"))
    decision = data["decisions"]["KAUS"]
    assert decision["strategy"] == "raw"
    # Selection values stored are the FIRST-half numbers.
    assert decision["ngr_vs_ndfd_pct"] == pytest.approx(-5.0, abs=0.01)
    assert decision["raw_vs_ndfd_pct"] == pytest.approx(5.0, abs=0.01)


def test_decide_router_reports_honest_second_half_oos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The chosen strategy's SECOND-half performance is the honest OOS number:
    in the reason string and in the selection_protocol block."""
    config_path = _patch_paths(monkeypatch, tmp_path)
    _write(
        tmp_path / "backtest_manifest.json",
        {"stations": {"KAUS": _station_summary(full_window_vs_ndfd=10.0, per_month=_NGR_MONTHS)}},
    )
    _write(
        tmp_path / "backtest_all_raw_manifest.json",
        {"stations": {"KAUS": _station_summary(full_window_vs_ndfd=2.5, per_month=_RAW_MONTHS)}},
    )

    decide_router.main(mode="ndfd_aware")

    data = json.loads(config_path.read_text(encoding="utf-8"))
    reason = data["decisions"]["KAUS"]["reason"]
    assert "winner's-curse guard" in reason
    assert "selected on first-half window" in reason
    # RAW chosen; its second half is exactly 0.00%.
    assert "+0.00%" in reason
    protocol = data["selection_protocol"]
    assert protocol["method"] == "split_window_v1"
    station_block = protocol["stations"]["KAUS"]
    assert station_block["split_applied"] is True
    assert station_block["honest_oos_second_half_vs_ndfd_pct"] == pytest.approx(0.0)
    assert station_block["second_half_months"] == "2025-03..2025-04"
    # Nested-CV out-of-scope note is documented, not silently absent.
    assert "out of scope" in protocol["description"]


def test_decide_router_flags_stations_without_split_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No per-month NDFD diagnostics → full-window selection, honestly flagged."""
    config_path = _patch_paths(monkeypatch, tmp_path)
    _write(
        tmp_path / "backtest_manifest.json",
        {"stations": {"KMIA": _station_summary(full_window_vs_ndfd=10.0, per_month=None)}},
    )
    _write(
        tmp_path / "backtest_all_raw_manifest.json",
        {"stations": {"KMIA": _station_summary(full_window_vs_ndfd=2.5, per_month=None)}},
    )

    decide_router.main(mode="ndfd_aware")

    data = json.loads(config_path.read_text(encoding="utf-8"))
    decision = data["decisions"]["KMIA"]
    assert decision["strategy"] == "ngr"  # full-window rule applies unchanged
    assert "split-window selection unavailable" in decision["reason"]
    assert data["selection_protocol"]["stations"]["KMIA"]["split_applied"] is False


def test_decide_router_legacy_mode_never_claims_first_half_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Legacy mode selects on brier_improvement_pct (vs the naive market),
    which has no per-month breakdown — reasons must NOT claim a first-half
    selection even when NDFD per-month diagnostics happen to exist."""
    config_path = _patch_paths(monkeypatch, tmp_path)
    _write(
        tmp_path / "backtest_manifest.json",
        {"stations": {"KAUS": _station_summary(full_window_vs_ndfd=10.0, per_month=_NGR_MONTHS)}},
    )

    decide_router.main(mode="legacy")

    data = json.loads(config_path.read_text(encoding="utf-8"))
    reason = data["decisions"]["KAUS"]["reason"]
    assert "selected on first-half window" not in reason
    assert "split-window selection unavailable" in reason


def test_decide_router_writes_config_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Temp sibling is renamed away and the result is valid JSON that
    StrategyRouterConfig can round-trip (extra selection_protocol key is
    ignored by from_dict)."""
    config_path = _patch_paths(monkeypatch, tmp_path)
    _write(
        tmp_path / "backtest_manifest.json",
        {"stations": {"KAUS": _station_summary(full_window_vs_ndfd=10.0, per_month=_NGR_MONTHS)}},
    )
    _write(
        tmp_path / "backtest_all_raw_manifest.json",
        {"stations": {"KAUS": _station_summary(full_window_vs_ndfd=2.5, per_month=_RAW_MONTHS)}},
    )

    decide_router.main(mode="ndfd_aware")

    assert not (tmp_path / "router_config.json.tmp").exists()
    cfg = StrategyRouterConfig.load(config_path)
    assert cfg.strategy_for("KAUS") == "raw"
