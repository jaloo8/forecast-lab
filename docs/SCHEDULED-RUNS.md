# SCHEDULED-RUNS.md — Running ingests on a schedule

This doc covers **Week 1 of CLAUDE.md §10**: run `kq ingest` on cron. Switch to Prefect 3 only if cron becomes unmanageable (typically month 2+).

## Summary

- One aggregate command runs everything: `uv run python -m kq ingest`
- It runs weather + METAR + NDFD + Kalshi + observed truth (ACIS) in sequence, tolerates per-sub-flow failures, and exits non-zero only if *every* sub-flow failed.
- No dedicated daemon. Cron triggers the command; the command exits; cron fires again on the next schedule.

## Recommended cadences

These match CLAUDE.md §5 Phase 1 and were chosen to balance freshness with rate-limit politeness.

| What | Cadence | Why |
|---|---|---|
| Weather ensembles | every 6 hours | Matches GEFS/ECMWF model cycles (00/06/12/18 UTC) |
| METAR observations | every 10 minutes | Same cadence as NWS updates; hourly is the bound anyway |
| Kalshi orderbook | every 1 minute during trading hours | Cron's minimum granularity; sub-minute needs Prefect later |

The aggregate `kq ingest` runs all four in one invocation — so you can schedule it coarsely (say, every 10 minutes) and accept weather being pulled more often than strictly necessary. The alternative is separate schedules for each flow, shown below.

## Option 1 — single schedule (simplest)

Run everything every 10 minutes. Weather endpoints cache aggressively so the extra calls are cheap.

```cron
# forecast-lab — all-in-one every 10 minutes
*/10 * * * * cd /path/to/forecast-lab && /path/to/uv run python -m kq ingest >> /path/to/forecast-lab/logs/cron.log 2>&1
```

## Option 2 — per-flow schedules (polite)

```cron
# Weather: every 6 hours aligned to model cycles
15 0,6,12,18 * * * cd /path/to/forecast-lab && /path/to/uv run python -m kq ingest-weather >> /path/to/forecast-lab/logs/cron.log 2>&1

# METAR: every 10 minutes
*/10 * * * * cd /path/to/forecast-lab && /path/to/uv run python -m kq ingest-metar >> /path/to/forecast-lab/logs/cron.log 2>&1

# Kalshi: every minute, limited to trading hours 13:00-23:00 UTC (9am-7pm ET)
* 13-23 * * * cd /path/to/forecast-lab && /path/to/uv run python -m kq ingest-kalshi >> /path/to/forecast-lab/logs/cron.log 2>&1
```

## Install on Mac (M1 Pro, development host)

The Mac is dev, not prod — you don't need a cron here normally. If you want one for local testing:

```bash
mkdir -p logs
crontab -e
# Paste Option 1 or Option 2. Use absolute paths; cron has no HOME or PATH.
# Example absolute paths:
#   uv        /Users/jloo/.local/bin/uv
#   project   /Users/jloo/Documents/GitHub/forecast-lab
```

## Install on Windows (prod host) via WSL2

> **Already installed (2026-05-24):** a **demo** soak crontab (16 jobs: ingest + weekly backtest + nightly backup + ntfy heartbeat) on the Windows PC — `crontab -l` to inspect, `crontab -r` to remove. cron is systemd-managed (`systemctl is-active cron` → active), so the `sudo service cron` dance below isn't needed **once WSL2 is up**. **Key gotcha:** WSL2 shuts its VM down when idle, which silently stops cron — verified the hard way (jobs hadn't fired). Fix is a **keep-alive** that holds the VM open: a detached `wsl … sleep infinity` runs now, and `Desktop\forecast-lab-ENABLE-KEEPALIVE.ps1` (run elevated) makes it survive reboots via a logon scheduled task. Alerting/backup/keep-alive scripts are on branch `feat/ops-hardening`. NBA-odds cadence is 6h (quota-safe). On `KALSHI_ENV=demo` the Kalshi passes find 0 markets; switch to prod ([`research/KALSHI-PROD-SWITCH.md`](research/KALSHI-PROD-SWITCH.md)) to book real paper trades. Full record: [`SESSION-2026-05-24-AUDIT.md`](SESSION-2026-05-24-AUDIT.md).

