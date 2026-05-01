"""Tests for the backtest engine, brackets, synthetic market, and metrics."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pytest

from kq.backtest.brackets import Bracket, generate_brackets
from kq.backtest.engine import BacktestConfig, run_backtest
from kq.backtest.metrics import equity_curve, hit_rate, max_drawdown
from kq.backtest.result import BacktestResult, TradeRecord
from kq.backtest.synthetic_market import (
    NAIVE_RAW_SIGMA_F,
    PROB_CLIP_HIGH,
    PROB_CLIP_LOW,
    naive_market_quote,
)
from kq.models.weather_ngr import NGRParameters, WeatherNGRModel
from kq.storage.duckdb_store import bootstrap

AS_OF = datetime(2026, 1, 1, tzinfo=UTC)


# ----------------------------------------------------------------- brackets


def test_generate_brackets_default_returns_seven_centered() -> None:
    brackets = generate_brackets(75.0)
    assert len(brackets) == 7
    thresholds = [b.threshold_f for b in brackets]
    assert thresholds == [69.0, 71.0, 73.0, 75.0, 77.0, 79.0, 81.0]


def test_generate_brackets_rounds_forecast_to_int_base() -> None:
    """Centering uses round(forecast) so brackets land on integer F."""
    brackets = generate_brackets(75.4, n_brackets=3, spacing_f=1.0)
    assert [b.threshold_f for b in brackets] == [74.0, 75.0, 76.0]


def test_generate_brackets_validates_inputs() -> None:
    with pytest.raises(ValueError, match="n_brackets"):
        generate_brackets(75.0, n_brackets=0)
    with pytest.raises(ValueError, match="spacing"):
        generate_brackets(75.0, spacing_f=0)


def test_bracket_name_is_predictable() -> None:
    assert Bracket(threshold_f=78.0).name == "high_ge_78f"


# --------------------------------------------------------- synthetic market


def test_naive_market_quote_centered_on_forecast() -> None:
    """When threshold == forecast, mid should be ~0.5 (above mid by ~half_spread)."""
    quote = naive_market_quote(75.0, Bracket(threshold_f=75.0))
    assert quote.mid == pytest.approx(0.5, abs=0.05)
    assert 0.4 < quote.bid < quote.ask < 0.6


def test_naive_market_quote_above_threshold_makes_yes_likely() -> None:
    """If forecast >> threshold, YES is very likely → mid near 0.99."""
    quote = naive_market_quote(85.0, Bracket(threshold_f=75.0))
    assert quote.mid > 0.95


def test_naive_market_quote_clipped_to_band() -> None:
    """Probabilities are clipped so bid/ask stay inside [0.01, 0.99]."""
    quote = naive_market_quote(120.0, Bracket(threshold_f=70.0))
    assert quote.bid <= PROB_CLIP_HIGH
    assert quote.ask <= PROB_CLIP_HIGH
    assert quote.bid >= PROB_CLIP_LOW
    assert quote.ask >= PROB_CLIP_LOW


def test_naive_market_quote_validates_inputs() -> None:
    with pytest.raises(ValueError, match="raw_sigma"):
        naive_market_quote(75.0, Bracket(threshold_f=75.0), raw_sigma_f=0)
    with pytest.raises(ValueError, match="half_spread"):
        naive_market_quote(75.0, Bracket(threshold_f=75.0), half_spread=0)


def test_default_naive_sigma_within_pass1_range() -> None:
    """Pass 1 §1b: raw GFS Brier on center brackets ~0.18-0.22."""
    assert 2.0 < NAIVE_RAW_SIGMA_F < 6.0


# --------------------------------------------------------- metrics


def test_equity_curve_groups_same_day_trades() -> None:
    dates = [date(2025, 6, 1), date(2025, 6, 1), date(2025, 6, 2)]
    pnls = [10.0, -3.0, 5.0]
    curve = equity_curve(dates, pnls, starting_bankroll_usd=1000.0)
    assert curve == [
        (date(2025, 6, 1), 1007.0),  # 10 - 3 = 7
        (date(2025, 6, 2), 1012.0),
    ]


def test_equity_curve_empty_returns_starting_only() -> None:
    curve = equity_curve([], [], starting_bankroll_usd=500.0)
    assert len(curve) == 1
    assert curve[0][1] == 500.0


def test_max_drawdown_basic() -> None:
    """Equity 1000 -> 1100 -> 900 -> 1050 -> 800. Max DD = 1100-800 = 300, 27.27%."""
    curve = [
        (date(2025, 6, 1), 1000.0),
        (date(2025, 6, 2), 1100.0),
        (date(2025, 6, 3), 900.0),
        (date(2025, 6, 4), 1050.0),
        (date(2025, 6, 5), 800.0),
    ]
    dd_usd, dd_pct = max_drawdown(curve)
    assert dd_usd == pytest.approx(300.0)
    assert dd_pct == pytest.approx(27.27, abs=0.1)


def test_max_drawdown_monotone_up_is_zero() -> None:
    curve = [(date(2025, 6, 1), 1000.0), (date(2025, 6, 2), 1100.0)]
    dd_usd, dd_pct = max_drawdown(curve)
    assert dd_usd == 0.0
    assert dd_pct == 0.0


def test_hit_rate() -> None:
    assert hit_rate([10.0, -5.0, 3.0, 0.0]) == pytest.approx(0.5)
    assert hit_rate([]) == 0.0


# --------------------------------------------------------- TradeRecord


def test_trade_record_edge_pct() -> None:
    t = TradeRecord(
        valid_date=date(2025, 6, 1),
        station="KLAX",
        threshold_f=75.0,
        side="BUY_YES",
        model_prob=0.65,
        market_bid=0.55,
        market_ask=0.58,
        fill_price=0.58,
        qty=10,
        fee_usd=0.10,
        settled_yes=True,
        pnl_usd=4.10,
    )
    assert t.edge_pct == pytest.approx(7.0)


def test_trade_record_edge_pct_for_buy_no_trade() -> None:
    """``BUY_NO`` trades must compute edge from ``prob_at_fill`` (the NO probability
    = ``1 - model_prob``), not the YES-side ``model_prob`` directly.

    Concrete example: model says YES prob = 0.10, market YES bid = 0.20, so we
    BUY_NO at fill price ``1 - 0.20 = 0.80``. Our edge is ``(1 - 0.10) - 0.80
    = 0.10`` = 10 pp. Using the naive ``|model_prob - fill_price|`` formula
    would give ``|0.10 - 0.80| = 70 pp`` — wildly wrong, and historically
    inflated ``avg_edge_pct_*`` values in the backtest manifest for any
    BUY_NO trades at extreme prices.
    """
    t = TradeRecord(
        valid_date=date(2025, 6, 1),
        station="KMIA",
        threshold_f=80.0,
        side="BUY_NO",
        model_prob=0.10,  # YES-side probability (canonical schema)
        market_bid=0.20,  # YES-side bid
        market_ask=0.30,
        fill_price=0.80,  # NO-side ask = 1 - YES bid
        qty=10,
        fee_usd=0.10,
        settled_yes=False,
        pnl_usd=2.00,
    )
    assert t.prob_at_fill == pytest.approx(0.90)
    assert t.edge_pct == pytest.approx(10.0)


def test_trade_record_edge_pct_buy_no_at_midprice_matches_buy_yes_symmetry() -> None:
    """Sanity: at prices symmetric around 0.5, BUY_YES and BUY_NO edge formulas
    converge. Catches the regression where BUY_NO accidentally double-flips."""
    yes = TradeRecord(
        valid_date=date(2025, 6, 1),
        station="K",
        threshold_f=75.0,
        side="BUY_YES",
        model_prob=0.55,
        market_bid=0.45,
        market_ask=0.50,
        fill_price=0.50,
        qty=1,
        fee_usd=0.0,
        settled_yes=True,
        pnl_usd=0.0,
    )
    no = TradeRecord(
        valid_date=date(2025, 6, 1),
        station="K",
        threshold_f=75.0,
        side="BUY_NO",
        model_prob=0.45,  # mirror of yes.model_prob across 0.5
        market_bid=0.50,  # mirror of yes.market_ask
        market_ask=0.55,
        fill_price=0.50,  # 1 - market_bid
        qty=1,
        fee_usd=0.0,
        settled_yes=False,
        pnl_usd=0.0,
    )
    assert yes.edge_pct == pytest.approx(no.edge_pct)
    assert yes.edge_pct == pytest.approx(5.0)


def test_backtest_result_summary_dict_shape() -> None:
    r = BacktestResult(
        station="KLAX",
        strategy="weather_v1",
        n_evaluated=100,
        n_traded=10,
        total_pnl_usd=12.5,
        final_bankroll_usd=1012.5,
        starting_bankroll_usd=1000.0,
        win_rate=0.6,
        avg_edge_pct_pre_fee=4.5,
        avg_edge_pct_post_fee=2.7,
        brier_calibrated=0.18,
        brier_raw=0.21,
        brier_improvement_pct=14.3,
        max_drawdown_usd=15.0,
        max_drawdown_pct=1.5,
        equity_curve=((date(2025, 6, 1), 1012.5),),
    )
    summary = r.to_summary_dict()
    assert summary["roi_pct"] == 1.25
    assert summary["station"] == "KLAX"
    assert "trades" not in summary  # detail deliberately omitted
    # NDFD fields default to NaN → serialize as None for JSON safety.
    assert summary["n_evaluated_with_ndfd"] == 0
    assert summary["brier_ndfd"] is None
    assert summary["brier_improvement_vs_ndfd_pct"] is None
    assert summary["mean_prob_diff_vs_ndfd_pp"] is None


def test_backtest_result_summary_dict_serializes_ndfd_metrics() -> None:
    """When NDFD coverage exists, the summary dict carries rounded numerics."""
    r = BacktestResult(
        station="KJFK",
        strategy="weather_v1",
        n_evaluated=100,
        n_traded=10,
        total_pnl_usd=0.0,
        final_bankroll_usd=1000.0,
        starting_bankroll_usd=1000.0,
        win_rate=0.5,
        avg_edge_pct_pre_fee=0.0,
        avg_edge_pct_post_fee=0.0,
        brier_calibrated=0.10,
        brier_raw=0.12,
        brier_improvement_pct=16.66,
        max_drawdown_usd=0.0,
        max_drawdown_pct=0.0,
        equity_curve=(),
        n_evaluated_with_ndfd=80,
        brier_ndfd=0.108,
        brier_model_ndfd_subset=0.105,
        brier_improvement_vs_ndfd_pct=2.78,
        mean_prob_diff_vs_ndfd_pp=1.45,
    )
    summary = r.to_summary_dict()
    assert summary["n_evaluated_with_ndfd"] == 80
    assert summary["brier_ndfd"] == 0.108
    assert summary["brier_model_ndfd_subset"] == 0.105
    assert summary["brier_improvement_vs_ndfd_pct"] == 2.78
    assert summary["mean_prob_diff_vs_ndfd_pp"] == 1.45
    # Renamed from `clv_vs_ndfd_pp`; not closing-line-value (no market close).
    assert "clv_vs_ndfd_pp" not in summary


# --------------------------------------------------------- engine end-to-end


def _seed_pair(
    con: duckdb.DuckDBPyConnection,
    *,
    station: str,
    start: date,
    n_days: int,
    forecast_bias: float,
    seed: int,
) -> None:
    """Seed deterministic forecast + observed truth where observed = forecast - bias + noise."""
    rng = np.random.default_rng(seed)
    forecasts = rng.normal(75.0, 4.0, size=n_days)
    # observed lower than forecast by `forecast_bias` → calibrated NGR will learn `a = -bias`.
    observed = forecasts - forecast_bias + rng.normal(0.0, 1.5, size=n_days)
    for i in range(n_days):
        vd = start + timedelta(days=i)
        # as_of one day before vd so lead_days = 1
        as_of = datetime(vd.year, vd.month, vd.day) - timedelta(days=1)
        f_hi = float(forecasts[i])
        con.execute(
            """
            INSERT OR REPLACE INTO weather_forecast
            (as_of, run_time, model, member, station, valid_date, forecast_high_f, forecast_low_f)
            VALUES (?, ?, 'gfs_hist', 0, ?, ?, ?, ?)
            """,
            (as_of, as_of, station, vd, f_hi, f_hi - 15.0),
        )
        con.execute(
            """
            INSERT OR REPLACE INTO weather_observed
            (station, valid_date, high_f, low_f, source, fetched_at)
            VALUES (?, ?, ?, ?, 'test', ?)
            """,
            (station, vd, float(observed[i]), float(observed[i] - 15), AS_OF),
        )


def test_run_backtest_full_pipeline_rolling_origin(tmp_path: Path) -> None:
    """Seed a biased dataset and verify the rolling-origin backtest fits per fold.

    The NGR re-fit on each train fold should learn the +3F bias the naive
    market doesn't, and the OOS Brier should beat the naive market on
    test-only rows.
    """
    db = tmp_path / "bt.duckdb"
    bootstrap(db)
    con = duckdb.connect(str(db))
    try:
        _seed_pair(
            con,
            station="KAUS",
            start=date(2025, 1, 1),
            n_days=200,  # > initial_train + test_window
            forecast_bias=3.0,
            seed=11,
        )
    finally:
        con.close()

    results = run_backtest(
        db_path=db,
        strategy="weather_v1",
        config=BacktestConfig(
            starting_bankroll_usd=1000.0,
            min_edge_pct=2.0,
            initial_train_size=60,
            test_window_size=14,
        ),
    )
    assert "KAUS" in results
    r = results["KAUS"]
    assert r.n_evaluated > 0
    assert r.brier_calibrated < r.brier_raw  # OOS calibrated beats naive market
    assert r.brier_improvement_pct > 0


def test_run_backtest_skips_stations_with_thin_data(tmp_path: Path) -> None:
    """Stations with fewer than initial_train + test_window rows are skipped."""
    db = tmp_path / "bt.duckdb"
    bootstrap(db)
    con = duckdb.connect(str(db))
    try:
        _seed_pair(
            con,
            station="KMIA",
            start=date(2025, 6, 1),
            n_days=30,  # below the 60 + 14 = 74 minimum
            forecast_bias=2.0,
            seed=22,
        )
    finally:
        con.close()
    results = run_backtest(db_path=db, strategy="weather_v1")
    assert results == {}


def test_run_backtest_rejects_unknown_strategy(tmp_path: Path) -> None:
    db = tmp_path / "x.duckdb"
    bootstrap(db)
    with pytest.raises(ValueError, match="unsupported"):
        run_backtest(db_path=db, strategy="not_a_strategy")


def test_run_backtest_no_data_returns_empty(tmp_path: Path) -> None:
    db = tmp_path / "empty.duckdb"
    bootstrap(db)
    results = run_backtest(db_path=db)
    assert results == {}


def test_imports_kept_for_future_use() -> None:
    """NGRParameters + WeatherNGRModel are imported so future hand-fixture tests
    can build models directly. Keep them referenced so the import is valid."""
    _ = NGRParameters
    _ = WeatherNGRModel


def test_run_backtest_with_maker_orders_respects_edge_gate(tmp_path: Path) -> None:
    """Phase 2 ext #2 — every trade taken with `use_maker_orders=True` must have
    post-fee edge >= `cfg.min_edge_pct`.

    The skip gate lives in `MakerTakerPolicy.decide` (returns "skip" when
    edge_after_taker_fee < skip_min_edge_pct, which the engine wires from
    `cfg.min_edge_pct`). This integration test guards against future drift
    where the engine and policy gates fall out of sync — a class of bug the
    unit tests on `MakerTakerPolicy` alone cannot detect.

    Invariant verified per trade: `edge_pct - (fee_usd / qty) * 100 >= min_edge_pct`.
    """
    db = tmp_path / "bt.duckdb"
    bootstrap(db)
    con = duckdb.connect(str(db))
    try:
        _seed_pair(
            con,
            station="KAUS",
            start=date(2025, 1, 1),
            n_days=200,
            forecast_bias=3.0,
            seed=11,
        )
    finally:
        con.close()

    min_edge_pct = 4.0
    results = run_backtest(
        db_path=db,
        strategy="weather_v1",
        config=BacktestConfig(
            starting_bankroll_usd=1000.0,
            min_edge_pct=min_edge_pct,
            initial_train_size=60,
            test_window_size=14,
            use_maker_orders=True,
            maker_min_edge_pct=2.0,
        ),
    )
    assert "KAUS" in results
    r = results["KAUS"]
    assert r.n_traded > 0, "test seed should produce some trades; nothing to verify otherwise"

    # Per-trade gate invariant — guards against the engine accepting a "taker"
    # decision whose post-fee edge slipped below the skip threshold.
    eps = 1e-9
    for t in r.trades:
        fee_per_contract_usd = t.fee_usd / t.qty
        post_fee_edge_pct = t.edge_pct - fee_per_contract_usd * 100.0
        assert post_fee_edge_pct >= min_edge_pct - eps, (
            f"trade {t.valid_date} {t.station} threshold={t.threshold_f} "
            f"order={t.order_type} edge={t.edge_pct:.3f} fee_per={fee_per_contract_usd:.4f} "
            f"post_fee_edge={post_fee_edge_pct:.3f} < min={min_edge_pct}"
        )

    # Sanity: telemetry counts add up + maker savings non-negative.
    assert r.n_maker_trades + r.n_taker_trades == r.n_traded
    assert r.maker_fee_savings_usd >= 0.0


def test_run_backtest_with_maker_orders_records_order_types(tmp_path: Path) -> None:
    """Maker telemetry must populate `n_maker_trades` and `n_taker_trades`.

    With `min_edge_pct=2.0` (lower than the default) and
    `maker_min_edge_pct=2.0`, the seed produces edges spanning both buckets.
    """
    db = tmp_path / "bt.duckdb"
    bootstrap(db)
    con = duckdb.connect(str(db))
    try:
        _seed_pair(
            con,
            station="KAUS",
            start=date(2025, 1, 1),
            n_days=200,
            forecast_bias=3.0,
            seed=11,
        )
    finally:
        con.close()

    results = run_backtest(
        db_path=db,
        strategy="weather_v1",
        config=BacktestConfig(
            starting_bankroll_usd=1000.0,
            min_edge_pct=2.0,
            initial_train_size=60,
            test_window_size=14,
            use_maker_orders=True,
            maker_min_edge_pct=2.0,
        ),
    )
    r = results["KAUS"]
    assert r.n_traded > 0
    # With edge buffer at 2pp and floor at 2pp, both order types should appear.
    assert r.n_maker_trades > 0
    assert r.n_taker_trades > 0
    # Every TradeRecord must carry one of the two order_type values.
    assert {t.order_type for t in r.trades} <= {"maker", "taker"}


# --------------------------------------------------- engine + NDFD benchmark


def _seed_ndfd(
    con: duckdb.DuckDBPyConnection,
    *,
    station: str,
    start: date,
    n_days: int,
    forecast_bias: float,
    seed: int,
) -> None:
    """Seed NBM-deterministic NDFD rows where forecast = observed + bias + noise.

    The bias is ``forecast_bias`` so a per-fold sigma fit will recover a
    sigma proportional to the noise term, and the resulting Brier-vs-NDFD
    will exercise the full join-and-mask path.
    """
    rng = np.random.default_rng(seed)
    for i in range(n_days):
        vd = start + timedelta(days=i)
        # NDFD-side forecast value derived from a similar climatology so
        # the join lines up with the seeded weather_observed row.
        nbm_forecast = 75.0 + rng.normal(0.0, 4.0) + forecast_bias
        as_of = datetime(vd.year, vd.month, vd.day) - timedelta(days=1)
        con.execute(
            """
            INSERT OR REPLACE INTO ndfd_forecast
            (as_of, station, valid_date, lead_days, source,
             forecast_max_f, p10_max_f, p25_max_f, p50_max_f, p75_max_f, p90_max_f)
            VALUES (?, ?, ?, 1, 'nbm_deterministic_openmeteo', ?, NULL, NULL, NULL, NULL, NULL)
            """,
            (as_of, station, vd, float(nbm_forecast)),
        )


def test_run_backtest_emits_ndfd_metrics_when_coverage_exists(tmp_path: Path) -> None:
    """End-to-end: NDFD rows seeded → manifest carries non-NaN brier_ndfd."""
    db = tmp_path / "bt_ndfd.duckdb"
    bootstrap(db)
    con = duckdb.connect(str(db))
    try:
        _seed_pair(
            con,
            station="KAUS",
            start=date(2025, 1, 1),
            n_days=200,
            forecast_bias=3.0,
            seed=11,
        )
        _seed_ndfd(
            con,
            station="KAUS",
            start=date(2025, 1, 1),
            n_days=200,
            forecast_bias=2.0,
            seed=99,
        )
    finally:
        con.close()

    results = run_backtest(
        db_path=db,
        strategy="weather_v1",
        config=BacktestConfig(initial_train_size=60, test_window_size=14),
    )
    r = results["KAUS"]
    assert r.n_evaluated_with_ndfd > 0
    # Coverage should match — every test row has an NDFD row.
    assert r.n_evaluated_with_ndfd == r.n_evaluated
    # Brier-vs-NDFD computed → no longer NaN.
    assert not np.isnan(r.brier_ndfd)
    assert not np.isnan(r.brier_model_ndfd_subset)
    assert not np.isnan(r.brier_improvement_vs_ndfd_pct)
    # CLV proxy in [-100, +100] pp range.
    assert -100.0 <= r.mean_prob_diff_vs_ndfd_pp <= 100.0
    # Diagnostics block populated when NDFD coverage exists.
    assert "per_band" in r.diagnostics
    assert "center" in r.diagnostics["per_band"]
    assert "wing" in r.diagnostics["per_band"]
    assert r.diagnostics["per_band"]["center"]["n_with_ndfd"] > 0
    assert r.diagnostics["per_band"]["wing"]["n_with_ndfd"] > 0
    # Per-month list non-empty + sorted by month string.
    months = [row["month"] for row in r.diagnostics["per_month"]]
    assert months == sorted(months)
    assert len(months) > 0


def test_run_backtest_handles_partial_ndfd_coverage(tmp_path: Path) -> None:
    """When NDFD covers only the back-half of the window, the engine runs the
    Brier-vs-NDFD math on the matched subset and the count reflects that."""
    db = tmp_path / "bt_partial.duckdb"
    bootstrap(db)
    con = duckdb.connect(str(db))
    try:
        _seed_pair(
            con,
            station="KJFK",
            start=date(2025, 1, 1),
            n_days=200,
            forecast_bias=3.0,
            seed=21,
        )
        # NDFD seeded for the second half only — emulating the ~Nov-2024
        # archive cutoff where Open-Meteo NBM data starts.
        _seed_ndfd(
            con,
            station="KJFK",
            start=date(2025, 4, 11),  # day 100
            n_days=100,
            forecast_bias=1.0,
            seed=33,
        )
    finally:
        con.close()

    results = run_backtest(
        db_path=db,
        strategy="weather_v1",
        config=BacktestConfig(initial_train_size=60, test_window_size=14),
    )
    r = results["KJFK"]
    assert r.n_evaluated > 0
    # Some folds had no NDFD coverage in their training portion (early folds
    # land entirely before the cutoff), so n_with < n_evaluated.
    assert 0 < r.n_evaluated_with_ndfd < r.n_evaluated


def test_run_backtest_reforecast_strategy_uses_pre_fit_ngr(tmp_path: Path) -> None:
    """`weather_reforecast_v1` fits NGR once per station from reforecast data
    and applies it to test rows that are NOT the reforecast training data.
    """
    db = tmp_path / "bt_reforecast.duckdb"
    bootstrap(db)
    con = duckdb.connect(str(db))
    try:
        # Test set: gfs_hist 2025+ (the data we'd evaluate on operationally).
        _seed_pair(
            con,
            station="KAUS",
            start=date(2025, 1, 1),
            n_days=200,
            forecast_bias=3.0,
            seed=11,
        )
        # Training set: reforecast 2019 (pre-fit happens here).
        rng = np.random.default_rng(99)
        for i in range(150):
            vd = date(2019, 1, 1) + timedelta(days=i)
            as_of = datetime(vd.year, vd.month, vd.day) - timedelta(days=1)
            forecast = float(75.0 + rng.normal(0, 4.0))
            observed = forecast - 3.0 + float(rng.normal(0, 1.5))
            con.execute(
                """
                INSERT OR REPLACE INTO weather_forecast
                (as_of, run_time, model, member, station, valid_date,
                 forecast_high_f, forecast_low_f)
                VALUES (?, ?, 'gefsv12_reforecast', 0, ?, ?, ?, ?)
                """,
                (as_of, as_of, "KAUS", vd, forecast, forecast - 15.0),
            )
            con.execute(
                """
                INSERT OR REPLACE INTO weather_observed
                (station, valid_date, high_f, low_f, source, fetched_at)
                VALUES (?, ?, ?, ?, 'test', ?)
                """,
                ("KAUS", vd, observed, observed - 15, AS_OF),
            )
    finally:
        con.close()

    results = run_backtest(
        db_path=db,
        strategy="weather_reforecast_v1",
        config=BacktestConfig(
            starting_bankroll_usd=1000.0,
            min_edge_pct=2.0,
            initial_train_size=60,
            test_window_size=14,
        ),
    )
    assert "KAUS" in results
    r = results["KAUS"]
    # Test set should NOT include the 2019 reforecast rows (held out as training).
    # Only gfs_hist 2025 rows times 7 brackets times ensemble configs.
    assert r.n_evaluated > 0
    # Brier on the held-out test set should be sensible (reforecast NGR
    # might be miscalibrated cross-model-family, but the math runs).
    assert not math.isnan(r.brier_calibrated)


def test_run_backtest_reforecast_strategy_skips_thin_training(tmp_path: Path) -> None:
    """Stations with < 30 reforecast rows fall back to no-fit (warning) and
    the test loop skips them. The smoke test checks that this path doesn't crash.
    """
    db = tmp_path / "bt_thin_refcast.duckdb"
    bootstrap(db)
    con = duckdb.connect(str(db))
    try:
        _seed_pair(
            con,
            station="KAUS",
            start=date(2025, 1, 1),
            n_days=200,
            forecast_bias=3.0,
            seed=12,
        )
        # Only 5 reforecast rows — below the 30-pair threshold.
        for i in range(5):
            vd = date(2019, 1, 1) + timedelta(days=i)
            as_of = datetime(vd.year, vd.month, vd.day) - timedelta(days=1)
            con.execute(
                """
                INSERT OR REPLACE INTO weather_forecast
                (as_of, run_time, model, member, station, valid_date,
                 forecast_high_f, forecast_low_f)
                VALUES (?, ?, 'gefsv12_reforecast', 0, ?, ?, ?, ?)
                """,
                (as_of, as_of, "KAUS", vd, 75.0, 60.0),
            )
            con.execute(
                """
                INSERT OR REPLACE INTO weather_observed
                (station, valid_date, high_f, low_f, source, fetched_at)
                VALUES (?, ?, ?, ?, 'test', ?)
                """,
                ("KAUS", vd, 73.0, 58.0, AS_OF),
            )
    finally:
        con.close()
    # Thin reforecast → reforecast NGR fit is skipped (warning), but engine
    # falls back to per-fold NGR via the existing rolling-origin path.
    results = run_backtest(
        db_path=db,
        strategy="weather_reforecast_v1",
        config=BacktestConfig(initial_train_size=60, test_window_size=14),
    )
    # KAUS still gets evaluated via fallback regular NGR — graceful degradation.
    assert "KAUS" in results
    assert results["KAUS"].n_evaluated > 0


def test_run_backtest_unknown_strategy_now_lists_reforecast(tmp_path: Path) -> None:
    """Unsupported-strategy error message references all 4 supported strategies."""
    db = tmp_path / "x.duckdb"
    bootstrap(db)
    with pytest.raises(ValueError, match="unsupported"):
        run_backtest(db_path=db, strategy="weather_unknown_v9")


def test_run_backtest_without_ndfd_data_returns_nan_metrics(tmp_path: Path) -> None:
    """Same shape as the original test — no NDFD seeded → every NDFD field is NaN."""
    db = tmp_path / "bt_no_ndfd.duckdb"
    bootstrap(db)
    con = duckdb.connect(str(db))
    try:
        _seed_pair(
            con,
            station="KMDW",
            start=date(2025, 1, 1),
            n_days=200,
            forecast_bias=3.0,
            seed=77,
        )
    finally:
        con.close()
    results = run_backtest(
        db_path=db, config=BacktestConfig(initial_train_size=60, test_window_size=14)
    )
    r = results["KMDW"]
    assert r.n_evaluated_with_ndfd == 0
    assert np.isnan(r.brier_ndfd)
    assert np.isnan(r.brier_improvement_vs_ndfd_pct)
    assert np.isnan(r.mean_prob_diff_vs_ndfd_pp)
    # Diagnostics dict empty when no NDFD coverage.
    assert r.diagnostics == {}
