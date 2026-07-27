"""Tests for the cron-ops shell scripts under `scripts/`.

These scripts run unattended on the WSL2 cron host (backup, log rotation,
the health-check heartbeat + ntfy alert). They were live on the box but
previously uncommitted; #27 version-controls them and pins their behavior
so a future edit can't silently break the operational safety net.

Every test is **hermetic and network-free**: scripts are driven with a
controlled ``HOME`` / temp repo / fake ``uv`` + ``notify-failure`` shims,
so nothing touches the real DB, real logs, or ntfy. The two scripts that
derive their repo root from their own location (``notify-failure.sh``,
``rotate-logs.sh``) are copied into a temp tree first, so we never read the
real ``.env`` (which carries a live NTFY topic) or rotate the real logs.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"


def _bash_available() -> bool:
    """Can we launch a POSIX bash that understands these scripts?

    Deliberately platform-gated rather than a bare ``shutil.which("bash")``.
    Two ways that probe lies on Windows, both observed:

    1. ``which`` searches PATH, but ``CreateProcess`` searches ``System32``
       first — so on a WSL-enabled box ``bash`` resolves to the WSL *launcher*,
       which cannot consume a Windows path argument. Every test then dies with
       exit 127 instead of skipping: the guard fails open.
    2. GitHub's ``windows-latest`` image ships Git-for-Windows bash on PATH, so
       the guard would not fire there either — and these tests are only
       hermetic under a POSIX PATH. Under Git-bash, ``/mingw64/bin`` precedes
       the fixture's fake-``curl`` shim, so ``notify-failure.sh`` would reach
       the *real* curl and POST to ntfy.sh from CI.

    These scripts are the POSIX cron-host ops layer; the Windows host schedules
    work through Task Scheduler instead (see docs/DEPLOY-WINDOWS.md). They also
    cover zero ``src/kq`` lines, so skipping them on Windows leaves the coverage
    gate untouched. Linux (WSL2 cron host + CI) always runs them in full.
    """
    if sys.platform == "win32":
        return False
    return shutil.which("bash") is not None


pytestmark = pytest.mark.skipif(
    not _bash_available(), reason="POSIX bash unavailable (Windows host); see _bash_available"
)


def _run(
    script: Path, *args: str, env: dict[str, str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), *args],
        env=env,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _base_env(**overrides: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update(overrides)
    return env


def _make_executable(p: Path) -> None:
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IRUSR | stat.S_IWUSR)


def _fake_repo(tmp_path: Path) -> tuple[Path, Path]:
    """A throwaway ``$HOME`` with an empty forecast-lab repo. Returns
    ``(home, repo)`` with ``repo/scripts`` and ``home/.local/bin`` created —
    the shared shape the cron-health + alert-drill script tests both need."""
    home = tmp_path / "home"
    repo = home / "forecast-lab"
    (repo / "scripts").mkdir(parents=True)
    (home / ".local" / "bin").mkdir(parents=True)
    return home, repo


def _write_fake_notify(scripts_dir: Path, marker: Path) -> None:
    """Drop a fake notify-failure.sh that ``touch``es ``marker`` instead of
    pushing to ntfy, so a test can assert the alert path fired."""
    notify = scripts_dir / "notify-failure.sh"
    notify.write_text(f'#!/usr/bin/env bash\ntouch "{marker}"\nexit 0\n')
    _make_executable(notify)


# ----------------------------------------------------------- backup-duckdb.sh
# Post-audit hardening (#PR-G): the script CHECKPOINTs before copying and
# fails loudly on any error. Tests always pin KQ_DUCKDB_CLI (a fake shim, or
# /nonexistent to force the uv-fallback / warn paths) so a real `duckdb` CLI
# on the host can never reach the FAKEDB fixture — hermetic + deterministic.


def _backup_home(tmp_path: Path) -> tuple[Path, Path]:
    """Build a fake $HOME with a forecast-lab repo + a DB file. Returns
    (home, db_path)."""
    home = tmp_path / "home"
    db = home / "forecast-lab" / "data" / "forecast_lab.duckdb"
    db.parent.mkdir(parents=True)
    db.write_text("FAKEDB")
    return home, db


def _fake_duckdb_cli(home: Path, *, exit_code: int = 0) -> tuple[Path, Path]:
    """Fake `duckdb` CLI: drops a marker when invoked, exits `exit_code`.
    Returns (cli_path, marker)."""
    bin_dir = home / "fakebin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    marker = home / "CHECKPOINT_CALLED"
    cli = bin_dir / "duckdb"
    cli.write_text(f'#!/usr/bin/env bash\ntouch "{marker}"\nexit {exit_code}\n')
    _make_executable(cli)
    return cli, marker


def _fake_uv(home: Path, *, exit_code: int = 0) -> Path:
    """Fake `uv` at the script's default $HOME/.local/bin/uv location:
    drops a marker when invoked, exits `exit_code`. Returns the marker."""
    uv = home / ".local" / "bin" / "uv"
    uv.parent.mkdir(parents=True, exist_ok=True)
    marker = home / "UV_CHECKPOINT_CALLED"
    uv.write_text(f'#!/usr/bin/env bash\ntouch "{marker}"\nexit {exit_code}\n')
    _make_executable(uv)
    return marker


def test_backup_writes_timestamped_copy_after_checkpoint(tmp_path: Path) -> None:
    home, _db = _backup_home(tmp_path)
    cli, marker = _fake_duckdb_cli(home)
    dest = tmp_path / "backups"
    res = _run(
        SCRIPTS / "backup-duckdb.sh",
        env=_base_env(HOME=str(home), KQ_BACKUP_DIR=str(dest), KQ_DUCKDB_CLI=str(cli)),
    )
    assert res.returncode == 0, res.stderr
    assert marker.exists()  # CHECKPOINT ran before the copy
    copies = list(dest.glob("forecast_lab_*.duckdb"))
    assert len(copies) == 1
    assert copies[0].read_text() == "FAKEDB"  # content preserved
    # Atomic-write discipline: no temp names left behind.
    assert not list(dest.glob("*.tmp.*"))


def test_backup_copies_wal_sidecar(tmp_path: Path) -> None:
    home, db = _backup_home(tmp_path)
    (db.parent / "forecast_lab.duckdb.wal").write_text("WAL")
    dest = tmp_path / "backups"
    res = _run(
        SCRIPTS / "backup-duckdb.sh",
        env=_base_env(HOME=str(home), KQ_BACKUP_DIR=str(dest), KQ_DUCKDB_CLI="/nonexistent"),
    )
    assert res.returncode == 0, res.stderr
    wal_copies = list(dest.glob("forecast_lab_*.duckdb.wal"))
    assert len(wal_copies) == 1
    assert wal_copies[0].read_text() == "WAL"


def test_backup_prunes_to_keep(tmp_path: Path) -> None:
    home, _db = _backup_home(tmp_path)
    dest = tmp_path / "backups"
    dest.mkdir()
    # Pre-seed 4 older backups with staggered (older) mtimes so `ls -t`
    # orders them strictly before the one the script is about to write.
    for i in range(4):
        old = dest / f"forecast_lab_2020010{i}T000000Z.duckdb"
        old.write_text("OLD")
        ts = 1_000_000 + i  # ascending, all well in the past
        os.utime(old, (ts, ts))
    res = _run(
        SCRIPTS / "backup-duckdb.sh",
        env=_base_env(
            HOME=str(home),
            KQ_BACKUP_DIR=str(dest),
            KQ_BACKUP_KEEP="2",
            KQ_DUCKDB_CLI="/nonexistent",
        ),
    )
    assert res.returncode == 0, res.stderr
    # 4 old + 1 new = 5, pruned to KEEP=2 newest.
    remaining = sorted(dest.glob("forecast_lab_*.duckdb"))
    assert len(remaining) == 2
    # The freshly-written backup (real content) must be among the survivors.
    assert any(p.read_text() == "FAKEDB" for p in remaining)


def test_backup_errors_when_no_db(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / "forecast-lab" / "data").mkdir(parents=True)  # repo but no DB file
    res = _run(
        SCRIPTS / "backup-duckdb.sh",
        env=_base_env(
            HOME=str(home), KQ_BACKUP_DIR=str(tmp_path / "b"), KQ_DUCKDB_CLI="/nonexistent"
        ),
    )
    assert res.returncode == 1
    assert "no DB" in res.stderr


def test_backup_fails_loudly_on_checkpoint_failure(tmp_path: Path) -> None:
    """A failed CHECKPOINT (writer holds the lock / corrupt DB) must abort
    the backup with a nonzero exit + message — never copy a torn snapshot."""
    home, _db = _backup_home(tmp_path)
    cli, marker = _fake_duckdb_cli(home, exit_code=1)
    dest = tmp_path / "backups"
    res = _run(
        SCRIPTS / "backup-duckdb.sh",
        env=_base_env(HOME=str(home), KQ_BACKUP_DIR=str(dest), KQ_DUCKDB_CLI=str(cli)),
    )
    assert res.returncode != 0
    assert marker.exists()
    assert "checkpoint failed" in res.stderr
    assert not list(dest.glob("forecast_lab_*.duckdb"))  # nothing written


def test_backup_falls_back_to_uv_checkpoint(tmp_path: Path) -> None:
    """No duckdb CLI -> checkpoint goes through `uv run python -c`."""
    home, _db = _backup_home(tmp_path)
    uv_marker = _fake_uv(home)
    dest = tmp_path / "backups"
    res = _run(
        SCRIPTS / "backup-duckdb.sh",
        env=_base_env(HOME=str(home), KQ_BACKUP_DIR=str(dest), KQ_DUCKDB_CLI="/nonexistent"),
    )
    assert res.returncode == 0, res.stderr
    assert uv_marker.exists()
    assert len(list(dest.glob("forecast_lab_*.duckdb"))) == 1


def test_backup_uv_checkpoint_failure_is_fatal(tmp_path: Path) -> None:
    home, _db = _backup_home(tmp_path)
    _fake_uv(home, exit_code=1)
    dest = tmp_path / "backups"
    res = _run(
        SCRIPTS / "backup-duckdb.sh",
        env=_base_env(HOME=str(home), KQ_BACKUP_DIR=str(dest), KQ_DUCKDB_CLI="/nonexistent"),
    )
    assert res.returncode != 0
    assert "checkpoint failed" in res.stderr
    assert not list(dest.glob("forecast_lab_*.duckdb"))


def test_backup_warns_but_proceeds_without_checkpoint_tooling(tmp_path: Path) -> None:
    """Neither duckdb CLI nor uv: still back up (atomically), but say so —
    an imperfect backup beats none, and the WARN lands in the cron log."""
    home, _db = _backup_home(tmp_path)  # no uv under this fake HOME
    dest = tmp_path / "backups"
    res = _run(
        SCRIPTS / "backup-duckdb.sh",
        env=_base_env(HOME=str(home), KQ_BACKUP_DIR=str(dest), KQ_DUCKDB_CLI="/nonexistent"),
    )
    assert res.returncode == 0, res.stderr
    assert "WARN" in res.stderr
    assert len(list(dest.glob("forecast_lab_*.duckdb"))) == 1


def test_backup_copy_failure_exits_nonzero(tmp_path: Path) -> None:
    """The old script exited 0 on copy failure (audit finding). Point the
    dest at an existing FILE so mkdir/cp fails -> must exit nonzero."""
    home, _db = _backup_home(tmp_path)
    dest_file = tmp_path / "not-a-dir"
    dest_file.write_text("occupied")
    res = _run(
        SCRIPTS / "backup-duckdb.sh",
        env=_base_env(HOME=str(home), KQ_BACKUP_DIR=str(dest_file), KQ_DUCKDB_CLI="/nonexistent"),
    )
    assert res.returncode != 0
    assert res.stderr.strip()  # loud: a message reached stderr


# ----------------------------------------------------------- notify-failure.sh
# Copied into a temp tree so it reads a CONTROLLED .env, never the real one
# (which carries a live NTFY topic — running the real script would push).


def _temp_notify(tmp_path: Path, *, env_contents: str | None) -> Path:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    script = repo / "scripts" / "notify-failure.sh"
    shutil.copy(SCRIPTS / "notify-failure.sh", script)
    _make_executable(script)
    if env_contents is not None:
        (repo / ".env").write_text(env_contents)
    return script


def test_notify_skips_when_topic_unset(tmp_path: Path) -> None:
    """No NTFY_TOPIC in env or .env -> clean no-op (exit 0), no network call.
    NTFY_TOPIC="" pins the env-var leg (the script honors $NTFY_TOPIC first
    since the 2026-07-01 unification) and keeps the test hermetic on a host
    with a real topic exported."""
    script = _temp_notify(tmp_path, env_contents="OTHER_KEY=value\n")
    res = _run(script, "test message", env=_base_env(NTFY_TOPIC=""))
    assert res.returncode == 0
    assert "skipping push" in res.stderr


def test_notify_skips_when_no_env_file(tmp_path: Path) -> None:
    """Missing .env entirely -> still a clean no-op (grep finds nothing)."""
    script = _temp_notify(tmp_path, env_contents=None)
    res = _run(script, "msg", env=_base_env(NTFY_TOPIC=""))
    assert res.returncode == 0
    assert "skipping push" in res.stderr


def test_notify_skips_when_topic_blank(tmp_path: Path) -> None:
    """NTFY_TOPIC present but empty in both env and .env -> no-op."""
    script = _temp_notify(tmp_path, env_contents="NTFY_TOPIC=\n")
    res = _run(script, "msg", env=_base_env(NTFY_TOPIC=""))
    assert res.returncode == 0
    assert "skipping push" in res.stderr


# ----------------------------------------------------------- rotate-logs.sh


def _logrotate_available() -> bool:
    return shutil.which("logrotate", path="/usr/sbin:/usr/bin:/bin") is not None


def _temp_rotate(tmp_path: Path, *, make_logdir: bool) -> Path:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    script = repo / "scripts" / "rotate-logs.sh"
    shutil.copy(SCRIPTS / "rotate-logs.sh", script)
    _make_executable(script)
    if make_logdir:
        logs = repo / "logs"
        logs.mkdir()
        (logs / "cron.log").write_text("line1\nline2\n")
    return script


def test_rotate_logs_missing_logdir_is_clean_noop(tmp_path: Path) -> None:
    script = _temp_rotate(tmp_path, make_logdir=False)
    res = _run(script, env=_base_env(PATH="/usr/sbin:" + os.environ.get("PATH", "")))
    assert res.returncode == 0
    assert "no log dir" in res.stderr


@pytest.mark.skipif(not _logrotate_available(), reason="logrotate not installed")
def test_rotate_logs_runs_clean_with_logrotate(tmp_path: Path) -> None:
    """With logrotate present and a real log dir, the script exits 0 and
    leaves the (freshly-rotated-state) log in place."""
    script = _temp_rotate(tmp_path, make_logdir=True)
    res = _run(script, env=_base_env(PATH="/usr/sbin:" + os.environ.get("PATH", "")))
    assert res.returncode == 0, res.stderr
    # First run initializes the logrotate state file under the temp repo.
    assert (script.parent.parent / ".logrotate.state").exists()


# ----------------------------------------------------------- cron-health.sh
# Driven with a fake `uv` (prints canned health JSON, controllable exit code)
# and a fake `notify-failure.sh` (drops a marker file) so we can assert the
# alert-only-on-CRIT contract without uv, the kq package, a DB, or ntfy.


def _temp_cron_health(tmp_path: Path, *, uv_exit: int) -> tuple[Path, Path, Path]:
    home, repo = _fake_repo(tmp_path)
    shutil.copy(SCRIPTS / "cron-health.sh", repo / "scripts" / "cron-health.sh")

    # Fake uv: ignore args, print canned JSON, exit with the requested code.
    uv = home / ".local" / "bin" / "uv"
    uv.write_text(f'#!/usr/bin/env bash\necho \'{{"overall":"x"}}\'\nexit {uv_exit}\n')
    _make_executable(uv)

    marker = repo / "ALERT_FIRED"
    _write_fake_notify(repo / "scripts", marker)
    return repo, repo / "logs" / "health.log", marker


def test_cron_health_logs_and_no_alert_when_ok(tmp_path: Path) -> None:
    repo, health_log, marker = _temp_cron_health(tmp_path, uv_exit=0)
    res = _run(
        repo / "scripts" / "cron-health.sh",
        env=_base_env(HOME=str(tmp_path / "home")),
    )
    assert res.returncode == 0
    assert health_log.exists()
    assert '"overall":"x"' in health_log.read_text()
    assert not marker.exists()  # OK -> no ntfy alert


def test_cron_health_no_alert_on_warn(tmp_path: Path) -> None:
    """WARN (exit 1) logs but does NOT push — mildly-late data never pages.
    The cron-death gap is closed on the health-check side: prolonged
    staleness escalates WARN -> CRIT (3x threshold), which lands in the
    exit>=2 push path pinned below."""
    repo, health_log, marker = _temp_cron_health(tmp_path, uv_exit=1)
    res = _run(
        repo / "scripts" / "cron-health.sh",
        env=_base_env(HOME=str(tmp_path / "home")),
    )
    assert res.returncode == 0
    assert health_log.exists()
    assert not marker.exists()  # WARN alone -> no ntfy alert


def test_cron_health_fires_alert_on_crit(tmp_path: Path) -> None:
    repo, health_log, marker = _temp_cron_health(tmp_path, uv_exit=2)
    res = _run(
        repo / "scripts" / "cron-health.sh",
        env=_base_env(HOME=str(tmp_path / "home")),
    )
    assert res.returncode == 0  # always exits 0 so cron never emails
    assert health_log.exists()
    assert marker.exists()  # CRIT (exit >= 2) -> alert fired


# ----------------------------------------------------------- alert-drill.sh
# The Phase 4 exit-criterion #2 drill. Driven with a fake `uv` (controls the
# health-check exit code) + a fake notify-failure.sh (marker), so we assert
# the injection-detects-CRIT + opt-in-push contract without uv, a DB, or ntfy.


def _temp_alert_drill(tmp_path: Path, *, health_exit: int) -> tuple[Path, Path, dict[str, str]]:
    """Build a temp repo with alert-drill.sh + a fake uv (health-check exits
    ``health_exit``; all other uv calls exit 0) + a fake notify-failure.sh
    that drops a marker. Returns ``(drill_script, marker, env)`` where ``env``
    already points HOME + UV at the fakes, so a test just calls
    ``_run(drill, ..., env=env)``."""
    home, repo = _fake_repo(tmp_path)

    drill = repo / "scripts" / "alert-drill.sh"
    shutil.copy(SCRIPTS / "alert-drill.sh", drill)
    _make_executable(drill)

    # Fake uv: the health-check call exits `health_exit`; the bootstrap
    # `python -c` call (and anything else) exits 0 so the drill proceeds.
    uv = home / ".local" / "bin" / "uv"
    uv.write_text(
        "#!/usr/bin/env bash\n"
        'case "$*" in\n'
        f'  *health-check*) echo \'{{"overall":"crit"}}\'; exit {health_exit};;\n'
        "  *) exit 0;;\n"
        "esac\n"
    )
    _make_executable(uv)

    marker = repo / "ALERT_FIRED"
    _write_fake_notify(repo / "scripts", marker)
    return drill, marker, _base_env(HOME=str(home), UV=str(uv))


def test_alert_drill_passes_on_crit_and_skips_push_by_default(tmp_path: Path) -> None:
    """Injection leg only: a CRIT (exit 2) health-check -> drill PASS (exit 0),
    and NO push fired without --push (so re-runs / CI never spam the phone)."""
    drill, marker, env = _temp_alert_drill(tmp_path, health_exit=2)
    res = _run(drill, env=env)
    assert res.returncode == 0, res.stderr
    assert "PASS" in res.stdout
    assert not marker.exists()  # delivery leg skipped by default


def test_alert_drill_push_fires_notify(tmp_path: Path) -> None:
    """--push fires notify-failure.sh exactly once on a detected CRIT."""
    drill, marker, env = _temp_alert_drill(tmp_path, health_exit=2)
    res = _run(drill, "--push", env=env)
    assert res.returncode == 0, res.stderr
    assert marker.exists()  # real (faked) push attempted


def test_alert_drill_fails_loudly_when_failure_not_escalated(tmp_path: Path) -> None:
    """The safety guard: if health-check returns only WARN (exit 1) on a
    broken pipeline, the drill must FAIL (exit 1) — a real outage that
    doesn't reach CRIT would never alert, and the drill must surface that."""
    drill, marker, env = _temp_alert_drill(tmp_path, health_exit=1)
    res = _run(drill, "--push", env=env)
    assert res.returncode == 1
    assert "FAIL" in res.stderr
    assert not marker.exists()  # no push when the drill itself failed


