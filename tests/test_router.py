"""Tests for RawForecastModel + StrategyRouter + decide_strategies_from_manifest."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from kq.models.raw_forecast import (
    PROB_CLIP_HIGH,
    PROB_CLIP_LOW,
    RawForecastModel,
)
from kq.models.router import (
    DEFAULT_RAW_SIGMA_F,
    MIN_BRIER_IMPROVEMENT_PCT,
    StationDecision,
    StrategyRouter,
    StrategyRouterConfig,
    decide_strategies_from_manifest,
    decide_strategies_ndfd_aware,
)
from kq.models.weather_ngr import NGRParameters, WeatherNGRModel

# ----------------------------------------------------------- RawForecastModel


def test_raw_predict_distribution_returns_fixed_sigma() -> None:
    m = RawForecastModel(raw_sigma_f=2.5)
    mu, sigma = m.predict_distribution(np.array([70.0, 80.0]))
    assert mu.tolist() == [70.0, 80.0]
    assert sigma.tolist() == [2.5, 2.5]


def test_raw_predict_proba_clipped() -> None:
    m = RawForecastModel(raw_sigma_f=1.0)
    p_low = m.predict_proba(np.array([70.0]), threshold=100.0)
    p_high = m.predict_proba(np.array([70.0]), threshold=0.0)
    assert p_low == pytest.approx(PROB_CLIP_LOW)
    assert p_high == pytest.approx(PROB_CLIP_HIGH)


def test_raw_predict_proba_monotone_in_threshold() -> None:
    m = RawForecastModel(raw_sigma_f=2.0)
    forecast = np.array([70.0])
    probs = [float(m.predict_proba(forecast, t)[0]) for t in [68.0, 70.0, 72.0]]
    assert probs == sorted(probs, reverse=True)


def test_raw_rejects_tiny_sigma() -> None:
    with pytest.raises(ValueError, match="raw_sigma_f"):
        RawForecastModel(raw_sigma_f=0.1)


# --------------------------------------------------- decide_strategies_from_manifest


def _bt_manifest(stations: dict[str, float]) -> dict:
    return {"stations": {s: {"brier_improvement_pct": v} for s, v in stations.items()}}


def _train_manifest(stations: dict[str, float]) -> dict:
    return {
        "stations": {
            s: {"fit_metadata": {"raw_residual_std": sigma}} for s, sigma in stations.items()
        }
    }


def test_decide_picks_ngr_above_threshold() -> None:
    bt = _bt_manifest({"KJFK": 20.1, "KAUS": 2.9, "KLAX": -7.5, "KMIA": -7.8})
    train = _train_manifest({"KJFK": 2.2, "KAUS": 3.0, "KLAX": 1.36, "KMIA": 1.31})
    cfg = decide_strategies_from_manifest(bt, train, threshold_pct=1.0)
    assert cfg.strategy_for("KJFK") == "ngr"
    assert cfg.strategy_for("KAUS") == "ngr"
    assert cfg.strategy_for("KLAX") == "raw"
    assert cfg.strategy_for("KMIA") == "raw"


def test_decide_threshold_inclusive() -> None:
    """Improvement EXACTLY equal to the threshold should pick NGR (>=)."""
    bt = _bt_manifest({"KAAA": 1.0})
    cfg = decide_strategies_from_manifest(bt, threshold_pct=1.0)
    assert cfg.strategy_for("KAAA") == "ngr"


def test_decide_default_threshold() -> None:
    bt = _bt_manifest({"KAAA": 0.5})  # below default 1.0
    cfg = decide_strategies_from_manifest(bt)
    assert cfg.decision_threshold_pct == MIN_BRIER_IMPROVEMENT_PCT
    assert cfg.strategy_for("KAAA") == "raw"


def test_decide_uses_default_sigma_when_training_missing() -> None:
    bt = _bt_manifest({"KAAA": 5.0})
    cfg = decide_strategies_from_manifest(bt, training_manifest=None)
    assert cfg.decisions["KAAA"].raw_residual_std_f == DEFAULT_RAW_SIGMA_F


def test_decide_records_reason_text() -> None:
    bt = _bt_manifest({"KJFK": 20.1, "KMIA": -7.8})
    cfg = decide_strategies_from_manifest(bt, threshold_pct=1.0)
    assert "keep calibration" in cfg.decisions["KJFK"].reason
    assert "raw forecast wins" in cfg.decisions["KMIA"].reason


# --------------------------------------------------- decide_strategies_ndfd_aware


def _bt_manifest_with_ndfd(stations: dict[str, dict[str, float]]) -> dict:
    """Build manifest where each station has the keys we need for NDFD logic."""
    return {
        "stations": {
            s: {
                "brier_improvement_pct": v.get("brier_vs_raw", 0.0),
                "brier_improvement_vs_ndfd_pct": v.get("brier_vs_ndfd"),
            }
            for s, v in stations.items()
        }
    }


def test_ndfd_aware_picks_strategy_with_better_ndfd_improvement() -> None:
    """At a given station, the strategy with higher NGR-vs-NDFD wins above threshold."""
    # KJFK: NGR clearly better. KMDW: RAW clearly better (the audit case).
    all_ngr = _bt_manifest_with_ndfd(
        {
            "KJFK": {"brier_vs_raw": 17.1, "brier_vs_ndfd": -2.0},
            "KMDW": {"brier_vs_raw": 6.2, "brier_vs_ndfd": -58.9},
        }
    )
    all_raw = _bt_manifest_with_ndfd(
        {
            "KJFK": {"brier_vs_raw": 0.0, "brier_vs_ndfd": -10.0},
            "KMDW": {"brier_vs_raw": 0.0, "brier_vs_ndfd": -51.1},
        }
    )
    cfg = decide_strategies_ndfd_aware(
        all_ngr_manifest=all_ngr,
        all_raw_manifest=all_raw,
        threshold_pct=1.0,
    )
    # KJFK: NGR -2.0% > RAW -10.0% by 8pp → NGR wins.
    assert cfg.strategy_for("KJFK") == "ngr"
    # KMDW: NGR -58.9% < RAW -51.1% by 7.8pp → RAW wins.
    assert cfg.strategy_for("KMDW") == "raw"
    # Metadata recorded.
    assert cfg.decisions["KJFK"].ngr_vs_ndfd_pct == -2.0
    assert cfg.decisions["KMDW"].raw_vs_ndfd_pct == -51.1


def test_ndfd_aware_threshold_avoids_noise_flips() -> None:
    """NGR only wins if it's better than RAW by at least threshold pct."""
    # NGR is 0.5pp better than RAW — under default 1.0% threshold, RAW wins.
    all_ngr = _bt_manifest_with_ndfd({"KAUS": {"brier_vs_ndfd": -3.0}})
    all_raw = _bt_manifest_with_ndfd({"KAUS": {"brier_vs_ndfd": -3.5}})
    cfg = decide_strategies_ndfd_aware(
        all_ngr_manifest=all_ngr,
        all_raw_manifest=all_raw,
        threshold_pct=1.0,
    )
    assert cfg.strategy_for("KAUS") == "raw"
    # Bump threshold below the gap → NGR wins.
    cfg2 = decide_strategies_ndfd_aware(
        all_ngr_manifest=all_ngr,
        all_raw_manifest=all_raw,
        threshold_pct=0.3,
    )
    assert cfg2.strategy_for("KAUS") == "ngr"


