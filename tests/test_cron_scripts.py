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
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"


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


# ----------------------------------------------------------- backup-duckdb.sh


def _backup_home(tmp_path: Path) -> tuple[Path, Path]:
    """Build a fake $HOME with a forecast-lab repo + a DB file. Returns
    (home, db_path)."""
    home = tmp_path / "home"
    db = home / "forecast-lab" / "data" / "forecast_lab.duckdb"
    db.parent.mkdir(parents=True)
    db.write_text("FAKEDB")
    return home, db


def test_backup_writes_timestamped_copy(tmp_path: Path) -> None:
    home, _db = _backup_home(tmp_path)
    dest = tmp_path / "backups"
    res = _run(
        SCRIPTS / "backup-duckdb.sh",
        env=_base_env(HOME=str(home), KQ_BACKUP_DIR=str(dest)),
    )
    assert res.returncode == 0, res.stderr
    copies = list(dest.glob("forecast_lab_*.duckdb"))
    assert len(copies) == 1
    assert copies[0].read_text() == "FAKEDB"  # content preserved


def test_backup_copies_wal_sidecar(tmp_path: Path) -> None:
    home, db = _backup_home(tmp_path)
    (db.parent / "forecast_lab.duckdb.wal").write_text("WAL")
    dest = tmp_path / "backups"
    res = _run(
        SCRIPTS / "backup-duckdb.sh",
        env=_base_env(HOME=str(home), KQ_BACKUP_DIR=str(dest)),
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
        env=_base_env(HOME=str(home), KQ_BACKUP_DIR=str(dest), KQ_BACKUP_KEEP="2"),
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
        env=_base_env(HOME=str(home), KQ_BACKUP_DIR=str(tmp_path / "b")),
    )
    assert res.returncode == 1
    assert "no DB" in res.stderr


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
    """No NTFY_TOPIC in .env -> clean no-op (exit 0), no network call."""
    script = _temp_notify(tmp_path, env_contents="OTHER_KEY=value\n")
    res = _run(script, "test message", env=_base_env())
    assert res.returncode == 0
    assert "skipping push" in res.stderr


def test_notify_skips_when_no_env_file(tmp_path: Path) -> None:
    """Missing .env entirely -> still a clean no-op (grep finds nothing)."""
    script = _temp_notify(tmp_path, env_contents=None)
    res = _run(script, "msg", env=_base_env())
    assert res.returncode == 0
    assert "skipping push" in res.stderr


def test_notify_skips_when_topic_blank(tmp_path: Path) -> None:
    """NTFY_TOPIC present but empty -> no-op."""
    script = _temp_notify(tmp_path, env_contents="NTFY_TOPIC=\n")
    res = _run(script, "msg", env=_base_env())
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
    home = tmp_path / "home"
    repo = home / "forecast-lab"
    (repo / "scripts").mkdir(parents=True)
    (home / ".local" / "bin").mkdir(parents=True)

    shutil.copy(SCRIPTS / "cron-health.sh", repo / "scripts" / "cron-health.sh")

    # Fake uv: ignore args, print canned JSON, exit with the requested code.
    uv = home / ".local" / "bin" / "uv"
    uv.write_text(f'#!/usr/bin/env bash\necho \'{{"overall":"x"}}\'\nexit {uv_exit}\n')
    _make_executable(uv)

    # Fake notify-failure: drop a marker so we can assert it was invoked.
    marker = repo / "ALERT_FIRED"
    notify = repo / "scripts" / "notify-failure.sh"
    notify.write_text(f'#!/usr/bin/env bash\ntouch "{marker}"\nexit 0\n')
    _make_executable(notify)

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


def test_cron_health_fires_alert_on_crit(tmp_path: Path) -> None:
    repo, health_log, marker = _temp_cron_health(tmp_path, uv_exit=2)
    res = _run(
        repo / "scripts" / "cron-health.sh",
        env=_base_env(HOME=str(tmp_path / "home")),
    )
    assert res.returncode == 0  # always exits 0 so cron never emails
    assert health_log.exists()
    assert marker.exists()  # CRIT (exit >= 2) -> alert fired
