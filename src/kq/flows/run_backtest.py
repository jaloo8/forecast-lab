"""Run-backtest flow + manifest emission.

Loads trained models from `models/`, runs the backtest engine across every
station with a fit, and writes a sibling `models/backtest_manifest.json`
(committed) summarizing the results — same pattern as `manifest.json`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import structlog

from kq.backtest.engine import BacktestConfig, run_backtest
from kq.config import REPO_ROOT, get_settings
from kq.flows.ingest_weather import _db_path_from_settings

log = structlog.get_logger(__name__)

MODELS_DIR = REPO_ROOT / "models"
BACKTEST_MANIFEST_PATH = MODELS_DIR / "backtest_manifest.json"


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
        ],
        "stations": {station: r.to_summary_dict() for station, r in results.items()},
    }
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with BACKTEST_MANIFEST_PATH.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    log.info("backtest.done", stations=len(results), manifest=str(BACKTEST_MANIFEST_PATH))

    print(f"backtested {len(results)} stations, manifest -> {BACKTEST_MANIFEST_PATH}")
    for station, summary in manifest["stations"].items():
        print(
            f"  {station}: "
            f"trades={summary['n_traded']:>4}/{summary['n_evaluated']:<5}  "
            f"pnl=${summary['total_pnl_usd']:>+8.2f}  "
            f"roi={summary['roi_pct']:>+6.2f}%  "
            f"win_rate={summary['win_rate']:.2%}  "
            f"dd={summary['max_drawdown_pct']:>5.2f}%  "
            f"brier_cal={summary['brier_calibrated']:.4f} "
            f"vs_raw={summary['brier_raw']:.4f} "
            f"({summary['brier_improvement_pct']:+.1f}%)"
        )


if __name__ == "__main__":
    main()
