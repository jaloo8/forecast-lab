# Roadmap

Living status board. Updated per merge. For the *why* behind any phase, see [`CLAUDE.md §5`](CLAUDE.md) and [`docs/research/PASS-1-FEASIBILITY.md`](docs/research/PASS-1-FEASIBILITY.md).

---

## Status legend

- ✅ **shipped** — on `main`, verified end-to-end
- 🟡 **in flight** — branch open or actively next
- ⬜ **planned** — design exists, no code yet
- ⏸ **deferred** — explicitly post-v1
- ❌ **non-goal** — listed in [`CLAUDE.md §2`](CLAUDE.md), don't add

---

## Phase 0 — Setup ✅

| Item | Status | Notes |
|---|---|---|
| Repo + uv + ruff + mypy strict + pytest | ✅ | `pyproject.toml` |
| GitHub Actions CI | ✅ | `.github/workflows/ci.yml` |
| DuckDB schema + `bootstrap_db.py` | ✅ | 7 tables (forecasts, observed, METAR, kalshi_*, signal, paper_trade, settlement) |
| Mac (M1 Pro) verified | ✅ | 154 tests pass |
| Windows / WSL2 verified | ⬜ | `docs/SETUP.md` walks through it; user-side action |

## Phase 1 — Data ingest ✅ (modulo Kalshi-prod-weather)

| Item | Status | PR / commit |
|---|---|---|
| Open-Meteo ensemble client (GEFS + ECMWF) | ✅ | `6f0b36b` |
| Open-Meteo historical backfill | ✅ | (later squash) |
| METAR client (aviationweather.gov) | ✅ | `827f0f0` |
| NWS ACIS observed-truth backfill | ✅ | (later squash) |
| Kalshi v2 read-only client + RSA-PSS auth | ✅ | `3b35d72` |
| `kq ingest` aggregate + cron docs | ✅ | `0b8a61f` |
| `--event-ticker` override (verified on demo NBA) | ✅ | `f10af61` |
| Reorg into packages + edge-case tests | ✅ | (squash in earlier session) |
| Kalshi LST settlement-day utility (DST-correct) | ✅ | `210363f` |
| **Production Kalshi weather verification** | ⏸ | Demo doesn't seed weather markets — waits on prod or Kalshi seeding |
| 7-day continuous cron run on Windows | ⬜ | User-side after Windows setup |

## Phase 2 — Weather model + paper trading 🟡

| Item | Status | Notes |
|---|---|---|
| Feature engineering + training-set join | ✅ | `78ba892` (PR C) |
| NGR weather model + per-station fits + manifest | ✅ | `72da247` (PR F) — only KJFK clears 5% Brier-improvement bar so far |
| **Backtest engine** (no Kalshi needed) | 🟡 | Next planned PR |
| Bracket-probability → Kalshi ticker mapping | ⬜ | Required for paper trading proper |
| Paper executor (signals → simulated trades) | ⬜ | After bracket mapping |
| Intraday METAR Bayesian nowcast update | ⬜ | Pass 1 §1b — biggest realistic edge source |
| Full GEFS reforecast (ensemble historical) | ⏸ | Replaces deterministic-only training; bigger project |

## Phase 3 — NBA ⬜ (deferred until Phase 2 ships)

| Item | Status |
|---|---|
| `nba_api` client | ⬜ |
| `nbainjuries` polling | ⬜ |
| Pinnacle odds (paid Odds API) | ⬜ — needs $30/mo budget |
| Vig-free fair model + 538-style Elo fallback | ⬜ |
| Extend paper trader + backtest to NBA | ⬜ |

## Phase 4 — Dashboard + monitoring ⬜

| Item | Status |
|---|---|
| Streamlit dashboard (open markets / signals / P&L / freshness) | ⬜ stub |
| Alerting (ntfy / Pushover) | ⬜ |
| `kq health` command | ⬜ candidate quality-of-life PR |

## Phase 5 — Real-money decision gate ⬜

10 hard criteria in [`CLAUDE.md §5`](CLAUDE.md). Snapshot of current readiness:

| Criterion | Status |
|---|---|
| ≥ 500 settled paper trades | 0 — no paper trader yet |
| Brier ≥ 5% better than raw on backtest | 1/6 stations cleared so far (KJFK +16.6%) |
| Reliability calibrated (10pp tolerance) | unknown — backtest engine will produce diagrams |
| Positive paper P&L over 3 weeks | 0 weeks |
| CLV vs. Pinnacle ≥ +1% on NBA | NBA not built |
| Flows ≥ 30 days without unrecoverable failure | 0 days continuous |
| Bankroll plan written | not yet |
| State availability for sports confirmed | not yet |
| CPA engaged for §1256 | not yet |
| NVIDIA HR/Legal disclosure | not yet |

**You are nowhere near Phase 5 and that's correct for where we are.**

## v2 (post-Phase-5) — explicitly deferred ⏸

- Equities research agent (Pass 2 architecture)
- Always-on autonomous research agent (LangGraph + MCP + Langfuse)
- Polymarket cross-venue read-only ingest
- Subscription product (huge legal layer; see `docs/COMPLIANCE-ADDENDUM.md`)

## Hard non-goals ❌

Per [`CLAUDE.md §2`](CLAUDE.md):

- Twitter / Reddit ingestion
- Sentiment / LLM-as-probability
- ML beyond NGR + LightGBM until baselines ship
- Live trading without Phase 5 gate
- NVDA-adjacent MNPI-tainted research

---

## What "next PR" means right now

**PR H — backtest engine.** Replays historical forecasts against historical observed truth, simulates trades using existing fee + Kelly modules, produces P&L curves + reliability diagrams. Doesn't need Kalshi. Tests the model end-to-end before any live trading.
