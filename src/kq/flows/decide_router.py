"""Generate `models/router_config.json` from the latest backtest + training manifests.

Usage:
    `kq decide-router` (or `python -m kq.flows.decide_router`)

Reads `models/backtest_manifest.json` + `models/manifest.json`, applies the
decision rule from `kq.models.router.decide_strategies_from_manifest`, and
writes `models/router_config.json` (committed). Run this AFTER any
`kq backtest` to refresh the routing.
"""

from __future__ import annotations

import json

import structlog

from kq.config import REPO_ROOT
from kq.models.router import (
    MIN_BRIER_IMPROVEMENT_PCT,
    decide_strategies_from_manifest,
)

log = structlog.get_logger(__name__)

MODELS_DIR = REPO_ROOT / "models"
TRAINING_MANIFEST = MODELS_DIR / "manifest.json"
BACKTEST_MANIFEST = MODELS_DIR / "backtest_manifest.json"
ROUTER_CONFIG = MODELS_DIR / "router_config.json"


def main(*, threshold_pct: float = MIN_BRIER_IMPROVEMENT_PCT) -> None:
    """`python -m kq decide-router` entrypoint."""
    if not BACKTEST_MANIFEST.exists():
        raise SystemExit(
            f"backtest manifest not found at {BACKTEST_MANIFEST}; "
            "run `make backtest STRATEGY=weather_v1` first"
        )
    backtest = json.loads(BACKTEST_MANIFEST.read_text(encoding="utf-8"))
    training = (
        json.loads(TRAINING_MANIFEST.read_text(encoding="utf-8"))
        if TRAINING_MANIFEST.exists()
        else None
    )

    cfg = decide_strategies_from_manifest(
        backtest_manifest=backtest,
        training_manifest=training,
        threshold_pct=threshold_pct,
    )
    cfg.save(ROUTER_CONFIG)

    log.info(
        "router.decided",
        threshold_pct=threshold_pct,
        n_stations=len(cfg.decisions),
        config=str(ROUTER_CONFIG),
    )
    print(f"router config written to {ROUTER_CONFIG}")
    for station, decision in sorted(cfg.decisions.items()):
        print(
            f"  {station}: {decision.strategy:>3}  "
            f"(brier improvement {decision.brier_improvement_pct:+.2f}%)  "
            f"sigma={decision.raw_residual_std_f:.2f}F"
        )


def _entrypoint(threshold_pct_str: str = "1.0") -> None:
    """Helper to allow CLI argparse parity without bringing in typer here."""
    main(threshold_pct=float(threshold_pct_str))


if __name__ == "__main__":  # pragma: no cover
    main()
