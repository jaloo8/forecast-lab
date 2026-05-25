# Session audit — 2026-05-24 (Windows/WSL2 bring-up + multi-sport foundation)

Autonomous IC7 session on the always-on **Windows PC (WSL2 Ubuntu)**. Picks up
from [`docs/SESSION-2026-05-13-AUDIT.md`](SESSION-2026-05-13-AUDIT.md), whose
headline was "the bottleneck has fully shifted from code to operations — the
Windows box + cron is the single highest-leverage move." This session did that
move, then used the remaining window for an owner-requested NFL + PGA expansion.

## Headline

- **Windows/WSL2 Phase 0 is DONE.** Repo cloned to `~/forecast-lab` (ext4, not
  `/mnt/c`), `uv` + deps installed, **994 tests green**, ruff/mypy/bandit clean,
  DuckDB bootstrapped, `sops`/`age` installed, age key verified, secrets loaded,
  **Kalshi `.pem` installed and auth confirmed live** against the demo endpoint.
- **Every `kq` flow smoke-tested end-to-end on this box** — all run correctly
  with real data (3,444 weather rows, 36 NDFD, 6 METAR, 2 Pinnacle NBA odds).
- **A demo cron soak is installed + verified firing** (16 jobs incl. ntfy
  alerting on CRIT + nightly DuckDB backup + weekly backtest refresh). **Caught
  during verification:** WSL2 idles its VM down between activity, so cron only
  runs while something holds the VM open. A detached `wsl … sleep infinity`
  keep-alive was started (proven via a 1-min canary that fired); for
  durability across reboots run `Desktop\forecast-lab-ENABLE-KEEPALIVE.ps1`
  **elevated** (registers a logon scheduled task). Without a keep-alive the
  crontab is installed but inert. ~1yr of weather/observed/NDFD was also
  backfilled so the weekly backtest is meaningful (train-weather verified: 6
  stations, n=388).
- **NFL + PGA foundation library shipped** on `feat/multi-sport-nfl-pga`
  (pushed; PR pending one click) — N-way golf devig, generic + outright Odds API
  fetches, NFL/PGA Kalshi ticker parsers, **42 new tests** (1036 total), no new
  deps. Design doc records the live-verified facts.
