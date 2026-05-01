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

---

## Paper-trading cron — Phase 2 exit criteria

CLAUDE.md §5 Phase 2 exit blocker: **14 days of continuous paper trading + ≥ 50 settled paper trades on the Windows box.** This is the operational gate before any live-money discussion. Add these cron entries on the Windows WSL2 host AFTER Phase 1 ingest is reliably running for 7+ days.

### Schedule recap

| What | Cadence | Why |
|---|---|---|
| Backtest (4 strategies) | weekly, Sunday 02:00-04:00 UTC | Refresh manifests with new training data. ~10 min wall time per strategy. |
| Decide router | weekly, Sunday 04:00 UTC | After all 4 backtests land, recompute per-station NGR-vs-RAW decisions. |
| Paper-trade submit | daily, **before** Kalshi market settlement (15:00 UTC for weather contracts, choose 14:30 UTC) | One pass/day per CLAUDE.md, mirrors the live executor's intended cadence. |
| Paper-trade settle | daily, **after** Kalshi settlement (chose 16:00 UTC) | Idempotent; resolves yesterday's open paper trades against actual observed truth. |

### Crontab entries

Add to the existing WSL2 crontab on the Windows PC. **Adjust the absolute paths** to match your install — `which uv` and `pwd` inside WSL2 reveal the right values.

```cron
# Weekly: refresh backtest manifests on Sunday 02:00 UTC.
# Runs all 4 strategies sequentially (~40min total). The router_v1 manifest
# is the active driver; the others are baseline comparisons.
0  2 * * 0 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq backtest --strategy weather_v1              >> /home/jason/forecast-lab/logs/cron.log 2>&1
30 2 * * 0 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq backtest --strategy weather_router_v1      >> /home/jason/forecast-lab/logs/cron.log 2>&1
0  3 * * 0 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq backtest --strategy weather_all_raw_v1     >> /home/jason/forecast-lab/logs/cron.log 2>&1
30 3 * * 0 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq backtest --strategy weather_reforecast_v1  >> /home/jason/forecast-lab/logs/cron.log 2>&1

# Weekly: recompute router decisions after all 4 backtests have landed.
0  4 * * 0 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq decide-router >> /home/jason/forecast-lab/logs/cron.log 2>&1

# Daily: paper-trading submit pass (one pass per day, mirroring the live cadence).
30 14 * * * cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq paper >> /home/jason/forecast-lab/logs/cron.log 2>&1

# Daily: settlement pass — idempotent, resolves yesterday's open trades.
0  16 * * * cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq paper --settle-only >> /home/jason/forecast-lab/logs/cron.log 2>&1
```

### Phase 2 exit checklist

After these cron entries have been running for 14 days continuously, verify:

```bash
# Count settled paper trades — bar is >= 50
duckdb data/forecast_lab.duckdb "SELECT COUNT(*) FROM settlement WHERE settled_at IS NOT NULL"

# Verify no daily run gaps in the cron log
grep -c "paper.run_once.done" logs/cron.log    # expect ~14 lines (one per day)

# Inspect any cron-level failures
grep -E "ERROR|Traceback" logs/cron.log | head
```

**Bar (per CLAUDE.md §5 Phase 5 readiness):** ≥ 50 settled trades, no unrecoverable cron failures, calibrated Brier scores in line with the backtest manifest, reliability diagrams (10 buckets) with no bucket off by > 10pp. Until all hold, Phase 5 (live trading) is blocked.

### Failure modes to monitor

- **Cron not firing (WSL2 sleeping).** Symptom: gaps in `cron.log`. Mitigation: `wsl.exe` keep-alive in Windows Task Scheduler (see "WSL2 caveat" above), or attach a `caffeinate`-equivalent to the wsl process.
- **Demo Kalshi API returns 0 markets in the off-season.** Symptom: `paper.submit.no_kalshi_weather_markets` warnings every day. Mitigation: switch the Kalshi client to read-only prod API for market discovery (no live-trading risk; book snapshots only), OR wait for the active weather contract season (Nov-Mar in 2025-26 cycle). Either is a configuration change; the paper executor itself is stable.
- **Bankroll depletion.** Symptom: `kelly_stake_zero_bankroll` warnings; trades stop firing. Mitigation: paper bankroll is per-environment and tracked separately from any live one. Reset via `--starting-bankroll-usd` on the next run; the settlement pass will continue resolving older trades regardless.
- **Stale forecast data.** Symptom: paper.submit `forecast.skipped_stale_horizon` warnings (forecast as_of older than the cutoff). Mitigation: this means the weather ingest cron above isn't running; verify Phase 1 ingest first.
