"""Train per-station NGR weather models from the joined training set.

What this does:
    1. Load the training set via `kq.features.weather.build_training_set`.
    2. Filter to the chosen lead time (default: 1 day ahead).
    3. For each station with enough samples, fit a `WeatherNGRModel` and
       evaluate it via rolling-origin time-series CV.
    4. Pickle each fit to `models/weather_ngr_{station}_lead{N}.pkl`
       (gitignored).
    5. Write/refresh `models/manifest.json` (committed) — a machine-readable
       summary of training window, sample count, OOS Brier (vs raw baseline),
       and reliability bins.

Stations with < `MIN_TRAIN_SAMPLES` rows are skipped with a warning. The
manifest still records them so re-runs are traceable.
"""

from __future__ import annotations

import json
import pickle  # nosec B403: writes & reads our own model artifacts only
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import structlog

from kq.config import REPO_ROOT, get_settings
from kq.features.weather import build_training_set, dedup_one_per_station_day
from kq.models.calibration import brier_score, reliability_bins, summarize_reliability
from kq.models.cv import rolling_origin_splits, sort_by_valid_date
from kq.models.weather_ngr import WeatherNGRModel, raw_brier_score
from kq.storage.duckdb_store import connect

log = structlog.get_logger(__name__)

MODELS_DIR = REPO_ROOT / "models"
MANIFEST_PATH = MODELS_DIR / "manifest.json"

DEFAULT_LEAD_DAYS = 1
DEFAULT_THRESHOLDS_F = tuple(range(40, 110, 5))  # 40, 45, ..., 105
MIN_TRAIN_SAMPLES = 30  # honest floor — below this, NGR is unstable
DEFAULT_INITIAL_TRAIN = 60  # rolling-CV warmup
DEFAULT_TEST_WINDOW = 14  # 2-week test windows


