"""Run-backtest flow + manifest emission.

Loads trained models from `models/`, runs the backtest engine across every
station with a fit, and writes a sibling `models/backtest_manifest.json`
(committed) summarizing the results — same pattern as `manifest.json`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from kq.backtest.engine import BacktestConfig, run_backtest
from kq.config import REPO_ROOT, get_settings
from kq.flows.ingest_weather import _db_path_from_settings

log = structlog.get_logger(__name__)

MODELS_DIR = REPO_ROOT / "models"
BACKTEST_MANIFEST_PATH = MODELS_DIR / "backtest_manifest.json"
ROUTER_BACKTEST_MANIFEST_PATH = MODELS_DIR / "backtest_router_manifest.json"
ALL_RAW_BACKTEST_MANIFEST_PATH = MODELS_DIR / "backtest_all_raw_manifest.json"
REFORECAST_BACKTEST_MANIFEST_PATH = MODELS_DIR / "backtest_reforecast_manifest.json"
ANALOG_BACKTEST_MANIFEST_PATH = MODELS_DIR / "backtest_analog_manifest.json"


def _manifest_path_for(strategy: str) -> Path:
    if strategy == "weather_router_v1":
        return ROUTER_BACKTEST_MANIFEST_PATH
    if strategy == "weather_all_raw_v1":
        return ALL_RAW_BACKTEST_MANIFEST_PATH
    if strategy == "weather_reforecast_v1":
        return REFORECAST_BACKTEST_MANIFEST_PATH
    if strategy == "weather_analog_v1":
        return ANALOG_BACKTEST_MANIFEST_PATH
    return BACKTEST_MANIFEST_PATH


def main(*, strategy: str = "weather_v1") -> None:
    """`python -m kq backtest --strategy weather_v1` entrypoint."""
    settings = get_settings()
    db_path = _db_path_from_settings(settings.database_url)
    cfg = BacktestConfig()

    log.info("backtest.starting", strategy=strategy, db=str(db_path))
    results = run_backtest(
        db_path=db_path,
        strategy=strategy,
        config=cfg,
    )

    manifest: dict[str, Any] = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "strategy": strategy,
        "evaluation": "rolling_origin_cv",
        "config": {
            "starting_bankroll_usd": cfg.starting_bankroll_usd,
            "min_edge_pct": cfg.min_edge_pct,
            "kelly_fraction": cfg.kelly_fraction,
            "max_stake_usd": cfg.max_stake_usd,
            "n_brackets": cfg.n_brackets,
            "bracket_spacing_f": cfg.bracket_spacing_f,
            "lead_days": cfg.lead_days,
            "initial_train_size": cfg.initial_train_size,
            "test_window_size": cfg.test_window_size,
        },
        "honest_caveats": [
            "Naive synthetic market (no historical Kalshi prices archive); P&L is "
            "an UPPER BOUND vs what real Kalshi market makers would price.",
            "P&L assumes the model can always trade at the displayed bid/ask; real "
            "fills are subject to liquidity + queue position.",
            "Brier improvement is the more invariant metric than P&L when comparing "
            "across stations.",
            "brier_ndfd is computed against NBM-deterministic Tmax wrapped in a "
            "per-fold-fitted Gaussian sigma (not true NBM probabilistic qmd). "
            "See docs/research/NDFD-BENCHMARK-SOURCE.md for the source decision "
            "and the upgrade path. Phase 5 readiness criterion #2 should be "
            "re-checked against true qmd before going live.",
            "n_evaluated_with_ndfd may be < n_evaluated because Open-Meteo's NBM "
            "history starts ~2024-11; pre-archive folds carry NaN.",
        ],
        "stations": {station: r.to_summary_dict() for station, r in results.items()},
    }
    out_path = _manifest_path_for(strategy)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    log.info("backtest.done", stations=len(results), manifest=str(out_path))

    print(f"backtested {len(results)} stations, manifest -> {out_path}")
    for station, summary in manifest["stations"].items():
        ndfd_pct = summary.get("brier_improvement_vs_ndfd_pct")
        n_ndfd = summary.get("n_evaluated_with_ndfd", 0)
        ndfd_chunk = (
            f"  vs_ndfd={ndfd_pct:+.1f}% (n={n_ndfd})" if ndfd_pct is not None else "  vs_ndfd=n/a"
        )
        print(
            f"  {station}: "
            f"trades={summary['n_traded']:>4}/{summary['n_evaluated']:<5}  "
            f"pnl=${summary['total_pnl_usd']:>+8.2f}  "
            f"roi={summary['roi_pct']:>+6.2f}%  "
            f"win_rate={summary['win_rate']:.2%}  "
            f"dd={summary['max_drawdown_pct']:>5.2f}%  "
            f"brier_cal={summary['brier_calibrated']:.4f} "
            f"vs_raw={summary['brier_raw']:.4f} "
            f"({summary['brier_improvement_pct']:+.1f}%)" + ndfd_chunk
        )


if __name__ == "__main__":
    main()
