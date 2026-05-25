# forecast-lab

Personal research lab for probabilistic forecasting and prediction-market analysis.

> **Status:** Private. Personal use. Paper trading only. Real-money trading is gated behind explicit criteria documented in [CLAUDE.md §5](CLAUDE.md).

> **➡ Current status & next steps live in [ROADMAP.md](ROADMAP.md).** That doc is updated on every merge — it's always more current than this README.

## What this is

A system that uses **public data only** — weather ensemble forecasts, NBA stats, news, SEC filings, earnings transcripts — and LLMs to find pricing mistakes in prediction markets and, eventually, equities. Starts narrow with Kalshi weather (daily high brackets at LAX, JFK, MDW, MIA, DEN, AUS) and NBA moneylines, expands later.

Three distinct phases (high-level — see [`ROADMAP.md`](ROADMAP.md) for live phase-by-phase status):

| Phase | Scope | Status (as of 2026-05-13) |
|---|---|---|
| **v1** | Kalshi weather + NBA paper trading | Phase 0 ✅ Mac (⬜ Windows/WSL2), Phase 1 ✅ (modulo prod-Kalshi-weather), Phase 2 ✅ code-complete (🟡 verdict pending NBM qmd Phase 2), Phase 3 ✅ code-complete end-to-end, Phase 4 🟡 dashboard panels shipped, Phase 5 🟡 5 of 8 code-side gates done; remaining is operational/external |
| **v2** | Equities research agent, tech-sector signals, always-on autonomous briefing | Deferred |
| **v3** | Subscription product (if ever) | Deferred past NVIDIA employment or requires restricted product universe + counsel |

## What edge actually exists

- **Weather:** realistic 2–10% ROI on turnover via bias-corrected GEFS/ECMWF ensembles + METAR nowcasting on tail brackets. Capacity-limited. Real.
- **NBA:** 1–5% if you execute well against cross-book pricing gaps with Pinnacle as vig-free anchor; zero or negative if you don't.
- **LLMs:** useful as extractors and synthesizers, bad as probability estimators. Never wire an LLM's numeric output directly into a bet-size function.

You need roughly **500 settled trades** before any paper-trading result is trustworthy, and **~4,300** before a 3% edge is statistically proven. This means months of paper trading, not weeks. The project is about *calibration discipline*, not finding a shortcut.

## Realistic expectations

On a $3–5k bankroll, year one probably lands somewhere between **–5% and +15%**. The asymmetry here isn't in P&L — it's in the skills: production-grade quant infrastructure, calibrated forecasting, a real portfolio piece, and the judgment to tell real edge from noise.

## Stack (v1)

- **Language:** Python 3.12
- **Package manager:** `uv`
- **Storage:** DuckDB (analytics) + SQLite (ops state) + Parquet (archival); Postgres + pgvector deferred to v2
- **Dashboard:** Streamlit
- **Scheduling:** WSL2 cron on the always-on Windows PC; Prefect 3 if/when cron becomes unmanageable
- **Lint/format:** `ruff`
- **Types:** `mypy --strict`
- **Tests:** `pytest` + `hypothesis`
- **Dev environment:** M1 Pro MacBook (dev) + always-on Windows PC via WSL2 (ingest + paper trading)

Full stack decisions, v2 stack, and agent architecture live in [docs/research/PASS-2-EQUITIES-AGENT.md](docs/research/PASS-2-EQUITIES-AGENT.md).

## Repo map

```
forecast-lab/
├── README.md                              # this file
├── CLAUDE.md                              # operating playbook (loaded by Claude Code)
├── SECURITY.md                            # secret-handling + rotation policy
├── pyproject.toml                         # uv workspace + tooling
├── Makefile                               # make ingest | backtest | paper | dashboard | test
├── .env.example                           # all env vars (never commit real .env)
├── .github/workflows/ci.yml               # ruff + mypy + pytest on PR
├── docs/
│   ├── COMPLIANCE-ADDENDUM.md             # supersedes Pass 2 compliance section
│   └── research/
│       ├── PASS-1-FEASIBILITY.md          # Kalshi feasibility + build plan
│       └── PASS-2-EQUITIES-AGENT.md       # equities data + agent architecture
├── src/kq/                                # main package
│   ├── config.py                          # pydantic-settings
│   ├── clients/                           # kalshi, openmeteo, metar, nba (stubs)
│   ├── storage/                           # duckdb wrapper + schemas.sql
│   ├── features/                          # weather, nba (stubs)
│   ├── models/                            # weather ensemble, nba elo, calibration (stubs)
│   ├── execution/                         # paper executor (live gated)
│   ├── backtest/                          # engine + metrics
│   └── dashboard/                         # streamlit app
├── tests/                                 # pytest
├── scripts/                               # bootstrap_db.py, one-shots
└── notebooks/                             # exploratory; NOT imported by prod code
```

## Getting started

See [docs/SETUP.md](docs/SETUP.md) for the full step-by-step — Mac is already verified; the Windows/WSL2 side is walked through end to end with a verification checklist. Quick version:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
uv sync
uv run pytest
uv run python scripts/bootstrap_db.py

