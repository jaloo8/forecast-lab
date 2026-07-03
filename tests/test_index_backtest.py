"""Index-brackets backtest tests: CV/PIT discipline + manifest honesty.

The synthetic series have KNOWN generating processes, so the assertions
pin statistical behavior (calibrated PIT under a well-specified model,
HAR-RV skill under vol clustering) rather than incidental numbers.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from kq.backtest.index_brackets import (
    IndexBacktestConfig,
    build_ladder,
    market_implied_comparison,
    run_index_backtest,
)
from kq.clients.yahoo_chart import IndexDailyBar
from kq.flows import run_index_backtest as flow
from kq.storage.duckdb_store import bootstrap, connect
from kq.storage.repositories.index_daily import insert_index_daily

_CFG = IndexBacktestConfig(initial_train_size=250, test_window_size=25)


def _dates(n: int) -> list[date]:
    start = date(2024, 1, 2)
    return [start + timedelta(days=i) for i in range(n)]


def _gbm_closes(rng: np.random.Generator, n: int, *, sigma: float = 0.008) -> np.ndarray:
    returns = rng.normal(0.0, sigma, n - 1)
    return 7500.0 * np.exp(np.concatenate([[0.0], np.cumsum(returns)]))


# --------------------------- ladder geometry ---------------------------


def test_ladder_mirrors_venue_geometry() -> None:
    ladder = build_ladder(7812.0, symbol="SPX", half_brackets=7)
    assert len(ladder) == 17  # 15 betweens + 2 tails
    kinds = [s.kind for s in ladder]
    assert kinds[0] == "less" and kinds[-1] == "greater"
    assert set(kinds[1:-1]) == {"between"}
    center = ladder[8]  # the bracket the previous close sits in
    assert center.floor == pytest.approx(7800.0)
    assert center.cap == pytest.approx(7824.9999)
    # Tail strikes reuse the venue's epsilon encoding.
    assert ladder[0].cap == pytest.approx(7800.0 - 7 * 25.0)
    assert ladder[-1].floor == pytest.approx(7800.0 + 8 * 25.0 - 0.0001)


def test_ladder_nasdaq_uses_coarser_width_and_epsilon() -> None:
    ladder = build_ladder(31550.0, symbol="NDX", half_brackets=7)
    center = ladder[8]
    assert center.floor == pytest.approx(31500.0)
    assert center.cap == pytest.approx(31599.99)


# --------------------------- CV / PIT discipline ---------------------------


def test_pit_calibrated_when_model_is_well_specified() -> None:
    """Constant-sigma Gaussian world: HAR-RV is (asymptotically) correctly
    specified, so PIT over the test windows must look Uniform(0,1)."""
    rng = np.random.default_rng(42)
    closes = _gbm_closes(rng, 600)
    result = run_index_backtest(_dates(600), closes, symbol="SPX", config=_CFG)
    assert result is not None
    assert result.pit_mean == pytest.approx(0.5, abs=0.06)
    assert result.pit_std == pytest.approx(math.sqrt(1.0 / 12.0), abs=0.06)
    # Sanity on the bookkeeping: each test day contributes one full ladder.
    assert result.n_evaluated == result.n_days * 17
    assert result.n_days == result.n_folds * _CFG.test_window_size


def test_har_beats_constant_vol_under_vol_clustering() -> None:
    """The lane's reason to exist: with regime-switching vol the HAR
    forecast must out-Brier the frozen constant-vol baseline."""
    rng = np.random.default_rng(3)
    n = 700
    # 100-day alternating calm/wild regimes — persistent enough for the
    # weekly/monthly cascade to latch onto.
    sigmas = np.where((np.arange(n - 1) // 100) % 2 == 0, 0.004, 0.020)
    returns = rng.normal(0.0, 1.0, n - 1) * sigmas
    closes = 7500.0 * np.exp(np.concatenate([[0.0], np.cumsum(returns)]))
    result = run_index_backtest(_dates(n), closes, symbol="SPX", config=_CFG)
    assert result is not None
    assert result.brier_har < result.brier_const
    # Full-ladder Brier dilutes the edge (far brackets are ~0 for both
    # models), so the margin is small in absolute terms; > 2% is a real
    # skill gap here, not noise (seed-checked across regimes).
    assert result.improvement_vs_const_pct > 2.0


def test_no_look_ahead_trailing_future_data_cannot_change_the_verdict() -> None:
    """Rolling-origin discipline pin: closes strictly AFTER the last
    evaluated test day must be invisible to every fit and every
    prediction. A leak (e.g. fitting on the full series) fails this."""
    rng = np.random.default_rng(9)
    n_used = 1 + _CFG.initial_train_size + _CFG.test_window_size  # exactly one fold
    # Trailing tail shorter than a test window: no second fold can form,
    # so every one of these sessions is strictly-future data.
    closes = _gbm_closes(rng, n_used + 20)
    dates = _dates(len(closes))
    base = run_index_backtest(dates, closes, symbol="SPX", config=_CFG)
    mutated = closes.copy()
    mutated[n_used:] *= 1.5  # a fake crash-rally in the unevaluated tail
    alt = run_index_backtest(dates, mutated, symbol="SPX", config=_CFG)
    assert base is not None and alt is not None
    assert base.n_folds == alt.n_folds == 1
    assert base.last_test_date == alt.last_test_date == dates[n_used - 1]
    assert base == alt  # frozen dataclass equality: every reported number identical


def test_insufficient_history_returns_none() -> None:
    rng = np.random.default_rng(1)
    closes = _gbm_closes(rng, 100)
    assert run_index_backtest(_dates(100), closes, symbol="SPX", config=_CFG) is None


# --------------------------- market-implied comparison ---------------------------


def test_market_implied_skips_loudly_with_zero_snaps(tmp_path: Path) -> None:
    db = tmp_path / "t.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        rng = np.random.default_rng(2)
        closes = _gbm_closes(rng, 50)
        verdict = market_implied_comparison(con, _dates(50), closes, symbol="SPX")
    finally:
        con.close()
    assert isinstance(verdict, str)
    assert "skipped" in verdict and "0 KXINX" in verdict


# --------------------------- manifest honesty (flow) ---------------------------


def test_backtest_index_manifest_names_the_comparison_that_ran(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "t.duckdb"
    bootstrap(db)
    con = connect(db)
    try:
        rng = np.random.default_rng(5)
        closes = _gbm_closes(rng, 400)
        bars = [
            IndexDailyBar(
                symbol="SPX",
                valid_date=d,
                open=float(c),
                high=float(c),
                low=float(c),
                close=float(c),
                source="yahoo_chart",
                fetched_at=datetime(2026, 7, 2, 23, 0, tzinfo=UTC),
            )
            for d, c in zip(_dates(400), closes, strict=True)
        ]
        insert_index_daily(con, bars)  # NDX left empty on purpose
    finally:
        con.close()

    manifest_path = tmp_path / "backtest_index_manifest.json"
    monkeypatch.setattr(flow, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(flow, "INDEX_BACKTEST_MANIFEST_PATH", manifest_path)
    assert flow.main(db_path=db) == 0

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # THE honesty requirement: the manifest states exactly which comparison ran.
    assert manifest["comparison_ran"].startswith("har_rv_vs_constant_vol ONLY")
    assert "skipped: 0 KXINX" in manifest["market_implied"]["SPX"]
    assert "skipped: 0 KXNASDAQ100" in manifest["market_implied"]["NDX"]
    assert manifest["index_book_snaps_stored"] == {"SPX": 0, "NDX": 0}
    spx = manifest["symbols"]["SPX"]
    assert spx["brier_har_rv"] > 0.0
    assert "skipped" in manifest["symbols"]["NDX"]
    assert manifest["honest_caveats"]


def test_backtest_index_exits_nonzero_when_nothing_ran(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "t.duckdb"
    bootstrap(db)
    monkeypatch.setattr(flow, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(flow, "INDEX_BACKTEST_MANIFEST_PATH", tmp_path / "m.json")
    assert flow.main(db_path=db) == 1
