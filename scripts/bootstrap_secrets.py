"""Decrypt ``secrets.enc.yaml`` (SOPS + age) and merge into ``.env``.

Usage:
    make bootstrap-secrets
    # or
    uv run python scripts/bootstrap_secrets.py

This is the per-machine onboarding step for any cloned working copy. It
expects the ``sops`` CLI and an age private key to be already present on
the machine -- see :doc:`docs/SECRETS.md` for the one-time setup.

Behavior:

* If ``.env`` does not exist, it is created from ``.env.example`` first
  so commented-out defaults and tunables are preserved verbatim.
* Each ``KEY: value`` in ``secrets.enc.yaml`` is decrypted and either
  rewritten in place (if a line ``KEY=...`` already exists) or appended.
* Comments, blank lines, and KEYs not in the encrypted file are left
  untouched -- machine-specific tweaks (LOG_LEVEL, KQ_LIVE, etc.) survive
  re-runs of this script.

Failure modes are made explicit:

* ``sops`` not on PATH -> install instructions printed; exit 1.
* No age key configured -> the underlying ``sops`` error surfaces; exit 1.
* ``secrets.enc.yaml`` missing -> exit 1 with a pointer to docs/SECRETS.md.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SECRETS_ENC = REPO_ROOT / "secrets.enc.yaml"
ENV_FILE = REPO_ROOT / ".env"
ENV_EXAMPLE = REPO_ROOT / ".env.example"


def _check_sops_installed() -> bool:
    if shutil.which("sops") is not None:
        return True
    sys.stderr.write(
        "ERROR: `sops` CLI not found on PATH.\n"
        "Install:\n"
        "  Mac:     brew install sops age\n"
        "  Windows: scoop install sops age   (or: winget install Mozilla.SOPS FiloSottile.age)\n"
        "  Linux:   apt-get install sops age (or use the GitHub releases)\n"
        "See docs/SECRETS.md for the full one-time setup.\n"
    )
    return False


def _decrypt_to_dotenv(secrets_path: Path) -> str | None:
    """Run ``sops --decrypt --output-type dotenv`` and return stdout, or None on error."""
    result = subprocess.run(
        ["sops", "--decrypt", "--output-type", "dotenv", str(secrets_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(
            f"sops decrypt failed (exit {result.returncode}):\n{result.stderr}\n"
            "If this is the first time on this machine, you need an age private key at "
            "~/.config/sops/age/keys.txt (Mac/Linux) or %APPDATA%\\sops\\age\\keys.txt "
            "(Windows). See docs/SECRETS.md.\n"
        )
        return None
    return result.stdout


def _parse_dotenv(text: str) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines from a dotenv-format string. Strips whitespace."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def _merge_into_env_file(env_path: Path, secrets: dict[str, str]) -> tuple[int, int]:
    """Update ``env_path`` so each ``KEY`` in ``secrets`` has the expected value.

    * Existing line ``KEY=...`` -> rewritten in place (preserves position).
    * Key not in file -> appended at end with a separator comment if needed.
    * All other lines (comments, blanks, unrelated keys) -> untouched.

    Returns ``(updated_in_place, appended)``.
    """
    if not env_path.exists():
        # Cold start: write a minimal file with just the secrets, no template
        # (caller is expected to copy from .env.example before calling us).
        env_path.write_text("\n".join(f"{k}={v}" for k, v in secrets.items()) + "\n")
        return (0, len(secrets))

    existing_lines = env_path.read_text().splitlines()
    out_lines: list[str] = []
    seen: set[str] = set()
    updated = 0

    for line in existing_lines:
        stripped = line.lstrip()
        if "=" in stripped and not stripped.startswith("#"):
            k = stripped.partition("=")[0].strip()
            if k in secrets:
                out_lines.append(f"{k}={secrets[k]}")
                seen.add(k)
                updated += 1
                continue
        out_lines.append(line)

    appended_keys = [k for k in secrets if k not in seen]
    if appended_keys:
        if out_lines and out_lines[-1].strip() != "":
            out_lines.append("")
        out_lines.append("# ---- Added by scripts/bootstrap_secrets.py ----")
        for k in appended_keys:
            out_lines.append(f"{k}={secrets[k]}")

    env_path.write_text("\n".join(out_lines) + "\n")
    return (updated, len(appended_keys))


def main() -> int:
    if not _check_sops_installed():
        return 1

    if not SECRETS_ENC.exists():
        sys.stderr.write(
            f"ERROR: {SECRETS_ENC.name} not found at repo root.\n"
            "If this is your first time, the secret store hasn't been created yet. "
            "See docs/SECRETS.md for how to bootstrap it.\n"
        )
        return 1

    if not ENV_FILE.exists() and ENV_EXAMPLE.exists():
        shutil.copy(ENV_EXAMPLE, ENV_FILE)
        print(f"Created {ENV_FILE.name} from {ENV_EXAMPLE.name}")

    decrypted = _decrypt_to_dotenv(SECRETS_ENC)
    if decrypted is None:
        return 1

    secrets = _parse_dotenv(decrypted)
    if not secrets:
        sys.stderr.write(
            f"WARNING: decryption succeeded but no keys parsed -- is {SECRETS_ENC.name} empty?\n"
        )
        return 0

    updated, appended = _merge_into_env_file(ENV_FILE, secrets)
    print(
        f"Loaded {len(secrets)} secrets into {ENV_FILE.name} "
        f"(updated {updated} in place, appended {appended} new)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