def train_all(
    *,
    db_path: Path | None = None,
    lead_days: int = DEFAULT_LEAD_DAYS,
    thresholds_f: Sequence[float] = DEFAULT_THRESHOLDS_F,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Train one NGR model per station with enough data; return manifest dict."""
    settings = get_settings()
    db = db_path or _db_path_from_settings(settings.database_url)
    out_dir = output_dir or MODELS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    con = connect(db)
    try:
        training = build_training_set(con)
    finally:
        con.close()

    manifest: dict[str, Any] = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "lead_days": lead_days,
        "thresholds_f": list(thresholds_f),
        "min_train_samples": MIN_TRAIN_SAMPLES,
        "initial_train": DEFAULT_INITIAL_TRAIN,
        "test_window": DEFAULT_TEST_WINDOW,
        # PR-F (audit #8/#9): n_samples counts DISTINCT (station, valid_date)
        # days (deduped, freshest as_of per day); CV test windows are
        # non-overlapping (step_size = test_window), so every day is
        # evaluated at most once.
        "n_semantics": "distinct station-days; non-overlapping CV test windows",
        "cv_step_size": DEFAULT_TEST_WINDOW,
        "stations": {},
    }

    if training.is_empty():
        log.warning("train.no_data")
        manifest["status"] = "no_data"
        _write_manifest(out_dir, manifest)
        return manifest

    # Filter to chosen lead time + drop rows with missing residuals.
    filtered = training.filter(
        (pl.col("lead_days") == lead_days)
        & pl.col("ens_mean_high_f").is_not_null()
        & pl.col("observed_high_f").is_not_null()
    )
    # One row per physical (station, valid_date) — several (as_of, model)
    # snapshots of the same day would otherwise pseudo-replicate every CV
    # statistic (2026-06-11 audit root cause #9 companion fix). Manifest
    # `n_samples` therefore counts distinct days.
    filtered = dedup_one_per_station_day(filtered)
    # Input provenance: which feature `model` values fed this training run
    # (e.g. 'prevday1_pool' = multi-model prevday consensus vs a single
    # 'gfs_prevday1' lane). Evidence is only comparable across runs with
    # the same input, so the manifest must say which one it was.
    manifest["input_models"] = sorted(filtered["model"].unique().to_list())

    for station in sorted(filtered["station"].unique().to_list()):
        station_df = sort_by_valid_date(filtered.filter(pl.col("station") == station))
        manifest["stations"][station] = _train_one_station(
            station=station,
            df=station_df,
            lead_days=lead_days,
            thresholds_f=thresholds_f,
            out_dir=out_dir,
        )

    _write_manifest(out_dir, manifest)
    log.info(
        "train.done",
        stations=len(manifest["stations"]),
        lead_days=lead_days,
        manifest=str(MANIFEST_PATH),
    )
    return manifest


def _train_one_station(
    *,
    station: str,
    df: pl.DataFrame,
    lead_days: int,
    thresholds_f: Sequence[float],
    out_dir: Path,
) -> dict[str, Any]:
    n = df.height
    record: dict[str, Any] = {
        "n_samples": n,
        "date_range": [df["valid_date"][0].isoformat(), df["valid_date"][-1].isoformat()],
    }
    if n < MIN_TRAIN_SAMPLES:
        log.warning("train.skipped_thin_data", station=station, n=n)
        record["status"] = "skipped_thin_data"
        return record

    ens_means = df["ens_mean_high_f"].to_numpy()
    ens_stds = df["ens_std_high_f"].to_numpy()
    ens_vars = ens_stds**2 if np.any(ens_stds > 0.0) else None
    observed = df["observed_high_f"].to_numpy()

    # OOS rolling-origin CV.
    cv_briers: list[float] = []
    cv_raw_briers: list[float] = []
    all_probs: list[float] = []
    all_outcomes: list[float] = []
    thresholds_arr = np.asarray(list(thresholds_f), dtype=float)

    for train_idx, test_idx in rolling_origin_splits(
        n_samples=n,
        initial_train_size=min(DEFAULT_INITIAL_TRAIN, n // 2),
        test_window_size=min(DEFAULT_TEST_WINDOW, max(1, n // 5)),
    ):
        m = WeatherNGRModel()
        train_vars = ens_vars[train_idx] if ens_vars is not None else None
        m.fit(ens_means[train_idx], observed[train_idx], ens_vars=train_vars)
        test_vars = ens_vars[test_idx] if ens_vars is not None else None
        cv_briers.append(
            m.brier_score(
                ens_means[test_idx],
                observed[test_idx],
                thresholds_arr,
                ens_vars=test_vars,
            )
        )
        cv_raw_briers.append(
            raw_brier_score(
                ens_means[test_idx],
                observed[test_idx],
                thresholds_arr,
                raw_sigma=max(m.fit_metadata["raw_residual_std"], 1.0),
            )
        )
        # Per-test-row median-bracket probability for an aggregate reliability diagram.
        median_t = float(np.median(thresholds_arr))
        all_probs.extend(m.predict_proba(ens_means[test_idx], median_t, ens_var=test_vars).tolist())
        all_outcomes.extend((observed[test_idx] > median_t).astype(int).tolist())

    # Final fit on the entire window (used for inference).
    final_model = WeatherNGRModel()
    final_model.fit(ens_means, observed, ens_vars=ens_vars)
    pickle_path = out_dir / f"weather_ngr_{station}_lead{lead_days}.pkl"
    with pickle_path.open("wb") as fh:
        pickle.dump(final_model, fh)

    if cv_briers:
        oos_brier = float(np.mean(cv_briers))
        oos_raw_brier = float(np.mean(cv_raw_briers))
        improvement_pct = (
            float((oos_raw_brier - oos_brier) / oos_raw_brier * 100.0) if oos_raw_brier > 0 else 0.0
        )
        bins = reliability_bins(np.asarray(all_probs), np.asarray(all_outcomes), n_bins=10)
        reliability = [
            {
                "lower": b.lower,
                "upper": b.upper,
                "n": b.n,
                "mean_predicted": None if np.isnan(b.mean_predicted) else b.mean_predicted,
                "mean_observed": None if np.isnan(b.mean_observed) else b.mean_observed,
            }
            for b in bins
        ]
        # Phase 5 #3 — n-aware reliability summary. See engine.py + the summary
        # docstring in `kq.models.calibration` for rationale.
        rs = summarize_reliability(bins)
        reliability_summary: dict[str, Any] = {
            "n_bins_total": rs.n_bins_total,
            "n_bins_qualifying": rs.n_bins_qualifying,
            "n_bins_failing": rs.n_bins_failing,
            "max_delta_pp": None if np.isnan(rs.max_delta_pp) else round(rs.max_delta_pp, 2),
            "max_delta_bin": rs.max_delta_bin,
            "passes_bar": rs.passes_bar,
            "min_n_threshold": rs.min_n_threshold,
            "tolerance_pp": rs.tolerance_pp,
        }
        # In-sample Brier as a sanity baseline (will always be lower than OOS).
        is_brier = brier_score(
            np.asarray(all_probs).clip(0.01, 0.99),
            np.asarray(all_outcomes),
        )
    else:
        oos_brier = float("nan")
        oos_raw_brier = float("nan")
        improvement_pct = 0.0
        reliability = []
        reliability_summary = {}
        is_brier = float("nan")

    record.update(
        {
            "status": "fit",
            "params": {
                "a": final_model.params.a if final_model.params else None,
                "b": final_model.params.b if final_model.params else None,
                "c": final_model.params.c if final_model.params else None,
                "d": final_model.params.d if final_model.params else None,
            },
            "fit_metadata": final_model.fit_metadata,
            "cv": {
                "n_folds": len(cv_briers),
                "oos_brier": oos_brier,
                "oos_raw_brier": oos_raw_brier,
                "improvement_pct": improvement_pct,
                "in_sample_brier_at_median": is_brier,
                "reliability_at_median": reliability,
                "reliability_summary": reliability_summary,
            },
            "pickle": _relative_or_absolute(pickle_path),
        }
    )
    log.info(
        "train.station_fit",
        station=station,
        n=n,
        oos_brier=round(oos_brier, 4),
        oos_raw_brier=round(oos_raw_brier, 4),
        improvement_pct=round(improvement_pct, 2),
    )
    return record


def _relative_or_absolute(path: Path) -> str:
    """Use repo-relative path when possible (committed manifest); fall back to absolute."""
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def _write_manifest(out_dir: Path, manifest: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "manifest.json").open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)


def _db_path_from_settings(url: str) -> Path:
    prefix = "duckdb:///"
    if not url.startswith(prefix):
        raise ValueError(f"Only duckdb:// URLs supported, got {url!r}")
    return Path(url.removeprefix(prefix))


def main(*, lead_days: int = DEFAULT_LEAD_DAYS) -> None:
    """`python -m kq train-weather` entrypoint."""
    manifest = train_all(lead_days=lead_days)
    n_fit = sum(1 for s in manifest.get("stations", {}).values() if s.get("status") == "fit")
    n_skip = sum(
        1 for s in manifest.get("stations", {}).values() if s.get("status") == "skipped_thin_data"
    )
    print(f"trained {n_fit} stations, skipped {n_skip}, manifest -> {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