def test_ndfd_aware_falls_back_to_legacy_when_ndfd_missing() -> None:
    """If either manifest lacks vs-NDFD data, use legacy brier_improvement_pct rule."""
    all_ngr = _bt_manifest_with_ndfd(
        {"KAUS": {"brier_vs_raw": 5.0}}  # no brier_vs_ndfd
    )
    all_raw = _bt_manifest_with_ndfd({"KAUS": {"brier_vs_raw": 0.0}})
    cfg = decide_strategies_ndfd_aware(
        all_ngr_manifest=all_ngr,
        all_raw_manifest=all_raw,
        threshold_pct=1.0,
    )
    # Falls back to legacy: NGR brier_vs_raw=5% >= 1% → NGR.
    assert cfg.strategy_for("KAUS") == "ngr"
    assert "NDFD data missing" in cfg.decisions["KAUS"].reason


def test_ndfd_aware_records_per_station_metadata() -> None:
    all_ngr = _bt_manifest_with_ndfd({"KJFK": {"brier_vs_ndfd": -2.0}})
    all_raw = _bt_manifest_with_ndfd({"KJFK": {"brier_vs_ndfd": -10.0}})
    cfg = decide_strategies_ndfd_aware(
        all_ngr_manifest=all_ngr,
        all_raw_manifest=all_raw,
    )
    d = cfg.decisions["KJFK"]
    assert d.ngr_vs_ndfd_pct == pytest.approx(-2.0)
    assert d.raw_vs_ndfd_pct == pytest.approx(-10.0)
    assert "NDFD-aware" in d.reason


def test_ndfd_aware_metadata_round_trips_through_json(tmp_path: Path) -> None:
    """Save+load a config built by the NDFD-aware path; metadata preserved."""
    all_ngr = _bt_manifest_with_ndfd({"KJFK": {"brier_vs_ndfd": -2.0}})
    all_raw = _bt_manifest_with_ndfd({"KJFK": {"brier_vs_ndfd": -10.0}})
    cfg = decide_strategies_ndfd_aware(all_ngr_manifest=all_ngr, all_raw_manifest=all_raw)
    path = tmp_path / "router.json"
    cfg.save(path)
    loaded = StrategyRouterConfig.load(path)
    assert loaded.decisions["KJFK"].ngr_vs_ndfd_pct == pytest.approx(-2.0)
    assert loaded.decisions["KJFK"].raw_vs_ndfd_pct == pytest.approx(-10.0)


