"""Generate `models/router_config.json` from the latest backtest manifests.

Usage:
    `kq decide-router` (or `python -m kq.flows.decide_router`)

**Two decision modes:**

1. **NDFD-aware (preferred when both manifests exist):** reads
   ``backtest_manifest.json`` (all-NGR via ``--strategy weather_v1``) AND
   ``backtest_all_raw_manifest.json`` (all-RAW via
   ``--strategy weather_all_raw_v1``), compares per-station NGR-vs-NDFD
   against RAW-vs-NDFD, picks the strategy with the better gate-aligned
   Brier improvement. Addresses the post-#15 audit finding that the
   legacy rule (vs synthetic raw market) can disagree with our gate
   criterion (vs NDFD).

2. **Legacy fallback:** when only the all-NGR manifest is present,
   uses ``brier_improvement_pct`` (vs synthetic naive market) as before.

Run order to enable the NDFD-aware path:

    $ kq backtest --strategy weather_v1
    $ kq backtest --strategy weather_all_raw_v1
    $ kq decide-router
"""

from __future__ import annotations

import json

import structlog

from kq.config import REPO_ROOT
from kq.models.router import (
    MIN_BRIER_IMPROVEMENT_PCT,
    StrategyRouterConfig,
    decide_strategies_from_manifest,
    decide_strategies_ndfd_aware,
)

log = structlog.get_logger(__name__)

MODELS_DIR = REPO_ROOT / "models"
TRAINING_MANIFEST = MODELS_DIR / "manifest.json"
BACKTEST_MANIFEST = MODELS_DIR / "backtest_manifest.json"
ALL_RAW_BACKTEST_MANIFEST = MODELS_DIR / "backtest_all_raw_manifest.json"
ROUTER_CONFIG = MODELS_DIR / "router_config.json"


def main(*, threshold_pct: float = MIN_BRIER_IMPROVEMENT_PCT) -> None:
    """`python -m kq decide-router` entrypoint."""
    if not BACKTEST_MANIFEST.exists():
        raise SystemExit(
            f"backtest manifest not found at {BACKTEST_MANIFEST}; "
            "run `kq backtest --strategy weather_v1` first"
        )
    backtest = json.loads(BACKTEST_MANIFEST.read_text(encoding="utf-8"))
    training = (
        json.loads(TRAINING_MANIFEST.read_text(encoding="utf-8"))
        if TRAINING_MANIFEST.exists()
        else None
    )

    cfg: StrategyRouterConfig
    if ALL_RAW_BACKTEST_MANIFEST.exists():
        all_raw = json.loads(ALL_RAW_BACKTEST_MANIFEST.read_text(encoding="utf-8"))
        cfg = decide_strategies_ndfd_aware(
            all_ngr_manifest=backtest,
            all_raw_manifest=all_raw,
            training_manifest=training,
            threshold_pct=threshold_pct,
        )
        mode = "ndfd_aware"
    else:
        cfg = decide_strategies_from_manifest(
            backtest_manifest=backtest,
            training_manifest=training,
            threshold_pct=threshold_pct,
        )
        mode = "legacy"

    cfg.save(ROUTER_CONFIG)

    log.info(
        "router.decided",
        mode=mode,
        threshold_pct=threshold_pct,
        n_stations=len(cfg.decisions),
        config=str(ROUTER_CONFIG),
    )
    print(f"router config written to {ROUTER_CONFIG} (mode={mode})")
    for station, decision in sorted(cfg.decisions.items()):
        if decision.ngr_vs_ndfd_pct is not None and decision.raw_vs_ndfd_pct is not None:
            print(
                f"  {station}: {decision.strategy:>3}  "
                f"(NGR vs NDFD {decision.ngr_vs_ndfd_pct:+.2f}% / "
                f"RAW vs NDFD {decision.raw_vs_ndfd_pct:+.2f}%)  "
                f"sigma={decision.raw_residual_std_f:.2f}F"
            )
        else:
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
