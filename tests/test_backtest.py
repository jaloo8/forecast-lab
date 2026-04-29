"""Tests for the backtest engine, brackets, synthetic market, and metrics."""

from __future__ import annotations

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