def test_ndfd_aware_handles_missing_station_in_raw_manifest() -> None:
    """A station present in NGR but missing from RAW should fall back to legacy."""
    all_ngr = _bt_manifest_with_ndfd({"KAUS": {"brier_vs_raw": 3.0, "brier_vs_ndfd": -5.0}})
    all_raw = _bt_manifest_with_ndfd({})  # KAUS missing entirely
    cfg = decide_strategies_ndfd_aware(
        all_ngr_manifest=all_ngr,
        all_raw_manifest=all_raw,
        threshold_pct=1.0,
    )
    assert cfg.strategy_for("KAUS") == "ngr"  # legacy: 3% >= 1%
    assert "NDFD data missing" in cfg.decisions["KAUS"].reason


# ---------------------------------------------------- StrategyRouterConfig I/O


def test_config_round_trip_json(tmp_path: Path) -> None:
    cfg = StrategyRouterConfig(decision_threshold_pct=1.5, generated_at="2026-01-01T00:00:00Z")
    cfg.decisions["KLAX"] = StationDecision(
        station="KLAX",
        strategy="raw",
        brier_improvement_pct=-7.5,
        raw_residual_std_f=1.36,
        reason="raw forecast wins",
    )
    cfg.decisions["KJFK"] = StationDecision(
        station="KJFK",
        strategy="ngr",
        brier_improvement_pct=20.1,
        raw_residual_std_f=2.2,
        reason="keep calibration",
    )

    path = tmp_path / "router.json"
    cfg.save(path)
    loaded = StrategyRouterConfig.load(path)

    assert loaded.strategy_for("KLAX") == "raw"
    assert loaded.strategy_for("KJFK") == "ngr"
    assert loaded.decision_threshold_pct == 1.5
    # Sorted in the on-disk JSON for deterministic diffs
    on_disk = json.loads(path.read_text())
    assert list(on_disk["decisions"].keys()) == ["KJFK", "KLAX"]


def test_config_strategy_for_unknown_station_uses_default() -> None:
    cfg = StrategyRouterConfig()
    assert cfg.strategy_for("KZZZ") == "raw"
    assert cfg.strategy_for("KZZZ", default="ngr") == "ngr"


# ------------------------------------------------------------ StrategyRouter


def _save_ngr_pickle(out_dir: Path, station: str, lead_days: int = 1) -> None:
    import pickle  # noqa: PLC0415 — test-local

    out_dir.mkdir(parents=True, exist_ok=True)
    model = WeatherNGRModel(params=NGRParameters(a=-3.0, b=1.0, c=4.0, d=0.0))
    with (out_dir / f"weather_ngr_{station}_lead{lead_days}.pkl").open("wb") as fh:
        pickle.dump(model, fh)


def test_router_dispatches_ngr_vs_raw(tmp_path: Path) -> None:
    cfg = StrategyRouterConfig()
    cfg.decisions["KJFK"] = StationDecision(
        station="KJFK",
        strategy="ngr",
        brier_improvement_pct=20.0,
        raw_residual_std_f=2.0,
        reason="ngr wins",
    )
    cfg.decisions["KLAX"] = StationDecision(
        station="KLAX",
        strategy="raw",
        brier_improvement_pct=-7.0,
        raw_residual_std_f=1.5,
        reason="raw wins",
    )
    cfg_path = tmp_path / "router.json"
    cfg.save(cfg_path)

    models_dir = tmp_path / "models"
    _save_ngr_pickle(models_dir, "KJFK")

    router = StrategyRouter.from_disk(cfg_path, models_dir)

    # KJFK uses the NGR pickle — calibrated mean with `a=-3` shifts forecast down.
    forecast = np.array([75.0])
    p_jfk = router.predict_proba("KJFK", forecast, threshold=72.0)
    # P(T > 72 | T ~ N(75 - 3, 2)) = P(Z > 0) = 0.5
    assert p_jfk[0] == pytest.approx(0.5, abs=0.05)

    # KLAX uses raw with sigma=1.5; mean stays at 75 → P(T > 72) = high
    p_lax = router.predict_proba("KLAX", forecast, threshold=72.0)
    assert p_lax[0] > 0.95


def test_router_raises_when_pickle_missing(tmp_path: Path) -> None:
    cfg = StrategyRouterConfig()
    cfg.decisions["KJFK"] = StationDecision(
        station="KJFK",
        strategy="ngr",
        brier_improvement_pct=20.0,
        raw_residual_std_f=2.0,
        reason="ngr wins",
    )
    cfg_path = tmp_path / "router.json"
    cfg.save(cfg_path)

    with pytest.raises(FileNotFoundError, match="pickle not found"):
        StrategyRouter.from_disk(cfg_path, tmp_path / "models")


def test_router_strategy_for_pass_through() -> None:
    cfg = StrategyRouterConfig()
    cfg.decisions["KJFK"] = StationDecision(
        station="KJFK",
        strategy="ngr",
        brier_improvement_pct=20.0,
        raw_residual_std_f=2.0,
        reason="x",
    )
    router = StrategyRouter(config=cfg)
    assert router.strategy_for("KJFK") == "ngr"
