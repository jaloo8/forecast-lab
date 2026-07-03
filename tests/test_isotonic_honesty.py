"""Honest-isotonic regression tests — pins the PIT discipline of the engine's
per-fold isotonic recalibration path.

Background: the 2026-07-01 audit's verification panels split 1/1 on the claim
"isotonic recalibration is fit in-sample". Lead verification (2026-07-02)
REFUTED it: `_fit_isotonic_for_fold` builds its (raw_prob, outcome) pairs from
the fold's training rows only and the fitted map is applied to the fold's test
window. A synthetic-data experiment through the real engine matched a
hand-rolled honest reference bit-for-bit, while the three leak variants each
flattered Brier (fit-on-own-test-window by ~0.031 absolute on the synthetic
set). These tests pin that honesty permanently; each would FAIL under one or
more of the leak variants:

    (a) pairs pooled across ALL folds (later folds' train windows contain
        earlier folds' test days);
    (b) pairs drawn from the fold's OWN test rows;
    (c) pairs from train rows but probabilities produced by a base model that
        itself saw test rows.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pytest

from kq.backtest.engine import BacktestConfig, _fit_isotonic_for_fold, run_backtest
from kq.backtest.weather_clv import SettledBracket
from kq.models.weather_ngr import WeatherNGRModel
from kq.storage.duckdb_store import bootstrap

AS_OF = datetime(2026, 1, 1, tzinfo=UTC)
START = date(2025, 1, 1)


# ------------------------------------------------ unit: helper reads train only


def test_fold_isotonic_fit_reads_only_train_rows() -> None:
    """`_fit_isotonic_for_fold` must be invariant to poisoning every row
    OUTSIDE `train_idx` — the direct pin for leak variant (b) at the helper
    level. The self-check at the end proves the poison WOULD have moved the
    fitted map had the helper read those rows, so a pass is never vacuous."""
    rng = np.random.default_rng(7)
    n, n_train = 100, 60
    ens = rng.normal(75.0, 6.0, size=n)
    obs = ens - 3.0 + rng.normal(0.0, 4.0, size=n)
    train_idx = np.arange(n_train)
    cfg = BacktestConfig()

    ngr = WeatherNGRModel()
    ngr.fit(ens[train_idx], obs[train_idx])

    cal_clean = _fit_isotonic_for_fold(
        active_model=ngr, train_idx=train_idx, ens_means=ens, observed=obs, cfg=cfg
    )
    assert not cal_clean.is_identity  # 60 days x 7 brackets = 420 pairs >= 150

    poisoned_ens = ens.copy()
    poisoned_obs = obs.copy()
    poisoned_ens[n_train:] += 7.7
    poisoned_obs[n_train:] += 999.0  # every poisoned pair would settle YES
    cal_poisoned = _fit_isotonic_for_fold(
        active_model=ngr,
        train_idx=train_idx,
        ens_means=poisoned_ens,
        observed=poisoned_obs,
        cfg=cfg,
    )

    grid = np.linspace(0.01, 0.99, 199)
    np.testing.assert_array_equal(cal_clean.predict(grid), cal_poisoned.predict(grid))

    # Self-check: fitting WITH the poisoned rows included must move the map;
    # otherwise the equality above proves nothing.
    cal_leaky = _fit_isotonic_for_fold(
        active_model=ngr,
        train_idx=np.arange(n),
        ens_means=poisoned_ens,
        observed=poisoned_obs,
        cfg=cfg,
    )
    assert not np.array_equal(cal_clean.predict(grid), cal_leaky.predict(grid))


# --------------------------------- end-to-end: probs blind to test-window truth


def _seed(db: Path, *, n_days: int, perturb_days: set[date], perturb_f: float) -> None:
    """One forecast/observed pair per day; observed shifted by `perturb_f`
    on `perturb_days`. Same LST-aware lead-1 as_of convention as test_backtest."""
    bootstrap(db)
    rng = np.random.default_rng(11)
    forecasts = rng.normal(75.0, 4.0, size=n_days)
    observed = forecasts - 3.0 + rng.normal(0.0, 1.5, size=n_days)
    con = duckdb.connect(str(db))
    try:
        for i in range(n_days):
            vd = START + timedelta(days=i)
            as_of = datetime(vd.year, vd.month, vd.day, 18, 0) - timedelta(days=1)
            f_hi = float(forecasts[i])
            obs_hi = float(observed[i]) + (perturb_f if vd in perturb_days else 0.0)
            con.execute(
                """
                INSERT OR REPLACE INTO weather_forecast
                (as_of, run_time, model, member, station, valid_date,
                 forecast_high_f, forecast_low_f)
                VALUES (?, ?, 'gfs_prevday1', 0, ?, ?, ?, ?)
                """,
                (as_of, as_of, "KAUS", vd, f_hi, f_hi - 15.0),
            )
            con.execute(
                """
                INSERT OR REPLACE INTO weather_observed
                (station, valid_date, high_f, low_f, source, fetched_at)
                VALUES (?, ?, ?, ?, 'test', ?)
                """,
                ("KAUS", vd, obs_hi, obs_hi - 15.0, AS_OF),
            )
    finally:
        con.close()


def test_backtest_probs_invariant_to_test_window_outcome_perturbation(
    tmp_path: Path,
) -> None:
    """Perturbing ONLY the observed outcomes of one test window W must leave

    1. every evaluation strictly BEFORE W bit-identical (probs AND outcomes) —
       no fold whose test precedes W may see W's rows in any fit; fails under
       variants (a) and (c); and
    2. the model probabilities OF W's own evaluations bit-identical (only the
       settled outcomes may change) — the fold that tests on W fits its base
       model and isotonic map strictly before W; fails under (b) and (c).

    Folds testing AFTER W legitimately train on W's rows, so their probs may
    (and should) change — not asserted. Config is the production default
    (skew-normal + isotonic recalibration both ON) except the test window is
    30 days: 30 x 7 = 210 pairs exceeds ``DEFAULT_MIN_PAIRS`` (150), so a
    leaky fit on W's own pairs would actually ENGAGE the calibrator rather
    than being masked by the small-sample identity fallback.
    """
    cfg = BacktestConfig(initial_train_size=60, test_window_size=30)
    n_days = 150
    # Fold test windows start at 60, 90, 120. W = fold 2's window.
    w_start, w_end = 90, 120
    w_days = {START + timedelta(days=i) for i in range(w_start, w_end)}
    w_start_date = START + timedelta(days=w_start)
    w_end_date = START + timedelta(days=w_end)

    def _records(perturb_f: float) -> list[SettledBracket]:
        db = tmp_path / f"iso_honesty_{perturb_f}.duckdb"
        _seed(db, n_days=n_days, perturb_days=w_days, perturb_f=perturb_f)
        results = run_backtest(db_path=db, strategy="weather_v1", config=cfg)
        return results["KAUS"].bracket_records

    base = _records(0.0)
    shifted = _records(8.0)
    assert len(base) == len(shifted) > 0

    n_before = n_in_w = 0
    for a, b in zip(base, shifted, strict=True):
        assert (a.valid_date, a.threshold_f) == (b.valid_date, b.threshold_f)
        if a.valid_date < w_start_date:
            n_before += 1
            assert a.model_prob_yes == b.model_prob_yes, (
                f"pre-W evaluation changed at {a.valid_date}: a fold fit saw "
                f"future test-window rows (leak variant a/c)"
            )
            assert a.observed_high_f == b.observed_high_f
        elif a.valid_date < w_end_date:
            n_in_w += 1
            assert a.model_prob_yes == b.model_prob_yes, (
                f"W's own model prob changed at {a.valid_date}: the fold's "
                f"model or isotonic map saw its own test outcomes (leak "
                f"variant b/c)"
            )
            assert b.observed_high_f == pytest.approx(a.observed_high_f + 8.0)

    # Sanity: both asserted regions were actually exercised.
    assert n_before == cfg.test_window_size * cfg.n_brackets
    assert n_in_w == cfg.test_window_size * cfg.n_brackets