Run `crontab -e` inside your WSL2 distro. Cron needs to be started once per Ubuntu boot:

```bash
sudo service cron status
sudo service cron start   # if not running
sudo update-rc.d cron defaults   # optional: auto-start on WSL2 boot
```

Then `crontab -e` and paste the same recipe, adjusting paths for your Linux home (e.g. `/home/jason/forecast-lab`).

### WSL2 caveat — must be running

Cron only fires when WSL2 is actually running. Two options:
1. Leave a WSL2 terminal open on the Windows PC (simplest).
2. Use `wsl.exe --exec ...` in Windows Task Scheduler as a keep-alive, or configure the WSL2 systemd service to auto-run.

Per Pass 2 §B6, v1 doesn't need heroics here — a `wsl.exe` instance started at Windows boot via Task Scheduler keeps the Linux side alive indefinitely.

### Recommended for an always-on host: native Windows, no WSL2

The keep-alive above is a mitigation, not a fix, and it failed in production —
the WSL2 VM idled down, cron stopped, and nothing alerted. `logs/cron.log` has
a near-total gap between 2026-06-05 and 2026-07-27, and `paper_trade` still has
0 rows (verified 2026-07-27), so the Phase 5 settled-trade clock has never
started.

**For a dedicated 24/7 box, deploy natively on Windows and schedule with Task
Scheduler instead: [`DEPLOY-WINDOWS.md`](DEPLOY-WINDOWS.md).** There is no VM to
idle down — Task Scheduler is part of the OS and runs whether or not anyone is
logged in — so the failure mode is removed rather than papered over. `uv`
brings its own Python; WSL is not needed at all. The trade-offs (the six ops
shell scripts are bash, GRIB2 ingest is Mac/WSL2-only) are listed in that doc.

Everything above and below stays valid for Linux, Mac, and any WSL2 install —
this is a recommendation for the production host, not a deprecation.

> **Cutover status: pending.** The production schedule still runs in the WSL2
> crontab on the Windows box (17 entries as of 2026-07-27). Nothing has moved
> to Task Scheduler yet.

## Timezone: cron does not run in UTC unless you say so

Every cadence in this doc is written in **UTC**, and several jobs are ordered
around venue events in UTC — `kq paper` must run before Kalshi's ~15:00 UTC
weather settlement, `kq ingest-observed` (10:00 UTC) before the 16:00 UTC settle
pass that reads the table it fills.

But cron interprets its schedule in the **host's local timezone** unless the
crontab sets `CRON_TZ=UTC` (Vixie cron) or the host clock itself is UTC.
Verified on the WSL2 cron host 2026-07-27: `/etc/timezone` is
`America/Los_Angeles` and the crontab sets no `CRON_TZ`, so the entries in this
doc fire on Pacific time there — `30 14 * * *` runs at 14:30 PDT (21:30 UTC),
seven hours after the intent, i.e. the submit pass lands well after the
settlement it is supposed to precede. Check any host before trusting its
schedule:

```bash
date; date -u          # do these differ?
crontab -l | grep CRON_TZ
```

Fix by making the intent explicit — either put `CRON_TZ=UTC` at the top of the
crontab (above the entries; it applies to the lines that follow), or set the
host clock to UTC. Note that DST makes a local-time schedule drift by an hour
twice a year on top of the fixed offset. Windows Task Scheduler has the same
trap in a different costume; see the UTC-vs-local section of
[`DEPLOY-WINDOWS.md`](DEPLOY-WINDOWS.md).

What this does *not* affect: interval jobs (`*/15` METAR, hourly Kalshi), and
the stored data — every timestamp written by `src/kq` uses `datetime.now(UTC)`,
so DuckDB stays UTC regardless of the host clock.

## Log rotation

