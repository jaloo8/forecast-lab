"""Per-station strategy router.

PR H taught us: NGR wins big on KJFK (+20.1% Brier) but loses on stations
where the raw forecast is already nearly perfect (LAX/MIA, raw_residual_std
~1.3F). The honest fix is to use whichever model wins per station, not to
swap NGR for a fancier model. This module is the dispatch + decision layer.

Flow:
    1. After a backtest produces `models/backtest_manifest.json`,
       `decide_strategies_from_manifest(...)` walks the per-station results
       and emits a `StrategyRouterConfig`: station -> 'ngr' | 'raw'.
    2. Save the config to `models/router_config.json` (committed) so
       reviewers can see the per-station choice rationale.
    3. At inference (or in the routed backtest strategy), `StrategyRouter`
       dispatches `predict_proba` to the right model per station.

The decision rule defaults to: use NGR if Brier improvement >=
`MIN_BRIER_IMPROVEMENT_PCT` (default 1%); otherwise raw. This is
intentionally conservative — a tiny "improvement" can be noise, especially
with limited data.
"""

from __future__ import annotations

import json
import pickle  # nosec B403: loads our own model artifacts only
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal

import numpy as np

from kq.models.raw_forecast import RawForecastModel
from kq.models.weather_ngr import WeatherNGRModel

Strategy = Literal["ngr", "raw", "reforecast", "analog"]

MIN_BRIER_IMPROVEMENT_PCT: Final = 1.0  # need >=1pp Brier improvement to use NGR
DEFAULT_RAW_SIGMA_F: Final = 3.5  # fallback when manifest lacks raw_residual_std
# Calibration-aware decision rule: a candidate strategy must clear this
# Brier-vs-NDFD tolerance to be considered (i.e., we won't pick a
# calibration-passing strategy if it bleeds 20pp on Brier-vs-NDFD vs the
# best alternative). Hysteresis margin against noise.
CALIBRATION_AWARE_BRIER_TOLERANCE_PP: Final = 5.0


@dataclass(frozen=True, slots=True)
class StationDecision:
    """Per-station routing choice + the rationale that produced it."""

    station: str
    strategy: Strategy
    brier_improvement_pct: float
    raw_residual_std_f: float
    reason: str
    # Phase 2 ext (post-#18) — NDFD-aware decision metadata. Set when the
    # router compared NGR-vs-NDFD against RAW-vs-NDFD per station. Both
    # values are the `brier_improvement_vs_ndfd_pct` from the respective
    # backtest manifests; the router picks the strategy with the higher
    # (less negative) value above ``threshold_pct``.
    ngr_vs_ndfd_pct: float | None = None
    raw_vs_ndfd_pct: float | None = None
    # Phase 5 #3 follow-up — calibration-aware decision metadata. Set when
    # the router considered each strategy's `reliability_summary.passes_bar`
    # (n-aware, default min_n=100) alongside Brier-vs-NDFD. None on legacy
    # decisions that didn't read the calibration field.
    reforecast_vs_ndfd_pct: float | None = None
    ngr_passes_calibration: bool | None = None
    raw_passes_calibration: bool | None = None
    reforecast_passes_calibration: bool | None = None


