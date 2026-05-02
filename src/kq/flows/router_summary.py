"""Router summary — read-only view of the live trading config.

Run via ``kq router-summary`` to answer "what would I trade today, per
station, and why?". Reads ``models/router_config.json`` (the live decision
file produced by ``kq decide-router``) and the four backtest manifests
(``v1``, ``router_v1``, ``all_raw_v1``, ``reforecast_v1``) and emits a
flat per-station view + aggregate summary.

Designed for two consumers:

  * **Human inspection** — pretty-printed station-by-station table, safe
    to paste into a runbook or commit message.
  * **Cron / alerting** — ``--json`` emits a structured object so a
    watchdog can compare against thresholds (e.g. drift detection: alert
    if `passes_calibration` flips between two consecutive runs).

The flow is **read-only**. No DB access, no external HTTP. Everything
lives in the JSON manifests under ``models/``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import structlog

from kq.config import REPO_ROOT

log = structlog.get_logger(__name__)

# Strategy short-names + their manifest paths (relative to REPO_ROOT/models/).
# The order here is the canonical "comparison view" order in the rendered
# output: cheapest config first, then router, then RAW baseline, then the
# experimental reforecast strategy.
_STRATEGIES: tuple[tuple[str, str], ...] = (
    ("v1", "backtest_manifest.json"),
    ("router_v1", "backtest_router_manifest.json"),
    ("all_raw_v1", "backtest_all_raw_manifest.json"),
    ("reforecast_v1", "backtest_reforecast_manifest.json"),
)

# CLAUDE.md §5 readiness #2 bar — Brier improvement vs NDFD must clear
# this threshold for a station to count toward the >= 4/6 stations gate.
BRIER_VS_NDFD_BAR_PCT: float = 2.0


@dataclass(frozen=True, slots=True)
class StationView:
    """One station's per-strategy snapshot. JSON-safe by construction."""

    station: str
    active_strategy: str  # "ngr" | "raw" | (future) "reforecast"
    decision_reason: str
    raw_residual_std_f: float | None
    # Per-strategy comparison (Brier improvement vs NDFD, in pp).
    brier_vs_ndfd_pct_by_strategy: dict[str, float | None]
    # Per-strategy reliability summary (passes_bar) at the n-aware threshold.
    calibration_passes_by_strategy: dict[str, bool | None]
    # Helpers for the summary aggregation.
    active_passes_brier_bar: bool  # Brier-vs-NDFD ≥ BRIER_VS_NDFD_BAR_PCT
    active_passes_calibration: bool  # router_v1's reliability_summary.passes_bar


@dataclass(frozen=True, slots=True)
class RouterSummary:
    """Top-level rollup. Used both as the JSON shape and the renderer input."""

    router_config_generated_at: str | None
    router_mode: str | None
    decision_threshold_pct: float | None
    n_stations: int
    n_stations_ngr: int
    n_stations_raw: int
    n_stations_other: int  # reforecast or future strategies
    n_passes_brier_bar: int  # vs NDFD ≥ BRIER_VS_NDFD_BAR_PCT under active config
    n_passes_calibration: int  # router_v1 reliability passes_bar
    phase5_passes_brier_bar: bool  # n_passes_brier_bar >= 4 (CLAUDE.md §5 #2)
    stations: list[StationView] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_json(path: Path) -> dict[str, Any] | None:
    """Return parsed JSON or None when the file doesn't exist. Never raises
    on missing — this flow is informational, missing manifests are surfaced
    as None values in the rendered output rather than a hard error.

    Non-dict top-level shapes (lists, scalars) are coerced to None — the
    manifests we read all have a top-level dict, so anything else is a
    sign of corruption we'd rather expose as "missing" than crash on.
    """
    if not path.exists():
        return None
    try:
        with path.open() as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        log.warning("router_summary.manifest_parse_failed", path=str(path), error=str(exc))
        return None
    if not isinstance(data, dict):
        log.warning(
            "router_summary.manifest_unexpected_shape", path=str(path), type=type(data).__name__
        )
        return None
    return data


