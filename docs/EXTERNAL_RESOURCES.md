# External Resources

Curated list of third-party libraries, datasets, and research that's actually relevant to this project. **Most "AI quant trading" GitHubs are noise.** Everything below was either evaluated by reading the docs/code or referenced in the research passes (`docs/research/PASS-1-FEASIBILITY.md`, `docs/research/PASS-2-EQUITIES-AGENT.md`).

Priority labels:

- **🟢 use-now** — drop-in valuable; consider adding to deps after current ROADMAP item
- **🟡 evaluate** — promising; needs a real eval before committing
- **🔵 read-for-pattern** — read their code/docs, don't necessarily import
- **⚪ aware-of** — exists, mostly useful as a reference
- **🔴 avoid** — TOS / quality / fit issues

---

## Solves a real gap we currently have

### 🟢 [pmxt — unified prediction-market SDK](https://agentbets.ai/guides/pmxt-python-library-tutorial/) + [`archive.pmxt.dev`](https://archive.pmxt.dev)

**Why it matters:** the [PR H backtest](../models/backtest_manifest.json) used a *synthetic* naive market because we don't have a historical Kalshi orderbook archive. **pmxt's free archive provides hourly snapshots** of Kalshi + Polymarket order book and trade data in Parquet format. Pointing our backtest at real Kalshi history would shrink the inflated P&L numbers and give a realistic edge estimate.

**Action item:** evaluate Parquet schema + retention; if usable, replace `naive_market_quote` with a real-prices loader. Targets ROADMAP Phase 2.

### 🟢 [scoringrules (frazane/scoringrules)](https://github.com/frazane/scoringrules)

**Why it matters:** comprehensive Python port of the academic R package `scoringRules` (Jordan et al.). Has CRPS for continuous variables, Energy Score, Variogram Score — all properly tested against the academic reference. Better than `properscoring` (which we currently use, more limited).

**Action item:** swap `properscoring` → `scoringrules` when we add CRPS for the continuous-variable forecasts. No hurry; current Brier-only path works.

### 🟡 [NOAA GEFSv12 reforecast on AWS](https://registry.opendata.aws/noaa-gefs/)

**Why it matters:** the *real* 31-member historical ensembles. Our NGR model has a `d` parameter (variance scaling) that's currently dormant because we use Open-Meteo's deterministic single-series API. Switching to the full reforecast would activate it. Already in ROADMAP Phase 2 v2 as deferred.

**Cost of adoption:** non-trivial. GRIB2 parsing, AWS S3 transfer, multi-TB historical archive. Worth doing once basic Phase 2 ships.

---

## Existing prediction-market frameworks (read-for-pattern, don't copy)

### 🔵 [evan-kolberg/prediction-market-backtesting](https://github.com/evan-kolberg/prediction-market-backtesting)

NautilusTrader-based, Kalshi + Polymarket adapters. Production-grade event-driven architecture. **Read for adapter patterns** if we want our Kalshi client to grow into a full execution engine. Reimplementing into our codebase would be a months-long project.

### 🔵 [braedonsaunders/homerun](https://github.com/braedonsaunders/homerun)

Open-source Polymarket + Kalshi paper-trading platform. 25+ built-in strategies. **Read for strategy taxonomy** — useful if we want to enumerate what other people consider tradable patterns. Their codebase is broader than ours; ours can stay narrower.

### ⚪ [arshka/pykalshi](https://github.com/arshka/pykalshi)

Unofficial Kalshi client with WebSocket streaming + pandas integration. Our `kq.clients.kalshi` covers the same surface. **Awareness only** — useful to compare API design choices.

### 🔴 [ryanfrigo/kalshi-ai-trading-bot](https://github.com/ryanfrigo/kalshi-ai-trading-bot) (and similar "AI-powered Kalshi bot" repos)

Most are LLM-as-probability-estimator. Pass 1 §1d documents that LLMs are systematically miscalibrated probability sources. Marketing > substance.

---

## Production-grade tooling (consider for v2)

### 🟡 [NautilusTrader](https://nautilustrader.io/)

Production-grade event-driven backtester (Rust core, Python API). Used by serious algorithmic trading shops. **Massive scope.** Probably overkill for v1; serious option for v2 when our backtest grows beyond what `kq.backtest.engine` cleanly handles.

### 🟡 [LangGraph](https://langchain-ai.github.io/langgraph/) + [Pydantic AI](https://ai.pydantic.dev/) + MCP

Already documented in [`docs/research/PASS-2-EQUITIES-AGENT.md`](research/PASS-2-EQUITIES-AGENT.md) as the v2 reference architecture for the always-on autonomous research agent. Defer until v1 ships.