Cron output lands in `logs/cron.log`. Rotate with `logrotate`:

```
# /etc/logrotate.d/forecast-lab (Linux/WSL2)
/path/to/forecast-lab/logs/*.log {
    daily
    rotate 14
    compress
    missingok
    notifempty
}
```

On Mac, `newsyslog` serves the same purpose.

If you use `kq --log-file <path>` instead of shell `>>` redirection, give
**each cron job its own file** (e.g. `logs/ingest.log`, `logs/paper.log`):
the built-in daily rotation (`TimedRotatingFileHandler`) is not
multi-process safe, so concurrent jobs sharing one `--log-file` can race
the midnight rename. Shell `>>` redirection into one shared `cron.log` +
logrotate (above) does not have this problem.

## What to expect

- `cron.log` fills with structlog JSON lines plus the 5-line per-run summary:
  ```
    OK  weather: 3444 rows
    OK  metar: 6 rows
    OK  ndfd: 6 rows
    ERR kalshi: 0 rows (credentials missing)
    OK  observed: 24 rows
  ```
- Weather cold-starts are ~8 seconds (6 stations × 2 models, serialized). METAR is ~1 second. Kalshi depends on market count — expect a few seconds during trading hours, skipped in off-hours.
- `make ingest` is the same command; useful for one-shot debug runs.

## When to graduate past cron

Signs you've outgrown cron:

- Schedules get dependencies (X only after Y completes successfully).
- You need sub-minute triggers for Kalshi book snapshots.
- You want first-class retry / DLQ semantics.
- You want a UI to inspect past runs.

At that point, per Pass 2 §B3, move to **Prefect 3** — `uv add prefect` and convert `flows/ingest_all.py` into a Prefect `@flow`. The Python code stays the same; only the scheduler changes.

---

## Paper-trading cron — Phase 2 exit criteria

CLAUDE.md §5 Phase 2 exit blocker: **14 days of continuous paper trading + ≥ 50 settled paper trades on the Windows box.** This is the operational gate before any live-money discussion. Add these cron entries on the Windows WSL2 host AFTER Phase 1 ingest is reliably running for 7+ days.

### Schedule recap

| What | Cadence | Why |
|---|---|---|
| Backtest (4 strategies) | weekly, Sunday 02:00-04:00 UTC | Refresh manifests with new training data. ~10 min wall time per strategy. |
| Decide router | weekly, Sunday 04:00 UTC | After all 4 backtests land, recompute per-station NGR-vs-RAW decisions. |
| Paper-trade submit (weather) | daily, **before** Kalshi market settlement (15:00 UTC for weather contracts, choose 14:30 UTC) | One pass/day per CLAUDE.md, mirrors the live executor's intended cadence. |
| Observed-truth ingest (ACIS) | daily 10:00 UTC | Refreshes `weather_observed` (trailing 3 days, idempotent) after each station's morning climate report publishes — the settle pass can never fire without it (audit 2026-06-11 #7). |
| Paper-trade settle (weather) | daily, **after** Kalshi settlement (chose 16:00 UTC) | Idempotent; resolves yesterday's open paper trades against actual observed truth. |
| Paper-trade submit + settle (NBA) | hourly during peak game window (22:00-04:00 UTC) + once 12:30 UTC for overnight settle | Pinnacle line movement is the edge driver; hourly catches the late-money close. Drives Phase 5 #5 accumulation. |
| Upstream: ingest-nba-schedule | daily 11:00 UTC | Populates `nba_game` with today's matchups. |
| Upstream: ingest-nba-odds | hourly during peak (22:15-04:15 UTC) | Pinnacle h2h via The Odds API; free-tier `regions=eu` is sufficient at this cadence. |
| Upstream: build-nba-crosswalk | daily 11:30 UTC | Matches Odds API UUIDs to nba_api game_ids; runs after schedule + at least one odds pull. |

### Weekly reality probe (post-2026-06-11 audit)

