# forecast-lab

Personal research lab for probabilistic forecasting and prediction-market analysis.

> **Status:** Private. Personal use. Paper trading only. Real-money trading is gated behind explicit criteria documented in [CLAUDE.md §5](CLAUDE.md).

> **➡ Current status & next steps live in [ROADMAP.md](ROADMAP.md).** That doc is updated on every merge — it's always more current than this README.

## What this is

A system that uses **public data only** — weather ensemble forecasts, NBA stats, news, SEC filings, earnings transcripts — and LLMs to find pricing mistakes in prediction markets and, eventually, equities. Starts narrow with Kalshi weather (daily high brackets at LAX, JFK, MDW, MIA, DEN, AUS) and NBA moneylines, expands later.

Three distinct phases (high-level — see [`ROADMAP.md`](ROADMAP.md) for live phase-by-phase status):

| Phase | Scope | Status |
|---|---|---|
| **v1** | Kalshi weather + NBA paper trading | Phase 0 ✅, Phase 1 ✅ (modulo prod-Kalshi-weather), Phase 2 🟡 (NGR + backtest shipped) |
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
cp .env.example .env
uv sync
uv run pytest
uv run python scripts/bootstrap_db.py
```

Then read [CLAUDE.md](CLAUDE.md) end to end before starting Phase 1 tasks.

## Documents index

Single place to find everything. Skim in this order if you're new (or future-you returning).

### Operational

- [`README.md`](README.md) — you are here
- [`CLAUDE.md`](CLAUDE.md) — operating playbook + phased plan + guardrails
- [`ROADMAP.md`](ROADMAP.md) — current status board, what's done / in-flight / next / deferred
- [`docs/SETUP.md`](docs/SETUP.md) — Mac + Windows-via-WSL2 setup walkthrough
- [`docs/SCHEDULED-RUNS.md`](docs/SCHEDULED-RUNS.md) — cron recipes for the always-on box
- [`docs/BANKROLL-PLAN.md`](docs/BANKROLL-PLAN.md) — Phase 5 #7 sizing + circuit-breaker discipline
- [`docs/SESSION-2026-05-04-AUDIT.md`](docs/SESSION-2026-05-04-AUDIT.md) — distinguished-dev-team audit of the open PR queue

### Quality + safety

- [`docs/CODE_QUALITY.md`](docs/CODE_QUALITY.md) — honest audit (coverage, bandit, pip-audit, weak spots, why-not-100%)
- [`docs/TESTING.md`](docs/TESTING.md) — testing matrix per module
- [`docs/BRANCH-PROTECTION.md`](docs/BRANCH-PROTECTION.md) — recommended GitHub branch protection settings
- [`docs/EXTERNAL_RESOURCES.md`](docs/EXTERNAL_RESOURCES.md) — curated list of third-party libs / datasets / repos with priority labels
- [`SECURITY.md`](SECURITY.md) — secret handling + rotation policy
- [`docs/COMPLIANCE-ADDENDUM.md`](docs/COMPLIANCE-ADDENDUM.md) — supersedes Pass 2 §A; the corrected compliance frame

### Research (long-form, source of truth for design decisions)

- [`docs/research/PASS-1-FEASIBILITY.md`](docs/research/PASS-1-FEASIBILITY.md) — Kalshi feasibility + build plan
- [`docs/research/PASS-2-EQUITIES-AGENT.md`](docs/research/PASS-2-EQUITIES-AGENT.md) — equities data stack + always-on agent architecture

## Compliance (short version)

Kalshi weather and NBA event contracts are **not securities** — 10b-5 doesn't apply. Public-data equity research is lawful. The real rules are narrow and documented in [docs/COMPLIANCE-ADDENDUM.md](docs/COMPLIANCE-ADDENDUM.md). This is not legal advice.

## Not legal / financial / tax advice

Nothing in this repository is legal, financial, tax, or investment advice. Anything commercial requires counsel. Verify state availability for sports markets before trading. Engage a CPA for §1256 treatment of Kalshi contracts.

## License

All rights reserved. Source-available for personal reference only; no license to use, copy, modify, or redistribute.
