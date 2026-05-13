# Secrets handling — SOPS + age

> **Goal:** clone the repo on any machine, run `make bootstrap-secrets`, and have your API keys populated automatically. No more re-pasting `ODDS_API_KEY` every time you set up a fresh box.

This repo encrypts API keys with [SOPS](https://github.com/getsops/sops) (Mozilla) using [age](https://github.com/FiloSottile/age) recipients. The encrypted blob (`secrets.enc.yaml`) is committed to git; the age private key stays on each machine and never leaves it.

## TL;DR

| You're on... | Do this |
|---|---|
| **First-ever setup** (you don't have an age key yet) | [§ One-time global setup](#one-time-global-setup) |
| **A fresh clone** on a machine that already has your age key | `make bootstrap-secrets` |
| **A fresh clone** on a NEW machine (no age key yet) | [§ Add a second machine](#add-a-second-machine), then `make bootstrap-secrets` |
| **Need to add or update a secret** | [§ Add or change a secret](#add-or-change-a-secret) |
| **Lost your age key** | [§ Recover from a lost age key](#recover-from-a-lost-age-key) |

## Threat model

* The encrypted file (`secrets.enc.yaml`) **is in git**. If your repo is leaked, the attacker still needs the age private key to decrypt — and the age private key is never in git.
* The age private key lives at `~/.config/sops/age/keys.txt` (Mac/Linux/WSL) or `%APPDATA%\sops\age\keys.txt` (Windows). It is plaintext on disk; rely on FileVault / BitLocker / disk encryption.
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

Open `.sops.yaml` at the repo root and replace `REPLACE_WITH_YOUR_AGE_PUBLIC_KEY` with the `age1...` public-key line. This file is committed to git — public keys are safe to commit.

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

## Add a new recipient (e.g., a co-developer's machine, a CI runner)

1. Have them generate their own age keypair: `age-keygen -o ~/.config/sops/age/keys.txt`
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

GitHub Actions does **not** currently use these secrets. The CI workflow at `.github/workflows/ci.yml` runs lint/format/types/tests against fixture data only — no live API calls. If we ever need a live-API CI step, we'd add the age key as a GitHub Actions secret, install `sops` in the workflow, and decrypt at job start. Out of scope for v1.
