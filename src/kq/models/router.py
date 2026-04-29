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

Strategy = Literal["ngr", "raw"]

MIN_BRIER_IMPROVEMENT_PCT: Final = 1.0  # need >=1pp Brier improvement to use NGR
DEFAULT_RAW_SIGMA_F: Final = 3.5  # fallback when manifest lacks raw_residual_std


@dataclass(frozen=True, slots=True)
class StationDecision:
    """Per-station routing choice + the rationale that produced it."""

    station: str
    strategy: Strategy
    brier_improvement_pct: float
    raw_residual_std_f: float
    reason: str


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
            cfg.decisions[station] = StationDecision(
                station=station,
                strategy=raw["strategy"],
                brier_improvement_pct=float(raw.get("brier_improvement_pct", 0.0)),
                raw_residual_std_f=float(raw.get("raw_residual_std_f", DEFAULT_RAW_SIGMA_F)),
                reason=str(raw.get("reason", "")),
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
        # Look up sigma in the training manifest if available.
        raw_sigma = DEFAULT_RAW_SIGMA_F
        if station in train_stations:
            fit_meta = train_stations[station].get("fit_metadata") or {}
            raw_sigma = max(
                float(fit_meta.get("raw_residual_std", DEFAULT_RAW_SIGMA_F)),
                DEFAULT_RAW_SIGMA_F * 0.3,  # numeric floor at ~1F
            )

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
