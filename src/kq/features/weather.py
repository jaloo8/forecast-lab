"""Weather feature engineering.

Two public entry points:

- `build_ensemble_features(con, ...)` — one row per
  `(station, valid_date, as_of, model)` with summary stats across members
  (mean / std / min / max / quantiles / member_count). For deterministic
  historical rows (model='gfs_hist', single member) std collapses to 0
  and quantiles equal the mean — we keep the row so downstream can filter
  or consume it uniformly.

- `build_training_set(con, ...)` — joins ensemble features with observed
  truth from `weather_observed`. One row per
  `(station, valid_date, as_of, model)` that has a settled observation.
  Adds `lead_days` and drops rows with missing observations.

All feature DataFrames carry an `as_of` column to preserve point-in-time
discipline (CLAUDE.md §6). Any downstream model MUST respect
`as_of <= signal_time - data_latency` when using these rows.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    import duckdb


FEATURE_COLUMNS: tuple[str, ...] = (
    "as_of",
    "run_time",
    "model",
    "station",
    "valid_date",
    "member_count",
    "ens_mean_high_f",
    "ens_std_high_f",
    "ens_min_high_f",
    "ens_max_high_f",
    "ens_q10_high_f",
    "ens_q25_high_f",
    "ens_q50_high_f",
    "ens_q75_high_f",
    "ens_q90_high_f",
    "ens_range_high_f",
    "ens_mean_low_f",
    "ens_std_low_f",
)


def build_ensemble_features(
    con: duckdb.DuckDBPyConnection,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    stations: Sequence[str] | None = None,
    models: Sequence[str] | None = None,
) -> pl.DataFrame:
    """Compute ensemble summary features from `weather_forecast`.

    Returns one row per `(station, valid_date, as_of, model)`. Rows with
    zero non-null `forecast_high_f` members are dropped.
    """
    where, params = _build_where(
        start_date=start_date,
        end_date=end_date,
        stations=stations,
        models=models,
    )

    # nosec B608: `where` only contains parameterized `?` placeholders built by
    # _build_where(); user values flow through `params` only, never via f-string.
    sql = f"""
        WITH agg AS (
            SELECT
                station,
                valid_date,
                as_of,
                run_time,
                model,
                COUNT(forecast_high_f) AS member_count,
                AVG(forecast_high_f) AS ens_mean_high_f,
                STDDEV_SAMP(forecast_high_f) AS ens_std_high_f,
                MIN(forecast_high_f) AS ens_min_high_f,
                MAX(forecast_high_f) AS ens_max_high_f,
                QUANTILE_CONT(forecast_high_f, 0.10) AS ens_q10_high_f,
                QUANTILE_CONT(forecast_high_f, 0.25) AS ens_q25_high_f,
                QUANTILE_CONT(forecast_high_f, 0.50) AS ens_q50_high_f,
                QUANTILE_CONT(forecast_high_f, 0.75) AS ens_q75_high_f,
                QUANTILE_CONT(forecast_high_f, 0.90) AS ens_q90_high_f,
                AVG(forecast_low_f) AS ens_mean_low_f,
                STDDEV_SAMP(forecast_low_f) AS ens_std_low_f
            FROM weather_forecast
            {where}
            GROUP BY station, valid_date, as_of, run_time, model
        )
        SELECT
            as_of, run_time, model, station, valid_date,
            member_count,
            ens_mean_high_f,
            COALESCE(ens_std_high_f, 0.0) AS ens_std_high_f,
            ens_min_high_f,
            ens_max_high_f,
            ens_q10_high_f,
            ens_q25_high_f,
            ens_q50_high_f,
            ens_q75_high_f,
            ens_q90_high_f,
            (ens_max_high_f - ens_min_high_f) AS ens_range_high_f,
            ens_mean_low_f,
            COALESCE(ens_std_low_f, 0.0) AS ens_std_low_f
        FROM agg
        WHERE member_count > 0
        ORDER BY station, valid_date, as_of, model
    """
    result = con.execute(sql, params).pl()
    return result.select(list(FEATURE_COLUMNS))


def build_training_set(
    con: duckdb.DuckDBPyConnection,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    stations: Sequence[str] | None = None,
    models: Sequence[str] | None = None,
) -> pl.DataFrame:
    """Join ensemble features with observed daily truth.

    Returns one row per (station, valid_date, as_of, model) where the
    observation is known. Adds:
        lead_days     = valid_date - date(as_of)
        observed_high_f, observed_low_f
        residual_high_f = observed_high_f - ens_mean_high_f
    """
    features = build_ensemble_features(
        con,
        start_date=start_date,
        end_date=end_date,
        stations=stations,
        models=models,
    )
    if features.is_empty():
        return features.with_columns(
            pl.lit(None, dtype=pl.Int32).alias("lead_days"),
            pl.lit(None, dtype=pl.Float64).alias("observed_high_f"),
            pl.lit(None, dtype=pl.Float64).alias("observed_low_f"),
            pl.lit(None, dtype=pl.Float64).alias("residual_high_f"),
        )

    observed = con.execute(
        "SELECT station, valid_date, high_f AS observed_high_f, low_f AS observed_low_f "
        "FROM weather_observed WHERE high_f IS NOT NULL"
    ).pl()

    joined = features.join(observed, on=["station", "valid_date"], how="inner")
    joined = joined.with_columns(
        (pl.col("valid_date") - pl.col("as_of").dt.date()).dt.total_days().alias("lead_days"),
        (pl.col("observed_high_f") - pl.col("ens_mean_high_f")).alias("residual_high_f"),
    )
    return joined


def _build_where(
    *,
    start_date: date | None,
    end_date: date | None,
    stations: Sequence[str] | None,
    models: Sequence[str] | None,
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if start_date is not None:
        clauses.append("valid_date >= ?")
        params.append(start_date)
    if end_date is not None:
        clauses.append("valid_date <= ?")
        params.append(end_date)
    if stations:
        placeholders = ",".join("?" for _ in stations)
        clauses.append(f"station IN ({placeholders})")
        params.extend(stations)
    if models:
        placeholders = ",".join("?" for _ in models)
        clauses.append(f"model IN ({placeholders})")
        params.extend(models)
    if not clauses:
        return "", params
    return "WHERE " + " AND ".join(clauses), params
