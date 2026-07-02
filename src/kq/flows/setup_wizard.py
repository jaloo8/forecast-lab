"""`kq setup` - the guided first-run wizard.

Design goal: installing forecast-lab should feel like installing a game.
``install.bat`` (Windows) or ``install.sh`` (Mac/Linux/WSL) gets the tools
and dependencies; this wizard does everything else - database, settings
file, optional market-account connection, and a final self-check - in
plain English, with safe defaults everywhere.

Everything here is idempotent: running ``kq setup`` again on a configured
machine just re-checks and reports.

The one thing the wizard cannot conjure is a Kalshi credential: that is a
password-equivalent for a real-money-capable account, so it must never
live in the git repo (SECURITY.md). The wizard offers the two supported
ways to provide it (the project's encrypted-vault key, or pasting your own
API details) and a zero-credential "free mode" that unlocks everything
except live Kalshi market data.
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404 - used to invoke our own bootstrap script
import sys
from pathlib import Path

import typer

from kq.config import REPO_ROOT

DB_PATH_DEFAULT = REPO_ROOT / "data" / "forecast_lab.duckdb"
ENV_PATH_DEFAULT = REPO_ROOT / ".env"
ENV_EXAMPLE_DEFAULT = REPO_ROOT / ".env.example"
BOOTSTRAP_SECRETS_SCRIPT = REPO_ROOT / "scripts" / "bootstrap_secrets.py"

_FREE_MODE_SUMMARY = """\
  Free mode is ready. Without a Kalshi account you can still:
    - download weather data (forecasts + actual temperatures)  -> kq ingest
    - train the temperature models                             -> kq train-weather
    - test the models against history                          -> kq backtest
    - open the dashboard in your browser                       -> kq dashboard
  The only things that stay off are watching/practice-trading real
  Kalshi markets. Run `kq setup` again any time to connect an account."""


def main(*, yes: bool = False) -> int:
    """Run the wizard. ``yes=True`` answers every question with its default
    (used by install scripts run in automation and by tests)."""
    return run_wizard(yes=yes)


def run_wizard(
    *,
    yes: bool = False,
    db_path: Path | None = None,
    env_path: Path | None = None,
    env_example_path: Path | None = None,
) -> int:
    """The four setup steps. Path arguments exist as test seams."""
    db = db_path or DB_PATH_DEFAULT
    env_file = env_path or ENV_PATH_DEFAULT
    env_example = env_example_path or ENV_EXAMPLE_DEFAULT

    typer.echo("")
    typer.echo("Welcome to forecast-lab! Setting you up (about 2 minutes).")
    typer.echo("")

    # -- Step 1: database ---------------------------------------------------
    typer.echo("Step 1 of 4 - Your database (where all downloaded data lives)")
    from kq.storage.duckdb_store import bootstrap  # noqa: PLC0415 - lazy: keeps --help fast

    already = db.exists()
    bootstrap(db)
    typer.echo(f"  OK - {'found existing' if already else 'created'}: {_pretty(db)}")
    typer.echo("")

    # -- Step 2: settings file ----------------------------------------------
    typer.echo("Step 2 of 4 - Your settings file (.env)")
    if env_file.exists():
        typer.echo(f"  OK - found existing: {_pretty(env_file)} (left untouched)")
    elif env_example.exists():
        shutil.copy(env_example, env_file)
        typer.echo(f"  OK - created from template: {_pretty(env_file)}")
    else:
        typer.echo("  WARNING - no .env.example template found; skipping.")
    typer.echo("")

    # -- Step 3: Kalshi account (optional) -----------------------------------
    typer.echo("Step 3 of 4 - Kalshi account (optional)")
    typer.echo("  Kalshi is the prediction-market website this project watches.")
    typer.echo("  Connecting an account lets the app see live market prices and")
    typer.echo("  practice-trade with pretend money. Skipping is completely fine -")
    typer.echo("  everything else works without it.")
    connected = _kalshi_step(env_file=env_file, yes=yes)
    typer.echo("")

    # -- Step 4: self-check ---------------------------------------------------
    typer.echo("Step 4 of 4 - Checking everything works")
    ok = _self_check(db=db, env_file=env_file, kalshi_connected=connected)
    typer.echo("")
    if connected:
        typer.echo("All set! Try these next:")
        typer.echo("  uv run kq ingest      (download today's data)")
        typer.echo("  uv run kq dashboard   (open the app in your browser)")
    else:
        typer.echo(_FREE_MODE_SUMMARY)
    typer.echo("")
    return 0 if ok else 1


def _kalshi_step(*, env_file: Path, yes: bool) -> bool:
    """Returns True if Kalshi credentials are (now) configured."""
    if _kalshi_configured(env_file):
        typer.echo("  OK - a Kalshi connection is already set up on this machine.")
        return True
    if yes:
        typer.echo("  Skipped (automatic mode) - running in free mode.")
        return False

    typer.echo("")
    typer.echo("  How would you like to continue?")
    typer.echo("    1. I have the project's secret vault key (a small file that")
    typer.echo("       unlocks the credentials already stored inside this project).")
    typer.echo("    2. I'll paste my own Kalshi API details.")
    typer.echo("    3. Skip for now - free mode. (You can rerun `kq setup` later.)")
    choice = typer.prompt("  Type 1, 2, or 3", default="3").strip()

    if choice == "1":
        return _bootstrap_from_vault()
    if choice == "2":
        return _prompt_and_write_credentials(env_file)
    typer.echo("  Skipped - running in free mode.")
    return False


def _bootstrap_from_vault() -> bool:
    """Decrypt the in-repo encrypted secrets into .env via the existing script.

    The script prints its own friendly errors (sops missing, no age key);
    we just relay success/failure.
    """
    result = subprocess.run(  # nosec B603 - fixed argv, our own script
        [sys.executable, str(BOOTSTRAP_SECRETS_SCRIPT)],
        check=False,
    )
    if result.returncode == 0:
        typer.echo("  OK - credentials unlocked from the project vault.")
        return True
    typer.echo("  That didn't work (see the message above). You can fix it and")
    typer.echo("  rerun `kq setup`, or choose option 2 or 3 instead.")
    return False


def _prompt_and_write_credentials(env_file: Path) -> bool:
    typer.echo("")
    typer.echo("  You can find these on kalshi.com under Account -> API keys.")
    key_id = typer.prompt("  Your API key ID").strip()
    pem = typer.prompt("  Path to your private key file (ends in .pem)").strip()
    pem_path = Path(pem).expanduser()
    if not pem_path.exists():
        typer.echo(f"  Hmm - no file at {pem_path}. Nothing saved; rerun `kq setup` to retry.")
        return False
    env = typer.prompt("  Practice account or real one? (demo/prod)", default="demo").strip()
    _set_env_value(env_file, "KALSHI_API_KEY_ID", key_id)
    _set_env_value(env_file, "KALSHI_PRIVATE_KEY_PATH", str(pem_path))
    _set_env_value(env_file, "KALSHI_ENV", "prod" if env.lower() == "prod" else "demo")
    typer.echo("  OK - saved to your .env file (which never leaves this computer).")
    return True


def _kalshi_configured(env_file: Path) -> bool:
    if not env_file.exists():
        return False
    values = _read_env(env_file)
    key_id = values.get("KALSHI_API_KEY_ID", "")
    pem = values.get("KALSHI_PRIVATE_KEY_PATH", "")
    return bool(key_id) and bool(pem) and Path(pem).expanduser().exists()


def _self_check(*, db: Path, env_file: Path, kalshi_connected: bool) -> bool:
    ok = True
    if db.exists():
        typer.echo(f"  OK - database ready ({_pretty(db)})")
    else:
        typer.echo("  PROBLEM - database file missing; rerun `kq setup`.")
        ok = False
    if env_file.exists():
        typer.echo(f"  OK - settings file ready ({_pretty(env_file)})")
    else:
        typer.echo("  WARNING - no settings file; defaults will be used.")
    typer.echo(
        "  OK - Kalshi connected"
        if kalshi_connected
        else "  OK - free mode (no Kalshi account connected)"
    )
    return ok


def _read_env(env_file: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, val = stripped.partition("=")
        values[key.strip()] = val.split("#", 1)[0].strip()
    return values


def _set_env_value(env_file: Path, key: str, value: str) -> None:
    """Rewrite ``KEY=...`` in place, or append; comments and order survive."""
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    prefix = f"{key}="
    replaced = False
    for i, line in enumerate(lines):
        if line.strip().startswith(prefix):
            lines[i] = f"{key}={value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{key}={value}")
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _pretty(path: Path) -> str:
    """Show paths relative to the repo when possible - shorter to read."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)