@dataclass
class StrategyRouterConfig:
    """Mapping of station -> strategy + provenance for the manifest."""

    decisions: dict[str, StationDecision] = field(default_factory=dict)
    generated_at: str = ""
    decision_threshold_pct: float = MIN_BRIER_IMPROVEMENT_PCT

    def strategy_for(self, station: str, *, default: Strategy = "raw") -> Strategy:
        """Return the chosen strategy for `station`, or `default` if unknown."""
        if station in self.decisions:
            return self.decisions[station].strategy
        return default

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "decision_threshold_pct": self.decision_threshold_pct,
            "decisions": {
                station: {
                    "strategy": d.strategy,
                    "brier_improvement_pct": round(d.brier_improvement_pct, 3),
                    "raw_residual_std_f": round(d.raw_residual_std_f, 3),
                    "reason": d.reason,
                    # NDFD-aware metadata; None when legacy decision rule was used.
                    "ngr_vs_ndfd_pct": (
                        round(d.ngr_vs_ndfd_pct, 3) if d.ngr_vs_ndfd_pct is not None else None
                    ),
                    "raw_vs_ndfd_pct": (
                        round(d.raw_vs_ndfd_pct, 3) if d.raw_vs_ndfd_pct is not None else None
                    ),
                    # Calibration-aware metadata; None when the calibration-aware
                    # mode was not used. Fields are emitted whenever any of them
                    # is non-None, so a JSON consumer can detect the mode by
                    # presence.
                    "reforecast_vs_ndfd_pct": (
                        round(d.reforecast_vs_ndfd_pct, 3)
                        if d.reforecast_vs_ndfd_pct is not None
                        else None
                    ),
                    "ngr_passes_calibration": d.ngr_passes_calibration,
                    "raw_passes_calibration": d.raw_passes_calibration,
                    "reforecast_passes_calibration": d.reforecast_passes_calibration,
                }
                for station, d in sorted(self.decisions.items())
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StrategyRouterConfig:
        cfg = cls(
            generated_at=str(data.get("generated_at", "")),
            decision_threshold_pct=float(
                data.get("decision_threshold_pct", MIN_BRIER_IMPROVEMENT_PCT)
            ),
        )
        for station, raw in (data.get("decisions") or {}).items():
            ngr_vs = raw.get("ngr_vs_ndfd_pct")
            raw_vs = raw.get("raw_vs_ndfd_pct")
            ref_vs = raw.get("reforecast_vs_ndfd_pct")
            cfg.decisions[station] = StationDecision(
                station=station,
                strategy=raw["strategy"],
                brier_improvement_pct=float(raw.get("brier_improvement_pct", 0.0)),
                raw_residual_std_f=float(raw.get("raw_residual_std_f", DEFAULT_RAW_SIGMA_F)),
                reason=str(raw.get("reason", "")),
                ngr_vs_ndfd_pct=(float(ngr_vs) if ngr_vs is not None else None),
                raw_vs_ndfd_pct=(float(raw_vs) if raw_vs is not None else None),
                reforecast_vs_ndfd_pct=(float(ref_vs) if ref_vs is not None else None),
                ngr_passes_calibration=raw.get("ngr_passes_calibration"),
                raw_passes_calibration=raw.get("raw_passes_calibration"),
                reforecast_passes_calibration=raw.get("reforecast_passes_calibration"),
            )
        return cfg

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, sort_keys=True)

    @classmethod
    def load(cls, path: Path) -> StrategyRouterConfig:
        with path.open(encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))


