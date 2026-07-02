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

**Winner's-curse guard (2026-07-01 audit, Tier 2).** Selecting the
per-station strategy on the SAME window it is then reported on inflates
the reported skill of whichever strategy got lucky (in-sample selection
reported as OOS). Minimal honest fix implemented here: the manifest
window is split chronologically in half using each station's
``diagnostics.per_month`` rows — the strategy is SELECTED on first-half
Brier-vs-NDFD, and the chosen strategy's SECOND-half Brier-vs-NDFD is
reported as the honest OOS number (appended to each decision's
``reason`` and recorded in the ``selection_protocol`` block of
``router_config.json``). Stations without >= 2 NDFD-covered months fall
back to full-window selection and are flagged. A full nested-CV
redesign (selection re-run inside every outer fold) is deliberately OUT
OF SCOPE for this fix — it requires the engine to emit per-fold
manifests. The n-aware calibration bar (``passes_bar``) also remains a
whole-window statistic; only the Brier-vs-NDFD selection metric is
split.
"""

from __future__ import annotations

import dataclasses
import json
import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import structlog

from kq.config import REPO_ROOT
from kq.models.router import (
    CALIBRATION_AWARE_BRIER_TOLERANCE_PP,
    MIN_BRIER_IMPROVEMENT_PCT,
    Strategy,
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


@dataclass(frozen=True, slots=True)
class SplitWindowStats:
    """First/second-half Brier-vs-NDFD for one (manifest, station) pair."""

    first_half_vs_ndfd_pct: float
    second_half_vs_ndfd_pct: float | None
    first_half_months: str  # "2025-01..2025-03"
    second_half_months: str
    n_first: int
    n_second: int


def _half_vs_ndfd_pct(rows: list[dict[str, Any]]) -> float | None:
    """n-weighted Brier-vs-NDFD improvement (%) over per-month rows."""
    n_total = sum(int(r["n_with_ndfd"]) for r in rows)
    if n_total <= 0:
        return None
    brier_model = sum(float(r["brier_model_subset"]) * int(r["n_with_ndfd"]) for r in rows)
    brier_ndfd = sum(float(r["brier_ndfd"]) * int(r["n_with_ndfd"]) for r in rows)
    brier_model /= n_total
    brier_ndfd /= n_total
    if brier_ndfd <= 0:
        return None
    return (brier_ndfd - brier_model) / brier_ndfd * 100.0


def _station_split_stats(summary: dict[str, Any]) -> SplitWindowStats | None:
    """Chronological half-split of one station's per-month NDFD diagnostics.

    Returns None when the manifest lacks >= 2 NDFD-covered months (the
    per-month diagnostics are the only per-period breakdown the committed
    manifests carry, so the split granularity is monthly).
    """
    diagnostics = summary.get("diagnostics") or {}
    per_month = [
        r
        for r in (diagnostics.get("per_month") or [])
        if int(r.get("n_with_ndfd", 0)) > 0
        and r.get("brier_model_subset") is not None
        and r.get("brier_ndfd") is not None
    ]
    if len(per_month) < 2:
        return None
    per_month.sort(key=lambda r: str(r["month"]))
    k = (len(per_month) + 1) // 2
    first, second = per_month[:k], per_month[k:]
    first_pct = _half_vs_ndfd_pct(first)
    second_pct = _half_vs_ndfd_pct(second)
    if first_pct is None:
        return None
    return SplitWindowStats(
        first_half_vs_ndfd_pct=first_pct,
        second_half_vs_ndfd_pct=second_pct,
        first_half_months=f"{first[0]['month']}..{first[-1]['month']}",
        second_half_months=f"{second[0]['month']}..{second[-1]['month']}",
        n_first=sum(int(r["n_with_ndfd"]) for r in first),
        n_second=sum(int(r["n_with_ndfd"]) for r in second),
    )


def _split_stats_by_station(
    manifest: dict[str, Any] | None,
) -> dict[str, SplitWindowStats]:
    if manifest is None:
        return {}
    out: dict[str, SplitWindowStats] = {}
    for station, summary in (manifest.get("stations") or {}).items():
        stats = _station_split_stats(summary)
        if stats is not None:
            out[station] = stats
    return out


def _selection_manifest(
    manifest: dict[str, Any],
    split_stats: dict[str, SplitWindowStats],
) -> dict[str, Any]:
    """Copy of ``manifest`` whose per-station ``brier_improvement_vs_ndfd_pct``
    is replaced by the FIRST-half value wherever the split is computable.

    The decision functions in ``kq.models.router`` then run unchanged on
    the selection window; stations without split stats keep their
    full-window value (flagged in the selection protocol)."""
    selection = deepcopy(manifest)
    for station, stats in split_stats.items():
        summary = (selection.get("stations") or {}).get(station)
        if summary is not None:
            summary["brier_improvement_vs_ndfd_pct"] = round(stats.first_half_vs_ndfd_pct, 4)
    return selection


def _apply_honest_oos_annotations(
    cfg: StrategyRouterConfig,
    split_by_strategy: dict[Strategy, dict[str, SplitWindowStats]],
) -> dict[str, dict[str, Any]]:
    """Append the honest second-half OOS number to every decision's reason.

    Mutates ``cfg.decisions`` in place (rebuilding the frozen
    ``StationDecision`` entries) and returns the per-station
    ``selection_protocol`` payload for the router config JSON.
    """
    protocol_stations: dict[str, dict[str, Any]] = {}
    for station, decision in sorted(cfg.decisions.items()):
        stats = split_by_strategy.get(decision.strategy, {}).get(station)
        if stats is not None and stats.second_half_vs_ndfd_pct is not None:
            suffix = (
                f" | winner's-curse guard: selected on first-half window "
                f"({stats.first_half_months}, n={stats.n_first}); honest OOS "
                f"second-half ({stats.second_half_months}, n={stats.n_second}) "
                f"vs NDFD: {stats.second_half_vs_ndfd_pct:+.2f}%"
            )
            protocol_stations[station] = {
                "split_applied": True,
                "selected_on_months": stats.first_half_months,
                "honest_oos_second_half_vs_ndfd_pct": round(stats.second_half_vs_ndfd_pct, 3),
                "second_half_months": stats.second_half_months,
                "n_second_half": stats.n_second,
            }
        else:
            suffix = (
                " | winner's-curse guard: split-window selection unavailable "
                "(insufficient per-month NDFD diagnostics for the chosen "
                "strategy); selected on full window — treat the headline "
                "number as in-sample-selected"
            )
            protocol_stations[station] = {
                "split_applied": False,
                "honest_oos_second_half_vs_ndfd_pct": None,
            }
        cfg.decisions[station] = dataclasses.replace(decision, reason=decision.reason + suffix)
    return protocol_stations


def _save_router_config_atomic(
    path: Path,
    cfg: StrategyRouterConfig,
    selection_protocol: dict[str, Any],
) -> None:
    """Serialize config + selection protocol via temp file + atomic rename."""
    data = cfg.to_dict()
    data["selection_protocol"] = selection_protocol
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)


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

    Winner's-curse guard: strategies are selected on the FIRST half of
    each manifest's per-month window; the chosen strategy's SECOND-half
    performance is reported as the honest OOS number (see module
    docstring; full nested CV is out of scope).
    """
    backtest, training, all_raw, reforecast = _load_manifests()
    resolved_mode = _resolve_mode(mode, all_raw, reforecast)

    # Split each manifest's per-station window in half: select on the first
    # half, report on the second (2026-07-01 audit, Tier 2). The decision
    # functions below receive "selection manifests" whose vs-NDFD numbers
    # are first-half only.
    split_by_strategy: dict[Strategy, dict[str, SplitWindowStats]] = {
        "ngr": _split_stats_by_station(backtest),
        "raw": _split_stats_by_station(all_raw),
        "reforecast": _split_stats_by_station(reforecast),
    }
    backtest_sel = _selection_manifest(backtest, split_by_strategy["ngr"])
    all_raw_sel = (
        _selection_manifest(all_raw, split_by_strategy["raw"]) if all_raw is not None else None
    )
    reforecast_sel = (
        _selection_manifest(reforecast, split_by_strategy["reforecast"])
        if reforecast is not None
        else None
    )

    cfg: StrategyRouterConfig
    if resolved_mode == "calibration_aware":
        if all_raw_sel is None or reforecast_sel is None:
            raise SystemExit(
                "mode=calibration_aware requires both backtest_all_raw_manifest.json "
                "and backtest_reforecast_manifest.json; run "
                "`kq backtest --strategy weather_all_raw_v1` and "
                "`kq backtest --strategy weather_reforecast_v1` first"
            )
        cfg = decide_strategies_calibration_aware(
            all_ngr_manifest=backtest_sel,
            all_raw_manifest=all_raw_sel,
            reforecast_manifest=reforecast_sel,
            training_manifest=training,
            threshold_pct=threshold_pct,
            brier_tolerance_pp=brier_tolerance_pp,
        )
    elif resolved_mode == "ndfd_aware":
        if all_raw_sel is None:
            raise SystemExit(
                "mode=ndfd_aware requires backtest_all_raw_manifest.json; "
                "run `kq backtest --strategy weather_all_raw_v1` first"
            )
        cfg = decide_strategies_ndfd_aware(
            all_ngr_manifest=backtest_sel,
            all_raw_manifest=all_raw_sel,
            training_manifest=training,
            threshold_pct=threshold_pct,
        )
    else:
        # Legacy mode selects on `brier_improvement_pct` (vs the synthetic
        # naive market), which has no per-month breakdown in the manifest —
        # the split guard cannot apply, and each reason says so (the empty
        # split dict below routes every station to the "unavailable" note).
        cfg = decide_strategies_from_manifest(
            backtest_manifest=backtest_sel,
            training_manifest=training,
            threshold_pct=threshold_pct,
        )

    annotation_split = split_by_strategy if resolved_mode != "legacy" else {}
    protocol_stations = _apply_honest_oos_annotations(cfg, annotation_split)
    selection_protocol: dict[str, Any] = {
        "method": "split_window_v1",
        "description": (
            "Per-station strategy SELECTED on the first half of the manifest's "
            "per-month NDFD-covered window; each decision's reason reports the "
            "chosen strategy's second-half Brier-vs-NDFD as the honest OOS "
            "number. Decisions' *_vs_ndfd_pct fields hold the first-half "
            "(selection) values where split_applied is true. Calibration "
            "passes_bar remains whole-window. Full nested-CV redesign "
            "deliberately out of scope (2026-07-01 audit, Tier 2)."
        ),
        "stations": protocol_stations,
    }
    _save_router_config_atomic(ROUTER_CONFIG, cfg, selection_protocol)

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
