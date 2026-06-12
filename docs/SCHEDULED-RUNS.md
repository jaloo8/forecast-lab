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
| Paper-trade submit (weather) | daily, **before** Kalshi market settlement (15:00 UTC for weather contracts, choose 14:30 UTC) | One pass/day per CLAUDE.md, mirrors the live executor's intended cadence. |
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
0 13 * * 1 cd /home/jason/forecast-lab && NTFY_TOPIC=flab-a7k2p9wq4m3x ./scripts/reality-probe.sh >> /home/jason/forecast-lab/logs/cron.log 2>&1
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
30 3 * * 0 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq backtest --strategy weather_reforecast_v1  >> /home/jason/forecast-lab/logs/cron.log 2>&1

# Weekly: recompute router decisions after all 4 backtests have landed.
0  4 * * 0 cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq decide-router >> /home/jason/forecast-lab/logs/cron.log 2>&1

# Daily: paper-trading submit pass (one pass per day, mirroring the live cadence).
30 14 * * * cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq paper >> /home/jason/forecast-lab/logs/cron.log 2>&1

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

```cron
# Every 15 min: surface pipeline staleness or manifest gaps.
# Exits 0 (OK) / 1 (WARN) / 2 (CRIT). Pair with `||` to alert only on
# CRIT, or with `>=2` to alert on either WARN or CRIT.
*/15 * * * * cd /home/jason/forecast-lab && /home/jason/.local/bin/uv run python -m kq health-check --json >> /home/jason/forecast-lab/logs/health.log 2>&1 || /home/jason/forecast-lab/scripts/notify-failure.sh
```

The check covers:

- `weather_forecast` / `metar_obs` / `ndfd_forecast` table freshness vs the
  ingest cadence (defaults: 12h / 30min / 12h)
- `kalshi_book_snap` freshness — WARN-only because demo legitimately has 0
  markets in off-season; tighten to CRIT once prod read-only is wired
- `models/backtest_manifest.json` mtime (default ≤ 7 days; matches the
  weekly backtest cron above)
- `models/router_config.json` mtime (default ≤ 7 days)

Exit codes: 0 = all OK, 1 = at least one WARN (no CRIT), 2 = at least one
CRIT or DB unreachable. The cron `||` triggers an alert only on CRIT;
remove the `|| ...notify-failure.sh` part if you want to alert on WARN too.

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

- **Cron not firing (WSL2 sleeping).** Symptom: gaps in `cron.log`. Mitigation: `wsl.exe` keep-alive in Windows Task Scheduler (see "WSL2 caveat" above), or attach a `caffeinate`-equivalent to the wsl process.
- **Demo Kalshi API returns 0 markets in the off-season.** Symptom: `paper.submit.no_kalshi_weather_markets` warnings every day. Mitigation: see "Switching to Kalshi prod for market discovery" below.
- **Bankroll depletion.** Symptom: `kelly_stake_zero_bankroll` warnings; trades stop firing. Mitigation: paper bankroll is per-environment and tracked separately from any live one. Reset via `--starting-bankroll-usd` on the next run; the settlement pass will continue resolving older trades regardless.
- **Stale forecast data.** Symptom: paper.submit `forecast.skipped_stale_horizon` warnings (forecast as_of older than the cutoff). Mitigation: this means the weather ingest cron above isn't running; verify Phase 1 ingest first.

### Switching to Kalshi prod for market discovery (read-only)

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