def decide_strategies_ndfd_aware(
    all_ngr_manifest: dict[str, Any],
    all_raw_manifest: dict[str, Any],
    training_manifest: dict[str, Any] | None = None,
    *,
    threshold_pct: float = MIN_BRIER_IMPROVEMENT_PCT,
) -> StrategyRouterConfig:
    """NDFD-aware router decision: pick the strategy with better Brier-vs-NDFD.

    Per-station rule: pick ``ngr`` if ``ngr_vs_ndfd_pct >= raw_vs_ndfd_pct +
    threshold_pct`` (NGR materially beats RAW on the NDFD comparison);
    else pick ``raw``. The threshold is a hysteresis margin to avoid
    noise-driven flips at borderline stations.

    Per the [post-#15 audit finding](../../ROADMAP.md), the legacy decision
    rule (``brier_improvement_pct`` vs synthetic raw market) can disagree
    with our gate criterion (``brier_improvement_vs_ndfd_pct``). At KMDW
    the legacy rule chose NGR (+6.2% vs raw market) but RAW had better
    NDFD comparison (-51% vs -59%). The NDFD-aware rule fixes that by
    optimizing the right objective directly.

    Falls back to the legacy ``decide_strategies_from_manifest`` for any
    station missing ``brier_improvement_vs_ndfd_pct`` in either manifest
    (e.g., NDFD coverage didn't reach the station's backtest window).
    """
    cfg = StrategyRouterConfig(
        generated_at=datetime.now(tz=UTC).isoformat(),
        decision_threshold_pct=threshold_pct,
    )
    ngr_stations = all_ngr_manifest.get("stations") or {}
    raw_stations = all_raw_manifest.get("stations") or {}
    train_stations = (training_manifest or {}).get("stations") or {}

    for station, ngr_summary in ngr_stations.items():
        raw_summary = raw_stations.get(station)
        ngr_vs_ndfd = ngr_summary.get("brier_improvement_vs_ndfd_pct")
        raw_vs_ndfd = raw_summary.get("brier_improvement_vs_ndfd_pct") if raw_summary else None

        # Fall back to legacy rule when NDFD data is missing on either side.
        if ngr_vs_ndfd is None or raw_vs_ndfd is None:
            improvement = float(ngr_summary.get("brier_improvement_pct", 0.0))
            raw_sigma = _lookup_raw_sigma(station, train_stations)
            if improvement >= threshold_pct:
                strategy: Strategy = "ngr"
                reason = (
                    f"NDFD data missing; legacy rule applied. "
                    f"NGR Brier improvement {improvement:+.2f}% "
                    f">= threshold {threshold_pct:.2f}% — keep calibration"
                )
            else:
                strategy = "raw"
                reason = (
                    f"NDFD data missing; legacy rule applied. "
                    f"NGR Brier improvement {improvement:+.2f}% "
                    f"< threshold {threshold_pct:.2f}% — raw forecast wins"
                )
            cfg.decisions[station] = StationDecision(
                station=station,
                strategy=strategy,
                brier_improvement_pct=improvement,
                raw_residual_std_f=raw_sigma,
                reason=reason,
            )
            continue

        # NDFD-aware decision: pick the strategy with higher (less negative)
        # vs-NDFD percentage above the hysteresis threshold.
        ngr_better_by = float(ngr_vs_ndfd) - float(raw_vs_ndfd)
        improvement = float(ngr_summary.get("brier_improvement_pct", 0.0))
        raw_sigma = _lookup_raw_sigma(station, train_stations)
        if ngr_better_by >= threshold_pct:
            strategy = "ngr"
            reason = (
                f"NDFD-aware: NGR vs NDFD {float(ngr_vs_ndfd):+.2f}% "
                f"vs RAW {float(raw_vs_ndfd):+.2f}% (NGR better by "
                f"{ngr_better_by:+.2f}pp >= threshold {threshold_pct:.2f}%)"
            )
        else:
            strategy = "raw"
            reason = (
                f"NDFD-aware: NGR vs NDFD {float(ngr_vs_ndfd):+.2f}% "
                f"vs RAW {float(raw_vs_ndfd):+.2f}% (NGR better by "
                f"{ngr_better_by:+.2f}pp < threshold {threshold_pct:.2f}% — raw wins)"
            )
        cfg.decisions[station] = StationDecision(
            station=station,
            strategy=strategy,
            brier_improvement_pct=improvement,
            raw_residual_std_f=raw_sigma,
            reason=reason,
            ngr_vs_ndfd_pct=float(ngr_vs_ndfd),
            raw_vs_ndfd_pct=float(raw_vs_ndfd),
        )
    return cfg


def _ndfd_aware_pick(
    ngr_vs: float | None,
    raw_vs: float | None,
    improvement: float,
    threshold_pct: float,
) -> Strategy:
    """Helper: NDFD-aware pick, with legacy fallback when NDFD data is absent."""
    if ngr_vs is not None and raw_vs is not None:
        return "ngr" if (ngr_vs - raw_vs) >= threshold_pct else "raw"
    return "ngr" if improvement >= threshold_pct else "raw"