`kq doctor` checks the system against the LIVE venue — payload shape, parser
coverage, settlement-source text, orderbook format — plus DB truth freshness
and the Phase 5 clocks. The audit showed wire-format drift can silently zero
the system for weeks; this probe bounds that exposure to one week.

```cron
# Weekly: reality-contact probe. Pushes ntfy on CRIT (reality drift).
# The ntfy topic is read from NTFY_TOPIC in .env (the same single source
# notify-failure.sh uses) — do NOT put a real topic name in the crontab or
# in this doc; anyone who knows an ntfy topic can read/publish to it.
0 13 * * 1 cd /home/jason/forecast-lab && ./scripts/reality-probe.sh >> /home/jason/forecast-lab/logs/cron.log 2>&1
```

Also run `make doctor` manually after every deploy to the box.

### Crontab entries

Add to the existing WSL2 crontab on the Windows PC. **Adjust the absolute paths** to match your install — `which uv` and `pwd` inside WSL2 reveal the right values.

```cron
# Weekly: refresh backtest manifests on Sunday 02:00 UTC.
# Runs all 4 strategies sequentially (~40min total). The router_v1 manifest
# is the active driver; the others are baseline comparisons.
0  2 * * 0 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq backtest --strategy weather_v1              >> /home/jason/forecast-lab/logs/cron.log 2>&1
30 2 * * 0 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq backtest --strategy weather_router_v1      >> /home/jason/forecast-lab/logs/cron.log 2>&1
0  3 * * 0 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq backtest --strategy weather_all_raw_v1     >> /home/jason/forecast-lab/logs/cron.log 2>&1
# NOTE (2026-08-08): the reforecast arm below is canonical for Mac/WSL hosts
# ONLY. It is deliberately NOT registered on the Windows host (a8): the host
# DB has no GEFSv12 reforecast rows and the GRIB tooling that produces them
# has no Windows wheels, so the job fails loudly every Sunday by design
# (2026-07-01 audit: never silently substitute). Declared in
# KNOWN_DIVERGENCES in tests/test_scheduled_job_coverage.py; re-register
# after a reforecast backfill lands in the host DB.
30 3 * * 0 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq backtest --strategy weather_reforecast_v1  >> /home/jason/forecast-lab/logs/cron.log 2>&1

# Weekly: recompute router decisions after all 4 backtests have landed.
0  4 * * 0 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq decide-router >> /home/jason/forecast-lab/logs/cron.log 2>&1

# Daily: paper-trading submit pass (one pass per day, mirroring the live cadence).
30 14 * * * cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq paper >> /home/jason/forecast-lab/logs/cron.log 2>&1

# Daily: observed-truth ingest (NWS ACIS daily climate values — the exact numbers
# Kalshi settles on) for the trailing 3 days, all stations. 10:00 UTC is after
# every station's early-morning climate report publishes and before the 16:00 UTC
# settle pass that reads this table (audit 2026-06-11 #7: settlement can never
# fire without a scheduled truth ingest). Idempotent — late corrections upsert.
0  10 * * * cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq ingest-observed >> /home/jason/forecast-lab/logs/cron.log 2>&1

# Daily: settlement pass — idempotent, resolves yesterday's open trades.
0  16 * * * cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq paper --settle-only >> /home/jason/forecast-lab/logs/cron.log 2>&1

# --- NBA paper-trading (Phase 5 #5: CLV vs Pinnacle on >= 100 settled games) ---
# Hourly during NBA peak hours (US evenings UTC = 22:00-04:00 next day). Each
# pass: pulls open Kalshi NBA markets, joins to latest Pinnacle quote +
# current Elo state, writes any sized intents, settles trades whose underlying
# game has resolved. Idempotent.
#
# Cadence is hourly rather than the once-daily weather cadence because line
# movement on Pinnacle is what drives edge — refreshing only once misses
# the late-money Kalshi opportunities that close just before tipoff.
0 22-23 * * * cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq paper-nba >> /home/jason/forecast-lab/logs/cron.log 2>&1
0 0-4 * * *  cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq paper-nba >> /home/jason/forecast-lab/logs/cron.log 2>&1

# Daily morning: NBA settle-only pass, picks up overnight finished games.
30 12 * * * cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq paper-nba --settle-only >> /home/jason/forecast-lab/logs/cron.log 2>&1

# Upstream NBA flows that paper-nba depends on (cron entries belong here too):
#   - kq ingest-nba-schedule  (yesterday + today's games; populates nba_game)
#   - kq ingest-nba-odds      (Pinnacle h2h via The Odds API; populates nba_odds)
#   - kq build-nba-crosswalk  (matches Odds API uuid -> nba_api game_id)
# Suggested cadence: ingest-nba-schedule daily 11:00 UTC, ingest-nba-odds
# hourly during game windows (matches paper-nba), build-nba-crosswalk daily
# 12:00 UTC (after schedule + at least one odds pull).
0  11 * * * cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq ingest-nba-schedule >> /home/jason/forecast-lab/logs/cron.log 2>&1
15 22-23 * * * cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq ingest-nba-odds >> /home/jason/forecast-lab/logs/cron.log 2>&1
15 0-4 * * *  cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq ingest-nba-odds >> /home/jason/forecast-lab/logs/cron.log 2>&1
30 11 * * * cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq build-nba-crosswalk >> /home/jason/forecast-lab/logs/cron.log 2>&1

# --- NFL TEAM lane (Phase B1). Built and prod-verified but never scheduled
# until 2026-08-06 — nfl_game and nfl_odds were both empty and the lane had
# booked zero trades. Cadence is deliberately BELOW the flow docstrings'
# recommendation: those ask for an hourly baseline plus 15-min game-day bursts,
# which the odds flow itself costs at 800-900 Odds API credits/month in season
# — over the free 500/mo tier once NBA's ~210/mo is stacked on. This game-day
# schedule is ~12 credits/week. The $30/mo tier (CLAUDE.md §11) would unlock
# the denser line history CLV measurement wants; that is a budget decision.
# ET->UTC converted at EDT; re-align after the November DST change. ---
40 10 * * * cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq ingest-nfl-schedule >> /home/jason/forecast-lab/logs/cron.log 2>&1
55 11 * * * cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq build-nfl-crosswalk >> /home/jason/forecast-lab/logs/cron.log 2>&1
# Odds ~T-60 before each Sunday slate (1:00pm / 4:25pm / 8:20pm ET)
10 16 * * 0 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq ingest-nfl-odds >> /home/jason/forecast-lab/logs/cron.log 2>&1
10 19 * * 0 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq ingest-nfl-odds >> /home/jason/forecast-lab/logs/cron.log 2>&1
10 23 * * 0 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq ingest-nfl-odds >> /home/jason/forecast-lab/logs/cron.log 2>&1
# Paper submit 15 min after each odds pull so the Pinnacle anchor is fresh
25 16 * * 0 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq paper-nfl >> /home/jason/forecast-lab/logs/cron.log 2>&1
25 19 * * 0 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq paper-nfl >> /home/jason/forecast-lab/logs/cron.log 2>&1
25 23 * * 0 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq paper-nfl >> /home/jason/forecast-lab/logs/cron.log 2>&1
# Settlement sweep: no Odds API credit, idempotent, catches Mon/Thu night games
40 12 * * * cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq paper-nfl --settle-only >> /home/jason/forecast-lab/logs/cron.log 2>&1

# --- NDFD benchmark forecast (the public baseline every weather model is
# scored against). 6-hourly, offset :20 off the writer grid. ---
20 */6 * * * cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq ingest-ndfd >> /home/jason/forecast-lab/logs/cron.log 2>&1

# --- Social / open-news event lane (Phase S1). Reddit Atom + RSS allowlists;
# EVENT TRIGGERS ONLY, never a probability input (CLAUDE.md §2). Every 15 min
# at :03/:18/:33/:48 -- offset minutes keep this writer off the metar
# (:00/:15/:30/:45), kalshi (:07/:22/:37/:52) and heartbeat (:05/:35) grid,
# because DuckDB is single-writer. Year-round: off-season roster news is
# still signal. ---
3,18,33,48 * * * * cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq ingest-social >> /home/jason/forecast-lab/logs/cron.log 2>&1

# --- Fantasy NFL lane (F1). In-season only in practice: each flow self-no-ops
# when nflverse has not published the season yet, so registering year-round is
# safe. Tue catches the full MNF slate, Wed sweeps nflverse corrections;
# scoring runs after the Wed corrections land; projections run Tue + Sun
# morning. Times are offset off the single-writer grid and clear of the
# same-hour daily jobs (nba-schedule 11:00, ndfd 12:20, nba-settle 12:30). ---
10 11 * * 2 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq ingest-nfl-players >> /home/jason/forecast-lab/logs/cron.log 2>&1
10 11 * * 3 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq ingest-nfl-players >> /home/jason/forecast-lab/logs/cron.log 2>&1
40 12 * * 2 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq project-fantasy-nfl >> /home/jason/forecast-lab/logs/cron.log 2>&1
10 13 * * 0 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq project-fantasy-nfl >> /home/jason/forecast-lab/logs/cron.log 2>&1
10 12 * * 3 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq score-fantasy-projections >> /home/jason/forecast-lab/logs/cron.log 2>&1

# --- Ops jobs. On the native-Windows host these run as PowerShell ports of
# the same scripts (scripts\*.ps1), registered by
# scripts/install-ops-tasks.ps1 rather than by the crontab. Listed here
# because THIS FILE is the canonical fleet list that
# tests/test_scheduled_job_coverage.py asserts against -- an ops job missing
# from here is exactly as invisible as a data lane missing from here. ---
50 9 * * * cd /home/jason/forecast-lab && ./scripts/backup-duckdb.sh >> /home/jason/forecast-lab/logs/cron.log 2>&1
10 0 * * * cd /home/jason/forecast-lab && ./scripts/rotate-logs.sh >> /home/jason/forecast-lab/logs/cron.log 2>&1
# Dashboard is a long-running service (AtStartup on Windows), not a periodic
# job; the cron-equivalent is an @reboot entry.
@reboot     cd /home/jason/forecast-lab && ./scripts/run-dashboard.sh >> /home/jason/forecast-lab/logs/dashboard.log 2>&1
# Status report: every 8h, anchored 00/08/16 local (prediction markets are
# 24/7; the 08:00 edition lands after the 07:30 paper-submit).
# :25, not :00 — the report runs `kq health-check`, which competes with the
# metar writer (:00/:15/:30/:45) for the single-writer DuckDB lock and with
# concurrent `uv run` invocations for the venv lock. Firing on the hour put
# every edition inside that window; one rendered "CRIT - 0 checks OK" on a
# system that was actually fine (2026-08-08). Same offset lesson kq-cron-health
# learned at :05/:35. The report also retries before reporting UNKNOWN.
25 */8 * * * cd /home/jason/forecast-lab && ./scripts/status-report.sh >> /home/jason/forecast-lab/logs/cron.log 2>&1
```

