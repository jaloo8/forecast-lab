# SETUP.md — Phase 0 environment setup

This is the exact, verified setup for both machines. Follow it top to bottom. When you're done, Phase 0 is complete and you're ready to start Phase 1 (Kalshi client + weather ingest) per [CLAUDE.md §5](../CLAUDE.md).

**Phase 0 is tooling-only.** We are NOT writing Kalshi code, pulling weather forecasts, or building models here. The goal is: `uv run pytest` passes on both machines, DuckDB is initialized, CI is green. That's it.

---

## What you need

- **Mac (M1 Pro)** — development machine. No WSL, no Docker, no Linux. Just native macOS.
- **Windows PC** — production machine that will eventually run overnight ingest. We use WSL2 so the codebase stays Linux-first and nothing is duplicated. Do not install uv/Python on native Windows.

## Machine 1 of 2: Mac (M1 Pro) — ✅ DONE (reference only)

This was completed on 2026-04-23. Kept here so you know what "done" looks like and can re-run if the machine is wiped.

```bash
# 1. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env      # or restart terminal

# 2. Clone + env
git clone https://github.com/jaloo8/forecast-lab.git
cd forecast-lab
cp .env.example .env             # leave values empty for Phase 0

# 3. Install deps (generates uv.lock if missing)
uv sync

# 4. Verify everything
uv run ruff check .
uv run ruff format --check .
uv run mypy src/kq
uv run pytest
uv run python -m kq version      # prints 0.0.1

# 5. Bootstrap DuckDB
uv run python scripts/bootstrap_db.py
# Expected: [bootstrap] DuckDB initialized at data/forecast_lab.duckdb
```

If all commands exit 0 and pytest shows `24 passed`, Phase 0 is done on this machine.

---

## Machine 2 of 2: Windows PC via WSL2 — ⬜ TODO

### Part A: one-time WSL2 install (skip if already installed)

Open **PowerShell as Administrator**:

```powershell
wsl --install -d Ubuntu
# Reboot when prompted
```

After reboot, Ubuntu opens a terminal and asks you to create a Linux username + password. Pick anything — this is a Linux user *inside* WSL, separate from your Windows account.

Verify:

```powershell
wsl --status
# Expected: Default Distribution: Ubuntu, Default Version: 2
```

If `wsl --status` shows Version 1, run `wsl --set-default-version 2`.

### Part B: GPU passthrough (only needed later for v2 agent)

Not needed for Phase 0 or v1. Will document separately when we get to the research agent.

### Part C: clone and set up

From this point, **every command is inside the Ubuntu/WSL2 terminal**, not PowerShell.

```bash
# 1. Update Ubuntu + install build basics
sudo apt update && sudo apt upgrade -y
sudo apt install -y git build-essential curl

# 2. Install GitHub CLI (makes cloning private repos painless)
(type -p wget >/dev/null || (sudo apt update && sudo apt-get install wget -y)) \
  && sudo mkdir -p -m 755 /etc/apt/keyrings \
  && out=$(mktemp) && wget -nv -O$out https://cli.github.com/packages/githubcli-archive-keyring.gpg \
  && cat $out | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
  && sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
  && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
  && sudo apt update \
  && sudo apt install gh -y

gh auth login
# Follow the prompts: GitHub.com -> HTTPS -> "Login with a web browser"
# Paste the device code when asked.

# 3. Clone inside the Linux filesystem (NOT /mnt/c). This is important.
cd ~
git clone https://github.com/jaloo8/forecast-lab.git
cd forecast-lab

# 4. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
# Make it permanent for future shells:
echo 'source $HOME/.local/bin/env' >> ~/.bashrc

# 5. Env file
cp .env.example .env

# 6. Install deps (uv.lock is already committed, so this is deterministic)
uv sync

# 7. Verify
uv run ruff check .
uv run ruff format --check .
uv run mypy src/kq
uv run pytest
uv run python -m kq version

# 8. Bootstrap the DuckDB schema (separate DB from the Mac one; that's fine)
uv run python scripts/bootstrap_db.py
```

### Verification checklist for Windows/WSL2

Tick each one before declaring Phase 0 done on Windows:

- [ ] `wsl --status` shows Version 2
- [ ] Repo is cloned under `~/forecast-lab` (NOT `/mnt/c/Users/.../forecast-lab`)
- [ ] `uv --version` prints a version number
- [ ] `uv sync` completes without errors
- [ ] `uv run pytest` shows **24 passed**
- [ ] `uv run ruff check .` exits 0
- [ ] `uv run mypy src/kq` exits 0 ("Success: no issues found in 27 source files")
- [ ] `uv run python -m kq version` prints `0.0.1`
- [ ] `data/forecast_lab.duckdb` exists

---

## Why "clone inside WSL2, not `/mnt/c`"?

When WSL2 accesses Windows files via `/mnt/c/...`, every file read crosses a 9P protocol boundary — Python test suites have been measured at 10–20× slower. Keeping the repo in `~/` (which is inside the Linux ext4 virtual disk) makes everything feel native.

You can still edit files from VS Code or Cursor on Windows — use the "Remote - WSL" extension. VS Code opens a window "attached" to WSL, so you browse `~/forecast-lab` from a Windows GUI but the filesystem and shell are Linux.

---

## Common issues

**`curl: command not found` on WSL2.** Run `sudo apt install -y curl` first.

**`uv: command not found` after install.** You forgot to `source $HOME/.local/bin/env` (or restart the terminal). The install script tells you this — easy to miss.

**`gh auth login` opens a browser but nothing happens.** Copy the 8-character device code from the terminal and paste it into the browser manually at https://github.com/login/device.

**`uv sync` fails on a package build.** Almost always missing `build-essential`. `sudo apt install -y build-essential` and retry.

**Tests pass locally but CI fails.** The most likely cause is an en-dash or em-dash in a docstring (RUF002). Grep for it: `grep -rn '[–—]' src tests`.

**`git clone` asks for a password.** You skipped `gh auth login`. Run it and retry.

---

## What happens after Phase 0

Phase 1 starts: [CLAUDE.md §5 Phase 1](../CLAUDE.md). That's when we actually write the Kalshi API client and start pulling weather forecasts. The tooling we just set up is the *platform* — now we build things on it.

Phase 0 is complete when all boxes above are ticked on both machines. Open the next Claude Code session and say "start Phase 1."
