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
                         `max_age_backtest_d` (default 7 days)
  6. router_config    — `models/router_config.json` mtime within `max_age_router_d`

Severity levels: ``ok``, ``warn``, ``crit``. The aggregate `Status` is the
worst severity across all checks. Exit codes:

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

log = structlog.get_logger(__name__)

Severity = Literal["ok", "warn", "crit"]

# Default freshness thresholds. These mirror the ingest cadences in
# docs/SCHEDULED-RUNS.md and are deliberately loose (2x the cadence) so a
# single missed cron tick doesn't trigger an alert.
DEFAULT_MAX_AGE_WEATHER_H: float = 12.0  # ingest is every 6h
DEFAULT_MAX_AGE_METAR_MIN: float = 30.0  # ingest is every 10min
DEFAULT_MAX_AGE_NDFD_H: float = 12.0  # ingest is every 6h
DEFAULT_MAX_AGE_KALSHI_H: float = 24.0  # informational; Kalshi-demo can be stale
DEFAULT_MAX_AGE_BACKTEST_D: float = 7.0  # weekly cron in SCHEDULED-RUNS.md
DEFAULT_MAX_AGE_ROUTER_D: float = 7.0


@dataclass(frozen=True, slots=True)
class Check:
    """One health-check result. JSON-safe by construction (no NaN, no datetime)."""

    name: str
    severity: Severity
    detail: str
    age_seconds: float | None  # None if the check doesn't have an age (e.g. count check)
    threshold_seconds: float | None


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
) -> Check:
    """Generic 'most recent timestamp from a table' freshness check.

    `sql` must SELECT a single TIMESTAMP column (or `NULL` when the table is empty).
    `severity_when_missing` controls behavior when no row exists at all (e.g.
    Kalshi off-season legitimately returns no rows — that's WARN, not CRIT).
    """
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
        )
    if age > threshold_seconds:
        return Check(
            name=name,
            severity=severity_when_stale,
            detail=f"stale by {age / 3600:.1f}h (threshold {threshold_seconds / 3600:.1f}h)",
            age_seconds=age,
            threshold_seconds=threshold_seconds,
        )
    return Check(
        name=name,
        severity="ok",
        detail=f"latest {age / 3600:.2f}h ago",
        age_seconds=age,
        threshold_seconds=threshold_seconds,
    )


def _file_mtime_check(
    path: Path,
    *,
    name: str,
    threshold_days: float,
    now: datetime,
    severity_when_missing: Severity = "crit",
    severity_when_stale: Severity = "warn",
) -> Check:
    """Check that `path` exists and has mtime within `threshold_days`."""
    threshold_s = threshold_days * 86_400.0
    if not path.exists():
        return Check(
            name=name,
            severity=severity_when_missing,
            detail="file does not exist",
            age_seconds=None,
            threshold_seconds=threshold_s,
        )
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    age = (now - mtime).total_seconds()
    if age > threshold_s:
        return Check(
            name=name,
            severity=severity_when_stale,
            detail=f"stale by {age / 86_400.0:.1f}d (threshold {threshold_days:.1f}d)",
            age_seconds=age,
            threshold_seconds=threshold_s,
        )
    return Check(
        name=name,
        severity="ok",
        detail=f"mtime {age / 86_400.0:.2f}d ago",
        age_seconds=age,
        threshold_seconds=threshold_s,
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
        )
    )
    checks.append(
        _table_freshness_check(
            con,
            name="metar_obs",
            sql="SELECT MAX(obs_time) FROM metar_obs",
            threshold_seconds=max_age_metar_min * 60.0,
            now=now_dt,
        )
    )
    checks.append(
        _table_freshness_check(
            con,
            name="ndfd_forecast",
            sql="SELECT MAX(as_of) FROM ndfd_forecast",
            threshold_seconds=max_age_ndfd_h * 3600.0,
            now=now_dt,
        )
    )
    # Kalshi: WARN-only on missing because demo returns 0 markets in off-season —
    # that's an operational reality, not a hard failure. Production should
    # tighten this to CRIT once prod-Kalshi market access is wired.
    checks.append(
        _table_freshness_check(
            con,
            name="kalshi_book_snap",
            sql="SELECT MAX(snap_time) FROM kalshi_book_snap",
            threshold_seconds=max_age_kalshi_h * 3600.0,
            now=now_dt,
            severity_when_missing="warn",
            severity_when_stale="warn",
        )
    )
    checks.append(
        _file_mtime_check(
            models_dir / "backtest_manifest.json",
            name="backtest_manifest",
            threshold_days=max_age_backtest_d,
            now=now_dt,
        )
    )
    checks.append(
        _file_mtime_check(
            models_dir / "router_config.json",
            name="router_config",
            threshold_days=max_age_router_d,
            now=now_dt,
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
    overrides = threshold_overrides or {}
    con = duckdb.connect(str(db), read_only=True)
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
        1 — at least one WARN (no CRIT)
        2 — at least one CRIT (or fundamental error)
    """
    try:
        status, rendered = run(json_output=json_output)
    except Exception as exc:
        log.error("health_check.failed", error=str(exc))
        print(f"health_check failed: {exc}")
        return 2

    print(rendered)
    return {"ok": 0, "warn": 1, "crit": 2}[status.overall]


# Public helpers for tests + library consumers.
__all__ = [
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