### Phase 2 exit checklist

After these cron entries have been running for 14 days continuously, run the
two ops commands shipped for this purpose:

```bash
# Aggregated rollup of the paper-trading window (read-only, no DB writes).
# Returns exit 0 iff both Phase 5 gates pass; 1 if still accumulating; 2 on
# fundamental error.
uv run python -m kq paper-summary --start 2026-XX-XX --end 2026-XX-XX

# Equivalent JSON-only output for cron alerting:
uv run python -m kq paper-summary --json | jq '.phase5_passes_settled_count, .phase5_passes_active_days'
```

The summary surfaces `n_settled`, `n_active_days`, win rate, total PnL,
current bankroll, and per-station breakdown. The two boolean gates
(`phase5_passes_settled_count`, `phase5_passes_active_days`) are the same
ones documented in CLAUDE.md §5 readiness criterion #1.

**Bar (per CLAUDE.md §5 Phase 5 readiness):** ≥ 50 settled trades, ≥ 14
active days, no unrecoverable cron failures, calibrated Brier scores in
line with the backtest manifest, reliability diagrams (10 buckets, n-aware
threshold) with no qualifying bucket off by > 10pp. Until all hold,
Phase 5 (live trading) is blocked.

### Continuous health-check cron (recommended)

Add to the WSL2 crontab to surface stale-data / missing-manifest issues
within a single missed cron tick. The `--json` flag pairs cleanly with
ntfy/Pushover/uptime-kuma watchdogs.

