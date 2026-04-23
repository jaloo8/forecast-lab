# SCHEDULED-RUNS.md — Running ingests on a schedule

This doc covers **Week 1 of CLAUDE.md §10**: run `kq ingest` on cron. Switch to Prefect 3 only if cron becomes unmanageable (typically month 2+).

## Summary

- One aggregate command runs everything: `uv run python -m kq ingest`
- It runs weather + METAR + Kalshi in sequence, tolerates per-sub-flow failures, and exits non-zero only if *every* sub-flow failed.
- No dedicated daemon. Cron triggers the command; the command exits; cron fires again on the next schedule.

## Recommended cadences

These match CLAUDE.md §5 Phase 1 and were chosen to balance freshness with rate-limit politeness.

| What | Cadence | Why |
|---|---|---|
| Weather ensembles | every 6 hours | Matches GEFS/ECMWF model cycles (00/06/12/18 UTC) |
| METAR observations | every 10 minutes | Same cadence as NWS updates; hourly is the bound anyway |
| Kalshi orderbook | every 1 minute during trading hours | Cron's minimum granularity; sub-minute needs Prefect later |

The aggregate `kq ingest` runs all three in one invocation — so you can schedule it coarsely (say, every 10 minutes) and accept weather being pulled more often than strictly necessary. The alternative is separate schedules for each flow, shown below.

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

## What to expect

- `cron.log` fills with structlog JSON lines plus the 3-line per-run summary:
  ```
    OK  weather: 3444 rows
    OK  metar: 6 rows
    ERR kalshi: 0 rows (credentials missing)
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
