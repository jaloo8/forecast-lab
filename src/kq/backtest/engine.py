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
from typing import Final

import numpy as np
import polars as pl
import structlog

from kq.backtest.brackets import Bracket, generate_brackets
from kq.backtest.metrics import equity_curve, hit_rate, max_drawdown
from kq.backtest.result import BacktestResult, TradeRecord
from kq.backtest.synthetic_market import MarketQuote, naive_market_quote
from kq.execution.fees import fee_per_contract
from kq.execution.kelly import fractional_kelly_stake
from kq.features.weather import build_training_set
from kq.models.calibration import brier_score, reliability_bins
from kq.models.cv import rolling_origin_splits
from kq.models.raw_forecast import RawForecastModel
from kq.models.router import StrategyRouterConfig
from kq.models.weather_ngr import WeatherNGRModel
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


def run_backtest(
    *,
    db_path: Path,
    strategy: str = "weather_v1",
    config: BacktestConfig | None = None,
    router_config_path: Path | None = None,
) -> dict[str, BacktestResult]:
    """Run the rolling-origin backtest for every station with enough data.

    Strategies supported:
        "weather_v1"        — pure NGR per station (every station uses NGR).
        "weather_router_v1" — per-station router; NGR or raw chosen by
                              `router_config_path` (defaults to
                              models/router_config.json).

    Returns a dict keyed by station ICAO. Stations with fewer than
    `initial_train_size + test_window_size` rows are skipped.
    """
    if strategy not in ("weather_v1", "weather_router_v1"):
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
    finally:
        con.close()

    if training.is_empty():
        log.warning("backtest.no_data")
        return {}

    filtered = training.filter(
        (pl.col("lead_days") == cfg.lead_days)
        & pl.col("ens_mean_high_f").is_not_null()
        & pl.col("observed_high_f").is_not_null()
    ).sort(["station", "valid_date"])

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
        )
        log.info(
            "backtest.station_done",
            station=station,
            **{k: v for k, v in results[station].to_summary_dict().items() if k != "station"},
        )

    return results


def _backtest_one_station(
    *,
    station: str,
    df: pl.DataFrame,
    cfg: BacktestConfig,
    strategy: str,
    router_cfg: StrategyRouterConfig | None = None,
) -> BacktestResult:
    """Rolling-origin backtest for a single station.

    The model is RE-FIT per fold on training rows only; trades are simulated
    only on test rows. This is the key property that makes the result honest.

    For strategy='weather_router_v1', the per-station decision in router_cfg
    determines whether NGR or RawForecastModel produces the test-window
    probabilities. Either way the naive market sigma comes from the freshly-
    fit NGR's metadata (so the counter-party comparison is held constant).
    """
    rows = df.sort("valid_date").to_dicts()
    n = len(rows)

    ens_means = np.asarray([float(r["ens_mean_high_f"]) for r in rows])
    observed = np.asarray([float(r["observed_high_f"]) for r in rows])
    valid_dates = [r["valid_date"] for r in rows]

    use_raw = (
        strategy == "weather_router_v1"
        and router_cfg is not None
        and router_cfg.strategy_for(station, default="ngr") == "raw"
    )

    bankroll = cfg.starting_bankroll_usd
    trades: list[TradeRecord] = []
    all_probs: list[float] = []
    all_outcomes: list[float] = []
    all_raw_probs: list[float] = []

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
        # Strategy dispatch — router decides per-station which model emits the
        # trading probability. Naive-market quote is held constant.
        active_model: WeatherNGRModel | RawForecastModel = (
            RawForecastModel(raw_sigma_f=market_sigma_f) if use_raw else ngr
        )

        for i in test_idx:
            forecast_mean = ens_means[i]
            observed_high = observed[i]
            valid_date = valid_dates[i]
            forecast_arr = np.array([forecast_mean])
            for bracket in generate_brackets(
                forecast_mean,
                n_brackets=cfg.n_brackets,
                spacing_f=cfg.bracket_spacing_f,
            ):
                model_prob = float(active_model.predict_proba(forecast_arr, bracket.threshold_f)[0])
                quote = naive_market_quote(forecast_mean, bracket, raw_sigma_f=market_sigma_f)
                outcome_yes = bool(observed_high > bracket.threshold_f)

                all_probs.append(model_prob)
                all_outcomes.append(1.0 if outcome_yes else 0.0)
                all_raw_probs.append(quote.mid)

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
        starting_bankroll=cfg.starting_bankroll_usd,
        final_bankroll=bankroll,
    )


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
    """Decide whether we have enough edge to trade; if so, return a TradeRecord."""
    if model_prob > quote.ask:
        side = "BUY_YES"
        fill_price = quote.ask
        prob_at_fill = model_prob
    elif model_prob < quote.bid:
        side = "BUY_NO"
        fill_price = 1 - quote.bid
        prob_at_fill = 1 - model_prob
    else:
        return None  # model price falls inside the spread

    edge = prob_at_fill - fill_price
    fee_per = fee_per_contract(fill_price, side="taker")
    edge_after_fee_pct = (edge - fee_per) * 100.0
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
    )


def _aggregate_results(
    *,
    station: str,
    strategy: str,
    trades: Sequence[TradeRecord],
    all_probs: np.ndarray,
    all_raw_probs: np.ndarray,
    all_outcomes: np.ndarray,
    starting_bankroll: float,
    final_bankroll: float,
) -> BacktestResult:
    n_evaluated = int(all_probs.size)
    n_traded = len(trades)

    pre_edges = [abs(t.model_prob - t.fill_price) * 100 for t in trades] or [0.0]
    post_edges = [
        (abs(t.model_prob - t.fill_price) - t.fee_usd / max(t.qty, 1)) * 100 for t in trades
    ] or [0.0]

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
    )