# API keys: either copy .env.example -> .env and paste manually,
# or (preferred for multi-machine) install sops + age and run:
brew install sops age              # one-time per machine
make bootstrap-secrets             # decrypts secrets.enc.yaml -> .env
# Full first-time + recovery walkthrough: docs/SECRETS.md
```

Then read [CLAUDE.md](CLAUDE.md) end to end before starting Phase 1 tasks.

## Running things — opt-in catalog

Every command below is **opt-in**: nothing runs automatically until you wire it into a cron / scheduled task. The recommended cron schedule lives in [`docs/SCHEDULED-RUNS.md`](docs/SCHEDULED-RUNS.md). On the Mac you'd typically run these on demand; on the always-on Windows PC (via WSL2) they're cron'd.

### Ingest commands (live data → DuckDB)

| Command | What it does | Cadence | Logs |
|---|---|---|---|
| `uv run python -m kq ingest-weather` | GEFS + ECMWF ensembles for 6 stations | every 6h | `logs/cron.log` |
| `uv run python -m kq ingest-metar` | METAR observations for 6 stations | every 10 min | `logs/cron.log` |
| `uv run python -m kq ingest-ndfd` | NWS NBM-deterministic Tmax benchmark | every 6h | `logs/cron.log` |
| `uv run python -m kq ingest-kalshi` | Kalshi orderbook snapshots | every 1 min during trading hours | `logs/cron.log` |
| `uv run python -m kq ingest-nba-schedule` | NBA games (yesterday + today) | hourly during season | `logs/cron.log` |
| `uv run python -m kq ingest-nba-odds` | The Odds API NBA moneylines (Pinnacle h2h) | hourly during season — **no-ops if `ODDS_API_KEY` empty** | `logs/cron.log` |
| `uv run python -m kq ingest-ecmwf-opendata` | ECMWF Open Data IFS HRES (mx2t24 at step=48h) | 4×/day after each cycle publish | `logs/cron.log` |
| `uv run python -m kq ingest` | All of the above in sequence | every 10 min (coarse) | `logs/cron.log` |

### Modeling + backtest commands (read-only, emit manifest JSONs)

| Command | What it does | When to run |
|---|---|---|
| `uv run python -m kq train-weather --lead-days 1` | Per-station NGR weather model fit; writes [models/manifest.json](models/manifest.json) | After a backfill or when changing the model |
| `uv run python -m kq backtest --strategy weather_v1` | Rolling-origin CV backtest; writes [models/backtest_manifest.json](models/backtest_manifest.json) | After a model retrain or when you want fresh Brier numbers |
| `uv run python -m kq backtest --strategy weather_router_v1` | Per-station NGR-vs-raw router backtest | Same |
| `uv run python -m kq backtest-nba-clv` | Replays finished NBA games through Elo + Pinnacle vig-strip; writes [models/backtest_nba_clv_manifest.json](models/backtest_nba_clv_manifest.json) | After NBA odds + games + crosswalk are populated |
| `uv run python -m kq decide-router` | Reads backtest manifests + writes per-station router config | After a fresh backtest |
| `uv run python -m kq build-nba-crosswalk` | Matches Odds API games to nba_api games via `(home, away, date)` | Daily after the NBA ingest flows |

### Operations + monitoring commands

| Command | What it does |
|---|---|
| `uv run python -m kq health-check` | Checks DuckDB freshness, manifest mtimes, and calibration-summary status. Exits 0/1/2 by severity for cron alerting. |
| `uv run python -m kq state-check` | Looks up Kalshi sports availability for the operator's state (Phase 5 #8). |
| `uv run python -m kq paper` | Weather paper-trade cycle (submit + settle). One pass per cron tick. |
| `uv run python -m kq paper-nba` | NBA paper-trade cycle (submit + settle). Pulls open Kalshi NBA markets, joins to Pinnacle + Elo, sizes via fractional Kelly, settles trades whose game resolved. Drives Phase 5 #5. |
| `uv run python -m kq paper-summary` | Per-station P&L + Brier + reliability summary from settled paper trades |
| `uv run python -m kq router-summary` | Compact per-station router-decision summary across backtest manifests |

### Mining the cron logs for model training

The cron logs themselves are operational telemetry, not training data. The actual training data lives in DuckDB:

- **Weather**: `weather_forecast` (ensemble + deterministic Tmax) ← used by NGR fit
- **Truth**: `weather_observed` (NWS ACIS daily climate) ← labels for NGR fit + Brier scoring
- **NDFD**: `ndfd_forecast` ← benchmark for Brier-vs-NDFD
- **NBA**: `nba_game` (settled scores), `nba_odds` (Pinnacle moneylines), `nba_game_crosswalk` (id bridge) ← used by Elo replay + CLV evaluator
- **METAR**: `metar_obs` (intraday temps) ← used by the Bayesian nowcast at signal time

If you want to inspect the data directly, `duckdb data/forecast_lab.duckdb` opens an interactive shell. The cron logs are useful for diagnosing ingest failures (rate limits, auth errors, network blips), not for training input. The `kq health-check` command is the structured-data version of "tail the log."

**The Windows/WSL2 box is online (2026-05-24) and a demo cron soak is running** — the free ingest commands (weather, METAR, NDFD, Pinnacle NBA odds) are producing data every tick. The Kalshi-dependent commands find 0 markets until the box is switched to Kalshi **prod** (demo is a sandbox; see [`docs/research/KALSHI-PROD-SWITCH.md`](docs/research/KALSHI-PROD-SWITCH.md)) — that switch is the one remaining unlock for paper-trade accumulation. Full status: [`docs/SESSION-2026-05-24-AUDIT.md`](docs/SESSION-2026-05-24-AUDIT.md).

## Documents index

Single place to find everything. Skim in this order if you're new (or future-you returning).

### Operational

- [`README.md`](README.md) — you are here
- [`CLAUDE.md`](CLAUDE.md) — operating playbook + phased plan + guardrails
- [`ROADMAP.md`](ROADMAP.md) — current status board, what's done / in-flight / next / deferred
- [`docs/SETUP.md`](docs/SETUP.md) — Mac + Windows-via-WSL2 setup walkthrough
- [`docs/SCHEDULED-RUNS.md`](docs/SCHEDULED-RUNS.md) — cron recipes for the always-on box
- [`docs/BANKROLL-PLAN.md`](docs/BANKROLL-PLAN.md) — Phase 5 #7 sizing + circuit-breaker discipline
- [`docs/SESSION-2026-05-04-AUDIT.md`](docs/SESSION-2026-05-04-AUDIT.md) — distinguished-dev-team audit of the (then-open) 25-PR queue
- [`docs/SESSION-2026-05-13-AUDIT.md`](docs/SESSION-2026-05-13-AUDIT.md) — **latest snapshot**: 0 open PRs, Phase 5 5-of-8 code-side gates done, operational checklist for the operator + a fresh-clone preamble for future Claude Code sessions

### Quality + safety

- [`docs/CODE_QUALITY.md`](docs/CODE_QUALITY.md) — honest audit (coverage, bandit, pip-audit, weak spots, why-not-100%)
- [`docs/TESTING.md`](docs/TESTING.md) — testing matrix per module
- [`docs/BRANCH-PROTECTION.md`](docs/BRANCH-PROTECTION.md) — recommended GitHub branch protection settings
- [`docs/EXTERNAL_RESOURCES.md`](docs/EXTERNAL_RESOURCES.md) — curated list of third-party libs / datasets / repos with priority labels
- [`SECURITY.md`](SECURITY.md) — secret handling + rotation policy
- [`docs/SECRETS.md`](docs/SECRETS.md) — multi-machine API-key sync via SOPS + age (`make bootstrap-secrets`)
- [`docs/COMPLIANCE-ADDENDUM.md`](docs/COMPLIANCE-ADDENDUM.md) — supersedes Pass 2 §A; the corrected compliance frame

### Research (long-form, source of truth for design decisions)

- [`docs/research/PASS-1-FEASIBILITY.md`](docs/research/PASS-1-FEASIBILITY.md) — Kalshi feasibility + build plan
- [`docs/research/PASS-2-EQUITIES-AGENT.md`](docs/research/PASS-2-EQUITIES-AGENT.md) — equities data stack + always-on agent architecture
- [`docs/research/RENAISSANCE-DEEP-DIVE-2026-05-08.md`](docs/research/RENAISSANCE-DEEP-DIVE-2026-05-08.md) — Renaissance Technologies lineage + math foundations (HMMs, Baum-Welch, EMOS, conformal, analog ensembles, proper scoring rules, microstructure) + honest assessment of what's replicable for a solo CPU-only operator. **Background/context** for the implementation specs below.
- [`docs/research/THREE-WORKSTREAMS-2026-05-13.md`](docs/research/THREE-WORKSTREAMS-2026-05-13.md) — **implementation-ready design spec** for three deferred follow-ups: P1 analog ensembles (per-station feature sets, CMA-ES weight learning), P2 NBA totals meta-labeling (Glicko-2 pace + Kelly-with-flip derivation), P3 NBM qmd S3 byte-range Phase 2. Includes 12-week integrated roadmap.

## Compliance (short version)

Kalshi weather and NBA event contracts are **not securities** — 10b-5 doesn't apply. Public-data equity research is lawful. The real rules are narrow and documented in [docs/COMPLIANCE-ADDENDUM.md](docs/COMPLIANCE-ADDENDUM.md). This is not legal advice.

## Not legal / financial / tax advice

Nothing in this repository is legal, financial, tax, or investment advice. Anything commercial requires counsel. Verify state availability for sports markets before trading. Engage a CPA for §1256 treatment of Kalshi contracts.

## License

All rights reserved. Source-available for personal reference only; no license to use, copy, modify, or redistribute.
