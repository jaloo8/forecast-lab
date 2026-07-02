# Secrets handling — SOPS + age

> **Goal:** clone the repo on any machine, run `make bootstrap-secrets`, and have your API keys populated automatically. No more re-pasting `ODDS_API_KEY` every time you set up a fresh box.

This repo encrypts API keys with [SOPS](https://github.com/getsops/sops) (Mozilla) using [age](https://github.com/FiloSottile/age) recipients. The encrypted blob (`secrets.enc.yaml`) is committed to git; the age private key stays on each machine and never leaves it.

## TL;DR

| You're on... | Do this |
|---|---|
| **First-ever setup** (you don't have an age key yet) | [§ One-time global setup](#one-time-global-setup) |
| **A fresh clone** on a machine that already has your age key | `./install.sh` (Mac/Linux/WSL) or `install.bat` (Windows), then pick option 1 (vault key) in the `kq setup` wizard — or run `make bootstrap-secrets` directly if dependencies are already installed. See [docs/GETTING-STARTED.md](GETTING-STARTED.md). |
| **A fresh clone** on a NEW machine (no age key yet) | [§ Add a second machine](#add-a-second-machine), then `make bootstrap-secrets` |
| **Need to add or update a secret** | [§ Add or change a secret](#add-or-change-a-secret) |
| **Lost your age key** | [§ Recover from a lost age key](#recover-from-a-lost-age-key) |

## Threat model

* The encrypted file (`secrets.enc.yaml`) **is in git**. If your repo is leaked, the attacker still needs the age private key to decrypt — and the age private key is never in git.
* The age private key lives at `~/Library/Application Support/sops/age/keys.txt` (macOS), `~/.config/sops/age/keys.txt` (Linux/WSL), or `%APPDATA%\sops\age\keys.txt` (Windows). It is plaintext on disk; rely on FileVault / BitLocker / disk encryption.
* If your laptop is compromised, the secrets are compromised — no different from `.env` in plaintext today.
* Per [`CLAUDE.md` §9](../CLAUDE.md), never commit clear-text keys, age private keys, or `.env`. The `.gitignore` already excludes `.env`, `.env.*`, and `secrets/*`.

## One-time global setup

You only do this once, ever. Subsequent machines re-use the same age key (see [§ Add a second machine](#add-a-second-machine)).

**1. Install SOPS and age:**

```bash
# Mac
brew install sops age

# Windows (PowerShell)
scoop install sops age
# or:  winget install Mozilla.SOPS
#      winget install FiloSottile.age

# Linux (Debian/Ubuntu)
apt-get install sops age
```

**2. Generate your age keypair:**

Use `make keygen-age` — it picks the right path per OS automatically:

```bash
make keygen-age
```

It writes the keypair to the OS-canonical path, prints where it landed, and prints your public key. Per-OS paths it uses:

| OS | Path |
|---|---|
| macOS | `~/Library/Application Support/sops/age/keys.txt` |
| Linux / WSL2 | `~/.config/sops/age/keys.txt` |
| Native Windows (PowerShell) | `%APPDATA%\sops\age\keys.txt` (not auto-handled by this Makefile; copy the file there manually) |

> **Why per-OS:** sops 3.12+ on macOS looks for the key in Apple's standard config dir (`~/Library/Application Support`) rather than the XDG `~/.config` path. If you use the wrong path, you get `no master key was able to decrypt the file` errors even with a perfectly good key.

The generated file contains both your private key (a `AGE-SECRET-KEY-1...` line) and your public key (a `# public key: age1...` comment line at the top).

**3. Wire the public key into the repo:**

Open `.sops.yaml` at the repo root and replace the existing `age1...` recipient with your own public key. This file is committed to git — public keys are safe to commit. (This repo already ships a configured recipient, so only do this if you are re-keying from scratch; to ADD yourself alongside the existing key, see [§ Add a new recipient](#add-a-new-recipient-eg-a-co-developers-machine-a-ci-runner).)

```yaml
creation_rules:
  - path_regex: secrets\.enc\.ya?ml$
    age: age1qf4...your-public-key...
```

**4. Create the encrypted secrets file:**

```bash
sops secrets.enc.yaml
```

This opens your `$EDITOR` (or vim) on a blank YAML buffer. Add your secrets in `KEY: value` format (no quotes needed for plain alphanumeric):

```yaml
ODDS_API_KEY: your-actual-key-here
KALSHI_API_KEY_ID: your-kalshi-id
ANTHROPIC_API_KEY: sk-ant-...
PUSHOVER_USER_KEY: ...
PUSHOVER_APP_TOKEN: ...
```

Save and exit. SOPS encrypts the values in place — when you re-open the file with `cat`, you'll see `ENC[AES256_GCM,...]` blobs instead of plaintext.

**5. Commit the encrypted file:**

```bash
git add secrets.enc.yaml .sops.yaml
git commit -m "chore: bootstrap encrypted secrets store"
```

**6. Populate your `.env`:**

```bash
make bootstrap-secrets
```

Output should look like:

```
Loaded 5 secrets into .env (updated 5 in place, appended 0 new)
```

You're done.

## Note to a Claude Code session bootstrapping a fresh clone

If you are Claude Code and the user has just cloned this repo on a new machine, **before doing anything else read [§ One-time global setup](#one-time-global-setup) and [§ Add a second machine](#add-a-second-machine) below**. The flow you cannot bypass:

1. **Do NOT run `make keygen-age`** on a fresh machine if the user already has an age keypair on another machine. Generating a fresh one will orphan every secret in `secrets.enc.yaml` — the data will be permanently undecryptable from this machine. Verify with the user first whether they have an existing key elsewhere.
2. **You cannot get the age private key on your own.** It must be transferred from the user's primary machine via 1Password / Tailscale / encrypted USB / similar. Stop and prompt the user for it the moment you realize they need this step.
3. **Same for `secrets/kalshi.pem`** (if Kalshi is configured). It's gitignored, must be transferred manually. Prompt the user.
4. **Once both are in place, run `./install.sh` / `install.bat`** (which installs deps and launches `kq setup`; choose option 1 to unlock the vault) — **or `make bootstrap-secrets` on an already-installed clone.** If it errors with `Failed to get the data key`, the age key is at the wrong path — see § Common errors and apply the OS-specific fix.

For the always-on Windows PC running WSL2 cron, see also [§ Windows-via-WSL2 specifics](#windows-via-wsl2-specifics) below.

## Add a second machine

You have an existing age key on Machine A and want to use it on Machine B.

**1. Install SOPS and age on Machine B** (same commands as step 1 above).

**2. Transfer your age private key.** The destination path on Machine B depends on its OS — see the per-OS table in [§ One-time global setup](#one-time-global-setup) step 2. Pick a transfer method based on what you have:

| Method | How |
|---|---|
| **1Password / Bitwarden secure note** | Copy the contents of your existing `keys.txt` into a secure note. On Machine B, paste into the OS-canonical path. |
| **Tailscale `tailscale file`** | `tailscale file cp ~/.config/sops/age/keys.txt machine-b:` (then move to the OS-canonical path on B) |
| **Encrypted USB / iMessage to yourself** | Manual transfer; delete from intermediary after. |
| **Direct SCP/SSH** | `scp ~/.config/sops/age/keys.txt user@machine-b:~/.config/sops/age/keys.txt` |

**Avoid:** plaintext email, Slack DMs, Discord, screenshots, paste-into-chat-with-AI. The age private key is the master key.

**3. Verify it landed:**

```bash
# macOS
ls -la ~/Library/Application\ Support/sops/age/keys.txt
# Linux/WSL
ls -la ~/.config/sops/age/keys.txt
# Native Windows (PowerShell)
dir %APPDATA%\sops\age\keys.txt
```

Permissions on Mac/Linux should be `600`. If they're not: `chmod 600 <path-to-keys.txt>`.

**4. Bootstrap:**

```bash
cd path/to/forecast-lab
make bootstrap-secrets
```

Done. From now on, both machines pull from the same encrypted file in git.

## Add or change a secret

```bash
sops secrets.enc.yaml
```

This opens the editor with the **decrypted** view. Add/edit `KEY: value` lines. On save, SOPS re-encrypts.

Then, on each machine that needs the new value:

```bash
git pull           # get the latest encrypted file
make bootstrap-secrets
```

The bootstrap script merges into `.env` non-destructively — it only touches lines whose `KEY=` matches an entry in `secrets.enc.yaml`. Your `LOG_LEVEL`, `KQ_LIVE`, etc. are untouched.

## Windows-via-WSL2 specifics

Concrete runbook for the always-on Windows PC (paired with the general flow in [docs/SETUP.md § Machine 2 of 2](SETUP.md)). Everything below runs **inside WSL2 Ubuntu**, not PowerShell.

**1. Install sops + age via direct binary** (Ubuntu's repo versions are often stale; pin to the same versions the Mac uses so the wire format matches exactly):

```bash
# sops
sudo curl -fsSL https://github.com/getsops/sops/releases/download/v3.12.2/sops-v3.12.2.linux.amd64 -o /usr/local/bin/sops
sudo chmod +x /usr/local/bin/sops

# age
curl -fsSL https://github.com/FiloSottile/age/releases/download/v1.3.1/age-v1.3.1-linux-amd64.tar.gz -o /tmp/age.tar.gz
tar xzf /tmp/age.tar.gz -C /tmp
sudo install -m 755 /tmp/age/age /usr/local/bin/age
sudo install -m 755 /tmp/age/age-keygen /usr/local/bin/age-keygen
rm -rf /tmp/age /tmp/age.tar.gz

sops --version   # 3.12.2
age --version    # v1.3.1
```

**2. Transfer the age private key from the Mac.** Path inside WSL2 is `~/.config/sops/age/keys.txt`. Pick any method from [§ Add a second machine](#add-a-second-machine) — Tailscale's `tailscale file cp` is fastest if both machines are on Tailscale.

```bash
mkdir -p ~/.config/sops/age
# After transfer: file should contain two lines starting with `# created:` and `AGE-SECRET-KEY-1...`
nano ~/.config/sops/age/keys.txt   # paste contents, save with Ctrl-O Ctrl-X
chmod 600 ~/.config/sops/age/keys.txt
```

**3. Populate `.env`:**

```bash
make bootstrap-secrets
```

Expected: `Loaded N secrets into .env (updated N in place, appended 0 new)`. If you get `Failed to get the data key`, see [§ Common errors](#common-errors).

**4. Transfer the Kalshi `.pem` file** (only if Kalshi is configured in `.env`). It's at `./secrets/kalshi.pem` on the Mac per the path in `.env`'s `KALSHI_PRIVATE_KEY_PATH`. Same secure-transfer methods as the age key.

```bash
mkdir -p secrets
# After transfer:
chmod 600 secrets/kalshi.pem
```

**5. Verify end-to-end:**

```bash
uv run python -m kq version    # should print package version, no errors
grep -c "^ODDS_API_KEY=." .env  # should print 1
ls -la secrets/kalshi.pem       # should exist if Kalshi configured
```

You're now ready to wire up cron per [docs/SCHEDULED-RUNS.md](SCHEDULED-RUNS.md).

**For a Claude Code session doing this work**: stop and prompt the user at steps 2 and 4 — those are the only ones you cannot perform autonomously. Everything else is mechanical.

## Add a new recipient (e.g., a co-developer's machine, a CI runner)

1. Have them generate their own age keypair: `make keygen-age` from the repo (picks the OS-correct path and won't clobber an existing key) — or `age-keygen -o <per-OS path from § One-time global setup step 2>` outside the repo.
2. They send you their **public** key (starts with `age1...`).
3. Append it to `.sops.yaml`:

   ```yaml
   creation_rules:
     - path_regex: secrets\.enc\.ya?ml$
       age: |-
         age1qf4...your-key
         age1xyz...new-recipient
   ```

4. Re-encrypt the existing file to include the new recipient:

   ```bash
   sops updatekeys secrets.enc.yaml
   git add .sops.yaml secrets.enc.yaml
   git commit -m "chore: add <name> as secrets recipient"
   ```

The new recipient can now `make bootstrap-secrets` after pulling.

## Recover from a lost age key

If you lose your age private key (laptop wiped without a backup, etc.) and have no other machine with the key:

1. **Rotate every secret at the provider.** Generate a fresh key for The Odds API, Kalshi, Anthropic, etc.
2. **Generate a new age keypair** ([§ One-time global setup](#one-time-global-setup) step 2).
3. **Replace the public key in `.sops.yaml`** with the new one.
4. **Recreate `secrets.enc.yaml`** with the new values:

   ```bash
   rm secrets.enc.yaml
   sops secrets.enc.yaml
   # paste new values, save, exit
   git add .sops.yaml secrets.enc.yaml
   git commit -m "chore: rotate secrets after key loss"
   ```

There is no recovery path for the encrypted file's previous contents. The encryption is the point. **Treat your age key like the master password it is: at minimum, store a copy in 1Password / Bitwarden / a paper backup in a safe.**

## What gets encrypted vs. what stays in `.env.example`

`secrets.enc.yaml` should hold **only the genuinely-secret values**. Public defaults (e.g., `LOG_LEVEL=INFO`, `TZ=UTC`, `KQ_LIVE=false`) live in `.env.example` and get copied to `.env` on the first `make bootstrap-secrets` run.

A reasonable split for v1:

| In `secrets.enc.yaml` (encrypted) | In `.env.example` (plain defaults) |
|---|---|
| `KALSHI_API_KEY_ID` | `KALSHI_ENV=demo` |
| `ODDS_API_KEY` | `KALSHI_PRIVATE_KEY_PATH=./secrets/kalshi.pem` |
| `BALLDONTLIE_API_KEY` | `OPEN_METEO_API_KEY=` (empty by default) |
| `ANTHROPIC_API_KEY` | `NOAA_USER_AGENT=...` (just an email) |
| `OPENAI_API_KEY` | `DATABASE_URL=...` |
| `VOYAGE_API_KEY` | `LOG_LEVEL=INFO` |
| `PUSHOVER_USER_KEY` | `KQ_LIVE=false` |
| `PUSHOVER_APP_TOKEN` | `KQ_KELLY_FRACTION=0.15` |
| `NTFY_TOPIC` (semi-secret) | All `AGENT_*` budget caps |

The Kalshi `.pem` file at `secrets/kalshi.pem` is **not** managed by SOPS in v1 (binary files are awkward to encrypt). Copy it manually to each machine via the same secure-transfer methods as the age key.

## Common errors

| Symptom | Cause | Fix |
|---|---|---|
| `sops: command not found` | SOPS not installed | `brew install sops age` (Mac) — or direct binary download from [getsops/sops releases](https://github.com/getsops/sops/releases) + [FiloSottile/age releases](https://github.com/FiloSottile/age/releases) when brew is unavailable. |
| `Failed to get the data key required to decrypt the SOPS file` on **macOS**, key is at `~/.config/sops/age/keys.txt` | sops 3.12+ on macOS looks in Apple's standard config dir, not XDG | Move the key: `mv ~/.config/sops/age/keys.txt ~/Library/Application\ Support/sops/age/keys.txt`. Or symlink: `mkdir -p ~/Library/Application\ Support/sops/age && ln -s ~/.config/sops/age/keys.txt ~/Library/Application\ Support/sops/age/keys.txt`. The Makefile's `make keygen-age` now writes to the right path automatically. |
| `Failed to get the data key required to decrypt the SOPS file` (other OSes) | Age key missing or wrong | Verify the key file at the per-OS path (see [§ One-time global setup](#one-time-global-setup) step 2) exists and contains an `AGE-SECRET-KEY-1` line. |
| `sops decrypt failed: no matching creation rules found` | `.sops.yaml` doesn't list `secrets.enc.yaml` pattern | Verify `path_regex: secrets\.enc\.ya?ml$` |
| `No secrets parsed -- is the file empty?` | Decryption succeeded but YAML had no `KEY: value` pairs | Run `sops secrets.enc.yaml` and add some |

## CI / automation

GitHub Actions does **not** currently use these SOPS-managed secrets. The CI workflows at `.github/workflows/ci.yml` (lint/format/types/tests + Bandit against fixture data only; the coverage upload uses a separate `CODECOV_TOKEN` Actions secret) and `.github/workflows/security-weekly.yml` (scheduled pip-audit + full Bandit scan) make no live API calls and never touch the SOPS-managed API keys. If we ever need a live-API CI step, we'd add the age key as a GitHub Actions secret, install `sops` in the workflow, and decrypt at job start. Out of scope for v1.