The easiest correct install is the shipped wrapper, which logs the JSON
snapshot and pushes only on CRIT:

```cron
# Every 15 min: surface pipeline staleness or manifest gaps (CRIT-only push).
*/15 * * * * /home/jason/forecast-lab/scripts/cron-health.sh
```

If you inline the command instead, alert on the **exit code being >= 2** —
do NOT use a bare `|| notify`: `||` fires on any non-zero exit, so a single
WARN (exit 1, e.g. one missed cron tick) would page, contradicting the
only-on-CRIT intent:

```cron
# Every 15 min: surface pipeline staleness or manifest gaps.
# Exits 0 (OK) / 1 (WARN) / 2 (CRIT). `[ $? -ge 2 ]` alerts on CRIT only.
*/15 * * * * cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq health-check --json >> /home/jason/forecast-lab/logs/health.log 2>&1; [ $? -ge 2 ] && /home/jason/forecast-lab/scripts/notify-failure.sh "health-check CRIT"
```

The check covers:

- `weather_forecast` / `metar_obs` / `ndfd_forecast` table freshness vs the
  ingest cadence (defaults: 12h / 30min / 12h)
- `kalshi_book_snap` freshness — WARN-only in code; prod read-only has been
  wired since 2026-05-30, so tightening this to CRIT is now actionable (see
  step 5 of the prod-switch section below)
