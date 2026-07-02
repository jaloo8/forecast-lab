"""System health check — read-only snapshot of pipeline freshness.

Run via ``kq health-check`` from cron to get a one-line status (and a
non-zero exit code on warnings/critical) so a downstream watchdog can
alert without parsing the human-readable output.

Checks (each maps to a `Check` dataclass):

  1. weather_forecast — most-recent `as_of` within `max_age_weather_h` (default 12h)
  2. metar_obs        — most-recent `obs_time` within `max_age_metar_min` (default 30min)
  3. ndfd_forecast    — most-recent `as_of` within `max_age_ndfd_h` (default 12h)
  4. kalshi_book_snap — most-recent `captured_at` within `max_age_kalshi_h` (default 1h
                        during trading hours, but the check is informational only —
                        Kalshi-demo legitimately returns 0 markets in off-season,
                        so a stale book snap is WARN, never CRIT)
  5. backtest_manifest — `models/backtest_manifest.json` mtime within
                         `max_age_backtest_d` (default 14 days — 2x the
                         weekly regeneration cadence)
  6. router_config    — `models/router_config.json` mtime within
                        `max_age_router_d` (default 14 days)

Severity levels: ``ok``, ``warn``, ``crit``. Freshness checks (1-3, 5, 6)
carry two thresholds:

  * age > ``max_age_*``                     → WARN (a missed cron tick)
  * age > ``crit_multiplier`` x ``max_age_*`` → CRIT (default 3x — the whole
    cron stack is dead, not just one late run)

kalshi_book_snap is the exception: WARN-only even when far past threshold
(demo off-season staleness is legitimate). Empty-table semantics are
unchanged: no rows at all is CRIT for the core tables (pipeline never ran —
this is the contract `scripts/alert-drill.sh` drills against), WARN for
Kalshi. The aggregate `Status` is the worst severity across all checks.
Exit codes:

  * 0 — all OK
  * 1 — at least one WARN, no CRIT
  * 2 — at least one CRIT (or a fundamental error like DB unreachable)

The flow is **read-only**. No DB writes, no external HTTP calls. Safe to
run from any machine that can reach the DuckDB file.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import duckdb
import structlog

from kq.config import REPO_ROOT, get_settings
from kq.flows.ingest_weather import _db_path_from_settings
from kq.storage.duckdb_store import connect, is_lock_conflict

log = structlog.get_logger(__name__)

Severity = Literal["ok", "warn", "crit"]

# Default freshness thresholds. These mirror the ingest cadences in
# docs/SCHEDULED-RUNS.md and are deliberately loose (2x the cadence) so a
# single missed cron tick doesn't trigger an alert.
DEFAULT_MAX_AGE_WEATHER_H: float = 12.0  # ingest is every 6h
DEFAULT_MAX_AGE_METAR_MIN: float = 30.0  # ingest is every 10min
DEFAULT_MAX_AGE_NDFD_H: float = 12.0  # ingest is every 6h
DEFAULT_MAX_AGE_KALSHI_H: float = 24.0  # informational; Kalshi-demo can be stale
# 2x the weekly Sunday backtest/router cron cadence, like every other
# threshold here. At 1x (7d) the check WARN-flapped in the race window
# between one Sunday's mtime and the next Sunday's regeneration.
DEFAULT_MAX_AGE_BACKTEST_D: float = 14.0  # weekly cron in SCHEDULED-RUNS.md
DEFAULT_MAX_AGE_ROUTER_D: float = 14.0

# Prolonged staleness escalates WARN -> CRIT past `crit_multiplier x threshold`.
# Audit 2026-06-11: freshness breaches were WARN forever, and cron-health.sh
# pushes only on CRIT — so a dead cron stack could never page. 3x the (already
# 2x-cadence) WARN threshold ≈ six consecutive missed ticks: unambiguously
# "the stack is down", not "one late run".
DEFAULT_CRIT_MULTIPLIER: float = 3.0

# Calibration-summary check thresholds (consume the conformal_summary +
# reliability_summary blocks the backtest manifest emits per station --
# see ``models/calibration.py`` and ``models/conformal.py``). Both are
# model-quality signals, not pipeline-failure signals: any breach is
# WARN, never CRIT, so the cron operator gets a daily nudge without
# being paged at 3 a.m. on an underlying-distribution drift event.
#
# 0.05 (5pp) is the n-aware reliability summary's standing bar. The
# conformal threshold is set 5pp below the nominal 0.90 target to
# accommodate the discrete jump in the (n+1)*(1-alpha) finite-sample
# correction at the test-window sample sizes we have.
DEFAULT_MIN_CONFORMAL_COVERAGE: float = 0.85
DEFAULT_MAX_RELIABILITY_DELTA_PP: float = 10.0


@dataclass(frozen=True, slots=True)
class Check:
    """One health-check result. JSON-safe by construction (no NaN, no datetime)."""

    name: str
    severity: Severity
    detail: str
    age_seconds: float | None  # None if the check doesn't have an age (e.g. count check)
    threshold_seconds: float | None
    crit_threshold_seconds: float | None = None  # None when the check can't escalate by age


@dataclass(frozen=True, slots=True)
class Status:
    """Aggregate status across all checks."""

    overall: Severity
    checked_at_utc: str
    checks: list[Check] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_SEVERITY_ORDER: dict[Severity, int] = {"ok": 0, "warn": 1, "crit": 2}


def _worst(*severities: Severity) -> Severity:
    """Pick the highest-severity label across the inputs."""
    return max(severities, key=lambda s: _SEVERITY_ORDER[s])


def _age_seconds(latest: datetime | None, *, now: datetime) -> float | None:
    """Return `(now - latest)` in seconds, or None when `latest` is missing."""
    if latest is None:
        return None
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=UTC)  # DuckDB stores naive-UTC
    return (now - latest).total_seconds()


def _table_freshness_check(
    con: duckdb.DuckDBPyConnection,
    *,
    name: str,
    sql: str,
    threshold_seconds: float,
    now: datetime,
    severity_when_missing: Severity = "crit",
    severity_when_stale: Severity = "warn",
    severity_when_dead: Severity = "crit",
    crit_multiplier: float = DEFAULT_CRIT_MULTIPLIER,
) -> Check:
    """Generic 'most recent timestamp from a table' freshness check.

    `sql` must SELECT a single TIMESTAMP column (or `NULL` when the table is empty).
    `severity_when_missing` controls behavior when no row exists at all (e.g.
    Kalshi off-season legitimately returns no rows — that's WARN, not CRIT).
    `severity_when_stale` applies past `threshold_seconds`; `severity_when_dead`
    applies past `crit_multiplier * threshold_seconds` (a dead cron stack, not
    a single missed tick — pass "warn" for informational-only checks).
    """
    crit_threshold = threshold_seconds * crit_multiplier
    row = con.execute(sql).fetchone()
    latest = row[0] if row else None
    age = _age_seconds(latest, now=now)
    if age is None:
        return Check(
            name=name,
            severity=severity_when_missing,
            detail="no rows in table",
            age_seconds=None,
            threshold_seconds=threshold_seconds,
            crit_threshold_seconds=crit_threshold,
        )
    if age > threshold_seconds:
        return Check(
            name=name,
            severity=severity_when_dead if age > crit_threshold else severity_when_stale,
            detail=(
                f"stale by {age / 3600:.1f}h (warn > {threshold_seconds / 3600:.1f}h, "
                f"crit > {crit_threshold / 3600:.1f}h)"
            ),
            age_seconds=age,
            threshold_seconds=threshold_seconds,
            crit_threshold_seconds=crit_threshold,
        )
    return Check(
        name=name,
        severity="ok",
        detail=f"latest {age / 3600:.2f}h ago",
        age_seconds=age,
        threshold_seconds=threshold_seconds,
        crit_threshold_seconds=crit_threshold,
    )


def _file_mtime_check(
    path: Path,
    *,
    name: str,
    threshold_days: float,
    now: datetime,
    severity_when_missing: Severity = "crit",
    severity_when_stale: Severity = "warn",
    severity_when_dead: Severity = "crit",
    crit_multiplier: float = DEFAULT_CRIT_MULTIPLIER,
) -> Check:
    """Check that `path` exists and has mtime within `threshold_days`.

    Same two-tier staleness as `_table_freshness_check`: WARN past
    `threshold_days`, `severity_when_dead` (default CRIT) past
    `crit_multiplier * threshold_days`.
    """
    threshold_s = threshold_days * 86_400.0
    crit_threshold_s = threshold_s * crit_multiplier
    if not path.exists():
        return Check(
            name=name,
            severity=severity_when_missing,
            detail="file does not exist",
            age_seconds=None,
            threshold_seconds=threshold_s,
            crit_threshold_seconds=crit_threshold_s,
        )
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    age = (now - mtime).total_seconds()
    if age > threshold_s:
        return Check(
            name=name,
            severity=severity_when_dead if age > crit_threshold_s else severity_when_stale,
            detail=(
                f"stale by {age / 86_400.0:.1f}d (warn > {threshold_days:.1f}d, "
                f"crit > {crit_threshold_s / 86_400.0:.1f}d)"
            ),
            age_seconds=age,
            threshold_seconds=threshold_s,
            crit_threshold_seconds=crit_threshold_s,
        )
    return Check(
        name=name,
        severity="ok",
        detail=f"mtime {age / 86_400.0:.2f}d ago",
        age_seconds=age,
        threshold_seconds=threshold_s,
        crit_threshold_seconds=crit_threshold_s,
    )


def _calibration_check(
    manifest_path: Path,
    *,
    name: str = "calibration_summary",
    min_empirical_coverage: float = DEFAULT_MIN_CONFORMAL_COVERAGE,
    max_reliability_delta_pp: float = DEFAULT_MAX_RELIABILITY_DELTA_PP,
) -> Check:
    """Read the active backtest manifest and surface per-station calibration
    breaches as a single aggregate health-check entry.

    Reports WARN (not CRIT) when any station fails either bar:

      * ``reliability_summary.passes_bar == False`` -- at least one
        statistically-meaningful bin is off by > 10 pp (Phase 5 §5 #3).
      * ``conformal_summary.empirical_coverage < min_empirical_coverage``
        -- prediction-set coverage at alpha=0.1 dropped more than 5pp below
        the 0.90 target on a chronological half-half split. This is a
        non-exchangeability signal -- regime drift between the
        calibration and test windows.

    Both signals are quality-of-fit, not pipeline-down indicators, so
    they're WARN by design. CRIT-level alerting on calibration would
    page the operator on legitimate distribution drift, which is the
    opposite of what we want.

    Returns ``Check`` with detail summarizing the worst-offending
    station(s).
    """
    if not manifest_path.exists():
        return Check(
            name=name,
            severity="warn",
            detail=f"manifest missing: {manifest_path.name}",
            age_seconds=None,
            threshold_seconds=None,
        )
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return Check(
            name=name,
            severity="warn",
            detail=f"manifest unreadable: {type(exc).__name__}",
            age_seconds=None,
            threshold_seconds=None,
        )

    stations = payload.get("stations") or {}
    reliability_failures: list[str] = []
    conformal_failures: list[tuple[str, float]] = []

    for icao, station in stations.items():
        rel = station.get("reliability_summary") or {}
        if rel.get("passes_bar") is False:
            reliability_failures.append(icao)
        conf = station.get("conformal_summary") or {}
        cov = conf.get("empirical_coverage")
        if isinstance(cov, int | float) and cov < min_empirical_coverage:
            conformal_failures.append((icao, float(cov)))

    if not reliability_failures and not conformal_failures:
        return Check(
            name=name,
            severity="ok",
            detail=(
                f"all {len(stations)} stations clear "
                f"(reliability passes_bar=True, conformal coverage >= "
                f"{min_empirical_coverage:.2f})"
            ),
            age_seconds=None,
            threshold_seconds=None,
        )

    pieces: list[str] = []
    if reliability_failures:
        pieces.append(
            f"reliability fails: {','.join(sorted(reliability_failures))} "
            f"(passes_bar=False; tolerance {max_reliability_delta_pp:.0f}pp)"
        )
    if conformal_failures:
        worst = sorted(conformal_failures, key=lambda t: t[1])[:3]
        worst_str = ", ".join(f"{icao}={cov:.3f}" for icao, cov in worst)
        pieces.append(
            f"conformal under-coverage at alpha=0.1: {worst_str} "
            f"(threshold {min_empirical_coverage:.2f})"
        )
    return Check(
        name=name,
        severity="warn",
        detail="; ".join(pieces),
        age_seconds=None,
        threshold_seconds=None,
    )


def run_checks(
    con: duckdb.DuckDBPyConnection,
    *,
    models_dir: Path,
    now: datetime | None = None,
    max_age_weather_h: float = DEFAULT_MAX_AGE_WEATHER_H,
    max_age_metar_min: float = DEFAULT_MAX_AGE_METAR_MIN,
    max_age_ndfd_h: float = DEFAULT_MAX_AGE_NDFD_H,
    max_age_kalshi_h: float = DEFAULT_MAX_AGE_KALSHI_H,
    max_age_backtest_d: float = DEFAULT_MAX_AGE_BACKTEST_D,
    max_age_router_d: float = DEFAULT_MAX_AGE_ROUTER_D,
    min_empirical_coverage: float = DEFAULT_MIN_CONFORMAL_COVERAGE,
    max_reliability_delta_pp: float = DEFAULT_MAX_RELIABILITY_DELTA_PP,
    calibration_manifest: str = "backtest_manifest.json",
    crit_multiplier: float = DEFAULT_CRIT_MULTIPLIER,
) -> Status:
    """Run every check and aggregate the status. `now` is overridable for tests."""
    now_dt = now or datetime.now(tz=UTC)

    checks: list[Check] = []
    checks.append(
        _table_freshness_check(
            con,
            name="weather_forecast",
            sql="SELECT MAX(as_of) FROM weather_forecast",
            threshold_seconds=max_age_weather_h * 3600.0,
            now=now_dt,
            crit_multiplier=crit_multiplier,
        )
    )
    checks.append(
        _table_freshness_check(
            con,
            name="metar_obs",
            sql="SELECT MAX(obs_time) FROM metar_obs",
            threshold_seconds=max_age_metar_min * 60.0,
            now=now_dt,
            crit_multiplier=crit_multiplier,
        )
    )
    checks.append(
        _table_freshness_check(
            con,
            name="ndfd_forecast",
            sql="SELECT MAX(as_of) FROM ndfd_forecast",
            threshold_seconds=max_age_ndfd_h * 3600.0,
            now=now_dt,
            crit_multiplier=crit_multiplier,
        )
    )
    # Kalshi: WARN-only on missing AND on prolonged staleness because demo
    # returns 0 markets in off-season — that's an operational reality, not a
    # hard failure. Production should tighten this to CRIT once prod-Kalshi
    # market access is wired.
    checks.append(
        _table_freshness_check(
            con,
            name="kalshi_book_snap",
            sql="SELECT MAX(snap_time) FROM kalshi_book_snap",
            threshold_seconds=max_age_kalshi_h * 3600.0,
            now=now_dt,
            severity_when_missing="warn",
            severity_when_stale="warn",
            severity_when_dead="warn",
            crit_multiplier=crit_multiplier,
        )
    )
    checks.append(
        _file_mtime_check(
            models_dir / "backtest_manifest.json",
            name="backtest_manifest",
            threshold_days=max_age_backtest_d,
            now=now_dt,
            crit_multiplier=crit_multiplier,
        )
    )
    checks.append(
        _file_mtime_check(
            models_dir / "router_config.json",
            name="router_config",
            threshold_days=max_age_router_d,
            now=now_dt,
            crit_multiplier=crit_multiplier,
        )
    )
    checks.append(
        _calibration_check(
            models_dir / calibration_manifest,
            min_empirical_coverage=min_empirical_coverage,
            max_reliability_delta_pp=max_reliability_delta_pp,
        )
    )

    overall: Severity = "ok"
    for c in checks:
        overall = _worst(overall, c.severity)

    return Status(
        overall=overall,
        checked_at_utc=now_dt.isoformat(),
        checks=checks,
    )


def render_human(status: Status) -> str:
    """One-line-per-check ASCII rendering. Sortable, copy-friendly, no colors."""
    lines: list[str] = [f"=== Health Check ({status.checked_at_utc}) ==="]
    glyph: dict[Severity, str] = {"ok": "OK ", "warn": "WRN", "crit": "CRT"}
    for c in status.checks:
        lines.append(f"  [{glyph[c.severity]}] {c.name:<22} {c.detail}")
    lines.append("")
    lines.append(f"Overall status: {status.overall.upper()}")
    return "\n".join(lines)


def run(
    *,
    db_path: Path | None = None,
    models_dir: Path | None = None,
    json_output: bool = False,
    now: datetime | None = None,
    threshold_overrides: dict[str, float] | None = None,
) -> tuple[Status, str]:
    """Connect, run checks, render. Returns (Status, rendered).

    `threshold_overrides` accepts keys matching the `max_age_*` parameter names
    of `run_checks` and lets a CLI flag forward them.
    """
    settings = get_settings()
    db = db_path or _db_path_from_settings(settings.database_url)
    md = models_dir or (REPO_ROOT / "models")
    overrides: dict[str, Any] = dict(threshold_overrides or {})
    # Read-only + never-create (duckdb_store.connect): a health probe must
    # not materialize an empty DB on a bad path, and must not take the write
    # lock out from under the cron writers. Bounded lock-conflict retry is
    # inside connect(); a still-locked DB surfaces via is_lock_conflict in
    # main() as WARN, not CRIT.
    con = connect(db, read_only=True)
    try:
        status = run_checks(con, models_dir=md, now=now, **overrides)
    finally:
        con.close()

    rendered = json.dumps(status.to_dict()) if json_output else render_human(status)
    log.info(
        "health_check.computed",
        overall=status.overall,
        n_checks=len(status.checks),
        crit=sum(1 for c in status.checks if c.severity == "crit"),
        warn=sum(1 for c in status.checks if c.severity == "warn"),
    )
    return status, rendered


def main(*, json_output: bool = False) -> int:
    """`python -m kq health-check` entrypoint.

    Returns:
        0 — all checks OK
        1 — at least one WARN (no CRIT), or the DB is transiently locked by
            a concurrent writer ("busy, retry next tick" — a lock collision
            with a cron writer must not page as CRIT)
        2 — at least one CRIT (or fundamental error)
    """
    try:
        status, rendered = run(json_output=json_output)
    except Exception as exc:
        if is_lock_conflict(exc):
            log.warning("health_check.db_busy", error=str(exc))
            print(
                "health_check: database busy (another process holds the write "
                "lock) — WARN, retry next tick"
            )
            return 1
        log.error("health_check.failed", error=str(exc))
        print(f"health_check failed: {exc}")
        return 2

    print(rendered)
    return {"ok": 0, "warn": 1, "crit": 2}[status.overall]


# Public helpers for tests + library consumers.
__all__ = [
    "DEFAULT_CRIT_MULTIPLIER",
    "DEFAULT_MAX_AGE_BACKTEST_D",
    "DEFAULT_MAX_AGE_KALSHI_H",
    "DEFAULT_MAX_AGE_METAR_MIN",
    "DEFAULT_MAX_AGE_NDFD_H",
    "DEFAULT_MAX_AGE_ROUTER_D",
    "DEFAULT_MAX_AGE_WEATHER_H",
    "Check",
    "Status",
    "main",
    "render_human",
    "run",
    "run_checks",
]