def _decide_one_calibration_aware(
    *,
    brier_by: dict[Strategy, float | None],
    passes_by: dict[Strategy, bool | None],
    improvement: float,
    threshold_pct: float,
    brier_tolerance_pp: float,
) -> tuple[Strategy, str]:
    """Per-station calibration-aware decision; returns (strategy, reason).

    Extracted so the outer loop stays small (PLR0912 / PLR0915 budget).
    """
    # Iterate over the typed Strategy values directly so mypy can narrow.
    strats: tuple[Strategy, Strategy, Strategy] = ("ngr", "raw", "reforecast")
    candidates: list[tuple[Strategy, float]] = []
    for strat in strats:
        v = brier_by[strat]
        if passes_by[strat] is True and v is not None:
            candidates.append((strat, v))
    all_known_brier = [v for v in brier_by.values() if v is not None]
    overall_best_brier = max(all_known_brier) if all_known_brier else None

    if not candidates:
        chosen = _ndfd_aware_pick(brier_by["ngr"], brier_by["raw"], improvement, threshold_pct)
        if brier_by["ngr"] is not None and brier_by["raw"] is not None:
            reason = (
                f"calibration-aware: no strategy clears the n-aware bar; "
                f"NDFD-aware fallback picks {chosen} "
                f"(NGR {brier_by['ngr']:+.2f}% vs RAW {brier_by['raw']:+.2f}%)"
            )
        else:
            reason = (
                f"calibration-aware: no calibration data and no NDFD comparison; "
                f"legacy rule picks {chosen} (Brier improvement {improvement:+.2f}%)"
            )
        return chosen, reason

    cand_strat, cand_brier = max(candidates, key=lambda t: t[1])
    if overall_best_brier is not None and (overall_best_brier - cand_brier) > brier_tolerance_pp:
        # Calibration winner trails the Brier leader by too much.
        chosen = _ndfd_aware_pick(brier_by["ngr"], brier_by["raw"], improvement, threshold_pct)
        reason = (
            f"calibration-aware fallback: {cand_strat} passes calibration "
            f"({cand_brier:+.2f}% vs NDFD) but trails the overall best "
            f"({overall_best_brier:+.2f}%) by more than {brier_tolerance_pp:.1f}pp; "
            f"defaulting to NDFD-aware pick ({chosen})"
        )
        return chosen, reason

    pretty = _format_brier_grid(brier_by, passes_by)
    reason = (
        f"calibration-aware: {cand_strat} passes the n-aware bar "
        f"({cand_brier:+.2f}% vs NDFD); within {brier_tolerance_pp:.1f}pp of "
        f"the overall best. {pretty}"
    )
    return cand_strat, reason


def decide_strategies_calibration_aware(
    all_ngr_manifest: dict[str, Any],
    all_raw_manifest: dict[str, Any],
    reforecast_manifest: dict[str, Any],
    training_manifest: dict[str, Any] | None = None,
    *,
    threshold_pct: float = MIN_BRIER_IMPROVEMENT_PCT,
    brier_tolerance_pp: float = CALIBRATION_AWARE_BRIER_TOLERANCE_PP,
) -> StrategyRouterConfig:
    """Calibration-aware router decision: prefer strategies that pass the
    n-aware reliability bar, but only if their Brier-vs-NDFD is competitive.

    Per-station rule (in order):

    1. Build the candidate set of strategies whose
       ``stations[ICAO].reliability_summary.passes_bar`` is True.
    2. Within that candidate set, pick the strategy with the **highest**
       Brier-vs-NDFD percentage (less-negative = better) — this is the
       calibration-passing strategy that also resolves best.
    3. If the best-calibration strategy on Brier-vs-NDFD is more than
       ``brier_tolerance_pp`` below the OVERALL best (regardless of
       calibration), fall back to the NDFD-aware decision (don't trade
       a 20pp Brier loss for a calibration win).
    4. If no strategy passes calibration, fall back to NDFD-aware (legacy).

    The motivation: post-PR #25 audit showed `weather_reforecast_v1`
    clears the n-aware calibration bar at 3 of 6 stations (KDEN, KJFK, KLAX)
    even though it loses on Brier-vs-NDFD overall. This rule says "use the
    well-calibrated strategy when its Brier penalty is small" — a Pareto
    pick rather than picking on a single axis.
    """
    cfg = StrategyRouterConfig(
        generated_at=datetime.now(tz=UTC).isoformat(),
        decision_threshold_pct=threshold_pct,
    )
    ngr_stations = all_ngr_manifest.get("stations") or {}
    raw_stations = all_raw_manifest.get("stations") or {}
    ref_stations = reforecast_manifest.get("stations") or {}
    train_stations = (training_manifest or {}).get("stations") or {}

    for station, ngr_summary in ngr_stations.items():
        raw_summary = raw_stations.get(station) or {}
        ref_summary = ref_stations.get(station) or {}

        brier_by: dict[Strategy, float | None] = {
            "ngr": ngr_summary.get("brier_improvement_vs_ndfd_pct"),
            "raw": raw_summary.get("brier_improvement_vs_ndfd_pct"),
            "reforecast": ref_summary.get("brier_improvement_vs_ndfd_pct"),
        }
        passes_by: dict[Strategy, bool | None] = {
            "ngr": (ngr_summary.get("reliability_summary") or {}).get("passes_bar"),
            "raw": (raw_summary.get("reliability_summary") or {}).get("passes_bar"),
            "reforecast": (ref_summary.get("reliability_summary") or {}).get("passes_bar"),
        }
        raw_sigma = _lookup_raw_sigma(station, train_stations)
        improvement = float(ngr_summary.get("brier_improvement_pct", 0.0))

        chosen, reason = _decide_one_calibration_aware(
            brier_by=brier_by,
            passes_by=passes_by,
            improvement=improvement,
            threshold_pct=threshold_pct,
            brier_tolerance_pp=brier_tolerance_pp,
        )

        cfg.decisions[station] = StationDecision(
            station=station,
            strategy=chosen,
            brier_improvement_pct=improvement,
            raw_residual_std_f=raw_sigma,
            reason=reason,
            ngr_vs_ndfd_pct=brier_by["ngr"],
            raw_vs_ndfd_pct=brier_by["raw"],
            reforecast_vs_ndfd_pct=brier_by["reforecast"],
            ngr_passes_calibration=passes_by["ngr"],
            raw_passes_calibration=passes_by["raw"],
            reforecast_passes_calibration=passes_by["reforecast"],
        )
    return cfg