- `models/backtest_manifest.json` mtime (default ≤ 14 days — 2× the weekly
  backtest cron above, so the check can't WARN-flap in the race window
  around the Sunday regeneration)
- `models/router_config.json` mtime (default ≤ 14 days)
- `calibration_summary` — WARN-only model-quality check read from the active
  backtest manifest: flags stations with reliability `passes_bar=False` or
  conformal empirical coverage < 0.85

Exit codes: 0 = all OK, 1 = at least one WARN (no CRIT, and also the
"database busy — retry next tick" case when a cron writer transiently holds
the DuckDB lock), 2 = at least one CRIT or DB unreachable. The exit-code
test (`[ $? -ge 2 ]`) alerts only on CRIT; replace it with `|| notify` only
if you actually want WARN (exit 1) to page too.

### Verifying the alert path end-to-end (Phase 4 exit #2 drill)

To confirm the *whole* chain works — a real failure → CRIT → ntfy → your
phone — without waiting for a real outage, run the drill:

```bash
scripts/alert-drill.sh            # safe: injects an empty-DB CRIT, asserts
                                  # health-check escalates it (exit 2). No push.
scripts/alert-drill.sh --push     # + fires ONE clearly-labeled ntfy alert.
                                  # Needs NTFY_TOPIC in .env + the topic
                                  # subscribed in the ntfy app. Check your phone.
```

The drill bootstraps a *throwaway* temp DB (the real DB/logs are untouched)
and exits non-zero if health-check *fails* to escalate a broken pipeline to
CRIT — so it doubles as a regression guard on the alert threshold. The
injection leg is hermetically unit-tested in `tests/test_cron_scripts.py`.

### Failure modes to monitor

