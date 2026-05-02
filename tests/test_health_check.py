"""Tests for `kq health-check`. Synthesizes age scenarios via clock injection."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb

from kq.flows.health_check import (
    Check,
    Status,
    render_human,
    run_checks,
)
from kq.storage.duckdb_store import bootstrap


def _to_naive_utc(dt: datetime) -> datetime:
    """DuckDB TIMESTAMP is naive; strip tz to avoid local-clock conversion."""
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt


def _seed_freshness(
    con: duckdb.DuckDBPyConnection,
    *,
    weather_age_h: float | None = 1.0,
    metar_age_min: float | None = 5.0,
    ndfd_age_h: float | None = 1.0,
    kalshi_age_h: float | None = 0.5,
    now: datetime,
) -> None:
    """Seed each table with a single row at the requested age (or skip if None)."""
    if weather_age_h is not None:
        ts = _to_naive_utc(now - timedelta(hours=weather_age_h))
        con.execute(
            """
            INSERT INTO weather_forecast (as_of, run_time, model, member, station,
                                          valid_date, forecast_high_f, forecast_low_f)
            VALUES (?, ?, 'gfs', 0, 'KAUS', ?, 75.0, 60.0)
            """,
            [ts, ts, ts.date()],
        )
    if metar_age_min is not None:
        ts = _to_naive_utc(now - timedelta(minutes=metar_age_min))
        con.execute(
            """
            INSERT INTO metar_obs (obs_time, station, temp_f)
            VALUES (?, 'KAUS', 70.0)
            """,
            [ts],
        )
    if ndfd_age_h is not None:
        ts = _to_naive_utc(now - timedelta(hours=ndfd_age_h))
        con.execute(
            """
            INSERT INTO ndfd_forecast (as_of, station, valid_date, lead_days, source,
                                       forecast_max_f)
            VALUES (?, 'KAUS', ?, 1, 'nbm_deterministic_openmeteo', 75.0)
            """,
            [ts, ts.date()],
        )
    if kalshi_age_h is not None:
        ts = _to_naive_utc(now - timedelta(hours=kalshi_age_h))
        con.execute(
            """
            INSERT INTO kalshi_book_snap (snap_time, ticker, yes_bid, yes_ask)
            VALUES (?, 'TEST-X', 0.50, 0.51)
            """,
            [ts],
        )


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    db = tmp_path / "h.duckdb"
    bootstrap(db)
    models = tmp_path / "models"
    models.mkdir()
    return db, models


def _by_name(status: Status, name: str) -> Check:
    for c in status.checks:
        if c.name == name:
            return c
    raise AssertionError(f"check {name!r} not in status: {[c.name for c in status.checks]}")


# ----------------------------------------------------------- run_checks


def test_all_ok_when_everything_fresh(tmp_path: Path) -> None:
    db, models = _setup(tmp_path)
    now = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    con = duckdb.connect(str(db))
    try:
        _seed_freshness(
            con,
            weather_age_h=1.0,
            metar_age_min=5.0,
            ndfd_age_h=1.0,
            kalshi_age_h=0.5,
            now=now,
        )
    finally:
        con.close()
    # Touch the two manifest files with current mtime.
    (models / "backtest_manifest.json").write_text("{}")
    (models / "router_config.json").write_text("{}")

    con = duckdb.connect(str(db), read_only=True)
    try:
        status = run_checks(con, models_dir=models, now=now)
    finally:
        con.close()
    assert status.overall == "ok"
    for c in status.checks:
        assert c.severity == "ok", f"{c.name} unexpectedly {c.severity}: {c.detail}"


def test_stale_weather_triggers_warn(tmp_path: Path) -> None:
    db, models = _setup(tmp_path)
    now = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    con = duckdb.connect(str(db))
    try:
        _seed_freshness(con, weather_age_h=24.0, now=now)  # > default 12h threshold
    finally:
        con.close()
    (models / "backtest_manifest.json").write_text("{}")
    (models / "router_config.json").write_text("{}")

    con = duckdb.connect(str(db), read_only=True)
    try:
        status = run_checks(con, models_dir=models, now=now)
    finally:
        con.close()
    weather = _by_name(status, "weather_forecast")
    assert weather.severity == "warn"
    assert "stale" in weather.detail
    assert weather.age_seconds is not None
    assert weather.age_seconds > 12 * 3600


def test_empty_weather_table_triggers_crit(tmp_path: Path) -> None:
    """No rows at all in weather_forecast is a CRIT — pipeline never ran."""
    db, models = _setup(tmp_path)
    now = datetime(2026, 1, 15, tzinfo=UTC)
    # Don't seed weather_forecast (intentional)
    con = duckdb.connect(str(db))
    try:
        _seed_freshness(con, weather_age_h=None, now=now)
    finally:
        con.close()
    (models / "backtest_manifest.json").write_text("{}")
    (models / "router_config.json").write_text("{}")

    con = duckdb.connect(str(db), read_only=True)
    try:
        status = run_checks(con, models_dir=models, now=now)
    finally:
        con.close()
    weather = _by_name(status, "weather_forecast")
    assert weather.severity == "crit"
    assert "no rows" in weather.detail
    assert status.overall == "crit"


def test_empty_kalshi_table_is_only_warn(tmp_path: Path) -> None:
    """Kalshi off-season legitimately has 0 markets — must NOT escalate to CRIT."""
    db, models = _setup(tmp_path)
    now = datetime(2026, 1, 15, tzinfo=UTC)
    con = duckdb.connect(str(db))
    try:
        _seed_freshness(con, kalshi_age_h=None, now=now)
    finally:
        con.close()
    (models / "backtest_manifest.json").write_text("{}")
    (models / "router_config.json").write_text("{}")

    con = duckdb.connect(str(db), read_only=True)
    try:
        status = run_checks(con, models_dir=models, now=now)
    finally:
        con.close()
    kalshi = _by_name(status, "kalshi_book_snap")
    assert kalshi.severity == "warn"
    # The aggregate must NOT be crit since kalshi-empty is the only deviation.
    assert status.overall == "warn"


def test_missing_backtest_manifest_triggers_crit(tmp_path: Path) -> None:
    db, models = _setup(tmp_path)
    now = datetime(2026, 1, 15, tzinfo=UTC)
    con = duckdb.connect(str(db))
    try:
        _seed_freshness(con, now=now)
    finally:
        con.close()
    # Don't create manifest files
    con = duckdb.connect(str(db), read_only=True)
    try:
        status = run_checks(con, models_dir=models, now=now)
    finally:
        con.close()
    backtest = _by_name(status, "backtest_manifest")
    assert backtest.severity == "crit"
    assert "does not exist" in backtest.detail
    assert status.overall == "crit"


def test_old_backtest_manifest_triggers_warn(tmp_path: Path) -> None:
    db, models = _setup(tmp_path)
    now = datetime(2026, 1, 15, tzinfo=UTC)
    con = duckdb.connect(str(db))
    try:
        _seed_freshness(con, now=now)
    finally:
        con.close()
    p = models / "backtest_manifest.json"
    p.write_text("{}")
    # Set mtime to 14 days ago (above the default 7d threshold).
    old = (now - timedelta(days=14)).timestamp()
    os.utime(p, (old, old))
    (models / "router_config.json").write_text("{}")

    con = duckdb.connect(str(db), read_only=True)
    try:
        status = run_checks(con, models_dir=models, now=now)
    finally:
        con.close()
    backtest = _by_name(status, "backtest_manifest")
    assert backtest.severity == "warn"
    assert "stale" in backtest.detail
    assert backtest.age_seconds is not None and backtest.age_seconds > 7 * 86400


def test_overall_picks_worst_severity(tmp_path: Path) -> None:
    """One CRIT and one WARN → overall is CRIT."""
    db, models = _setup(tmp_path)
    now = datetime(2026, 1, 15, tzinfo=UTC)
    # Weather stale (warn), backtest_manifest missing (crit)
    con = duckdb.connect(str(db))
    try:
        _seed_freshness(con, weather_age_h=24.0, now=now)
    finally:
        con.close()
    (models / "router_config.json").write_text("{}")

    con = duckdb.connect(str(db), read_only=True)
    try:
        status = run_checks(con, models_dir=models, now=now)
    finally:
        con.close()
    assert status.overall == "crit"
    severities = {c.name: c.severity for c in status.checks}
    assert severities["weather_forecast"] == "warn"
    assert severities["backtest_manifest"] == "crit"


def test_thresholds_are_overridable(tmp_path: Path) -> None:
    """Custom thresholds tighten/relax the freshness windows."""
    db, models = _setup(tmp_path)
    now = datetime(2026, 1, 15, tzinfo=UTC)
    con = duckdb.connect(str(db))
    try:
        _seed_freshness(con, weather_age_h=10.0, now=now)
    finally:
        con.close()
    (models / "backtest_manifest.json").write_text("{}")
    (models / "router_config.json").write_text("{}")

    # Default 12h threshold → 10h is fresh → ok.
    con = duckdb.connect(str(db), read_only=True)
    try:
        status_default = run_checks(con, models_dir=models, now=now)
    finally:
        con.close()
    assert _by_name(status_default, "weather_forecast").severity == "ok"

    # Tightened 5h threshold → 10h is stale → warn.
    con = duckdb.connect(str(db), read_only=True)
    try:
        status_tight = run_checks(con, models_dir=models, now=now, max_age_weather_h=5.0)
    finally:
        con.close()
    assert _by_name(status_tight, "weather_forecast").severity == "warn"


# ----------------------------------------------------------- render


def test_render_human_includes_overall_line() -> None:
    s = Status(
        overall="warn",
        checked_at_utc="2026-01-15T12:00:00+00:00",
        checks=[
            Check(
                name="weather_forecast",
                severity="ok",
                detail="latest 1.00h ago",
                age_seconds=3600.0,
                threshold_seconds=43200.0,
            ),
            Check(
                name="metar_obs",
                severity="warn",
                detail="stale by 0.5h (threshold 0.5h)",
                age_seconds=1800.0,
                threshold_seconds=1800.0,
            ),
        ],
    )
    out = render_human(s)
    assert "Overall status: WARN" in out
    assert "weather_forecast" in out
    assert "metar_obs" in out
    assert "[OK ]" in out
    assert "[WRN]" in out


def test_status_to_dict_round_trips_through_json() -> None:
    """JSON-safety guarantee for the `--json` flag."""
    s = Status(
        overall="ok",
        checked_at_utc="2026-01-15T12:00:00+00:00",
        checks=[
            Check(
                name="x", severity="ok", detail="fresh", age_seconds=10.0, threshold_seconds=60.0
            ),
        ],
    )
    blob = json.dumps(s.to_dict())
    parsed = json.loads(blob)
    assert parsed["overall"] == "ok"
    assert parsed["checks"][0]["name"] == "x"
    assert parsed["checks"][0]["severity"] == "ok"
