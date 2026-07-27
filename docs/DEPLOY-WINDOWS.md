# DEPLOY-WINDOWS.md — running forecast-lab on a native-Windows always-on host

> **Status (2026-07-27): this is a procedure, not a record.** The production
> schedule still runs under WSL2 cron on the old box. The native-Windows
> cutover has **not** happened, and nothing below has been executed end to end
> on the target host. Update this banner and [`ROADMAP.md`](../ROADMAP.md) when
> it has.

This is the runbook for standing the repo up on a Windows machine with **no
WSL**, and scheduling the jobs that [`SCHEDULED-RUNS.md`](SCHEDULED-RUNS.md)
describes as cron entries. `SCHEDULED-RUNS.md` remains the source of truth for
*which* jobs run and *at what UTC cadence*; this doc covers *how* to run them
on Windows.

## Why native Windows

WSL2 shuts its VM down when idle, which stops cron with no error anywhere.
`SCHEDULED-RUNS.md` has listed "Cron not firing (WSL2 sleeping)" as a known
failure mode since 2026-05-24, and that is exactly what bit production: the
jobs stopped for weeks and nothing alerted (`logs/cron.log` has a near-total
gap between 2026-06-05 and 2026-07-27). `paper_trade` still has 0 rows, so the
Phase 5 settled-trade clock ([`CLAUDE.md`](../CLAUDE.md) §5 criterion #1) has
never started.

A native-Windows host removes the failure mode instead of mitigating it. Task
Scheduler is part of the OS, survives reboots, and has no VM to idle down. The
price is the platform differences in [Known platform
differences](#known-platform-differences) — mostly that the six ops scripts are
bash.

## Prereqs

| What | Notes |
|---|---|
| Windows 10 or 11, always on | Disable sleep/hibernate on AC: `powercfg /change standby-timeout-ac 0`, `powercfg /change hibernate-timeout-ac 0`. A sleeping host has the same silent-death problem as a sleeping WSL2 VM. |
| `git` | Git for Windows. It also ships `bash.exe` — relevant below. |
| `uv` | The only Python installer you need. **uv brings its own Python**; do not install Python separately. `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"`, or let `install.bat` do it. |
| **WSL** | **Not required.** Do not install it for this. |

Python version: `pyproject.toml` sets `requires-python = ">=3.12"`, so uv will
happily resolve whatever recent interpreter it finds — and the hosts have
drifted apart exactly that way (CI pins 3.12, the WSL dev box runs 3.13, a
fresh Windows host resolved 3.14). If the checkout carries a `.python-version`
file, uv honors it and that is the intended pin. Either way, run
`uv run python -V` and confirm it matches the other machines before you trust a
green test run.

## Install

```powershell
git clone https://github.com/jaloo8/forecast-lab.git C:\forecast-lab
cd C:\forecast-lab
uv sync
uv run python -m kq version
```

`uv run python -m kq version` printing the package version means the install is
sound. `uv run kq ...` is the same thing via the console script.

One-command path: double-click (or run) **`install.bat`** at the repo root. It
installs uv if missing, runs `uv sync`, then walks the `kq setup` wizard
(database, `.env`, optional Kalshi credentials). See
[`GETTING-STARTED.md`](GETTING-STARTED.md). The wizard is the friendly path;
everything it does can be done by hand with the commands in this doc.

`make` is not available on Windows and the `Makefile` assumes a POSIX shell, so
every `make <target>` in the other docs has to be run as its underlying
command. The `Makefile` at the repo root spells each one out (it is readable as
a plain text file), and the common ones are listed in
[`CLAUDE.md`](../CLAUDE.md) §12 — e.g. `make bootstrap` is
`uv run python scripts/bootstrap_db.py`, `make doctor` is `uv run python -m kq doctor`.

## What git does not carry (manual transfer)

Four things live outside git and must reach the new host by hand. Move them
over an encrypted channel (1Password, Tailscale file copy, encrypted USB).
**Never** paste key material into a chat, a doc, a commit, or a task argument.

| Item | Path | How to get it on the new host |
|---|---|---|
| Settings + API keys | `.env` | Preferred: install `sops` + `age`, put the age private key at `%APPDATA%\sops\age\keys.txt`, then `uv run python scripts/bootstrap_secrets.py` (this is what `make bootstrap-secrets` runs). The age private key itself cannot be recovered from git — see [`SECRETS.md`](SECRETS.md), and read its "Note to a Claude Code session bootstrapping a fresh clone" before touching keys. Fallback: copy `.env` from the old host. |
| Kalshi private key | `secrets/kalshi.pem` | Copy from the old host. Gitignored by design (`*.pem`, `secrets/*`). Without it, Kalshi passes run in a degraded no-credentials mode. |
| The database | `data/forecast_lab.duckdb` (+ `.wal` if present) | Copy from the old host. This file *is* the accumulated history and the Phase 5 clocks; a fresh host with an empty DB restarts those clocks at zero. Copy it while no job is writing (the backup script's `CHECKPOINT`-then-copy is the pattern). |
| Trained NGR models | `models\weather_ngr_<STATION>_lead1.pkl` | Copy from the old host, **or** regenerate with `uv run kq train-weather` then `uv run kq decide-router` (needs training history already in the DB). The `models\*.json` manifests **are** committed; only the `.pkl` files are gitignored. This is load-bearing, not cosmetic: `StrategyRouter.from_disk` refuses to start for a modeled station whose artifact is missing. The pickles are plain project dataclasses (no compiled or path-bearing objects), so copying them across OSes is fine. |

## Scheduling: `scripts\install-scheduled-tasks.ps1`

The Windows equivalent of the crontab. It registers the jobs from
[`SCHEDULED-RUNS.md`](SCHEDULED-RUNS.md) as Windows Scheduled Tasks (named
`kq-*`, grouped in one Task Scheduler folder), converts each UTC cadence to the
host's local time, and prints the UTC → local table. It is idempotent — re-run
it to update in place.

| Parameter | Purpose |
|---|---|
| `-RepoPath` | Repo root on the host. |
| `-UvPath` | Full path to `uv.exe`. Scheduled tasks get a minimal environment — the same reason every cron line in `SCHEDULED-RUNS.md` spells out `/home/jason/.local/bin/uv` instead of a bare `uv`. |
| `-TaskFolder` | Task Scheduler folder to create the tasks under (single level), so they are visible and removable as a group. |
| `-RunAsUser` | Account the tasks run as, registered "run whether the user is logged on or not". |
| `-DryRun` | Print the whole plan — UTC → local table, task names, actions, triggers — and register nothing. `-WhatIf` works too. **Run this first, every time.** |
| `-Uninstall` | Unregister every task in `-TaskFolder` and remove the folder. |
| `-WithBashJobs` / `-BashPath` | Opt in to the three bash-based jobs (backup / health / rotate). Off by default — see [Known platform differences](#known-platform-differences). |

Run `powershell -File scripts\install-scheduled-tasks.ps1 -?` for the
authoritative parameter list in your checkout. Registration needs an
**elevated** PowerShell; the script checks and tells you if you are not.

The jobs run through `scripts\kq-job.cmd`, which does what the cron line's
`cd repo && … >> logs/cron.log 2>&1` did for free: enter the repo root, run
`uv run python -m kq <subcommand>`, append the output to `logs\cron.log`, and
propagate the child's exit code so Task Scheduler's Last Run Result stays
meaningful.

Read the printed UTC → local table before you accept the install. It is the one
artifact that makes the next section's mistakes visible — and diff it against
the recipe in [`SCHEDULED-RUNS.md`](SCHEDULED-RUNS.md) rather than assuming the
two agree. The installer reproduces the **17 jobs that were live in the WSL2
crontab**, which is not the same set as the jobs that doc recommends: as of
2026-07-27 neither the crontab nor the installer schedules
`kq ingest-observed`, even though the settlement pass cannot resolve a trade
without it (audit 2026-06-11 root cause #7). Check for that gap before you rely
on the schedule.

Inspect what you actually got:

```powershell
Get-ScheduledTask -TaskPath "\forecast-lab\" |
    Get-ScheduledTaskInfo |
    Select-Object TaskName, LastRunTime, LastTaskResult, NextRunTime, NumberOfMissedRuns
```

`LastTaskResult` of `0` is success. `NumberOfMissedRuns` climbing is the
Windows analogue of "gaps in `cron.log`" — the signal nobody was watching
during the outage above.

## The UTC vs local-time gotcha

**This is the most important correctness note in this doc.** Every cadence in
`SCHEDULED-RUNS.md` is written in UTC, and several jobs are ordered around
venue events *in UTC*: the weather submit pass must run before Kalshi's ~15:00
UTC weather settlement, `ingest-observed` (10:00 UTC) must run before the 16:00
UTC settle pass that reads the table it fills.

**Windows Task Scheduler triggers fire on local wall-clock time.** A trigger
registered as "07:30" fires at 07:30 in the host's timezone — not 07:30 UTC. So
every UTC cadence has to be converted with the host's offset. The installer does
that conversion for you and prints the result; two things still bite:

**1. The day of week shifts too.** The weekly backtests are "Sunday 02:00 UTC".
On a Pacific host (the current target) that is **Saturday** 19:00 local. Convert
the day, not just the clock.

**2. DST drift.** Local time moves an hour twice a year; a trigger registered as
a local wall-clock time does not. Worked example, Pacific:

| Cron (UTC) | Job | Intent | Local, PDT (UTC-7) | Local, PST (UTC-8) |
|---|---|---|---|---|
| `0 10 * * *` | `kq ingest-observed` | before the settle pass | 03:00 | 02:00 |
| `30 14 * * *` | `kq paper` | **before** 15:00 UTC settlement | 07:30 | 06:30 |
| `0 16 * * *` | `kq paper --settle-only` | **after** settlement | 09:00 | 08:00 |
| `0 2 * * 0` | `kq backtest` (weekly) | Sunday 02:00 UTC | **Sat** 19:00 | **Sat** 18:00 |
| `50 9 * * *` | `backup-duckdb` | quiet minute | 02:50 | 01:50 |
| `*/15 * * * *` | `kq ingest-metar` | interval | no conversion | no conversion |

Register `kq paper` at 07:30 local in July and it fires at 14:30 UTC, as
intended. Come November the host goes to UTC-8, the trigger still says 07:30
local, and the job now fires at **15:30 UTC — after the settlement it was
supposed to precede**. Nothing errors. The submit pass just quietly stops
producing trades for four months.

The installer converts UTC → local **once, at install time**, and Task
Scheduler then keeps that local wall-clock time forever. So the drift is real
and it is on you to handle. Pick **one** mitigation and write down which one:

- **(a) Set the host clock to UTC** — `Get-TimeZone`, then `Set-TimeZone -Id "UTC"`
  (elevated). The installer's conversion becomes a no-op, DST drift disappears,
  and every Windows-visible timestamp (Event Viewer, Explorer, task Next Run
  Time) matches how the DB stores time. Cleanest option for a dedicated 24/7
  box; the cost is that interactive use of the machine shows UTC clocks.
- **(b) Re-run the installer after each DST transition** — the script's own
  recommendation, and it is idempotent so re-running is safe. US transitions are
  the second Sunday in March and the first Sunday in November; put both on a
  calendar. Weaker than (a): it depends on a human remembering.

A third option exists but the installer does not use it today: Task Scheduler
stores a trigger's `StartBoundary` as an ISO-8601 timestamp, and a trailing `Z`
makes it UTC (the GUI checkbox is "Synchronize across time zones"), which would
make the tasks DST-proof without touching the host clock. To see what you
actually got: `Export-ScheduledTask -TaskName <name> -TaskPath "\forecast-lab\"`
and read the `<StartBoundary>` element — no `Z` means local, so (a) or (b)
applies.

What does **not** need converting: interval jobs (`*/15` METAR, hourly Kalshi),
and the data itself. Every timestamp written by `src/kq` uses
`datetime.now(UTC)`, so what lands in DuckDB is UTC regardless of the host
clock ([`CLAUDE.md`](../CLAUDE.md) §4). Only *when jobs fire* changes.

Cron has the same trap in a different costume — see the timezone caveat in
[`SCHEDULED-RUNS.md`](SCHEDULED-RUNS.md#timezone-cron-does-not-run-in-utc-unless-you-say-so).

## Known platform differences

**The six ops shell scripts are bash.** `backup-duckdb.sh`, `cron-health.sh`,
`notify-failure.sh`, `rotate-logs.sh`, `alert-drill.sh`, `reality-probe.sh` all
start `#!/usr/bin/env bash`. Windows has no `bash` on PATH by default. Git for
Windows ships one at `C:\Program Files\Git\bin\bash.exe`; putting that on PATH
makes the scripts *run*, but it does not make them *correct*:

- `backup-duckdb.sh` and `cron-health.sh` hardcode `REPO="$HOME/forecast-lab"`
  and `UV="$HOME/.local/bin/uv"` — the Linux layout. Under Git Bash, `$HOME` is
  `C:\Users\<you>`, so both paths miss.
- `rotate-logs.sh` drives `logrotate`, which is Linux-only.

That is why `install-scheduled-tasks.ps1` leaves the three bash jobs
(backup / health / rotate) **unregistered unless you pass `-WithBashJobs`**, and
prints a report saying so. Until Windows equivalents exist, those three cron
slots are simply not covered. Where the underlying logic is Python it is
cross-platform, so you can schedule it directly and alert on the exit code:

| Bash script | Windows stand-in | Exit codes |
|---|---|---|
| `cron-health.sh` | `uv run kq health-check --json` | 0 OK · 1 WARN · 2 CRIT (alert on ≥ 2, **not** on any non-zero) |
| `reality-probe.sh` | `uv run kq doctor --json` | 0 OK · 1 WARN · 2 CRIT |
| `backup-duckdb.sh` | copy `data\forecast_lab.duckdb` on a schedule, after a DuckDB `CHECKPOINT` | — |
| `rotate-logs.sh` | none yet; watch `logs\` size | — |

**GRIB2 ingest is Mac/WSL2-only.** `eccodeslib` has no Windows wheels, so
`pyproject.toml` marks it `sys_platform != 'win32'`. That makes
`kq ingest-ecmwf-opendata`, `kq plan-gefsv12-pull`, and
`kq pull-gefsv12-reforecasts` unavailable on this host. None of them is in the
scheduled set, so the production cadence is unaffected, and the imports are
lazy so the rest of the package works normally.

**`tests/test_cron_scripts.py` skips when bash is absent.** The module carries a
`pytest.mark.skipif` on `shutil.which("bash")`, so on a host without bash those
tests skip instead of erroring. Observed on the target host on 2026-07-27,
*before* that guard: a full run produced 23 failures, all in that file, all
`FileNotFoundError: [WinError 2]` from `subprocess` — bash not on PATH. Every
other test passed. If you see those errors instead of skips, the checkout
predates the guard.

**Working directory and log appends.** The cron lines all begin with
`cd /home/jason/forecast-lab` and end with `>> logs/cron.log 2>&1`; a Scheduled
Task action is a bare `CreateProcess` with no shell, so it gets neither. Both
are the `scripts\kq-job.cmd` wrapper's job — it enters the repo root (the DB,
`logs\`, and `models\` are all resolved relative to it) and merges each run's
output into `logs\cron.log` under a retry loop, because Windows append handles
are not shared for write and jobs pile up on the hour. If you add a task by
hand, go through the wrapper rather than invoking `uv` directly.

## Verification checklist

Run top to bottom on the new host. Every step should exit 0 unless noted.

```powershell
uv run python -m kq version          # prints the package version
uv run pytest                        # full suite green (test_cron_scripts skips without bash)
uv run ruff check .                  # dev checks; optional on a pure prod host
uv run mypy src/kq
uv run kq doctor                     # live venue probes. 0 OK / 1 WARN / 2 CRIT
uv run kq health-check               # pipeline freshness. 0 OK / 1 WARN / 2 CRIT
uv run kq ingest                     # one manual pass; expect the 5-line OK/ERR summary
uv run kq dashboard                  # Streamlit opens in a browser; Ctrl+C to stop
```

Notes on what "correct" looks like:

- `kq health-check` returning **2 (CRIT) on a fresh empty database is correct**,
  not a failure. It clears once a full ingest cycle has landed.
- `kq doctor` is deliberately non-hermetic — it makes real calls to Kalshi's
  public endpoints. Run it after every deploy ([`CLAUDE.md`](../CLAUDE.md) §12).
- After the tasks are registered: dry-run first, then confirm each task's first
  fire with the `Get-ScheduledTaskInfo` command above.
- 24 hours in: `logs\cron.log` has lines from every job, `NumberOfMissedRuns` is
  0, `kq health-check` is 0 or 1 (not 2), and
  `uv run kq paper-summary --json` reports a non-zero trade count once a submit
  pass has run against live markets. `paper-summary` exits 1 while the Phase 2
  counts are still accumulating — that is informational, not a failure.

## Cutover

Not done yet. When it happens, the sequence matters:

1. Stand the Windows host up and run the whole verification checklist against a
   throwaway/empty DB.
2. **Stop the WSL2 crontab first** (`crontab -r`, or comment every line out).
   The DuckDB file is a single file with no server: two hosts running the same
   jobs against two copies diverge permanently and the histories cannot be
   merged afterwards. Only one host may be scheduled at a time.
3. Copy `data\forecast_lab.duckdb` (checkpointed, with the host idle), `.env`,
   `secrets\kalshi.pem`, and `models\*.pkl` across.
4. Register the tasks, dry-run first.
5. Watch 48 hours: task `LastTaskResult`, `logs\cron.log`, `kq health-check`,
   `kq doctor`.
6. Update this doc's status banner, [`ROADMAP.md`](../ROADMAP.md), and
   [`SCHEDULED-RUNS.md`](SCHEDULED-RUNS.md).

Keep the WSL2 box's DB copy until the Windows host has produced several days of
clean, verified runs. It is the only rollback.

## See also

- [`SCHEDULED-RUNS.md`](SCHEDULED-RUNS.md) — which jobs run, at what UTC cadence, and why
- [`GETTING-STARTED.md`](GETTING-STARTED.md) — the one-command installer path
- [`SETUP.md`](SETUP.md) — the manual per-machine setup (Mac + WSL2)
- [`SECRETS.md`](SECRETS.md) — SOPS + age, including the native-Windows key path
- [`TESTING.md`](TESTING.md) — what the suite covers and what skips where
- [`CLAUDE.md`](../CLAUDE.md) §10 — always-on host requirements