def summarize(models_dir: Path) -> RouterSummary:
    """Compose the summary by reading every manifest under ``models_dir``.

    Tolerant of missing files: a station's per-strategy entry shows None
    when its corresponding manifest is absent or malformed.
    """
    router_cfg = _load_json(models_dir / "router_config.json") or {}
    decisions = router_cfg.get("decisions", {}) or {}

    # Load every backtest manifest once. Keyed by short strategy name.
    manifests: dict[str, dict[str, Any]] = {}
    for short, fname in _STRATEGIES:
        manifest = _load_json(models_dir / fname)
        if manifest is not None:
            manifests[short] = manifest

    # Collect the union of all stations seen anywhere — router decisions
    # are authoritative when available, otherwise we fall back to manifest
    # stations (e.g. when router_config.json is missing).
    stations: set[str] = set(decisions.keys())
    for m in manifests.values():
        stations.update((m.get("stations") or {}).keys())

    views: list[StationView] = []
    n_ngr = n_raw = n_other = 0
    n_passes_brier = 0
    n_passes_calib = 0

    for station in sorted(stations):
        decision = decisions.get(station, {}) or {}
        active = (decision.get("strategy") or "raw").lower()
        if active == "ngr":
            n_ngr += 1
        elif active == "raw":
            n_raw += 1
        else:
            n_other += 1

        brier_by: dict[str, float | None] = {}
        calib_by: dict[str, bool | None] = {}
        for short in (s for s, _ in _STRATEGIES):
            row = (manifests.get(short, {}).get("stations") or {}).get(station) or {}
            brier_by[short] = row.get("brier_improvement_vs_ndfd_pct")
            rs = row.get("reliability_summary") or {}
            calib_by[short] = rs.get("passes_bar")

        # The active strategy's NDFD-relative score is whichever manifest
        # corresponds to the live config. The router today writes per-station
        # `strategy = "ngr" | "raw"`; both interpretations live under
        # `weather_router_v1`'s manifest because that's the dispatched
        # strategy. So `router_v1` is the source of truth for the *active*
        # number, not `v1` or `all_raw_v1`.
        active_brier = brier_by.get("router_v1")
        passes_brier = active_brier is not None and active_brier >= BRIER_VS_NDFD_BAR_PCT
        if passes_brier:
            n_passes_brier += 1

        # Calibration is similarly evaluated under the active dispatched
        # strategy, which is `router_v1`.
        passes_calib = bool(calib_by.get("router_v1") or False)
        if passes_calib:
            n_passes_calib += 1

        views.append(
            StationView(
                station=station,
                active_strategy=active,
                decision_reason=str(decision.get("reason") or ""),
                raw_residual_std_f=decision.get("raw_residual_std_f"),
                brier_vs_ndfd_pct_by_strategy=brier_by,
                calibration_passes_by_strategy=calib_by,
                active_passes_brier_bar=passes_brier,
                active_passes_calibration=passes_calib,
            )
        )

    return RouterSummary(
        router_config_generated_at=router_cfg.get("generated_at"),
        router_mode=router_cfg.get("mode"),
        decision_threshold_pct=router_cfg.get("decision_threshold_pct"),
        n_stations=len(views),
        n_stations_ngr=n_ngr,
        n_stations_raw=n_raw,
        n_stations_other=n_other,
        n_passes_brier_bar=n_passes_brier,
        n_passes_calibration=n_passes_calib,
        phase5_passes_brier_bar=n_passes_brier >= 4,  # CLAUDE.md §5 #2
        stations=views,
    )