### ⚪ [smolagents (HuggingFace)](https://github.com/huggingface/smolagents)

Lightweight agent framework. Worth tracking as an alternative to LangGraph if Pass 2's stack proves too heavy for what we actually need.

---

## Statistical references (academic; read-not-import)

### 🔵 [Combinatorial Purged Cross-Validation (CPCV)](https://www.insightbig.com/post/traditional-backtesting-is-outdated-use-cpcv-instead) — López de Prado

More rigorous than rolling-origin; reduces overlap leakage. Standard in quant lit. Worth reading to understand whether our current rolling-origin has overlap-leakage issues. If our naive market backtest stays clean, CPCV is over-engineering.

### 🔵 EMOS / NGR foundational papers

- [Calibrated Probabilistic Forecasting Using EMOS — UW Statistics overview](https://stat.uw.edu/seminars/calibrated-probabilistic-weather-forecasting-using-ensemble-model-output-statistics-emos-and)
- [Statistical Postprocessing of Ensemble Forecasts — Wessel et al. 2024](https://rmets.onlinelibrary.wiley.com/doi/10.1002/qj.4701)

These are the why-this-form-of-NGR papers. Our `kq.models.weather_ngr` is a simplified version of the methods these describe. Worth re-reading before adding LightGBM residuals or moving to neural-network post-processing.

### ⚪ DeepMind GraphCast / Microsoft Aurora

Flagship neural weather models. **Beautiful research, fundamentally outside what a solo retail builder can use.** Require GPUs + TBs of training data. Don't even try.

---

## Generic tools (not project-specific but worth knowing)

| Tool | Use case | Status |
|---|---|---|
| [`mutmut`](https://github.com/boxed/mutmut) | Mutation testing — kills weak tests | 🟡 candidate; in `docs/CODE_QUALITY.md` backlog |
| [`hypothesis`](https://hypothesis.readthedocs.io/) | Property-based testing | ✅ already in dev deps; need to extend to parsers |
| [`gitleaks`](https://github.com/gitleaks/gitleaks) | Pre-commit secret scanner | ✅ already in `.pre-commit-config.yaml` |
| [`Polars`](https://pola.rs/) | Faster pandas alternative | ✅ already in deps; used in features/backtest |

---

## Explicitly evaluated and rejected

### 🔴 [d60/twikit](https://github.com/d60/twikit) — Twitter/X scraper without API keys

- Logs in with **your** username + password and scrapes via internal endpoints
- TOS violation; account-ban risk is real (their own `ToProtectYourAccount.md` is a tell)
- Last release Feb 2025 — likely to break as Twitter changes auth flow
- Even if it worked: weather sentiment doesn't predict temperature (Pass 1 §1d); NBA injury sentiment is dwarfed by official `nbainjuries`

**Defense:** [`tests/test_no_twikit_dep.py`](../tests/test_no_twikit_dep.py) asserts `twikit` is not in installed deps so a future "let's just try it" gets caught at CI.

### 🔴 Twitter/X API Basic ($100/mo, 10k tweets/mo)

10k/mo is worthless for analytics — exhausted in a day at 1 query/min. Pro tier ($5k/mo) is not retail.

### 🟡 [Reddit PRAW](https://praw.readthedocs.io/) — read-only Reddit API

Free for personal use, 100 QPM, fully TOS-compliant. **Not for v1** but acceptable as a v2 *collection-only* item if we ever want to A/B test Reddit signal in NBA markets. Documented in `ROADMAP.md` v2 deferred section.

### 🔴 [Panniantong/Agent-Reach](https://github.com/Panniantong/Agent-Reach)

Cool tool (CLI giving AI agents internet access via wrapped scrapers), but **not relevant to weather/NBA forecasting models.** Where it could fit: Pass 2's deferred always-on research agent — slot it in as a "tool layer" for the LangGraph/MCP architecture, not for v1 data ingestion.

### 🔴 yfinance for any commercial use

No license to redistribute. Increasingly flaky. Listed for awareness only — never build production on it.

---

## How to maintain this list

When you encounter a new GitHub repo / library / paper that someone claims will help:

1. **Read the docs, not the README** — README is marketing; docs are reality.
2. **Check the last release date** — anything > 12 months stale on a fast-moving stack (LLM, scraping) is a yellow flag.
3. **Map it to a real ROADMAP gap.** If it doesn't fit a labeled gap, it's likely scope creep.
4. **Add a row here with one of the priority labels above.** Future-you will thank present-you.

When in doubt: prefer doing less with quality, over more with hype.
