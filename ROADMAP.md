# Roadmap

Living status board. Updated **on every merge to `main`** — see [How this doc stays current](#how-this-doc-stays-current) at the bottom. For the *why* behind any phase, see [`CLAUDE.md §5`](CLAUDE.md), [`docs/research/PASS-1-FEASIBILITY.md`](docs/research/PASS-1-FEASIBILITY.md), and the [Pass 1 extension memo](docs/research/PASS-1-EXTENSION-EMOS-EXECUTION.md) (April 2026 — EMOS + execution upgrades that survive the deployment bar; concrete next-quarter ship list at the bottom of this doc).

---

## TL;DR — where we are right now

- **Phase 0 ✅** — tooling green on Mac (162→183 tests, mypy strict, ruff clean, coverage 87%)
- **Phase 1 ✅** — all four data ingest paths verified end-to-end (Open-Meteo / METAR / Kalshi-auth / NWS ACIS); only gap is production-Kalshi-weather (demo doesn't seed those markets)
- **Phase 2 🟡 mid-flight** — feature engineering, NGR model, PIT-correct backtest engine, per-station router, bracket→Kalshi mapping, paper executor + settlement loop, AND the intraday METAR Bayesian nowcast (Pass 1 §1b's biggest remaining edge source) now all on `main`. **Next**: the [Pass 1 extension package](#phase-2-extension--ship-list-from-pass-1-extension-research) (NDFD benchmark 🟡, maker/taker rule, isotonic recalibration, skew-normal NGR, climatology blend) + cron wire-up on Windows box.
- **Phase 3-5** — not started. Phase 5 (real-money gate) you are nowhere near, and that's correct.

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
| GitHub Actions CI (lint + format + types + tests + coverage gate + bandit) | ✅ | `.github/workflows/ci.yml` |
| Weekly security scan (pip-audit + full bandit) | ✅ | `.github/workflows/security-weekly.yml` |
| DuckDB schema + `bootstrap_db.py` | ✅ | 8 tables (forecasts, observed, METAR, kalshi_*, signal, paper_trade, settlement) |
| Mac (M1 Pro) verified | ✅ | 183 tests pass; coverage 87% |
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
| Reorg into packages + edge-case tests | ✅ | (squash) |
| Kalshi LST settlement-day utility (DST-correct) | ✅ | `210363f` |
| **Production Kalshi weather verification** | ⏸ | Demo doesn't seed weather markets — waits on prod or Kalshi seeding |
| 7-day continuous cron run on Windows | ⬜ | User-side after Windows setup |

## Phase 2 — Weather model + paper trading 🟡

| Item | Status | Notes |
|---|---|---|
| Feature engineering + training-set join | ✅ | `78ba892` (PR C) |
| NGR weather model + per-station fits + manifest | ✅ | `72da247` (PR F) — only KJFK clears 5% Brier-improvement bar in training |
| **Backtest engine (rolling-origin CV, PIT-correct)** | ✅ | `705be02` (PR H) — same finding holds OOS: KJFK +20.1% Brier, LAX/MIA NGR overfits |
| **Per-station strategy router** (NGR for KJFK/KAUS/KDEN; raw for LAX/MDW/MIA) | ✅ | (PR J — this commit) `kq decide-router` reads backtest_manifest.json and writes router_config.json with per-station NGR-vs-raw choice. `kq backtest --strategy weather_router_v1` runs through the router. Raw-strategy stations correctly take 0 trades when their model agrees with the naive market — sitting out is the right action when there's no edge. |
| **Bracket → Kalshi ticker mapping** | ✅ | (PR K) `clients/kalshi/_ticker_parser.py` parses `KXHIGHLAX-26APR30-T75`-style weather tickers; `backtest/bracket_match.py` matches generated brackets to live Kalshi markets. **Format unverified against prod weather markets** (demo doesn't seed weather) — best guess from Pass 1 §1a + observed NBA/MLB ticker conventions. 39 new tests covering all 6 stations + defensive parsing. |
| **Paper executor (signals → simulated trades + settlement)** | ✅ | (PR L) `execution/paper.py` (signal eval, fee + Kelly sizing, deterministic IDs), `storage/repositories/paper_trades.py` (idempotent `signal` + `paper_trade` upserts, settlement loop), `flows/paper_trade.py` (submit + settle in one call), wired to `kq paper [--settle-only] [--target-date YYYY-MM-DD] [--starting-bankroll-usd ...]`. Cannot reach live endpoint by construction. **49 new tests** covering pure logic, repository, and end-to-end flow. **Submit pass is dormant until prod weather markets are reachable**; settle pass is exercised every cron tick regardless. |
| **Intraday METAR Bayesian nowcast** | ✅ | (PR M) `models/nowcast.py` — given today's METAR `t_so_far` + LST-day `fraction_remaining`, shrink prior sigma (Brownian) and floor mu at the observed max. Wired into the paper flow's `run_once(use_nowcast=True)` (default on; degenerates to vanilla prior when no obs). Router gained `predict_distribution` so the (mu, sigma) prior can be re-used downstream. **24 new tests** covering pure math, leak-protection (future obs filtered), all 6 stations, and flow integration. Not active in backtest yet — that's a v2 follow-up. |
| Real Kalshi orderbook history (via [pmxt archive](https://archive.pmxt.dev)) | ⬜ | Would replace synthetic naive market in backtest with real data; see `docs/EXTERNAL_RESOURCES.md` |
| CPCV (Combinatorial Purged CV) instead of rolling-origin | ⏸ | More rigorous; only worth it if our rolling-origin shows obvious overlap leakage |

## Phase 2 extension — ship list from Pass 1 extension research

Research input: [`docs/research/PASS-1-EXTENSION-EMOS-EXECUTION.md`](docs/research/PASS-1-EXTENSION-EMOS-EXECUTION.md) (April 2026, deep-research session). The memo applies a strict deployability filter ("works in published literature AND has shipped at solo / small-shop scale, public data, CPU-only") and ranks techniques by Brier-improvement-per-engineering-time. The five items below are the priority ship list before Phase 5 — none requires new dependencies *except* `cvxpy` and `pythie` for two of the larger items. Realistic stacked Brier improvement: ~10-15% on top of current setup. See the memo for citations + per-station expectations + honest base-rate caveats.

| # | Item | Status | LoC | Notes |
|---|---|---|---|---|
| 1 | **NDFD benchmark + CLV tracking** | ✅ shipped | ~600 | Pull NWS NDFD probabilistic Tmax forecast at T-1h before market close; track our model's Brier vs NDFD per station. **Without this we cannot honestly tell if we have edge.** Bar: ≥ 2-3% Brier improvement vs NDFD across ≥ 4 of 6 stations consistently. **Source decision (2026-04-29):** v1 ships NBM-deterministic via Open-Meteo (no eccodes dep) wrapped in a per-fold fitted-sigma; the true `qmd` probabilistic upgrade via `s3://noaa-nbm-grib2-pds` is tracked as a follow-up — see [`docs/research/NDFD-BENCHMARK-SOURCE.md`](docs/research/NDFD-BENCHMARK-SOURCE.md). PR data layer = `c12b23d` (#10); PR backtest CLV = (this commit). **Verdict: 3 of 6 stations clear the ≥ 2-3% bar, 1 ties, 2 fail — see [Phase 2 NDFD verdict table](#phase-2-ndfd-benchmark-verdict-2026-04-29) below.** Bar of "≥ 4 of 6 stations" not yet cleared; Pass 1 ext items #2-#5 (maker rule, isotonic, skew-NGR, climatology blend) are now load-bearing for getting KAUS / KMDW / KDEN over the line. |
| 2 | **Maker-vs-taker decision rule** | ⬜ | ~150 | Kalshi's maker fee is 25-28× cheaper than taker. Post passively when fair value is ≥ 2 ticks better than the marginal taker price post-fee, withdraw maker on every NWS METAR push. ~25 bps savings per round-trip. |
| 3 | **Isotonic recalibration (CORP / PAV)** | ⬜ | ~50 | `sklearn.isotonic.IsotonicRegression` post-NGR layer with rolling 200-500-day window. Cheapest defensible Brier reduction (2-8% on top of NGR). Refit nightly. |
| 4 | **Skew-normal NGR predictive distribution** | ⬜ | ~50 | Replaces NGR's Gaussian assumption with `scipy.stats.skewnorm`. Addresses bounded-below + heavy-upper-tail shape of Tmax. Allen et al. 2023 reports 8-15% upper-tail Brier improvement at +2σ thresholds (where wing-bracket trades live). |
| 5 | **Climatology blending at long lead** | ⬜ | ~80 | At lead 5-7d our parametric tails are too thin; blend toward climatology with weight = exp(-lead/τ), τ ≈ 4 days. Defends Phase 5 reliability gate at the wings; see Wessel et al. 2024 *QJRMS*. |
| 6 | **GEFSv12 reforecast-trained NGR** | ⏸ deferred | ~300 | Train NGR on 30-year reforecasts from `s3://noaa-gefs-retrospective` (~25 GB). Hagedorn-Hamill-Whitaker 2008: roughly *doubles* CRPSS over short-window NGR — biggest single training-side lever, especially for KLAX/KMDW/KMIA overfit problem. Bigger project; do after items 1-5. |
| 7 | **Member-by-member (MBM) router leg** | ⏸ deferred | ~150 | Wraps Belgian RMI's `pythie` library. Drop-in alternative to NGR for the failing-NGR stations. CPRSS parity-or-slight-improvement vs NGR; main upside is dropping the Gaussian assumption. |
| 8 | **CVX-Kelly with bracket correlation matrix** | ⏸ deferred | ~150 | Replaces our 0.15× heuristic with explicit constrained optimization across same-day correlated brackets via `cvxpy`. New dep: `cvxpy`. Per-day refit. Probably bumps optimal fraction to 0.20-0.30×. |
| 9 | **Ornstein-Uhlenbeck nowcast** | ⏸ deferred | ~100 | Replaces Brownian-σ shrink in `kq.models.nowcast` with mean-reversion to a deterministic diurnal-climatology curve. PhD's #2 math complaint. Worth more than any training-side technique at the bad-NGR stations during 10-14 local. |
| 10 | **LightGBM quantile regression with extended MOS predictors** | ⏸ post-Phase-5 | ~250 | Sanctioned ML lane (CLAUDE.md §2 allows once 500 calibrated trades ship). Predictors: dewpoint, BL height, persistence, climatology. Realistic gain over NGR: 3-10% CRPSS at bad stations, 0-3% at KJFK. |

**Items explicitly NOT shipping** (research confirms negative-EV at our scale):
- Deep neural postprocessing (Höhlein/Mlakar/Rasp-Lerch DRN) — needs 100k+ pairs, we have 12k → guaranteed overfit
- LLM-derived features — Pass 1 §1d already disqualified
- Almgren-Chriss / equities-style execution — wrong asset class for binary contracts

**Realistic post-fee edge after items 1-5:** central case 80-120 bps at 50¢ centerline (~+81% annualized on $1k bankroll, ~2,500 trades/year, 0.20× Kelly). **Plan against the pessimistic 30-60 bps / +31%.** Kalshi's pre-fee average return is **−20%** per the Whelan/UCD paper — base rate is brutal.

### Phase 2 NDFD benchmark verdict (2026-04-29)

First real Brier-vs-NDFD comparison on the joint backtest+NDFD window (~163 days per station, 2024-11-01 → 2025-06-10). Per-fold residual sigma fit on training portion only — PIT correct. Bar per the [Pass 1 extension memo](docs/research/PASS-1-EXTENSION-EMOS-EXECUTION.md): ≥ 2-3% Brier improvement vs NDFD. Manifests: [`models/backtest_manifest.json`](models/backtest_manifest.json), [`models/backtest_router_manifest.json`](models/backtest_router_manifest.json).

| Station | Router strat | brier_model_subset | brier_ndfd | Δ vs NDFD | CLV proxy (pp) | Verdict |
|---|---|---|---|---|---|---|
| KJFK | NGR | 0.0793 | 0.0921 | **+13.9%** | +10.5 | ✅ clears bar |
| KLAX | RAW | 0.0495 | 0.1555 | **+61.7%** | +24.9 | ✅ clears bar (suspicious — see below) |
| KMIA | RAW | 0.0495 | 0.0784 | **+36.9%** | +15.5 | ✅ clears bar |
| KDEN | NGR | 0.1136 | 0.1136 | **−0.02%** | +10.0 | 🟡 tied |
| KAUS | NGR | 0.0969 | 0.0807 | **−20.1%** | +7.1 | ❌ fails bar |
| KMDW | RAW | 0.0985 | 0.0615 | **−60.0%** | +1.7 | ❌ fails bar |

**Reading the table:**
- "≥ 4 of 6 stations clear the bar" target → **3 of 6 cleared.** Not yet at the gate criterion #2 reframing.
- CLV proxy (mean `model_prob - ndfd_prob`) is **positive at every station** → our model is uniformly more bullish on YES than NDFD. Combined with the Brier results, that's "directionally similar but better-calibrated where we win, worse-calibrated where we lose."
- KLAX's +61.7% is suspicious — `brier_ndfd=0.1555` is unusually high, likely the Gaussian wrapper choking on the marine-station bimodal Tmax distribution (sea breeze regime). The [Allen et al. 2023 skew-normal NGR (item #4)](docs/research/PASS-1-EXTENSION-EMOS-EXECUTION.md) is the principled fix; that should narrow the apparent gap. Read the +61.7% as "the deterministic-Gaussian benchmark is structurally wrong here," not "we have 61% edge."
- KMDW −60.0% is the inverse: NDFD has materially lower Brier than us at this continental-climate station, where NBM is in its sweet spot. NGR overfits (router selects raw); raw produces a constant-prob row that NDFD outclasses. **This is the most consequential gap to close.** [Item #4 (skew-normal NGR)](docs/research/PASS-1-EXTENSION-EMOS-EXECUTION.md) and [item #1 deferred (GEFSv12 reforecast training)](docs/research/PASS-1-EXTENSION-EMOS-EXECUTION.md) are the two levers most likely to flip KMDW.

**What this means for the ship list (items #2-#5):** they were "nice to have"; they are now **load-bearing** for clearing the Phase 5 gate criterion #2 reframing. Specifically:
- Items #3 + #4 + #5 (isotonic recal, skew-NGR, climatology blend) target KAUS, KDEN, KMDW directly.
- Item #2 (maker/taker rule) is execution hygiene that compounds with whatever Brier we ship.
- Once items #2-#5 land, re-run this verdict and re-check the ≥ 4 of 6 bar.

**Caveats called out honestly in the manifest's `honest_caveats`:**
- Benchmark is **NBM-deterministic + Gaussian wrapper**, not true probabilistic NBM `qmd`. Per [research doc](docs/research/NDFD-BENCHMARK-SOURCE.md), upgrading to true `qmd` likely **narrows** the apparent KLAX/KMIA wins and **widens** the KMDW loss — the deterministic-Gaussian benchmark is roughly self-canceling in expected error direction, but skew-aware quantiles will be sharper everywhere.
- 12,544 of 28,616 evaluations per station have NDFD coverage (~44%) — Open-Meteo's NBM history starts ~2024-11-01. Earlier folds carry NaN; subsequent folds are the comparable subset.
- Phase 5 readiness criterion #2 should be **re-checked against true `qmd`** before crossing the gate.

## Phase 3 — NBA ⬜ (deferred until Phase 2 ships)

| Item | Status |
|---|---|
| `nba_api` client | ⬜ |
| `nbainjuries` polling | ⬜ |
| Pinnacle odds (paid Odds API, ~$30/mo) | ⬜ |
| Vig-free fair model + 538-style Elo fallback | ⬜ |
| Extend paper trader + backtest to NBA | ⬜ |

## Phase 4 — Dashboard + monitoring ⬜

| Item | Status |
|---|---|
| Streamlit dashboard (open markets / signals / P&L / freshness) | ⬜ stub |
| Alerting (ntfy / Pushover) | ⬜ |
| `kq health` command (ingest freshness check) | ⬜ candidate quality-of-life PR |

## Phase 5 — Real-money decision gate ⬜

10 hard criteria in [`CLAUDE.md §5`](CLAUDE.md). Live readiness snapshot:

| # | Criterion | Status |
|---|---|---|
| 1 | ≥ 500 settled paper trades | 0 settled — paper executor + settlement loop shipped (PR L); cron wiring + prod-weather access still ⬜ |
| 2 | Brier ≥ 5% better than raw on backtest | **1/6 stations** under pure NGR (KJFK +20.1%); router policy correctly applies NGR only where it wins. **NDFD-relative gauge (the real one, per [Pass 1 ext memo](docs/research/PASS-1-EXTENSION-EMOS-EXECUTION.md)):** 3/6 stations clear ≥ 2-3% Brier vs NDFD (KJFK, KLAX, KMIA); KDEN ties; KAUS, KMDW fail. **Bar of ≥ 4/6 not cleared.** See [§Phase 2 NDFD benchmark verdict](#phase-2-ndfd-benchmark-verdict-2026-04-29). Items #2-#5 of the [extension ship list](#phase-2-extension--ship-list-from-pass-1-extension-research) now load-bearing for closing the gap. |
| 3 | Reliability calibrated (no 10pp deviations) | Reliability bins emitted in backtest manifest; needs visual review |
| 4 | Positive paper P&L over 3 weeks | 0 weeks |
| 5 | CLV vs. Pinnacle ≥ +1% on NBA | NBA not built |
| 6 | Flows ≥ 30 days without unrecoverable failure | 0 days continuous (Mac dev only; Windows not yet running) |
| 7 | Bankroll plan written + 0.15× Kelly caps coded | Kelly caps coded ✅; written plan ⬜ |
| 8 | State availability for sports confirmed | not yet |
| 9 | CPA engaged for §1256 | not yet |
| 10 | NVIDIA HR/Legal disclosure | not yet |

**You are nowhere near Phase 5 and that's correct for where we are.**

## v2 (post-v1) — explicitly deferred ⏸

| Item | Why deferred |
|---|---|
| Equities research agent (Pass 2 architecture) | v1 weather/NBA must be calibrated first |
| Always-on autonomous research agent (LangGraph + MCP + Langfuse) | Same |
| Polymarket cross-venue read-only ingest | Useful for arbitrage signals; needs v1 baseline first |
| **Reddit (PRAW) read-only social scraper** | Decided in PR I — collected for future A/B testing only, never wired into v1 model. Twitter/X scraping is non-goal (TOS + low signal — see Pass 1 §1d). |
| Subscription product | Huge legal layer; see `docs/COMPLIANCE-ADDENDUM.md`; needs counsel + LLC |

## Hard non-goals ❌

Per [`CLAUDE.md §2`](CLAUDE.md):

- **Twitter / X scraping** — TOS-violating, account-ban risk, near-zero predictive lift on weather/NBA per Pass 1 §1d. Reddit (PRAW) is OK as a v2 *collection-only* item.
- **Sentiment / LLM-as-probability** — LLMs are bad calibrators (Pass 1 §1d).
- **ML beyond NGR + LightGBM** until baselines ship 500 settled trades.
- **Live trading** without the §5 gate.
- **NVDA-adjacent MNPI-tainted research** (see `docs/COMPLIANCE-ADDENDUM.md`).
- **Direct pushes to `main`** — must go through PR + CI green (enforce via [`docs/BRANCH-PROTECTION.md`](docs/BRANCH-PROTECTION.md)).

---

## How this doc stays current

The discipline is simple: **every PR that lands on `main` updates this doc** in the same commit. Specifically:

- A new feature shipped → mark its row ✅ + commit hash
- A new gap discovered → add a row with ⬜ or 🟡
- A non-goal decided → add to the "deferred" or "non-goals" section with rationale
- The Phase 5 readiness table → re-check whenever a relevant criterion's status changes

This is enforced socially (CLAUDE.md §14 lists it as a coding-standards rule) rather than mechanically — a custom CI check could be added to fail PRs that touch `src/` without touching `ROADMAP.md`, but that has more false positives than value at this stage.

If you ever find this doc out of sync with the codebase, that's a bug and the fix is a one-line PR. Don't let it rot.