def _format_brier_grid(
    brier_by: dict[Strategy, float | None],
    passes_by: dict[Strategy, bool | None],
) -> str:
    """One-line summary of (brier-vs-ndfd, calibration-pass) per strategy.
    Used in `decide_strategies_calibration_aware` rationale strings."""
    cells = []
    for strat in ("ngr", "raw", "reforecast"):
        b = brier_by[strat]
        p = passes_by[strat]
        b_s = f"{b:+.2f}%" if b is not None else "—"
        p_s = "PASS" if p is True else ("FAIL" if p is False else "—")
        cells.append(f"{strat}=({b_s},{p_s})")
    return " ".join(cells)


def _lookup_raw_sigma(station: str, train_stations: dict[str, Any]) -> float:
    """Per-station residual sigma from the training manifest, with a floor."""
    if station in train_stations:
        fit_meta = train_stations[station].get("fit_metadata") or {}
        return max(
            float(fit_meta.get("raw_residual_std", DEFAULT_RAW_SIGMA_F)),
            DEFAULT_RAW_SIGMA_F * 0.3,  # numeric floor at ~1F
        )
    return DEFAULT_RAW_SIGMA_F


def decide_strategies_from_manifest(
    backtest_manifest: dict[str, Any],
    training_manifest: dict[str, Any] | None = None,
    *,
    threshold_pct: float = MIN_BRIER_IMPROVEMENT_PCT,
) -> StrategyRouterConfig:
    """Walk a backtest manifest and emit a StrategyRouterConfig.

    Per-station rule: pick `ngr` if backtest Brier improvement vs naive
    >= `threshold_pct`; else `raw`. The training manifest is consulted for
    `raw_residual_std_f` (fallback to DEFAULT_RAW_SIGMA_F).
    """
    cfg = StrategyRouterConfig(
        generated_at=datetime.now(tz=UTC).isoformat(),
        decision_threshold_pct=threshold_pct,
    )
    bt_stations = backtest_manifest.get("stations") or {}
    train_stations = (training_manifest or {}).get("stations") or {}

    for station, summary in bt_stations.items():
        improvement = float(summary.get("brier_improvement_pct", 0.0))
        raw_sigma = _lookup_raw_sigma(station, train_stations)

        if improvement >= threshold_pct:
            strategy: Strategy = "ngr"
            reason = (
                f"NGR Brier improvement {improvement:+.2f}% "
                f">= threshold {threshold_pct:.2f}% — keep calibration"
            )
        else:
            strategy = "raw"
            reason = (
                f"NGR Brier improvement {improvement:+.2f}% "
                f"< threshold {threshold_pct:.2f}% — raw forecast wins"
            )

        cfg.decisions[station] = StationDecision(
            station=station,
            strategy=strategy,
            brier_improvement_pct=improvement,
            raw_residual_std_f=raw_sigma,
            reason=reason,
        )
    return cfg


