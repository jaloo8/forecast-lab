"""Backtest engine: replay forecasts vs observed truth, simulate trades, emit P&L.

**Point-in-time discipline (the most important property of this engine):**
The backtest re-fits the NGR model inside each rolling-origin CV fold and
evaluates only on the test portion of that fold. Trained pickles in
`models/` are for **inference on future days**, never for replaying history
- using them here would be in-sample evaluation and would produce
fantasy-land returns. Per CLAUDE.md §5 Phase 2: "use `as_of <= signal_time`
for every feature. No exceptions."

Per the user's greenlit defaults: rolling-origin time-series CV, no random
shuffles, fee + fractional-Kelly applied, naive synthetic market as the
counter-party (since we don't have a historical Kalshi orderbook archive).

Conceptual flow:
    1. Load training/eval rows from the joined training set.
    2. Sort by valid_date; split with `rolling_origin_splits`.
    3. For each (train_idx, test_idx) fold:
         a. Fit fresh NGR on `train_idx` only.
         b. For each row in `test_idx`:
              - Generate synthetic Kalshi-style brackets centered on the forecast
              - Compute calibrated probability + naive-market quote per bracket
              - If |edge| > min after fees, simulate a trade and book P&L
    4. Aggregate test-only trades into a `BacktestResult`.

Strategies supported in v1:
    "weather_v1" - per-station NGR at lead=1, rolling-origin CV.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Final

import numpy as np
import polars as pl
import structlog

from kq.backtest.brackets import Bracket, generate_brackets
from kq.backtest.diagnostics import per_band_brier, per_month_metrics
from kq.backtest.metrics import equity_curve, hit_rate, max_drawdown
from kq.backtest.ndfd_benchmark import (
    NdfdLookup,
    fit_residual_stats,
    gaussian_exceedance,
    load_ndfd_lookup,
)
from kq.backtest.result import BacktestResult, TradeRecord
from kq.backtest.synthetic_market import MarketQuote, naive_market_quote
from kq.execution.fees import fee_per_contract
from kq.execution.kelly import fractional_kelly_stake
from kq.execution.maker_taker import MakerTakerPolicy
from kq.features.weather import build_training_set
from kq.models.calibration import brier_score, reliability_bins, summarize_reliability
from kq.models.climatology import StationClimatology, blend_probability
from kq.models.cv import rolling_origin_splits
from kq.models.isotonic_calibration import IsotonicCalibrator
from kq.models.raw_forecast import RawForecastModel
from kq.models.router import StrategyRouterConfig
from kq.models.weather_ngr import WeatherNGRModel
from kq.models.weather_skew_ngr import WeatherSkewNGRModel
from kq.storage.duckdb_store import connect

log = structlog.get_logger(__name__)

DEFAULT_BANKROLL_USD: Final = 1_000.0
DEFAULT_MIN_EDGE_PCT: Final = 4.0  # post-fee minimum edge to trade
DEFAULT_KELLY_FRACTION: Final = 0.15
DEFAULT_MAX_STAKE_USD: Final = 50.0
DEFAULT_INITIAL_TRAIN: Final = 60
DEFAULT_TEST_WINDOW: Final = 14


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    starting_bankroll_usd: float = DEFAULT_BANKROLL_USD
    min_edge_pct: float = DEFAULT_MIN_EDGE_PCT
    kelly_fraction: float = DEFAULT_KELLY_FRACTION
    max_stake_usd: float = DEFAULT_MAX_STAKE_USD
    n_brackets: int = 7
    bracket_spacing_f: float = 2.0
    lead_days: int = 1
    initial_train_size: int = DEFAULT_INITIAL_TRAIN
    test_window_size: int = DEFAULT_TEST_WINDOW
    # Phase 2 ext #3 — Pool-Adjacent-Violators recalibration on top of the
    # active model's raw probabilities. Per-fold fit, training-portion only.
    # Defaults on; toggle via the config (no CLI flag yet — A/B by editing).
    use_isotonic_recal: bool = True
    # Phase 2 ext #4 — replace NGR's Gaussian likelihood with skew-normal.
    # Falls back to Gaussian seed if the optimizer doesn't improve over
    # alpha=0, so this can only be neutral or better — strict-no-worse
    # property. Per-fold fit. Naive market sigma still derived from the
    # Gaussian NGR for fair counterparty comparison.
    use_skew_normal: bool = True
    # Phase 2 ext #5 — blend the (post-isotonic) model probability with a
    # per-(station, month) Gaussian climatology, weight = exp(-lead/tau).
    # At lead=1, tau=4 model gets ~78%; at lead=5 ~29%. Defends against
    # over-confident parametric tails at long lead.
    #
    # **Default OFF for v1.** Empirical finding (2026-04-30): at lead=1 the
    # blend is net-negative at every station (Brier-vs-NDFD regressions of
    # -8pp to -24pp). At lead=1 the model is sharp; pulling sharp-correct
    # predictions toward the diffuse climatology trades sharpness for a
    # wing-defense the v1 backtest doesn't need. The mechanism is ready for
    # lead 5-7 backtests when we add them. See ROADMAP §"Post-#16 update".
    use_climatology_blend: bool = False
    climatology_tau_days: float = 4.0
    # Phase 2 ext #2 — maker/taker decision policy. When `use_maker_orders`
    # is True, edge >= `maker_min_edge_pct` (above the skip threshold) posts
    # maker (1 tick inside spread, maker fee); below that, takers as before.
    # Default ON because the memo's "skip and you leave money on the floor"
    # framing applies to lead-1 too (model-agnostic).
    use_maker_orders: bool = True
    maker_min_edge_pct: float = 2.0  # 2 Kalshi ticks of edge buffer
    # Maker fill rate assumption for the backtest. 1.0 matches the memo's
    # stated savings; lower it for sensitivity analysis. Live executor
    # tracks realized fills separately.
    maker_fill_rate: float = 1.0


def run_backtest(
    *,
    db_path: Path,
    strategy: str = "weather_v1",
    config: BacktestConfig | None = None,
    router_config_path: Path | None = None,
) -> dict[str, BacktestResult]:
    """Run the rolling-origin backtest for every station with enough data.

    Strategies supported:
        "weather_v1"           — pure NGR per station (every station uses NGR).
        "weather_router_v1"    — per-station router; NGR or raw chosen by
                                 ``router_config_path`` (defaults to
                                 ``models/router_config.json``).
        "weather_all_raw_v1"   — pure RAW per station (every station uses
                                 ``RawForecastModel``). Used by the NDFD-aware
                                 router as the all-RAW comparison baseline
                                 against the all-NGR ``weather_v1`` manifest.
        "weather_reforecast_v1"— NGR fit on GEFSv12 reforecast data
                                 (model='gefsv12_reforecast') for each
                                 station ONCE (not per fold) — the reforecast
                                 archive is 2000-2019, all PIT-prior to our
                                 2024+ test window, so a single fit per
                                 station is honest. The pre-fit NGR is then
                                 used across all test rows. Per Phase 2 ext
                                 #6 / Hagedorn-Hamill-Whitaker 2008.

    Returns a dict keyed by station ICAO. Stations with fewer than
    `initial_train_size + test_window_size` rows are skipped.
    """
    if strategy not in (
        "weather_v1",
        "weather_router_v1",
        "weather_all_raw_v1",
        "weather_reforecast_v1",
    ):
        raise ValueError(f"unsupported strategy {strategy!r}")
    cfg = config or BacktestConfig()

    router_cfg: StrategyRouterConfig | None = None
    if strategy == "weather_router_v1":
        path = router_config_path or (Path("models") / "router_config.json")
        if not path.exists():
            raise FileNotFoundError(
                f"router config not found at {path}; "
                "run kq decide-router first or use --strategy weather_v1"
            )
        router_cfg = StrategyRouterConfig.load(path)

    con = connect(db_path)
    try:
        training = build_training_set(con)
        ndfd_lookup = load_ndfd_lookup(con)
        # Pre-fit reforecast NGRs (one per station) when the strategy needs
        # them. The reforecast archive (2000-2019) is all PIT-prior to our
        # backtest test window (2024-11+), so a single fit per station is
        # PIT-correct and saves N-fold compute.
        reforecast_ngrs: dict[str, WeatherNGRModel] = {}
        if strategy == "weather_reforecast_v1":
            reforecast_training = build_training_set(con, models=("gefsv12_reforecast",))
            reforecast_ngrs = _fit_per_station_ngr(reforecast_training)
            if not reforecast_ngrs:
                log.warning("backtest.reforecast_training_empty")
    finally:
        con.close()

    if training.is_empty():
        log.warning("backtest.no_data")
        return {}

    filtered = training.filter(
        (pl.col("lead_days") == cfg.lead_days)
        & pl.col("ens_mean_high_f").is_not_null()
        & pl.col("observed_high_f").is_not_null()
        # Reforecast rows (model='gefsv12_reforecast') are excluded from the
        # rolling-origin CV for ALL strategies:
        #   * weather_reforecast_v1 — already consumed separately as the
        #     pre-fit per-station NGR training set (see line above this
        #     block + _fit_per_station_ngr); including them in test rows
        #     would be in-sample evaluation. (Original Phase 2 ext #6 fix.)
        #   * weather_v1 / weather_router_v1 / weather_all_raw_v1 — operational
        #     strategies should fit + evaluate on operational forecasts only.
        #     Mixing 2015-2019 GEFSv12 reforecast pairs with 2024+ operational
        #     pairs contaminates the per-fold NGR fit and pollutes the test
        #     set with model-family pairs that the live system never sees.
        # Pre-existing bug exposed when 2015-2018 NWS ACIS observed truth was
        # backfilled (2026-05-01); previously the reforecast-vs-observed JOIN
        # silently dropped most reforecast rows, masking the issue.
        & (pl.col("model") != "gefsv12_reforecast")
    )
    filtered = filtered.sort(["station", "valid_date"])

    results: dict[str, BacktestResult] = {}
    min_required = cfg.initial_train_size + cfg.test_window_size
    for station in sorted(filtered["station"].unique().to_list()):
        station_df = filtered.filter(pl.col("station") == station)
        if station_df.height < min_required:
            log.warning(
                "backtest.thin_data_skipped",
                station=station,
                n=station_df.height,
                required=min_required,
            )
            continue
        results[station] = _backtest_one_station(
            station=station,
            df=station_df,
            cfg=cfg,
            strategy=strategy,
            router_cfg=router_cfg,
            ndfd_lookup=ndfd_lookup,
            reforecast_ngr=reforecast_ngrs.get(station),
        )
        log.info(
            "backtest.station_done",
            station=station,
            **{k: v for k, v in results[station].to_summary_dict().items() if k != "station"},
        )

    return results


def _backtest_one_station(  # noqa: PLR0915, PLR0912 — per-fold rolling-origin loop is intrinsically multi-step; splitting muddles the PIT discipline more than it clarifies
    *,
    station: str,
    df: pl.DataFrame,
    cfg: BacktestConfig,
    strategy: str,
    router_cfg: StrategyRouterConfig | None = None,
    ndfd_lookup: NdfdLookup | None = None,
    reforecast_ngr: WeatherNGRModel | None = None,
) -> BacktestResult:
    """Rolling-origin backtest for a single station.

    The model is RE-FIT per fold on training rows only; trades are simulated
    only on test rows. This is the key property that makes the result honest.

    For strategy='weather_router_v1', the per-station decision in router_cfg
    determines whether NGR or RawForecastModel produces the test-window
    probabilities. Either way the naive market sigma comes from the freshly-
    fit NGR's metadata (so the counter-party comparison is held constant).

    The optional ``ndfd_lookup`` injects NWS NBM-deterministic Tmax for an
    apples-to-apples Brier-vs-NDFD column. Per-fold Gaussian sigma is fit on
    the training portion only — same PIT discipline as the NGR fit. Test
    rows missing NDFD coverage carry NaN through and are filtered out of
    the NDFD comparison in ``_aggregate_results`` so the join is honest.
    """
    rows = df.sort("valid_date").to_dicts()
    n = len(rows)

    ens_means = np.asarray([float(r["ens_mean_high_f"]) for r in rows])
    observed = np.asarray([float(r["observed_high_f"]) for r in rows])
    valid_dates = [r["valid_date"] for r in rows]

    # Per-row NBM lookup — NaN where Open-Meteo's NBM history doesn't reach
    # (~pre-2024-11). The fold-level sigma fit drops these rows; the test-row
    # path also drops them so the Brier-vs-NDFD comparison only counts
    # evaluations with both predictions present.
    ndfd_dates = ndfd_lookup.for_station(station) if ndfd_lookup is not None else {}
    nbm_means = np.asarray([ndfd_dates.get(vd, float("nan")) for vd in valid_dates], dtype=float)

    use_raw = strategy == "weather_all_raw_v1" or (
        strategy == "weather_router_v1"
        and router_cfg is not None
        and router_cfg.strategy_for(station, default="ngr") == "raw"
    )

    bankroll = cfg.starting_bankroll_usd
    trades: list[TradeRecord] = []
    all_probs: list[float] = []
    all_outcomes: list[float] = []
    all_raw_probs: list[float] = []
    all_ndfd_probs: list[float] = []
    # Diagnostic-only accumulators — feed per-band + per-month breakdowns.
    all_bracket_idx: list[int] = []
    all_valid_dates: list[date] = []

    for train_idx, test_idx in rolling_origin_splits(
        n_samples=n,
        initial_train_size=cfg.initial_train_size,
        test_window_size=cfg.test_window_size,
    ):
        # Always fit the NGR — we need its raw_residual_std for the naive
        # market sigma even when we end up using the raw forecast for trading.
        ngr = WeatherNGRModel()
        ngr.fit(ens_means[train_idx], observed[train_idx])
        market_sigma_f = max(ngr.fit_metadata.get("raw_residual_std", 3.5), 1.0)
        # Phase 2 ext #4: optionally swap to skew-normal NGR for the active
        # (trading) model when not using RAW. Naive market sigma stays
        # Gaussian-NGR-derived to keep the counterparty comparison constant
        # across config variations.
        calibrated_model: WeatherNGRModel | WeatherSkewNGRModel
        if strategy == "weather_reforecast_v1" and reforecast_ngr is not None:
            # Phase 2 ext #6: use the pre-fit reforecast NGR (one fit per
            # station, not per fold). Reforecast 2000-2019 is all PIT-prior
            # to the test window, so the discipline holds trivially.
            calibrated_model = reforecast_ngr
        elif cfg.use_skew_normal:
            skew = WeatherSkewNGRModel()
            skew.fit(ens_means[train_idx], observed[train_idx])
            calibrated_model = skew
        else:
            calibrated_model = ngr
        # Strategy dispatch — router decides per-station which model emits the
        # trading probability. Naive-market quote is held constant.
        active_model: WeatherNGRModel | WeatherSkewNGRModel | RawForecastModel = (
            RawForecastModel(raw_sigma_f=market_sigma_f) if use_raw else calibrated_model
        )

        # Per-fold NBM (bias, sigma); None when the training window has too few
        # NDFD-covered rows. All test rows in this fold inherit None.
        # The bias is critical: empirical NBM bias on Open-Meteo's archive
        # ranges from -0.9 °F to -3.6 °F across our 6 stations. Skipping it
        # handicaps NDFD by up to 1.6 sigma on marine sites (verified spike
        # 2026-04-29). See ndfd_benchmark.fit_residual_stats docstring.
        ndfd_stats = fit_residual_stats(nbm_means[train_idx], observed[train_idx])

        # Phase 2 ext #3 — fit per-fold isotonic recalibrator on the active
        # model's training-portion (prob, outcome) pairs. Pools across all
        # brackets per the Pass 1 ext memo §3 ("calibrate by quintile of
        # model-predicted P, not by ticker"). Identity fallback when training
        # has fewer than `IsotonicCalibrator.min_pairs` pairs.
        iso_calibrator = (
            _fit_isotonic_for_fold(
                active_model=active_model,
                train_idx=train_idx,
                ens_means=ens_means,
                observed=observed,
                cfg=cfg,
            )
            if cfg.use_isotonic_recal
            else None
        )

        # Phase 2 ext #5 — fit per-fold per-(station, month) climatology
        # from training-portion observed truth. Used to blend model probs
        # toward climatology weighted by lead-time. Skips fitting when
        # disabled in cfg; predict_proba returns None for sparse buckets.
        climatology = (
            _fit_climatology_for_fold(
                station=station,
                train_idx=train_idx,
                observed=observed,
                valid_dates=valid_dates,
            )
            if cfg.use_climatology_blend
            else None
        )

        for i in test_idx:
            forecast_mean = ens_means[i]
            observed_high = observed[i]
            valid_date = valid_dates[i]
            forecast_arr = np.array([forecast_mean])
            nbm_mean_i = nbm_means[i]
            for bracket_idx, bracket in enumerate(
                generate_brackets(
                    forecast_mean,
                    n_brackets=cfg.n_brackets,
                    spacing_f=cfg.bracket_spacing_f,
                )
            ):
                raw_model_prob = float(
                    active_model.predict_proba(forecast_arr, bracket.threshold_f)[0]
                )
                recalibrated_prob = (
                    float(iso_calibrator.predict(np.array([raw_model_prob]))[0])
                    if iso_calibrator is not None
                    else raw_model_prob
                )
                # Phase 2 ext #5 — climatology blend applied AFTER isotonic
                # so the recalibrated distribution is what we damp toward
                # climatology, not the raw model output.
                if climatology is not None:
                    clim_prob = climatology.predict_proba(station, valid_date, bracket.threshold_f)
                    if clim_prob is not None:
                        model_prob = blend_probability(
                            recalibrated_prob,
                            clim_prob,
                            lead_days=cfg.lead_days,
                            tau_days=cfg.climatology_tau_days,
                        )
                    else:
                        model_prob = recalibrated_prob
                else:
                    model_prob = recalibrated_prob
                quote = naive_market_quote(forecast_mean, bracket, raw_sigma_f=market_sigma_f)
                outcome_yes = bool(observed_high > bracket.threshold_f)

                all_probs.append(model_prob)
                all_outcomes.append(1.0 if outcome_yes else 0.0)
                all_raw_probs.append(quote.mid)
                all_bracket_idx.append(bracket_idx)
                all_valid_dates.append(valid_date)
                if ndfd_stats is not None and not np.isnan(nbm_mean_i):
                    bias, sigma = ndfd_stats
                    all_ndfd_probs.append(
                        gaussian_exceedance(
                            mean=float(nbm_mean_i) - bias,
                            sigma=sigma,
                            threshold=bracket.threshold_f,
                        )
                    )
                else:
                    all_ndfd_probs.append(float("nan"))

                trade = _maybe_trade(
                    station=station,
                    valid_date=valid_date,
                    bracket=bracket,
                    model_prob=model_prob,
                    quote=quote,
                    outcome_yes=outcome_yes,
                    bankroll=bankroll,
                    cfg=cfg,
                )
                if trade is not None:
                    trades.append(trade)
                    bankroll += trade.pnl_usd

    return _aggregate_results(
        station=station,
        strategy=strategy,
        trades=trades,
        all_probs=np.asarray(all_probs),
        all_raw_probs=np.asarray(all_raw_probs),
        all_outcomes=np.asarray(all_outcomes),
        all_ndfd_probs=np.asarray(all_ndfd_probs),
        all_bracket_idx=np.asarray(all_bracket_idx, dtype=int),
        all_valid_dates=all_valid_dates,
        n_brackets=cfg.n_brackets,
        starting_bankroll=cfg.starting_bankroll_usd,
        final_bankroll=bankroll,
    )


def _fit_per_station_ngr(training: pl.DataFrame) -> dict[str, WeatherNGRModel]:
    """Fit a single NGR per station using the entire training set (no CV folds).

    Used by ``weather_reforecast_v1``: the GEFSv12 reforecast archive is
    2000-2019, all PIT-prior to our test window (2024-11+), so a single
    per-station fit is honest. Stations with too few training rows are
    omitted from the result dict.
    """
    if training.is_empty():
        return {}
    out: dict[str, WeatherNGRModel] = {}
    filtered = training.filter(
        pl.col("ens_mean_high_f").is_not_null() & pl.col("observed_high_f").is_not_null()
    )
    for station in sorted(filtered["station"].unique().to_list()):
        rows = filtered.filter(pl.col("station") == station)
        ens_means = np.asarray(rows["ens_mean_high_f"].to_list(), dtype=float)
        observed = np.asarray(rows["observed_high_f"].to_list(), dtype=float)
        if ens_means.size < 30:
            log.warning(
                "backtest.reforecast_thin_data_skipped",
                station=station,
                n=int(ens_means.size),
            )
            continue
        model = WeatherNGRModel()
        model.fit(ens_means, observed)
        out[station] = model
        log.info(
            "backtest.reforecast_ngr_fit",
            station=station,
            n=int(ens_means.size),
            ngr_form=model.fit_metadata.get("form"),
        )
    return out


def _fit_climatology_for_fold(
    *,
    station: str,
    train_idx: np.ndarray,
    observed: np.ndarray,
    valid_dates: list[date],
) -> StationClimatology:
    """Build per-(station, month) Gaussian climatology from training-fold rows.

    Per-fold so each fold's climatology is fit only on data PIT-prior to
    its test window — same discipline as the NGR fit. Cost is O(n_train);
    one pass over the training portion.
    """
    rows = [(valid_dates[i], float(observed[i])) for i in train_idx]
    return StationClimatology().fit_one_station(station, rows)


def _fit_isotonic_for_fold(
    *,
    active_model: WeatherNGRModel | WeatherSkewNGRModel | RawForecastModel,
    train_idx: np.ndarray,
    ens_means: np.ndarray,
    observed: np.ndarray,
    cfg: BacktestConfig,
) -> IsotonicCalibrator:
    """Build (raw_prob, outcome) pairs from training rows x bracket grid; fit isotonic.

    Pools across brackets — one calibrator per fold per station. Identity
    fallback when fewer than ``IsotonicCalibrator.min_pairs`` valid pairs.
    Cost is O(n_train x n_brackets) ``predict_proba`` calls; for the v1
    defaults (60 train rows x 7 brackets = 420 pairs) this is negligible.
    """
    raw_probs: list[float] = []
    outcomes: list[float] = []
    for i in train_idx:
        forecast_mean = ens_means[i]
        observed_high = observed[i]
        forecast_arr = np.array([forecast_mean])
        for bracket in generate_brackets(
            forecast_mean,
            n_brackets=cfg.n_brackets,
            spacing_f=cfg.bracket_spacing_f,
        ):
            p = float(active_model.predict_proba(forecast_arr, bracket.threshold_f)[0])
            raw_probs.append(p)
            outcomes.append(1.0 if observed_high > bracket.threshold_f else 0.0)
    cal = IsotonicCalibrator()
    cal.fit(np.asarray(raw_probs), np.asarray(outcomes))
    return cal


def _maybe_trade(
    *,
    station: str,
    valid_date: date,
    bracket: Bracket,
    model_prob: float,
    quote: MarketQuote,
    outcome_yes: bool,
    bankroll: float,
    cfg: BacktestConfig,
) -> TradeRecord | None:
    """Decide whether we have enough edge to trade; if so, return a TradeRecord.

    Phase 2 ext #2: when ``cfg.use_maker_orders`` is True, eligible trades
    post maker (1 tick inside spread, maker fee) instead of taker; the
    ``MakerTakerPolicy`` decides per-trade based on edge magnitude.
    """
    if model_prob > quote.ask:
        side = "BUY_YES"
        fill_price_taker = quote.ask
        prob_at_fill = model_prob
    elif model_prob < quote.bid:
        side = "BUY_NO"
        fill_price_taker = 1 - quote.bid
        prob_at_fill = 1 - model_prob
    else:
        return None  # model price falls inside the spread

    edge_pre_fee = prob_at_fill - fill_price_taker

    if cfg.use_maker_orders:
        policy = MakerTakerPolicy(
            maker_min_edge_pct=cfg.maker_min_edge_pct,
            skip_min_edge_pct=cfg.min_edge_pct,
        )
        decision = policy.decide(
            edge_pre_fee=edge_pre_fee,
            fill_price_taker=fill_price_taker,
        )
        if decision == "skip":
            return None
        if decision == "maker":
            order_type = "maker"
            fill_price = policy.maker_fill_price(fill_price_taker, side=side)
            fee_per = fee_per_contract(fill_price, side="maker")
        else:
            order_type = "taker"
            fill_price = fill_price_taker
            fee_per = fee_per_contract(fill_price, side="taker")
    else:
        # Legacy path: always taker.
        order_type = "taker"
        fill_price = fill_price_taker
        fee_per = fee_per_contract(fill_price, side="taker")
        edge_after_fee_pct = (edge_pre_fee - fee_per) * 100.0
        if edge_after_fee_pct < cfg.min_edge_pct:
            return None

    stake_usd = fractional_kelly_stake(
        prob=prob_at_fill,
        price=fill_price,
        bankroll_usd=bankroll,
        fraction=cfg.kelly_fraction,
        max_stake_usd=cfg.max_stake_usd,
    )
    if stake_usd <= 0:
        return None

    qty = max(1, math.floor(stake_usd / fill_price))
    fee_total = round(fee_per * qty, 4)

    won = outcome_yes if side == "BUY_YES" else not outcome_yes
    payout_per_contract = 1.0 if won else 0.0
    pnl = qty * (payout_per_contract - fill_price) - fee_total

    return TradeRecord(
        valid_date=valid_date,
        station=station,
        threshold_f=bracket.threshold_f,
        side=side,
        model_prob=model_prob,
        market_bid=quote.bid,
        market_ask=quote.ask,
        fill_price=fill_price,
        qty=qty,
        fee_usd=fee_total,
        settled_yes=outcome_yes,
        pnl_usd=round(pnl, 4),
        order_type=order_type,
    )


def _aggregate_results(
    *,
    station: str,
    strategy: str,
    trades: Sequence[TradeRecord],
    all_probs: np.ndarray,
    all_raw_probs: np.ndarray,
    all_outcomes: np.ndarray,
    all_ndfd_probs: np.ndarray,
    all_bracket_idx: np.ndarray,
    all_valid_dates: list[date],
    n_brackets: int,
    starting_bankroll: float,
    final_bankroll: float,
) -> BacktestResult:
    n_evaluated = int(all_probs.size)
    n_traded = len(trades)

    # Use the side-correct edge from TradeRecord.edge_pct — for BUY_NO trades,
    # the naive ``|model_prob - fill_price|`` formula compares unrelated YES-side
    # probability to NO-side fill price, inflating the apparent edge. See the
    # `TradeRecord.edge_pct` and `prob_at_fill` docstrings.
    pre_edges = [t.edge_pct for t in trades] or [0.0]
    post_edges = [t.edge_pct - (t.fee_usd / max(t.qty, 1)) * 100.0 for t in trades] or [0.0]

    if n_evaluated > 0:
        brier_cal = brier_score(np.clip(all_probs, 0.01, 0.99), all_outcomes)
        brier_raw_val = brier_score(np.clip(all_raw_probs, 0.01, 0.99), all_outcomes)
    else:
        brier_cal = float("nan")
        brier_raw_val = float("nan")
    improvement = (
        (brier_raw_val - brier_cal) / brier_raw_val * 100.0
        if (n_evaluated > 0 and brier_raw_val > 0)
        else 0.0
    )

    # NDFD comparison runs only on rows with both predictions present.
    # Re-computing the model's Brier on the same subset is what makes this
    # apples-to-apples — without it we'd be comparing brier(model) on the
    # full window vs brier(ndfd) on a partial window.
    ndfd_mask = ~np.isnan(all_ndfd_probs)
    n_with_ndfd = int(ndfd_mask.sum())
    if n_with_ndfd > 0:
        brier_ndfd = brier_score(
            np.clip(all_ndfd_probs[ndfd_mask], 0.01, 0.99),
            all_outcomes[ndfd_mask],
        )
        brier_model_subset = brier_score(
            np.clip(all_probs[ndfd_mask], 0.01, 0.99),
            all_outcomes[ndfd_mask],
        )
        improvement_vs_ndfd = (
            (brier_ndfd - brier_model_subset) / brier_ndfd * 100.0
            if brier_ndfd > 0
            else float("nan")
        )
        # Mean prob diff vs benchmark: mean(model_prob - ndfd_prob) over
        # matched evaluations. Positive → our model is more bullish than
        # NDFD on the YES leg, on average. Read in conjunction with
        # brier_improvement_vs_ndfd_pct. NOT closing-line value — we
        # don't have a Kalshi market close to anchor against.
        mean_prob_diff_pp = float((all_probs[ndfd_mask] - all_ndfd_probs[ndfd_mask]).mean() * 100.0)
    else:
        brier_ndfd = float("nan")
        brier_model_subset = float("nan")
        improvement_vs_ndfd = float("nan")
        mean_prob_diff_pp = float("nan")

    trade_dates = [t.valid_date for t in trades]
    trade_pnls = [t.pnl_usd for t in trades]
    curve = equity_curve(trade_dates, trade_pnls, starting_bankroll_usd=starting_bankroll)
    dd_usd, dd_pct = max_drawdown(curve)

    bins = reliability_bins(all_probs, all_outcomes, n_bins=10) if n_evaluated > 0 else []
    reliability = [
        {
            "lower": b.lower,
            "upper": b.upper,
            "n": b.n,
            "mean_predicted": None if math.isnan(b.mean_predicted) else b.mean_predicted,
            "mean_observed": None if math.isnan(b.mean_observed) else b.mean_observed,
        }
        for b in bins
    ]
    # Phase 5 #3 — n-aware reliability summary. The raw `reliability` list above
    # carries every bucket including small-n ones; the summary collapses to a
    # pass/fail over the statistically-meaningful subset (n >= min_n). See
    # `kq.models.calibration.summarize_reliability` docstring for the rationale.
    if bins:
        rs = summarize_reliability(bins)
        reliability_summary: dict[str, Any] = {
            "n_bins_total": rs.n_bins_total,
            "n_bins_qualifying": rs.n_bins_qualifying,
            "n_bins_failing": rs.n_bins_failing,
            "max_delta_pp": None if math.isnan(rs.max_delta_pp) else round(rs.max_delta_pp, 2),
            "max_delta_bin": rs.max_delta_bin,
            "passes_bar": rs.passes_bar,
            "min_n_threshold": rs.min_n_threshold,
            "tolerance_pp": rs.tolerance_pp,
        }
    else:
        reliability_summary = {}

    # Diagnostic deepens — answer "where does our model gain/lose vs NDFD?"
    # Both helpers operate on the matched subset internally; passing the full
    # arrays + the NaN sentinel keeps the engine ignorant of the masking.
    if n_evaluated > 0 and n_with_ndfd > 0:
        diagnostics: dict[str, Any] = {
            "per_band": per_band_brier(
                bracket_idx=all_bracket_idx,
                model_probs=all_probs,
                ndfd_probs=all_ndfd_probs,
                outcomes=all_outcomes,
                n_brackets=n_brackets,
            ),
            "per_month": per_month_metrics(
                valid_dates=all_valid_dates,
                model_probs=all_probs,
                ndfd_probs=all_ndfd_probs,
                outcomes=all_outcomes,
            ),
        }
    else:
        diagnostics = {}

    # Phase 2 ext #2 — maker/taker telemetry. `maker_fee_savings_usd` is what
    # we saved on the maker-typed trades vs the counterfactual taker fee at
    # the same fill price. Positive = real savings vs taker-only baseline.
    n_maker = sum(1 for t in trades if t.order_type == "maker")
    n_taker = len(trades) - n_maker
    maker_savings = 0.0
    for t in trades:
        if t.order_type != "maker":
            continue
        # Counterfactual taker fee at the SAME fill price (we already moved
        # 1 tick inside for maker; the price-improvement is a separate win
        # from the fee-discount, so this metric isolates the fee delta).
        ctf_taker_fee_per = fee_per_contract(t.fill_price, side="taker")
        ctf_taker_fee_total = round(ctf_taker_fee_per * t.qty, 4)
        maker_savings += ctf_taker_fee_total - t.fee_usd

    return BacktestResult(
        station=station,
        strategy=strategy,
        n_evaluated=n_evaluated,
        n_traded=n_traded,
        total_pnl_usd=float(final_bankroll - starting_bankroll),
        final_bankroll_usd=final_bankroll,
        starting_bankroll_usd=starting_bankroll,
        win_rate=hit_rate(trade_pnls),
        avg_edge_pct_pre_fee=float(np.mean(pre_edges)),
        avg_edge_pct_post_fee=float(np.mean(post_edges)),
        brier_calibrated=brier_cal,
        brier_raw=brier_raw_val,
        brier_improvement_pct=improvement,
        max_drawdown_usd=dd_usd,
        max_drawdown_pct=dd_pct,
        equity_curve=tuple(curve),
        reliability=reliability,
        trades=list(trades),
        n_evaluated_with_ndfd=n_with_ndfd,
        brier_ndfd=brier_ndfd,
        brier_model_ndfd_subset=brier_model_subset,
        brier_improvement_vs_ndfd_pct=improvement_vs_ndfd,
        mean_prob_diff_vs_ndfd_pp=mean_prob_diff_pp,
        diagnostics=diagnostics,
        n_maker_trades=n_maker,
        n_taker_trades=n_taker,
        maker_fee_savings_usd=round(maker_savings, 4),
        reliability_summary=reliability_summary,
    )