def render_human(summary: RouterSummary) -> str:
    """ASCII-only, paste-friendly station-by-station view + aggregate summary."""
    lines: list[str] = []
    lines.append("=== Active Router Configuration ===")
    if summary.router_config_generated_at:
        lines.append(f"Generated: {summary.router_config_generated_at}")
    if summary.router_mode:
        lines.append(f"Mode: {summary.router_mode}")
    if summary.decision_threshold_pct is not None:
        lines.append(f"Decision threshold: {summary.decision_threshold_pct:.2f}%")
    lines.append("")

    if not summary.stations:
        lines.append("(no stations in router_config or any manifest)")
        return "\n".join(lines)

    for v in summary.stations:
        lines.append(f"{v.station}  → {v.active_strategy.upper()}")
        if v.decision_reason:
            lines.append(f"           reason: {v.decision_reason}")
        # Brier vs NDFD across all strategies — the canonical comparison line.
        brier_cells = []
        for short, _ in _STRATEGIES:
            val = v.brier_vs_ndfd_pct_by_strategy.get(short)
            brier_cells.append(f"{short}={_format_pct(val)}")
        lines.append(f"           brier-vs-ndfd: {'  '.join(brier_cells)}")
        # Calibration pass/fail across all strategies (when reliability_summary present).
        calib_cells = []
        for short, _ in _STRATEGIES:
            passes = v.calibration_passes_by_strategy.get(short)
            calib_cells.append(f"{short}={_format_pass(passes)}")
        lines.append(f"           calibration : {'  '.join(calib_cells)}")
        lines.append("")

    lines.append("=== Summary ===")
    lines.append(
        f"Stations: {summary.n_stations} total — "
        f"{summary.n_stations_ngr} ngr, {summary.n_stations_raw} raw, "
        f"{summary.n_stations_other} other"
    )
    lines.append(
        f"Brier-vs-NDFD bar (>= {BRIER_VS_NDFD_BAR_PCT:.0f}%): "
        f"{summary.n_passes_brier_bar}/{summary.n_stations} pass under active config "
        f"(Phase 5 #2 needs >= 4: {'PASS' if summary.phase5_passes_brier_bar else 'FAIL'})"
    )
    lines.append(
        f"Calibration bar (n-aware, default min_n=100): "
        f"{summary.n_passes_calibration}/{summary.n_stations} pass under active config"
    )
    return "\n".join(lines)


def _format_pct(value: float | None) -> str:
    if value is None:
        return "—".rjust(7)
    return f"{value:+6.2f}%"


def _format_pass(value: bool | None) -> str:
    if value is None:
        return "—".rjust(4)
    return "PASS" if value else "FAIL"


def run(*, models_dir: Path | None = None, json_output: bool = False) -> tuple[RouterSummary, str]:
    """Library entry point. Returns (summary, rendered string)."""
    md = models_dir or (REPO_ROOT / "models")
    summary = summarize(md)
    rendered = json.dumps(summary.to_dict()) if json_output else render_human(summary)
    log.info(
        "router_summary.computed",
        n_stations=summary.n_stations,
        n_passes_brier=summary.n_passes_brier_bar,
        n_passes_calib=summary.n_passes_calibration,
        phase5_passes_brier=summary.phase5_passes_brier_bar,
    )
    return summary, rendered


def main(*, json_output: bool = False) -> int:
    """`python -m kq router-summary` entrypoint.

    Returns:
        0 — Phase 5 #2 currently passes (>= 4/6 brier bar)
        1 — Phase 5 #2 currently fails (informational, not error)
        2 — Fundamental failure (manifest parse error, etc.)
    """
    try:
        summary, rendered = run(json_output=json_output)
    except Exception as exc:
        log.error("router_summary.failed", error=str(exc))
        print(f"router_summary failed: {exc}")
        return 2
    print(rendered)
    return 0 if summary.phase5_passes_brier_bar else 1


__all__ = [
    "BRIER_VS_NDFD_BAR_PCT",
    "RouterSummary",
    "StationView",
    "main",
    "render_human",
    "run",
    "summarize",
]
