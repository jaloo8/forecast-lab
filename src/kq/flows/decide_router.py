"""Generate `models/router_config.json` from the latest backtest manifests.

Usage:
    `kq decide-router [--mode {ndfd_aware,calibration_aware,legacy}]`

**Three decision modes:**

1. **calibration_aware (Phase 5 #3-aware):** reads all four manifests
   plus the n-aware reliability summary on each. Per station, prefers a
   strategy whose ``reliability_summary.passes_bar`` is True among
   {ngr, raw, reforecast}, picking the highest Brier-vs-NDFD within
   that calibration-passing set. Falls back to NDFD-aware if no
   strategy passes calibration, or if the best-calibration strategy
   trails the overall best Brier-vs-NDFD by more than
   ``CALIBRATION_AWARE_BRIER_TOLERANCE_PP`` (default 5pp).

2. **ndfd_aware (preferred when both manifests exist):** reads
   ``backtest_manifest.json`` (all-NGR via ``--strategy weather_v1``) AND
   ``backtest_all_raw_manifest.json`` (all-RAW via
   ``--strategy weather_all_raw_v1``), compares per-station NGR-vs-NDFD
   against RAW-vs-NDFD, picks the strategy with the better gate-aligned
   Brier improvement. Addresses the post-#15 audit finding that the
   legacy rule (vs synthetic raw market) can disagree with our gate
   criterion (vs NDFD).

3. **legacy fallback:** when only the all-NGR manifest is present,
   uses ``brier_improvement_pct`` (vs synthetic naive market) as before.

Run order to enable the calibration-aware path:

    $ kq backtest --strategy weather_v1
    $ kq backtest --strategy weather_all_raw_v1
    $ kq backtest --strategy weather_reforecast_v1
    $ kq decide-router --mode calibration_aware
"""

from __future__ import annotations

import json
from typing import Literal

import structlog

from kq.config import REPO_ROOT
from kq.models.router import (
    CALIBRATION_AWARE_BRIER_TOLERANCE_PP,
    MIN_BRIER_IMPROVEMENT_PCT,
    StrategyRouterConfig,
    decide_strategies_calibration_aware,
    decide_strategies_from_manifest,
    decide_strategies_ndfd_aware,
)

log = structlog.get_logger(__name__)

Mode = Literal["calibration_aware", "ndfd_aware", "legacy", "auto"]

MODELS_DIR = REPO_ROOT / "models"
TRAINING_MANIFEST = MODELS_DIR / "manifest.json"
BACKTEST_MANIFEST = MODELS_DIR / "backtest_manifest.json"
ALL_RAW_BACKTEST_MANIFEST = MODELS_DIR / "backtest_all_raw_manifest.json"
REFORECAST_BACKTEST_MANIFEST = MODELS_DIR / "backtest_reforecast_manifest.json"
ROUTER_CONFIG = MODELS_DIR / "router_config.json"


def _load_manifests() -> tuple[
    dict[str, object], dict[str, object] | None, dict[str, object] | None, dict[str, object] | None
]:
    """Read every manifest under `MODELS_DIR`. Missing optional manifests
    return None — only the all-NGR manifest is required."""
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
    all_raw = (
        json.loads(ALL_RAW_BACKTEST_MANIFEST.read_text(encoding="utf-8"))
        if ALL_RAW_BACKTEST_MANIFEST.exists()
        else None
    )
    reforecast = (
        json.loads(REFORECAST_BACKTEST_MANIFEST.read_text(encoding="utf-8"))
        if REFORECAST_BACKTEST_MANIFEST.exists()
        else None
    )
    return backtest, training, all_raw, reforecast


def _resolve_mode(
    requested: Mode,
    all_raw: dict[str, object] | None,
    reforecast: dict[str, object] | None,
) -> Mode:
    """Resolve `auto` to the strongest available mode given which manifests
    exist; returns the requested value unchanged for explicit modes."""
    if requested != "auto":
        return requested
    if all_raw is not None and reforecast is not None:
        return "calibration_aware"
    if all_raw is not None:
        return "ndfd_aware"
    return "legacy"


