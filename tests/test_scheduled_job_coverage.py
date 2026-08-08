"""The scheduled-fleet coverage guard.

WHY THIS EXISTS
---------------
A job that is documented but never registered on the host does not fail --
it simply never runs, and nothing anywhere says so. That silence has now
cost this project twice:

* ``kq ingest-observed`` was dropped in the native-Windows cutover, so
  ``weather_observed`` went stale and **every** weather paper trade became
  unsettleable. 70 trades sat open with a fully green dashboard until someone
  happened to ask "how are the trades doing?" (fixed 2026-07-27, PR #120).
* The same cutover also dropped ``kq paper-nba`` (submit), the reforecast
  backtest arm, and the weekly ``kq doctor`` reality probe -- the last of
  which is the only automated check that would have caught the first one
  (fixed 2026-07-28, PR #122).

PR #120 claimed ingest-observed was "the only missing data lane". That claim
came from a one-directional grep and was wrong by three. Hence this test
compares BOTH directions and covers non-data jobs (probes, backtests, ops)
as well, which a data-lane-only check would have missed.

WHAT IT ASSERTS
---------------
``docs/SCHEDULED-RUNS.md`` is the canonical job list. Every job documented
there must be registered by one of the installers, and every job the
installers register must be documented there. Divergences must be declared
in :data:`KNOWN_DIVERGENCES` with a stated reason -- an undeclared one fails.

The comparison is on job IDENTITY (which command runs), not cadence: the doc
carries illustrative cron lines alongside the canonical block, and times
legitimately shift (DST re-runs, writer-grid offsets). Identity is what went
missing both times; cadence never did.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC = REPO_ROOT / "docs" / "SCHEDULED-RUNS.md"
MAIN_INSTALLER = REPO_ROOT / "scripts" / "install-scheduled-tasks.ps1"
OPS_INSTALLER = REPO_ROOT / "scripts" / "install-ops-tasks.ps1"

# Divergences that are intentional. Each entry must carry a reason; delete an
# entry the moment it stops being true rather than letting it rot into an
# excuse. Keep this list SHORT -- it is the escape hatch that could hide the
# next outage.
KNOWN_DIVERGENCES: dict[str, str] = {
    # The aggregate wrapper is documented as an ALTERNATIVE to registering the
    # individual ingest lanes; the host registers the lanes separately so each
    # one's failure is visible on its own task.
    "kq:ingest": "documented as an all-in-one alternative; host runs the lanes individually",
    # `kq health-check --json` is documented as the raw command, but on the
    # host it runs inside the cron-health wrapper (which adds the ntfy push).
    # script:cron-health being registered is what satisfies it.
    "kq:health-check": "invoked by script:cron-health, which IS registered",
    # Restored in #122, then deliberately unregistered 2026-08-08: its first
    # Sunday run failed with `backtest.reforecast_training_empty` — the host
    # DB carries no GEFSv12 reforecast rows, and the GRIB tooling that
    # produces them is Mac/WSL-only (no Windows eccodes wheels). The engine's
    # loud refusal is correct; a permanently-failing job just trains the
    # operator to ignore the status report's ATTENTION state. Delete this
    # entry (and re-add the installer row) once a reforecast backfill lands
    # in the host DB.
    "kq:backtest --strategy weather_reforecast_v1": (
        "reforecast training data absent on the Windows host; job can never "
        "succeed there — re-register after a reforecast backfill"
    ),
}

_KQ_LINE = re.compile(r"(?:python -m kq|/kq)\s+([a-z0-9-]+)((?:\s+--[a-z0-9-]+(?:\s+[\w.]+)?)*)")
_SCRIPT_LINE = re.compile(r"scripts/([a-z0-9-]+)\.(?:sh|ps1)")
# Five-field cron lines, plus the @-shorthands. `@reboot` is how a
# long-running service (the dashboard) is expressed in crontab terms; on the
# Windows host it becomes an AtStartup trigger.
_CRON_SHORTHAND = "reboot|yearly|annually|monthly|weekly|daily|midnight|hourly"
_CRON_LINE = re.compile(rf"^\s*(?:[\d*][\d,*/ -]*\s+[\d*]|@(?:{_CRON_SHORTHAND})\b)")


def _normalize_kq(sub: str, flags: str) -> str:
    """Job identity for a kq command.

    Only flags that make it a DIFFERENT job are part of the identity:
    ``--settle-only`` (settle pass vs submit pass) and ``--strategy X``
    (each backtest arm is its own scheduled job). Cosmetic flags such as
    ``--json`` are not.
    """
    key = f"kq:{sub}"
    if "--settle-only" in flags:
        key += " --settle-only"
    strategy = re.search(r"--strategy\s+([\w.]+)", flags)
    if strategy:
        key += f" --strategy {strategy.group(1)}"
    return key


def _documented_jobs() -> set[str]:
    jobs: set[str] = set()
    for raw in DOC.read_text(encoding="utf-8").splitlines():
        if not _CRON_LINE.match(raw):
            continue
        m = _KQ_LINE.search(raw)
        if m:
            jobs.add(_normalize_kq(m.group(1), m.group(2) or ""))
            continue
        s = _SCRIPT_LINE.search(raw.replace("\\", "/"))
        if s:
            jobs.add(f"script:{s.group(1)}")
    return jobs


def _registered_jobs() -> set[str]:
    jobs: set[str] = set()

    main = MAIN_INSTALLER.read_text(encoding="utf-8")
    # $Jobs entries: KqArgs = @('paper', '--settle-only')
    for args in re.findall(r"KqArgs\s*=\s*@\(([^)]*)\)", main):
        parts = re.findall(r"'([^']*)'", args)
        if not parts:
            continue
        jobs.add(_normalize_kq(parts[0], " ".join(parts[1:])))
    # ...or Shell = 'scripts\backup-duckdb.sh' for the legacy bash entries.
    for shell in re.findall(r"Shell\s*=\s*'([^']*)'", main):
        s = _SCRIPT_LINE.search(shell.replace("\\", "/"))
        if s:
            jobs.add(f"script:{s.group(1)}")

    ops = OPS_INSTALLER.read_text(encoding="utf-8")
    # Register-OpsTask 'kq-rotate-logs' ... "...\scripts\rotate-logs.ps1"
    for block in re.findall(r"Register-OpsTask\s+'[^']+'(.*?)(?=Register-OpsTask|\Z)", ops, re.S):
        s = _SCRIPT_LINE.search(block.replace("\\", "/"))
        if s:
            jobs.add(f"script:{s.group(1)}")
    return jobs


def _explain(keys: set[str]) -> str:
    return "\n".join(f"    - {k}" for k in sorted(keys))


def test_documented_jobs_are_all_registered() -> None:
    """The outage direction: documented but never registered == silently absent."""
    documented = _documented_jobs()
    registered = _registered_jobs()
    assert documented, "parsed zero jobs out of the doc — the parser or the doc format broke"

    missing = {j for j in documented - registered if j not in KNOWN_DIVERGENCES}
    assert not missing, (
        "These jobs are documented in docs/SCHEDULED-RUNS.md but NO installer registers them.\n"
        "On the host they simply never run, and nothing fails:\n"
        f"{_explain(missing)}\n\n"
        "Register them in scripts/install-scheduled-tasks.ps1 (or install-ops-tasks.ps1 for "
        "ops/shell jobs), or add an entry to KNOWN_DIVERGENCES with a reason."
    )


def test_registered_jobs_are_all_documented() -> None:
    """The reverse direction: a job nobody wrote down is a job nobody maintains.

    PR #120's one-directional check would have passed while three jobs were
    missing; this half is what makes the guard complete.
    """
    documented = _documented_jobs()
    registered = _registered_jobs()
    assert registered, "parsed zero jobs out of the installers — the parser or a script broke"

    undocumented = {j for j in registered - documented if j not in KNOWN_DIVERGENCES}
    assert not undocumented, (
        "These jobs are registered by an installer but appear in NO cron line in "
        "docs/SCHEDULED-RUNS.md, which is supposed to be the canonical list:\n"
        f"{_explain(undocumented)}\n\n"
        "Add them to docs/SCHEDULED-RUNS.md (a cron-syntax line so this parser sees them), "
        "or add an entry to KNOWN_DIVERGENCES with a reason."
    )


def test_known_divergences_are_still_real() -> None:
    """Stop the escape hatch from rotting.

    An entry that no longer appears on EITHER side is stale and must be
    deleted, otherwise the allowlist slowly becomes a place where real gaps
    hide.
    """
    live = _documented_jobs() | _registered_jobs()
    stale = {k for k in KNOWN_DIVERGENCES if k not in live}
    assert not stale, (
        "KNOWN_DIVERGENCES entries that no longer match any documented or registered job — "
        f"delete them:\n{_explain(stale)}"
    )


def test_the_four_jobs_this_guard_was_built_for() -> None:
    """Regression pins for the jobs actually lost in the cutover.

    Named explicitly so that if any of them is ever dropped again the failure
    says WHICH one and WHY it matters, rather than only showing up as a set
    difference.
    """
    registered = _registered_jobs()
    for job, why in (
        ("kq:ingest-observed", "settlement truth; without it NO weather trade can ever settle"),
        ("kq:paper-nba", "the NBA SUBMIT pass; without it the lane books zero trades all season"),
        ("script:reality-probe", "weekly kq doctor; the only unattended venue-drift check"),
    ):
        assert job in registered, f"{job} is not registered by any installer — {why}"

    # The fourth cutover casualty — the reforecast backtest arm — is now a
    # DECLARED divergence rather than a registration: its training data does
    # not exist on the Windows host and cannot be produced there (GRIB
    # tooling is Mac/WSL-only), so its first restored run failed and would
    # have failed every Sunday forever. It must be either registered OR
    # declared with a reason; being silently absent from both is the original
    # outage class this guard exists for.
    reforecast = "kq:backtest --strategy weather_reforecast_v1"
    assert reforecast in _registered_jobs() or reforecast in KNOWN_DIVERGENCES, (
        f"{reforecast} is neither registered nor a declared divergence — "
        "it has been silently dropped AGAIN"
    )