- **Cron not firing (WSL2 sleeping).** Symptom: gaps in `cron.log`. Mitigation: `wsl.exe` keep-alive in Windows Task Scheduler (see "WSL2 caveat" above), or attach a `caffeinate`-equivalent to the wsl process. **This mitigation has already failed once in production** (weeks of silently dead pipeline — see the gap noted above); the durable fix is a native-Windows deploy — [`DEPLOY-WINDOWS.md`](DEPLOY-WINDOWS.md).
- **Jobs firing at the wrong hour.** Symptom: entries land in `cron.log` at times that don't match the UTC cadences above — e.g. the submit pass running *after* settlement, so it books nothing. Cause: cron uses the host's local timezone. See [Timezone: cron does not run in UTC unless you say so](#timezone-cron-does-not-run-in-utc-unless-you-say-so).
- **Demo Kalshi API returns 0 markets in the off-season.** Symptom: `paper.submit.no_kalshi_weather_markets` warnings every day. Mitigation: see "Switching to Kalshi prod for market discovery" below.
- **Bankroll depletion.** Symptom: submit passes stop recording trades — `paper.run_once.done` shows recorded=0 with a non-positive bankroll snapshot (Kelly sizing silently returns $0 stakes; no dedicated warning is emitted). Mitigation: paper bankroll is per-environment and tracked separately from any live one. Reset via `--starting-bankroll-usd` on the next run; the settlement pass will continue resolving older trades regardless.
- **Stale forecast data.** Symptom: `paper.submit.no_forecasts` warnings (no ensemble rows for the target valid_date). Note there is no as_of-staleness cutoff — an old forecast for the right valid_date is still used silently, so verify Phase 1 ingest freshness via `kq health-check` rather than the paper-trade logs.

### Switching to Kalshi prod for market discovery (read-only)

> **Status: done on the always-on box 2026-05-30** (see
> [`SESSION-2026-05-30-AUDIT.md`](SESSION-2026-05-30-AUDIT.md)). Keep these
> steps for bootstrapping a fresh machine.

The Kalshi *demo* environment (`https://demo-api.kalshi.co`) is a sandbox
for testing the trade-execution flow; it does NOT seed real weather
contracts. Demo regularly returns 0 markets when you query a weather
event ticker, which prevents `kq paper` from finding anything to bet
against.

To unblock paper-trading without touching real-money execution:

1. **Create a Kalshi account** at <https://kalshi.com> and request API
   access. The API needs an RSA key pair: Kalshi gives you the
   `api_key_id` (UUID-ish string) and you generate the matching private
   key locally (`openssl genrsa -out secrets/kalshi.pem 2048`; upload
   the public half to Kalshi's dashboard).

2. **Save credentials and switch the env var** in `.env`:

   ```dotenv
   KALSHI_ENV=prod
   KALSHI_API_KEY_ID=<the UUID Kalshi gave you>
   KALSHI_PRIVATE_KEY_PATH=secrets/kalshi.pem
   ```

   The base URL flips from `demo-api.kalshi.co` →
   `api.elections.kalshi.com` automatically (per
   `src/kq/clients/kalshi/client.py:18-21`).

3. **No further code changes needed** for paper trading. The Kalshi
   client is read-only by design (`kq.clients.kalshi.client.KalshiClient`
   exposes no order-placement methods); switching to prod gives you
   real market data + book snapshots without any live-money risk. The
   `--live` CLI flag remains gated behind CLAUDE.md §9's two-flag
   handshake and is the only path to actual order submission.

4. **Verify** with a one-shot ingest:

   ```bash
   uv run python -m kq ingest-kalshi
   ```

   You should see non-zero `markets:` counts in the structlog output for
   each event ticker (especially during weather-contract season,
   Nov–Mar in the 2025-26 cycle).

5. **Tighten the health-check threshold** for `kalshi_book_snap` once
   prod is wired — currently it WARNs on missing because demo legitimately
   has 0 markets; under prod it should CRIT (set
   `severity_when_missing="crit"` in
   `src/kq/flows/health_check.py` for the kalshi check).

Compliance note (per [`docs/COMPLIANCE-ADDENDUM.md`](COMPLIANCE-ADDENDUM.md)):
read-only market data via prod Kalshi has the same posture as the demo
client (no real-money trading, no NMPI exposure). The Phase 5 gate in
CLAUDE.md §5 still controls when actual orders can be placed.