- **The remaining blocker is external, not code:** Kalshi **prod** read access
  (demo seeds 0 markets, so paper trades can't accumulate). One-step runbook:
  [`docs/research/KALSHI-PROD-SWITCH.md`](research/KALSHI-PROD-SWITCH.md).

## What needs the operator (you)

| Action | Why | Where |
|---|---|---|
| **Create a Kalshi prod API key + switch `KALSHI_ENV=prod`** | Demo seeds 0 markets — the single thing blocking Phase 5 #1/#4/#5 settled-trade accumulation | [`KALSHI-PROD-SWITCH.md`](research/KALSHI-PROD-SWITCH.md) |
| **Open the multi-sport PR** (one click) | Branch is pushed; `gh` not installed so I didn't auto-create it | `https://github.com/jaloo8/forecast-lab/pull/new/feat/multi-sport-nfl-pga` |
| **Run `Desktop\forecast-lab-ENABLE-KEEPALIVE.ps1` (elevated)** | Makes the WSL keep-alive survive reboots so cron keeps firing. A detached keep-alive is running now but dies on reboot/`wsl --shutdown`. | Desktop script |
| **Keep the Windows PC on** (+ logged in, or enable auto-login) | Cron only fires while WSL2 is alive; the logon task needs a logon | n/a |
| **Subscribe to ntfy topic `flab-a7k2p9wq4m3x`** | Get phone alerts on CRIT health-check (stale data / failures). Install the ntfy app, add that topic. | https://ntfy.sh |
| Back up the age key to 1Password (if not already) | Only catastrophic-loss point in the secrets pipeline | `docs/SECRETS.md` |

## Phase 0 (Windows) — verification record

All inside WSL2 Ubuntu, repo `~/forecast-lab`:

| Check | Result |
|---|---|
| Clone (ext4, via Windows GCM credential helper) | ✅ `438b81c` main |
| `uv` 0.11.16 + `uv sync` | ✅ no build tools needed |
| `uv run pytest` | ✅ 994 passed (baseline) |
| `ruff check` / `ruff format --check` / `mypy src/kq` | ✅ clean |
| `make bootstrap` (DuckDB) | ✅ `data/forecast_lab.duckdb` |
| `sops` 3.12.2 + `age` v1.3.1 (`~/.local/bin`, no sudo) | ✅ |
| Age key (`~/.config/sops/age/keys.txt`, mode 600) | ✅ public key matches `.sops.yaml` recipient |
| `make bootstrap-secrets` | ✅ ODDS_API_KEY + KALSHI_API_KEY_ID loaded |
| Kalshi `.pem` (mode 600, 2048-bit RSA) | ✅ live auth OK on demo |

Deviations from `docs/SETUP.md` (all benign, documented): cloned via the Windows
Git Credential Manager instead of `gh auth login` (repo is private; avoids
needing `gh`); `sops`/`age` to `~/.local/bin` instead of `/usr/local/bin`
(avoids needing the WSL `sudo` password — they're only used by the manual
`bootstrap-secrets`, never by cron).

## Smoke-test matrix (this box, real endpoints)

| Flow | Result |
|---|---|
| `health-check` | OK after ingest (0 CRIT; WARNs = demo Kalshi empty + known calibration state) |
| `state-check --state CA` | ✅ green (Phase 5 #8) |
| `ingest-weather` | ✅ 3,444 rows (GFS+ECMWF, 6 stations) |
| `ingest-metar` | ✅ 6 rows |
| `ingest-ndfd` | ✅ 36 rows |
| `ingest-nba-schedule` | ✅ 0 games (season tail; flow OK) |
| `ingest-nba-odds` | ✅ 2 games from Pinnacle; **498/500 credits left** |
| `build-nba-crosswalk` / `ingest-kalshi` / `backtest-nba-clv` / `paper-nba --settle-only` / `router-summary` | ✅ all run; empty results are environmental (demo + fresh DB) |

`train-weather` / full `backtest` not re-run on this box (fresh DB has no
history; manifests are committed from the Mac and the weekly backtest cron will
regenerate them as data accumulates). Not a gap — flagged for transparency.

## Multi-sport (NFL + PGA) — what shipped

Branch `feat/multi-sport-nfl-pga` (commits `979d2aa`, `d56f421`):

- **`vig_strip.devig_outright`** — N-way power/multiplicative devig for golf;
  `OutrightMarket` / `OutrightFairProbabilities`. Power default (corrects
  favorite-longshot bias on big fields). 2-way path untouched.
- **`the_odds_api`** — generic `fetch_h2h(sport_key)` (NBA + NFL),
  `fetch_outrights(sport_key)` + `parse_outrights_response` (filters
  `outrights_lay`, tolerates null home/away); `SPORT_NFL` + 4 `GOLF_MAJOR_KEYS`.
- **`_ticker_parser_nfl` / `_ticker_parser_pga`** — Kalshi parsers, both flagged
  UNVERIFIED vs prod, round-trip tested.
- **42 new tests** (fixture + hypothesis property + round-trip). Full suite
  1036 passed; ruff/mypy/bandit/pip-audit all clean. **No new dependencies.**

Live-verified facts (recorded in
[`docs/research/MULTI-SPORT-NFL-PGA-DESIGN.md`](research/MULTI-SPORT-NFL-PGA-DESIGN.md)):
NFL `h2h` carries Pinnacle (75 games even off-season); **golf has NO Pinnacle**
on the Odds API (anchor to the lowest-vig book; booksums 1.375–2.48).

**Deferred (need prod markets + more code):** `nfl_odds`/`pga_outright_odds`
schema + repos, `ingest-nfl-odds`/`ingest-pga-odds` flows, NFL team + **golf
player-name** crosswalks, Odds API `/scores`→settlement, `paper-nfl`/`paper-pga`.
NFL/PGA stay outside the v1 weather+NBA scope (`CLAUDE.md §2`); same Phase 5 gate.

## Cron soak (demo) — installed

`crontab -l` on this box: **16 jobs** — weather 6h, METAR 15min, NDFD 6h, Kalshi
hourly, NBA schedule/odds/crosswalk/settle daily-ish, weather paper submit/settle
daily, **weekly backtest (weather_v1 / router / all_raw) + decide-router Sun**,
**nightly DuckDB backup 09:50 UTC** (`scripts/backup-duckdb.sh`), and a
**health-check heartbeat every 30min that pushes an ntfy alert on CRIT**
(`scripts/cron-health.sh` → topic `flab-a7k2p9wq4m3x`). Logs:
`~/forecast-lab/logs/cron.log` + `logs/health.log`; backups in
`~/forecast-lab-backups` (keep 14). NBA-odds cadence is deliberately
conservative (6h = 4 credits/day) to protect the 500/mo free quota. Inspect
with `crontab -l`; remove with `crontab -r`.

**Required for any of this to run: a WSL keep-alive** (WSL2 idles its VM down
otherwise). A detached one is running now; run the elevated Desktop script for
reboot durability (see Headline + operator table).

**On demo this proves reliability + accumulates free data; it will NOT book
Kalshi paper trades until the prod switch.** The alerting + backup + keep-alive
scripts live on branch `feat/ops-hardening` (pushed).

## Verification commands for when you're back

```bash
wsl -d Ubuntu                          # enter the box
cd ~/forecast-lab
crontab -l                             # confirm soak still installed
tail -50 logs/cron.log                 # see what's fired
tail -20 logs/health.log               # heartbeat (0=OK 1=WARN 2=CRIT)
uv run python -m kq health-check       # live snapshot
git -C ~/forecast-lab log --oneline -5 # see this session's commits
```

## Phase 5 readiness delta this session

No gate flipped (those need settled trades, which need prod). But the
**operational substrate** every gate depends on is now in place: the box runs,
flows work, cron fires. The clock that was "0 days of cron uptime" is now
ticking. The one remaining unlock is the prod key.