def main(
    *,
    threshold_pct: float = MIN_BRIER_IMPROVEMENT_PCT,
    mode: Mode = "auto",
    brier_tolerance_pp: float = CALIBRATION_AWARE_BRIER_TOLERANCE_PP,
) -> None:
    """`python -m kq decide-router` entrypoint.

    `mode='auto'` picks the most powerful mode whose manifests exist:
    calibration_aware > ndfd_aware > legacy. Pass an explicit value to
    override (useful when comparing modes side-by-side).
    """
    backtest, training, all_raw, reforecast = _load_manifests()
    resolved_mode = _resolve_mode(mode, all_raw, reforecast)

    cfg: StrategyRouterConfig
    if resolved_mode == "calibration_aware":
        if all_raw is None or reforecast is None:
            raise SystemExit(
                "mode=calibration_aware requires both backtest_all_raw_manifest.json "
                "and backtest_reforecast_manifest.json; run "
                "`kq backtest --strategy weather_all_raw_v1` and "
                "`kq backtest --strategy weather_reforecast_v1` first"
            )
        cfg = decide_strategies_calibration_aware(
            all_ngr_manifest=backtest,
            all_raw_manifest=all_raw,
            reforecast_manifest=reforecast,
            training_manifest=training,
            threshold_pct=threshold_pct,
            brier_tolerance_pp=brier_tolerance_pp,
        )
    elif resolved_mode == "ndfd_aware":
        if all_raw is None:
            raise SystemExit(
                "mode=ndfd_aware requires backtest_all_raw_manifest.json; "
                "run `kq backtest --strategy weather_all_raw_v1` first"
            )
        cfg = decide_strategies_ndfd_aware(
            all_ngr_manifest=backtest,
            all_raw_manifest=all_raw,
            training_manifest=training,
            threshold_pct=threshold_pct,
        )
    else:
        cfg = decide_strategies_from_manifest(
            backtest_manifest=backtest,
            training_manifest=training,
            threshold_pct=threshold_pct,
        )

    cfg.save(ROUTER_CONFIG)

    log.info(
        "router.decided",
        mode=resolved_mode,
        threshold_pct=threshold_pct,
        n_stations=len(cfg.decisions),
        config=str(ROUTER_CONFIG),
    )
    print(f"router config written to {ROUTER_CONFIG} (mode={resolved_mode})")
    for station, decision in sorted(cfg.decisions.items()):
        print(_format_station_summary(station, decision))


def _format_station_summary(station: str, decision: object) -> str:
    """Pick the richest one-line summary based on which decision fields
    are populated. Calibration-aware decisions get the per-strategy grid;
    NDFD-aware get the NGR-vs-RAW pair; legacy get the Brier improvement."""
    # Avoid importing StationDecision at the module level just for the type
    # annotation — duck-type via attribute access here.
    ref_vs = getattr(decision, "reforecast_vs_ndfd_pct", None)
    ngr_vs = getattr(decision, "ngr_vs_ndfd_pct", None)
    raw_vs = getattr(decision, "raw_vs_ndfd_pct", None)
    sigma = getattr(decision, "raw_residual_std_f", 0.0)
    strat = getattr(decision, "strategy", "?")
    improvement = getattr(decision, "brier_improvement_pct", 0.0)

    if ref_vs is not None:
        return (
            f"  {station}: {strat:>10}  "
            f"(NGR {_fmt(ngr_vs)} | RAW {_fmt(raw_vs)} | reforecast {_fmt(ref_vs)})  "
            f"sigma={sigma:.2f}F"
        )
    if ngr_vs is not None and raw_vs is not None:
        return (
            f"  {station}: {strat:>10}  "
            f"(NGR vs NDFD {ngr_vs:+.2f}% / RAW vs NDFD {raw_vs:+.2f}%)  "
            f"sigma={sigma:.2f}F"
        )
    return f"  {station}: {strat:>10}  (brier improvement {improvement:+.2f}%)  sigma={sigma:.2f}F"


def _fmt(value: float | None) -> str:
    """Compact +/-pp format with em-dash for missing values."""
    return f"{value:+.2f}%" if value is not None else "—"


def _entrypoint(threshold_pct_str: str = "1.0") -> None:
    """Helper to allow CLI argparse parity without bringing in typer here."""
    main(threshold_pct=float(threshold_pct_str))


if __name__ == "__main__":  # pragma: no cover
    main()
