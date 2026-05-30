"""End-to-end pipeline smoke — the producer/consumer *contract* test.

Every flow has its own unit test, but those test each flow in isolation
against a *hand-written* fixture manifest. Nothing asserts that the
artifact one flow **writes** is exactly the shape the downstream flows
**read**. So a rename like ``conformal_summary`` -> ``conformal`` in
:meth:`BacktestResult.to_summary_dict` would pass every per-flow test
and silently blank out the dashboard + router + health calibration view.

This module closes that gap. It runs the real producer
(:func:`kq.backtest.engine.run_backtest`) over a seeded fixture DB,
emits the manifest the way :mod:`kq.flows.run_backtest` does, then feeds
that *same* manifest through every consumer and asserts each one parses
it coherently:

- dashboard :func:`kq.dashboard.panels.parse_conformal_rows`
- :func:`kq.flows.router_summary.summarize`
- :func:`kq.flows.health_check.run_checks` (calibration check)

It's the one test that turns the whole machine over on synthetic data
and asserts the cross-flow contract holds. Network-free, deterministic
(seeded RNG), CI-safe.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb

from kq.backtest.engine import BacktestConfig, run_backtest
from kq.dashboard.panels import format_conformal_table, parse_conformal_rows
from kq.flows.health_check import run_checks
from kq.flows.router_summary import summarize as summarize_router
from kq.storage.duckdb_store import bootstrap

# Reuse the canonical deterministic seeders from the engine's own end-to-end
# tests rather than re-defining them — so the seeding contract (observed =
# forecast - bias + noise; NDFD benchmark) lives in exactly one place and this
# smoke can't quietly drift from what test_backtest.py exercises.
from tests.test_backtest import _seed_ndfd, _seed_pair

_STATIONS = ("KAUS", "KJFK")


def _emit_manifest(results: dict[str, Any], *, strategy: str) -> dict[str, Any]:
    """Mirror the manifest dict that ``kq.flows.run_backtest`` writes.

    Critically uses ``BacktestResult.to_summary_dict()`` — the same
    producer the real flow uses — so the contract under test is the real
    one, not a hand-rolled fixture.
    """
    return {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "strategy": strategy,
        "evaluation": "rolling_origin_cv",
        "stations": {station: r.to_summary_dict() for station, r in results.items()},
    }


def _seeded_db(tmp_path: Path) -> Path:
    db = tmp_path / "smoke.duckdb"
    bootstrap(db)
    con = duckdb.connect(str(db))
    try:
        for idx, station in enumerate(_STATIONS):
            _seed_pair(
                con,
                station=station,
                start=date(2025, 1, 1),
                n_days=220,
                forecast_bias=3.0 + idx,
                seed=11 + idx,
            )
            _seed_ndfd(
                con,
                station=station,
                start=date(2025, 1, 1),
                n_days=220,
                forecast_bias=2.0 + idx,
                seed=99 + idx,
            )
    finally:
        con.close()
    return db


def _write_pipeline_artifacts(models: Path, manifest: dict[str, Any]) -> None:
    """Lay down the artifacts the cron pipeline writes: the v1 + router_v1
    backtest manifests and a router_config the summary consumer reads."""
    models.mkdir(parents=True, exist_ok=True)
    (models / "backtest_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (models / "backtest_router_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    router_config = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "mode": "auto",
        "decision_threshold_pct": 1.0,
        "decisions": {
            station: {"strategy": "ngr", "reason": "smoke fixture"} for station in _STATIONS
        },
    }
    (models / "router_config.json").write_text(json.dumps(router_config), encoding="utf-8")


# --------------------------------------------------------------- the contract


def test_backtest_manifest_flows_to_every_consumer(tmp_path: Path) -> None:
    """Producer → manifest → (dashboard, router_summary, health_check).

    The single assertion that matters: the keys
    ``BacktestResult.to_summary_dict`` emits are exactly the keys every
    downstream consumer reads. If a producer-side rename drifts from a
    consumer, this fails where the per-flow tests stay green.
    """
    db = _seeded_db(tmp_path)

    # --- producer: the real backtest engine ---
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
    assert set(results) == set(_STATIONS), "both seeded stations should be evaluated"

    # The contract keys must be present on every station summary.
    for station, r in results.items():
        summary = r.to_summary_dict()
        for key in (
            "brier_calibrated",
            "brier_raw",
            "brier_improvement_vs_ndfd_pct",
            "reliability_summary",
            "conformal_summary",
        ):
            assert key in summary, f"{station} summary missing contract key {key!r}"

    manifest = _emit_manifest(results, strategy="weather_v1")
    models = tmp_path / "models"
    _write_pipeline_artifacts(models, manifest)

    # --- consumer 1: dashboard conformal panel ---
    rows = parse_conformal_rows(manifest["stations"])
    # parse is total — never raises — and the renderer must accept its output.
    table = format_conformal_table(rows)
    assert isinstance(table, str) and table
    for row in rows:
        assert row.coverage_status in {"✅", "⚠️", "❌"}
        assert 0.0 <= row.empirical_coverage <= 1.0

    # --- consumer 2: router summary ---
    router = summarize_router(models)
    assert router.n_stations == len(_STATIONS)
    seen = {v.station for v in router.stations}
    assert seen == set(_STATIONS)
    for v in router.stations:
        # router_v1 manifest is the source of truth for the active number;
        # we wrote it, so the brier-vs-ndfd value must round-trip (not None).
        assert v.brier_vs_ndfd_pct_by_strategy.get("router_v1") is not None

    # --- consumer 3: health-check calibration view ---
    con = duckdb.connect(str(db), read_only=True)
    try:
        status = run_checks(con, models_dir=models, now=datetime.now(tz=UTC))
    finally:
        con.close()
    names = {c.name for c in status.checks}
    assert "calibration_summary" in names, "health-check must read the backtest manifest"
    # The just-written manifest must register as fresh, not missing.
    backtest_check = next(c for c in status.checks if c.name == "backtest_manifest")
    assert backtest_check.severity in {"ok", "warn"}
    assert "does not exist" not in backtest_check.detail


def test_backtest_calibrated_beats_raw_on_biased_fixture(tmp_path: Path) -> None:
    """Sanity floor for the smoke fixture: with a real +bias, the NGR re-fit
    must out-calibrate the naive market on OOS rows — otherwise the fixture
    isn't exercising the producer meaningfully and the contract test above
    would be vacuous."""
    db = _seeded_db(tmp_path)
    results = run_backtest(
        db_path=db,
        strategy="weather_v1",
        config=BacktestConfig(initial_train_size=60, test_window_size=14),
    )
    for station, r in results.items():
        assert r.n_evaluated > 0, f"{station} evaluated zero OOS rows"
        assert r.brier_calibrated < r.brier_raw, f"{station} calibrated did not beat raw"
