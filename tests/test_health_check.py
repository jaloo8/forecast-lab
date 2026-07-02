"""Tests for `kq health-check`. Synthesizes age scenarios via clock injection."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from kq.flows import health_check
from kq.flows.health_check import (
    DEFAULT_CRIT_MULTIPLIER,
    DEFAULT_MIN_CONFORMAL_COVERAGE,
    Check,
    Status,
    _calibration_check,
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
    # Set mtime to 20 days ago (above the default 14d = 2x-weekly threshold).
    old = (now - timedelta(days=20)).timestamp()
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
    assert backtest.age_seconds is not None and backtest.age_seconds > 14 * 86400


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


# ----------------------------------------------------- staleness escalation
# Audit 2026-06-11: freshness → WARN forever + cron-health.sh pushes only on
# CRIT meant a dead cron stack could never page. Prolonged staleness (past
# crit_multiplier x the WARN threshold, default 3x) must escalate to CRIT.


def test_crit_multiplier_default_pin() -> None:
    """Pin the escalation multiplier so changes are deliberate."""
    assert DEFAULT_CRIT_MULTIPLIER == 3.0


def test_stale_just_past_warn_stays_warn_overall(tmp_path: Path) -> None:
    """Mildly late (2x the 12h threshold, below the 3x crit bar) is WARN, not
    CRIT — overall maps to exit 1, so a single missed tick never pages."""
    db, models = _setup(tmp_path)
    now = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    con = duckdb.connect(str(db))
    try:
        _seed_freshness(con, weather_age_h=24.0, now=now)  # 12h < 24h < 36h
    finally:
        con.close()
    (models / "backtest_manifest.json").write_text("{}")
    (models / "router_config.json").write_text("{}")

    con = duckdb.connect(str(db), read_only=True)
    try:
        status = run_checks(con, models_dir=models, now=now)
    finally:
        con.close()
    assert _by_name(status, "weather_forecast").severity == "warn"
    assert status.overall == "warn"


def test_very_stale_weather_escalates_to_crit(tmp_path: Path) -> None:
    """Past 3x the WARN threshold (12h → 36h) the check goes CRIT, and both
    thresholds are visible in the check output."""
    db, models = _setup(tmp_path)
    now = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    con = duckdb.connect(str(db))
    try:
        _seed_freshness(con, weather_age_h=40.0, now=now)  # > 3 * 12h
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
    assert "warn > 12.0h" in weather.detail
    assert "crit > 36.0h" in weather.detail
    assert weather.threshold_seconds == 12 * 3600
    assert weather.crit_threshold_seconds == 36 * 3600
    assert status.overall == "crit"  # → exit 2 → cron-health.sh pushes


def test_dead_cron_everything_stale_is_crit(tmp_path: Path) -> None:
    """The cron-death scenario: every table stale for many hours → the core
    freshness checks all escalate, overall is CRIT (exit 2 → phone buzzes)."""
    db, models = _setup(tmp_path)
    now = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    con = duckdb.connect(str(db))
    try:
        _seed_freshness(
            con,
            weather_age_h=48.0,  # > 3 * 12h
            metar_age_min=600.0,  # > 3 * 30min
            ndfd_age_h=48.0,  # > 3 * 12h
            kalshi_age_h=80.0,  # > 3 * 24h, but informational → warn
            now=now,
        )
    finally:
        con.close()
    (models / "backtest_manifest.json").write_text("{}")
    (models / "router_config.json").write_text("{}")

    con = duckdb.connect(str(db), read_only=True)
    try:
        status = run_checks(con, models_dir=models, now=now)
    finally:
        con.close()
    severities = {c.name: c.severity for c in status.checks}
    assert severities["weather_forecast"] == "crit"
    assert severities["metar_obs"] == "crit"
    assert severities["ndfd_forecast"] == "crit"
    assert severities["kalshi_book_snap"] == "warn"  # WARN-only by design
    assert status.overall == "crit"


def test_very_stale_kalshi_stays_warn(tmp_path: Path) -> None:
    """Kalshi is informational-only: even far past 3x threshold it must stay
    WARN (demo off-season staleness is legitimate, never a page)."""
    db, models = _setup(tmp_path)
    now = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    con = duckdb.connect(str(db))
    try:
        _seed_freshness(con, kalshi_age_h=100.0, now=now)  # > 3 * 24h
    finally:
        con.close()
    (models / "backtest_manifest.json").write_text("{}")
    (models / "router_config.json").write_text("{}")

    con = duckdb.connect(str(db), read_only=True)
    try:
        status = run_checks(con, models_dir=models, now=now)
    finally:
        con.close()
    assert _by_name(status, "kalshi_book_snap").severity == "warn"
    assert status.overall == "warn"


def test_very_old_backtest_manifest_escalates_to_crit(tmp_path: Path) -> None:
    """File-mtime freshness escalates too: 50d > 3 * 14d → CRIT."""
    db, models = _setup(tmp_path)
    now = datetime(2026, 1, 15, tzinfo=UTC)
    con = duckdb.connect(str(db))
    try:
        _seed_freshness(con, now=now)
    finally:
        con.close()
    p = models / "backtest_manifest.json"
    p.write_text("{}")
    old = (now - timedelta(days=50)).timestamp()
    os.utime(p, (old, old))
    (models / "router_config.json").write_text("{}")

    con = duckdb.connect(str(db), read_only=True)
    try:
        status = run_checks(con, models_dir=models, now=now)
    finally:
        con.close()
    backtest = _by_name(status, "backtest_manifest")
    assert backtest.severity == "crit"
    assert "warn > 14.0d" in backtest.detail
    assert "crit > 42.0d" in backtest.detail
    assert status.overall == "crit"


def test_crit_multiplier_is_overridable(tmp_path: Path) -> None:
    """A tightened multiplier flips a would-be WARN to CRIT."""
    db, models = _setup(tmp_path)
    now = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    con = duckdb.connect(str(db))
    try:
        _seed_freshness(con, weather_age_h=24.0, now=now)
    finally:
        con.close()
    (models / "backtest_manifest.json").write_text("{}")
    (models / "router_config.json").write_text("{}")

    # Default 3x → 24h < 36h → warn.
    con = duckdb.connect(str(db), read_only=True)
    try:
        status_default = run_checks(con, models_dir=models, now=now)
    finally:
        con.close()
    assert _by_name(status_default, "weather_forecast").severity == "warn"

    # Tightened 1.5x → 24h > 18h → crit.
    con = duckdb.connect(str(db), read_only=True)
    try:
        status_tight = run_checks(con, models_dir=models, now=now, crit_multiplier=1.5)
    finally:
        con.close()
    assert _by_name(status_tight, "weather_forecast").severity == "crit"


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


def _write_calibration_manifest(
    path: Path,
    *,
    stations: dict[str, dict[str, object]],
) -> None:
    """Helper -- write a synthetic backtest manifest with the calibration
    blocks that ``_calibration_check`` consumes."""
    payload = {"stations": stations}
    path.write_text(json.dumps(payload), encoding="utf-8")


# ----------------------------------------------------------- calibration check


def test_calibration_check_ok_when_all_stations_clear(tmp_path: Path) -> None:
    """Reliability passes_bar=True AND conformal coverage at threshold for
    every station -> OK."""
    manifest = tmp_path / "backtest_manifest.json"
    _write_calibration_manifest(
        manifest,
        stations={
            "KAUS": {
                "reliability_summary": {"passes_bar": True},
                "conformal_summary": {"empirical_coverage": 0.91},
            },
            "KJFK": {
                "reliability_summary": {"passes_bar": True},
                "conformal_summary": {"empirical_coverage": 0.90},
            },
        },
    )
    check = _calibration_check(manifest)
    assert check.severity == "ok"
    assert "all 2 stations clear" in check.detail


def test_calibration_check_warns_on_reliability_failure(tmp_path: Path) -> None:
    """At least one station with passes_bar=False -> WARN with the ICAO
    surfaced in the detail."""
    manifest = tmp_path / "backtest_manifest.json"
    _write_calibration_manifest(
        manifest,
        stations={
            "KAUS": {
                "reliability_summary": {"passes_bar": False},
                "conformal_summary": {"empirical_coverage": 0.95},  # not the issue
            },
            "KJFK": {
                "reliability_summary": {"passes_bar": True},
                "conformal_summary": {"empirical_coverage": 0.92},
            },
        },
    )
    check = _calibration_check(manifest)
    assert check.severity == "warn"
    assert "reliability fails: KAUS" in check.detail
    # KJFK is OK -> shouldn't appear in the failure list.
    assert "KJFK" not in check.detail.split("conformal")[0]


def test_calibration_check_warns_on_conformal_under_coverage(tmp_path: Path) -> None:
    """Empirical coverage below 0.85 (default) -> WARN with the worst
    offenders surfaced in ascending order."""
    manifest = tmp_path / "backtest_manifest.json"
    _write_calibration_manifest(
        manifest,
        stations={
            "KAUS": {
                "reliability_summary": {"passes_bar": True},
                "conformal_summary": {"empirical_coverage": 0.81},
            },
            "KMDW": {
                "reliability_summary": {"passes_bar": True},
                "conformal_summary": {"empirical_coverage": 0.79},  # worst
            },
            "KJFK": {
                "reliability_summary": {"passes_bar": True},
                "conformal_summary": {"empirical_coverage": 0.92},  # ok
            },
        },
    )
    check = _calibration_check(manifest)
    assert check.severity == "warn"
    # Worst offender (KMDW) listed first.
    detail = check.detail
    assert "conformal under-coverage" in detail
    assert detail.index("KMDW") < detail.index("KAUS")
    # Healthy station shouldn't appear.
    assert "KJFK" not in detail


def test_calibration_check_warns_on_both_failure_types(tmp_path: Path) -> None:
    manifest = tmp_path / "backtest_manifest.json"
    _write_calibration_manifest(
        manifest,
        stations={
            "KAUS": {
                "reliability_summary": {"passes_bar": False},
                "conformal_summary": {"empirical_coverage": 0.80},
            },
        },
    )
    check = _calibration_check(manifest)
    assert check.severity == "warn"
    assert "reliability fails" in check.detail
    assert "conformal under-coverage" in check.detail


def test_calibration_check_warns_when_manifest_missing(tmp_path: Path) -> None:
    """Cron operator should be alerted when no backtest manifest exists --
    the calibration view is stale by definition."""
    check = _calibration_check(tmp_path / "does_not_exist.json")
    assert check.severity == "warn"
    assert "manifest missing" in check.detail


def test_calibration_check_warns_on_unparseable_manifest(tmp_path: Path) -> None:
    """A truncated / malformed JSON file should not crash the health
    check -- WARN with the exception class name in the detail."""
    bad = tmp_path / "backtest_manifest.json"
    bad.write_text("{ this is not json", encoding="utf-8")
    check = _calibration_check(bad)
    assert check.severity == "warn"
    assert "JSONDecodeError" in check.detail or "unreadable" in check.detail


def test_calibration_check_threshold_is_overridable(tmp_path: Path) -> None:
    """A tightened threshold flips a previously-OK station to WARN."""
    manifest = tmp_path / "backtest_manifest.json"
    _write_calibration_manifest(
        manifest,
        stations={
            "KAUS": {
                "reliability_summary": {"passes_bar": True},
                "conformal_summary": {"empirical_coverage": 0.88},
            },
        },
    )
    default_check = _calibration_check(manifest)
    assert default_check.severity == "ok"
    tight_check = _calibration_check(manifest, min_empirical_coverage=0.90)
    assert tight_check.severity == "warn"
    assert "KAUS=0.880" in tight_check.detail


def test_calibration_check_default_threshold_pin() -> None:
    """Pin the default conformal-coverage threshold so changes are deliberate."""
    assert DEFAULT_MIN_CONFORMAL_COVERAGE == 0.85


def test_run_checks_includes_calibration_summary(tmp_path: Path) -> None:
    """End-to-end: run_checks emits a `calibration_summary` Check entry."""
    db, models = _setup(tmp_path)
    now = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    con = duckdb.connect(str(db))
    try:
        _seed_freshness(con, now=now)
    finally:
        con.close()
    _write_calibration_manifest(
        models / "backtest_manifest.json",
        stations={
            "KAUS": {
                "reliability_summary": {"passes_bar": True},
                "conformal_summary": {"empirical_coverage": 0.92},
            },
        },
    )
    (models / "router_config.json").write_text("{}")

    con = duckdb.connect(str(db), read_only=True)
    try:
        status = run_checks(con, models_dir=models, now=now)
    finally:
        con.close()
    cal = _by_name(status, "calibration_summary")
    assert cal.severity == "ok"


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


# ----------------------------------------------------------- lock-conflict -> WARN


def test_main_returns_warn_on_lock_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    """A concurrent writer holding the DuckDB lock is 'busy, retry next tick'
    (exit 1 = WARN) — not the CRIT page path (2026-07-01 audit: lock
    collisions caused false CRIT pages)."""

    def _locked(*_a: object, **_k: object) -> object:
        raise duckdb.IOException(
            'IO Error: Could not set lock on file "x.duckdb": Conflicting lock is held'
        )

    monkeypatch.setattr(health_check, "connect", _locked)
    assert health_check.main() == 1


def test_main_returns_crit_on_other_db_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Anything that is NOT the transient lock class stays a CRIT exit."""

    def _broken(*_a: object, **_k: object) -> object:
        raise duckdb.IOException("IO Error: Cannot open database: file is corrupt")

    monkeypatch.setattr(health_check, "connect", _broken)
    assert health_check.main() == 2