# ----------------------------------------------------------- reality-probe.sh
# Item: bare `uv` exited 127 under cron's minimal PATH, so the weekly probe
# never actually ran. Driven with an explicit UV shim (the same override the
# alert-drill tests use) + a fake notify-failure.sh marker: hermetic, no uv,
# no network, no real doctor run.


def _temp_reality_probe(tmp_path: Path, *, doctor_exit: int) -> tuple[Path, Path, dict[str, str]]:
    """Temp repo with reality-probe.sh + a fake uv (prints one CRIT line and
    exits ``doctor_exit``) + a fake notify-failure.sh marker. Returns
    ``(probe_script, marker, env)``."""
    home, repo = _fake_repo(tmp_path)
    probe = repo / "scripts" / "reality-probe.sh"
    shutil.copy(SCRIPTS / "reality-probe.sh", probe)
    _make_executable(probe)

    uv = home / ".local" / "bin" / "uv"
    uv.write_text(
        "#!/usr/bin/env bash\necho '[CRIT] payload-shape.KXHIGHLAX: synthetic drift'\n"
        f"exit {doctor_exit}\n"
    )
    _make_executable(uv)

    marker = repo / "ALERT_FIRED"
    _write_fake_notify(repo / "scripts", marker)
    return probe, marker, _base_env(HOME=str(home), UV=str(uv))


