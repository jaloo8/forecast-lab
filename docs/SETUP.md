# SETUP.md — Phase 0 environment setup

This is the historical Kalshi Phase 0 setup reference. For the current stock research path, use [Stock Paper Lab](STOCK-PAPER-LAB.md); do not initialize a second paper writer from these instructions. Recheck machine paths and current host state before following this older setup. When you're done, Phase 0 is complete and you're ready to start Phase 1 (Kalshi client + weather ingest) per [CLAUDE.md §5](../CLAUDE.md).

**Fast path:** for a dev/laptop install, run `install.bat` (Windows) or `./install.sh` (Mac/Linux/WSL) — one command installs uv, syncs deps, and runs the `kq setup` wizard. See [docs/GETTING-STARTED.md](GETTING-STARTED.md). The runbook below is the manual path and the production (WSL2 cron) setup.

**Phase 0 is tooling-only.** We are NOT writing Kalshi code, pulling weather forecasts, or building models here. The goal is: `uv run pytest` passes on both machines, DuckDB is initialized, CI is green. That's it.

---

## What you need

- **Mac (M1 Pro)** — development machine. No WSL, no Docker, no Linux. Just native macOS.
- **Windows PC** — production machine that runs overnight ingest. Cron/production runs under WSL2 so the codebase stays Linux-first (GRIB2 ingest paths are Mac/WSL2-only — no Windows wheels for `eccodeslib`). Native-Windows dev also works: run `install.bat`, which installs uv and the deps for you.

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

# 6. (Optional but recommended) install pre-commit hooks for this clone.
make install-hooks
# ruff, gitleaks, and "no direct-to-main" run on every `git commit`.
```

If all commands exit 0 and pytest shows `1,150+ passed` (130+ back when this was first run in April 2026), Phase 0 is done on this machine.

---

## Machine 2 of 2: Windows PC via WSL2 — ⬜ TODO

> **✅ COMPLETED 2026-05-24** on the Windows PC (user `jason`, repo `~/forecast-lab`). 994 tests green, DuckDB + secrets + Kalshi auth verified, demo cron soak live. Full record: [`docs/SESSION-2026-05-24-AUDIT.md`](SESSION-2026-05-24-AUDIT.md). The runbook below is retained for a wipe / re-setup. **Deviations that worked (and are now the recommended path on this box):** cloned via the Windows Git Credential Manager instead of `gh auth login` (repo is private; `gh` isn't installed) — set `git config --local credential.helper "/mnt/d/Git/mingw64/bin/git-credential-manager.exe"` then clone/push normally; installed `sops`/`age` to `~/.local/bin` instead of `/usr/local/bin` to avoid needing the WSL `sudo` password (they're only used by `bootstrap-secrets`, never cron). The header still reads "TODO" only to preserve the anchor that other docs link to.

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

# 5. Install deps (uv.lock is already committed, so this is deterministic)
uv sync

# 6. Install sops + age (for decrypting secrets.enc.yaml -> .env)
# Ubuntu's repo versions are often stale; pull current binaries direct from GitHub.
# Use the SAME version pins as the Mac side so the wire format matches exactly.
sudo curl -fsSL https://github.com/getsops/sops/releases/download/v3.12.2/sops-v3.12.2.linux.amd64 -o /usr/local/bin/sops
sudo chmod +x /usr/local/bin/sops
curl -fsSL https://github.com/FiloSottile/age/releases/download/v1.3.1/age-v1.3.1-linux-amd64.tar.gz -o /tmp/age.tar.gz
tar xzf /tmp/age.tar.gz -C /tmp
sudo install -m 755 /tmp/age/age /usr/local/bin/age
sudo install -m 755 /tmp/age/age-keygen /usr/local/bin/age-keygen
rm -rf /tmp/age /tmp/age.tar.gz
sops --version && age --version  # both should print version numbers

# 7. Provision the age private key (THIS IS THE ONLY STEP CLAUDE CAN'T DO FOR YOU)
# Copy the contents of ~/.config/sops/age/keys.txt from your Mac to this same path
# on WSL2. See docs/SECRETS.md § "Add a second machine" for transfer methods
# (1Password secure note, Tailscale file-cp, encrypted USB, etc.).
mkdir -p ~/.config/sops/age
nano ~/.config/sops/age/keys.txt   # paste the two lines from your Mac's key file
chmod 600 ~/.config/sops/age/keys.txt

# 8. Populate .env from the encrypted store
make bootstrap-secrets
# Expected output: "Loaded N secrets into .env (updated N in place, appended 0 new)"

# 9. Provision the Kalshi .pem private key (if Kalshi is configured in your .env)
# Same secure-transfer pattern as the age key — the .pem is NOT in git per .gitignore.
mkdir -p secrets
cp /path/to/transferred/kalshi.pem secrets/kalshi.pem
chmod 600 secrets/kalshi.pem

# 10. Verify
uv run ruff check .
uv run ruff format --check .
uv run mypy src/kq
uv run pytest
uv run python -m kq version

# 11. Bootstrap the DuckDB schema (separate DB from the Mac one; that's fine)
make bootstrap
```

### Verification checklist for Windows/WSL2

Tick each one before declaring Phase 0 done on Windows:

- [ ] `wsl --status` shows Version 2
- [ ] Repo is cloned under `~/forecast-lab` (NOT `/mnt/c/Users/.../forecast-lab`)
- [ ] `uv --version` prints a version number
- [ ] `uv sync` completes without errors
- [ ] `sops --version` and `age --version` both work
- [ ] `~/.config/sops/age/keys.txt` exists (mode 600) and contains the same `AGE-SECRET-KEY-1...` line as the Mac
- [ ] `make bootstrap-secrets` succeeds and prints "Loaded N secrets into .env"
- [ ] `grep -c "^ODDS_API_KEY=." .env` returns `1` (key actually present)
- [ ] `secrets/kalshi.pem` exists (if Kalshi is configured)
- [ ] `uv run pytest` is green (1,150+ passed)
- [ ] `uv run ruff check .` exits 0
- [ ] `uv run mypy src/kq` exits 0
- [ ] `uv run python -m kq version` prints the package version
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
