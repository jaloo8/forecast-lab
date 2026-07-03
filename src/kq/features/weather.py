"""Weather feature engineering.

Public entry points:

- `build_ensemble_features(con, ...)` — one row per
  `(station, valid_date, as_of, model)` with summary stats across members
  (mean / std / min / max / quantiles / member_count). For deterministic
  historical rows (model='gfs_prevday1', single member) std collapses to 0
  and quantiles equal the mean — we keep the row so downstream can filter
  or consume it uniformly.

- `build_training_set(con, ...)` — joins ensemble features with observed
  truth from `weather_observed`. One row per
  `(station, valid_date, as_of, model)` that has a settled observation.
  Adds `lead_days` and drops rows with missing observations.

- `dedup_one_per_station_day(df)` — collapse a training frame to at most
  one row per `(station, valid_date)` so backtest/CV statistics count each
  physical day exactly once (2026-06-11 audit root cause #9 companion fix).

**Multi-model prevday pooling (Phase A, 2026-07-02):** when two or more
true-lead-1 lanes (`model` ending in `'_prevday1'` — see
`kq.clients.openmeteo.PREV_DAY1_MODELS`) survive the query filters, they
are pooled into a single `model='prevday1_pool'` row per
`(station, valid_date)`: each lane is one pseudo-member, so
`ens_mean_high_f` becomes the cross-model consensus mean of the per-model
daily maxes and `ens_std_high_f` becomes the cross-model spread (the
"variance/spread column" — `ens_std_high_f**2` feeds NGR's `d·ens_var`
term in training). The individual lane rows are REPLACED by the pooled
row so downstream dedup never has to pick one lane arbitrarily. This
mirrors what live ingest gives the models (GEFS + ECMWF members) —
closing the 2026-07-01 audit caveat (b) that the honest backfill was
single-model while live is multi-model. PIT honesty: the pooled `as_of`
is the LATEST `as_of` of the contributing lanes (the pool exists only
once its last input does); with the shared `previous_day1_as_of` formula
all lanes carry the identical honest instant, so the pooled lead stays
exactly 1 LST day. The single-model path still works: pass a one-lane
`models=` list, or `pool_prevday=False`; with only one prevday lane
present, behavior is byte-identical to the pre-Phase-A output.

**Lead-day convention (PR-F):** `lead_days` counts *station-local-standard*
calendar days between `as_of` and `valid_date`, because Kalshi contracts
settle on LST days (`kq.utils.kalshi_dates`). A forecast known at 23:00 LST
the evening before the settlement day is lead-1 even when that instant has
already rolled into `valid_date` in UTC (e.g. 07:00 UTC at KLAX). Stations
absent from `STATIONS_BY_ICAO` (e.g. pre-PR-C KJFK rows still in old DBs)
fall back to a UTC-day lead.

All feature DataFrames carry an `as_of` column to preserve point-in-time
discipline (CLAUDE.md §6). Any downstream model MUST respect
`as_of <= signal_time - data_latency` when using these rows.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING, Final

import polars as pl

from kq.clients.openmeteo import PREV_DAY1_SUFFIX
from kq.clients.stations import STATIONS_BY_ICAO

if TYPE_CHECKING:
    import duckdb

# Synthetic model name for the pooled cross-model prevday consensus row.
# Deliberately does NOT end in '_prevday1' so it can never be re-pooled.
PREVDAY_POOL_MODEL: Final = "prevday1_pool"


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
    pool_prevday: bool = True,
) -> pl.DataFrame:
    """Compute ensemble summary features from `weather_forecast`.

    Returns one row per `(station, valid_date, as_of, model)`. Rows with
    zero non-null `forecast_high_f` members are dropped.

    With `pool_prevday=True` (default) and >= 2 distinct `*_prevday1`
    lanes present after filtering, the lane rows are replaced by one
    pooled `model='prevday1_pool'` row per `(station, valid_date)` whose
    stats treat each lane as a pseudo-member (see module docstring). Pass
    `pool_prevday=False` or a single-lane `models=` list for the
    single-model path.
    """
    where, params = _build_where(
        start_date=start_date,
        end_date=end_date,
        stations=stations,
        models=models,
    )

    # NOTE: `where` is interpolated into the f-string but only contains `?`
    # placeholders built by `_build_where()` — user values are passed via
    # `params` to `con.execute`, never via the f-string. B608 is globally
    # suppressed in pyproject.toml [tool.bandit] for this reason.
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
    result = con.execute(sql, params).pl().select(list(FEATURE_COLUMNS))
    if pool_prevday:
        result = _pool_prevday_lanes(result)
    return result


def _pool_prevday_lanes(features: pl.DataFrame) -> pl.DataFrame:
    """Replace `*_prevday1` lane rows with one pooled row per (station, day).

    Each lane's `ens_mean_high_f` (its daily max — lanes are deterministic,
    single-member) becomes one pseudo-member of the pooled row, so the
    pooled `ens_std_high_f` is the cross-model spread. No-op when fewer
    than 2 distinct lanes are present (single-model path stays intact).
    """
    if features.is_empty():
        return features
    is_lane = pl.col("model").str.ends_with(PREV_DAY1_SUFFIX)
    lanes = features.filter(is_lane)
    if lanes["model"].n_unique() < 2:
        return features

    high = pl.col("ens_mean_high_f")
    low = pl.col("ens_mean_low_f")
    pooled = (
        lanes.group_by(["station", "valid_date"])
        .agg(
            # PIT: the pool is available only when its LAST input is. All
            # prevday lanes share the deterministic previous_day1_as_of
            # instant, so max() is both honest and a no-op in practice.
            pl.col("as_of").max().alias("as_of"),
            pl.col("run_time").max().alias("run_time"),
            high.count().cast(pl.Int64).alias("member_count"),
            high.mean().alias("ens_mean_high_f"),
            high.std().fill_null(0.0).alias("ens_std_high_f"),
            high.min().alias("ens_min_high_f"),
            high.max().alias("ens_max_high_f"),
            high.quantile(0.10, interpolation="linear").alias("ens_q10_high_f"),
            high.quantile(0.25, interpolation="linear").alias("ens_q25_high_f"),
            high.quantile(0.50, interpolation="linear").alias("ens_q50_high_f"),
            high.quantile(0.75, interpolation="linear").alias("ens_q75_high_f"),
            high.quantile(0.90, interpolation="linear").alias("ens_q90_high_f"),
            low.mean().alias("ens_mean_low_f"),
            low.std().fill_null(0.0).alias("ens_std_low_f"),
        )
        .with_columns(
            pl.lit(PREVDAY_POOL_MODEL).alias("model"),
            (pl.col("ens_max_high_f") - pl.col("ens_min_high_f")).alias("ens_range_high_f"),
        )
        .select(list(FEATURE_COLUMNS))
    )
    return (
        pl.concat([features.filter(~is_lane), pooled], how="vertical_relaxed")
        .sort(["station", "valid_date", "as_of", "model"])
        .select(list(FEATURE_COLUMNS))
    )


def build_training_set(
    con: duckdb.DuckDBPyConnection,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    stations: Sequence[str] | None = None,
    models: Sequence[str] | None = None,
    pool_prevday: bool = True,
) -> pl.DataFrame:
    """Join ensemble features with observed daily truth.

    Returns one row per (station, valid_date, as_of, model) where the
    observation is known. `pool_prevday` (default True) pools multiple
    `*_prevday1` lanes into `model='prevday1_pool'` consensus rows before
    the join — see `build_ensemble_features`. Adds:
        lead_days     = valid_date - station-local-standard date(as_of)
                        (see module docstring; UTC fallback for unknown
                        stations)
        observed_high_f, observed_low_f
        residual_high_f = observed_high_f - ens_mean_high_f
    """
    features = build_ensemble_features(
        con,
        start_date=start_date,
        end_date=end_date,
        stations=stations,
        models=models,
        pool_prevday=pool_prevday,
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
    # LST-aware lead: shift the (naive-UTC) as_of into the station's fixed
    # LST offset before taking the calendar date. Unknown stations get
    # offset 0 (UTC behavior) so legacy rows keep a well-defined lead.
    offset_expr = pl.col("station").replace_strict(
        {icao: s.lst_offset_hours for icao, s in STATIONS_BY_ICAO.items()},
        default=0,
        return_dtype=pl.Int32,
    )
    local_as_of_date = (pl.col("as_of") + pl.duration(hours=offset_expr)).dt.date()
    joined = joined.with_columns(
        (pl.col("valid_date") - local_as_of_date).dt.total_days().alias("lead_days"),
        (pl.col("observed_high_f") - pl.col("ens_mean_high_f")).alias("residual_high_f"),
    )
    return joined


def dedup_one_per_station_day(df: pl.DataFrame) -> pl.DataFrame:
    """Collapse to at most one row per ``(station, valid_date)``.

    Multiple forecast rows can exist for the same physical day (several
    ``as_of`` snapshots, several models). Counting each of them as a
    separate evaluation pseudo-replicates every backtest/CV statistic —
    the same defect class as 2026-06-11 audit root cause #9. Policy:
    keep the row with the **latest** ``as_of`` (the freshest information
    honestly available at the row's lead), tie-breaking on ``model`` name
    ascending for determinism. Output is sorted by (station, valid_date).
    """
    if df.is_empty():
        return df
    required = {"station", "valid_date", "as_of"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"dedup_one_per_station_day: missing columns {sorted(missing)}")
    sort_cols = ["station", "valid_date", "as_of"]
    descending = [False, False, True]
    if "model" in df.columns:
        sort_cols.append("model")
        descending.append(False)
    return (
        df.sort(sort_cols, descending=descending)
        .unique(subset=["station", "valid_date"], keep="first", maintain_order=True)
        .sort(["station", "valid_date"])
    )


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