def test_reality_probe_resolves_uv_never_bare(tmp_path: Path) -> None:
    """The probe must run uv via the resolved $UV / $HOME/.local/bin/uv
    chain — a bare `uv` is exit 127 under cron's minimal PATH and the probe
    silently never runs (2026-07-01 audit)."""
    src = (SCRIPTS / "reality-probe.sh").read_text(encoding="utf-8")
    assert '"$UV" run python -m kq doctor' in src
    assert "$HOME/.local/bin/uv" in src  # the documented fallback location
    # And the fake-uv drive proves the resolution actually works end-to-end:
    probe, _marker, env = _temp_reality_probe(tmp_path, doctor_exit=0)
    res = _run(probe, env=env)
    assert res.returncode == 0, res.stderr
    assert "[CRIT]" in res.stdout  # doctor output passed through


def test_reality_probe_warn_passes_through_without_push(tmp_path: Path) -> None:
    probe, marker, env = _temp_reality_probe(tmp_path, doctor_exit=1)
    res = _run(probe, env=env)
    assert res.returncode == 1  # exit code passthrough for the cron log
    assert not marker.exists()  # WARN never pages


def test_reality_probe_crit_pushes_through_notify_failure(tmp_path: Path) -> None:
    """CRIT pushes via notify-failure.sh — the ONE topic source (env/.env),
    no hardcoded topic or inline curl in the probe."""
    probe, marker, env = _temp_reality_probe(tmp_path, doctor_exit=2)
    res = _run(probe, env=env)
    assert res.returncode == 2
    assert marker.exists()  # alert path fired
    src = (SCRIPTS / "reality-probe.sh").read_text(encoding="utf-8")
    assert "notify-failure.sh" in src
    assert "curl" not in src  # push goes through the shared script only


def test_notify_env_var_beats_dotenv(tmp_path: Path) -> None:
    """notify-failure.sh reads $NTFY_TOPIC first (the same env source the
    probe environment provides), falling back to .env — unified alert
    config. Faked curl on PATH records the URL it was given."""
    script = _temp_notify(tmp_path, env_contents="NTFY_TOPIC=dotenv-topic\n")
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    curl_log = tmp_path / "curl_args.txt"
    fake_curl = bin_dir / "curl"
    fake_curl.write_text('#!/usr/bin/env bash\necho "$@" >> "' + str(curl_log) + '"\nexit 0\n')
    _make_executable(fake_curl)
    # os.pathsep keeps the injected PATH valid on both POSIX (:) and the
    # Windows Git-Bash host (; — MSYS converts it for the child bash).
    env = _base_env(
        NTFY_TOPIC="env-topic",
        PATH=f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
    )
    res = _run(script, "msg", env=env)
    assert res.returncode == 0
    args = curl_log.read_text()
    assert "ntfy.sh/env-topic" in args  # env var won
    assert "dotenv-topic" not in args