@dataclass
class StrategyRouter:
    """Runtime dispatch from `(station, forecast)` to the chosen model.

    Constructed by giving it the loaded NGR pickles per station + the raw
    sigma per station. `predict_proba(station, ...)` looks up the strategy
    and calls the right model.
    """

    config: StrategyRouterConfig
    ngr_models: dict[str, WeatherNGRModel] = field(default_factory=dict)
    _raw_models: dict[str, RawForecastModel] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        # Pre-build raw models from the per-station sigmas.
        for station, decision in self.config.decisions.items():
            self._raw_models[station] = RawForecastModel(raw_sigma_f=decision.raw_residual_std_f)

    @classmethod
    def from_disk(
        cls,
        config_path: Path,
        models_dir: Path,
        *,
        lead_days: int = 1,
    ) -> StrategyRouter:
        """Load router config + matching NGR pickles for every NGR-using station."""
        config = StrategyRouterConfig.load(config_path)
        ngr_models: dict[str, WeatherNGRModel] = {}
        for station, decision in config.decisions.items():
            if decision.strategy != "ngr":
                continue
            pickle_path = models_dir / f"weather_ngr_{station}_lead{lead_days}.pkl"
            if not pickle_path.exists():
                raise FileNotFoundError(
                    f"router says {station} -> ngr but pickle not found at {pickle_path}"
                )
            with pickle_path.open("rb") as fh:
                ngr_models[station] = pickle.load(fh)  # nosec B301: trusted artifact
        return cls(config=config, ngr_models=ngr_models)

    def predict_proba(
        self,
        station: str,
        ens_mean: float | np.ndarray,
        threshold: float,
        *,
        ens_var: float | np.ndarray | None = None,
    ) -> np.ndarray:
        """Dispatch to the per-station chosen model and return P(T > threshold)."""
        strategy = self.config.strategy_for(station, default="raw")
        if strategy == "ngr":
            model = self.ngr_models.get(station)
            if model is None:
                raise RuntimeError(f"router says {station} -> ngr but no NGR model loaded")
            return model.predict_proba(ens_mean, threshold, ens_var=ens_var)
        # raw path — synthesize a RawForecastModel on the fly if not pre-built
        raw = self._raw_models.get(station) or RawForecastModel(raw_sigma_f=DEFAULT_RAW_SIGMA_F)
        return raw.predict_proba(ens_mean, threshold)

    def predict_distribution(
        self,
        station: str,
        ens_mean: float | np.ndarray,
        *,
        ens_var: float | np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Dispatch to the chosen model and return ``(mu, sigma)`` for the prior.

        Used by the intraday METAR nowcast (``kq.models.nowcast``) — it needs
        the predictive Gaussian's parameters, not just the threshold-conditional
        probability, so it can shrink sigma based on time-of-day.
        """
        strategy = self.config.strategy_for(station, default="raw")
        if strategy == "ngr":
            model = self.ngr_models.get(station)
            if model is None:
                raise RuntimeError(f"router says {station} -> ngr but no NGR model loaded")
            return model.predict_distribution(ens_mean, ens_var=ens_var)
        raw = self._raw_models.get(station) or RawForecastModel(raw_sigma_f=DEFAULT_RAW_SIGMA_F)
        return raw.predict_distribution(ens_mean)

    def strategy_for(self, station: str) -> Strategy:
        """Convenience pass-through."""
        return self.config.strategy_for(station)
