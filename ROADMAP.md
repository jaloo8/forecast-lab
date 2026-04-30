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
| 3 | **Isotonic recalibration (CORP / PAV)** | ✅ shipped | ~280 | `sklearn.isotonic.IsotonicRegression` post-active-model layer; per-fold fit on training-portion (prob, outcome) pairs pooled across brackets. PIT-correct. Default-on via `cfg.use_isotonic_recal=True`. **Verdict (post-#14 stacked on #13): KMIA pure-NGR flipped fail→pass (-13.8% → +4.4%); KDEN +19.7pp jump (-21.8% → -2.1%, now within sample-overlap noise of the bar); KMDW +14pp (-67% → -52%); KJFK barely moved (-4.1% → -2.6%); KAUS regressed slightly (-17.6% → -20.4%, isotonic over-corrects at well-fit stations).** See [§Phase 2 NDFD verdict — post-#14](#post-14-isotonic-update-2026-04-29). 2 of 6 still clear bar but 2 more land on the boundary. |
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

First real Brier-vs-NDFD comparison on the joint backtest+NDFD window (~163 days per station, 2024-11-01 → 2025-06-10). Per-fold residual `(bias, sigma)` fit on training portion only — PIT correct. Bar per the [Pass 1 extension memo](docs/research/PASS-1-EXTENSION-EMOS-EXECUTION.md): ≥ 2-3% Brier improvement vs NDFD. Manifests: [`models/backtest_manifest.json`](models/backtest_manifest.json), [`models/backtest_router_manifest.json`](models/backtest_router_manifest.json).

> **Audit correction (2026-04-29 evening):** A post-PR-#12 IC7 audit caught that PR #11's sigma fit omitted the bias term — `gaussian_exceedance(nbm_mean, sigma)` was using `nbm_mean` as the predictive center, but Open-Meteo's NBM under-forecasts CONUS Tmax by **0.9 to 3.6 °F** depending on station (verified empirically 2026-04-29; KLAX is at -1.6σ). The bias-uncorrected verdict made our model look better than it is at biased stations. **The numbers below are the bias-corrected ones; #11 and #12's verdict tables in earlier commits are obsolete.** See PR #13 (audit-fix) for the math.

| Station | Router strat | brier_model_subset | brier_ndfd | Δ vs NDFD (%) | abs Brier delta | mean prob diff (pp) | Verdict |
|---|---|---|---|---|---|---|---|
| KLAX | RAW | 0.0596 | 0.1037 | **+42.5%** | +0.0441 | -7.34 | ✅ clears bar |
| KMIA | RAW | 0.0495 | 0.0549 | **+10.0%** | +0.0054 | -5.49 | ✅ clears bar |
| KJFK | NGR | 0.0793 | 0.0762 | **−4.1%** | −0.0031 | -0.89 | ❌ fails (was wrongly listed +13.9% pre-fix) |
| KAUS | NGR | 0.0969 | 0.0823 | **−17.6%** | −0.0146 | -3.11 | ❌ fails |
| KDEN | NGR | 0.1136 | 0.0933 | **−21.8%** | −0.0203 | -1.06 | ❌ fails (was wrongly listed −0.0% pre-fix) |
| KMDW | RAW | 0.0984 | 0.0589 | **−67.1%** | −0.0395 | -2.90 | ❌ fails |

**Reading the table:**
- **Only 2 of 6 stations clear the ≥ 2-3% bar.** That's a worse picture than #11/#12 reported pre-audit. Both wins are at marine stations (KLAX, KMIA) where NBM's bias is largest and the Gaussian wrapper is least appropriate to NBM's true distributional shape — read the wins as "we beat the deterministic-Gaussian benchmark we built; true NBM `qmd` would likely narrow these wins." Phase 5 readiness criterion #2 reframing (≥ 4 of 6) is **clearly not cleared.**
- `mean_prob_diff_vs_ndfd_pp` (formerly mislabeled "CLV") = `mean(model_prob - ndfd_prob)` over the matched subset. **All values are now negative** — after bias correction, NDFD's predictive distribution shifts upward (because NBM was under-forecasting), so its YES probabilities are uniformly higher than our model's. This is consistent with NDFD being a sharper benchmark; pre-fix the proxy was misleadingly positive. Not closing-line value; we have no Kalshi market close to anchor against.
- KMDW −67% is the deepest gap — uniformly bad across all months and both bracket bands (see diagnostic below). Post-processing alone won't fix it; the [deferred item #6 (GEFSv12 reforecast training)](docs/research/PASS-1-EXTENSION-EMOS-EXECUTION.md) is the obvious lever there.

**Caveats called out honestly in the manifest's `honest_caveats`:**
- Benchmark is **NBM-deterministic + per-fold-fitted bias-corrected Gaussian**, not true probabilistic NBM `qmd`. Per [research doc](docs/research/NDFD-BENCHMARK-SOURCE.md), upgrading to true `qmd` likely **narrows** the apparent KLAX/KMIA wins (which both rely on the Gaussian-wrap mismatch with marine bimodal Tmax) and **widens** the KMDW loss — `qmd` would be a sharper benchmark in both directions.
- 12,544 of 28,616 evaluations per station have NDFD coverage (~44%) — Open-Meteo's NBM history starts ~2024-11-01. Earlier folds carry NaN; subsequent folds are the comparable subset.
- **Rolling-origin step=1 inflates the apparent sample.** ~163 unique calendar days × 7 brackets = ~1,140 independent (day, bracket) evaluations per station — not the 12,544 the `n` field suggests. Each calendar day appears in up to 14 overlapping test windows. Brier confidence intervals at the true `n` are wider than 4-decimal precision implies; treat ±2 percentage-point swings as within-noise.
- Phase 5 readiness criterion #2 should be **re-checked against true `qmd`** before crossing the gate.

#### Diagnostic deepen (2026-04-29) — what's actually breaking us

Per-bracket-band breakdown (center = ±1 around forecast mean; wing = ±2/±3). All numbers below are bias-corrected:

| Station | Center Δ% | Center abs delta | Wing Δ% | Wing abs delta | Diagnosis |
|---|---|---|---|---|---|
| KLAX | **+35.0%** | +0.069 | **+76.5%** | +0.025 | Wins both; marine bounded-distribution helps us |
| KMIA | **+8.7%** | +0.010 | +30.9% | +0.002 | Real but small win; consistent center+wing |
| KJFK | -6.9% | -0.009 | +3.9% | +0.001 | Loses center slightly, wings ~tied (small denominator) |
| KAUS | -3.3% | -0.005 | -74.8% | -0.022 | Loses both; wing % inflated by tiny denominator |
| KDEN | -7.7% | -0.013 | -77.0% | -0.026 | Loses both; chinook-event tails are real but absolute gap is small |
| KMDW | -46.5% | -0.053 | -166% | -0.030 | **Largest absolute loss anywhere** at center; wing % inflated |

Wing percentages can be misleading because wing absolute Brier denominators are tiny (0.014-0.083). The *absolute* Brier delta column is the honest read; KMDW's center -0.053 is the largest single gap on the board.

Per-month breakdown (KDEN sample as the bias-correction-most-impacted station): Nov -2.7%, Dec +3.8%, Jan -28.3%, Feb -30.6%, Mar -36.7%. KDEN's pre-correction "winter wins" were artifacts of the bias term. KMDW remains uniformly bad across every month (-37% to -91%) — structural, not seasonal.

**Reframed conclusions (post-audit):**

1. **The bias-uncorrected verdict (PRs #11/#12) was not just inflated — it was wrong about which stations win.** KJFK, KDEN, and KMIA-pure-NGR all flipped from "win" to "fail." Only KLAX and KMIA-router still clear the bar.
2. **The "wins center, loses wings" finding from the diagnostic in #12 was largely a bias artifact.** After bias correction, most stations lose at *both* bracket bands. The story is closer to "our NGR is overfitting and a bias-corrected NBM beats it" than "our NGR has wrong tails."
3. **KMDW is the deepest gap and it's structural** (largest absolute Brier delta, uniformly bad). Item #6 (GEFSv12 reforecast training) is more directly load-bearing than the Pass 1 ext memo originally framed.
4. **Skew-normal NGR (item #4) is still useful** but its expected impact is smaller than originally claimed — wing absolute deltas are 0.001-0.030, so even an 8-15% wing Brier improvement (Allen 2023) corresponds to small absolute gains. **Isotonic recalibration (item #3)** may be the better next ship if it lifts our miscalibrated center probabilities.

**Updated ship-list priority (was #4 first; revised after audit):**
- **#3 first (isotonic recalibration, ~50 LoC):** addresses the center-band miscalibration the bias correction surfaced. Cheapest, most directly targets the now-visible center losses at KAUS/KJFK/KDEN.
- **#4 second (skew-normal NGR, ~50 LoC):** still useful but addresses smaller absolute gains than originally projected. Pair with #3.
- **#5 third (climatology blend at long lead, ~80 LoC):** wing defense; lower priority now that wing absolute gaps are visible as small.
- **#2 anytime (maker/taker rule, ~150 LoC):** model-agnostic execution hygiene; orthogonal.
- **Item #6 (GEFSv12 reforecast training):** elevated from "deferred post-Phase-5" to "schedule before #4-5 if KMDW is the priority outlier to close." Largest single absolute gap on the board.

#### Post-#14 isotonic update (2026-04-29 evening)

Stacked on PR #13 (audit fix): isotonic recalibration on top of the bias-corrected NDFD benchmark. Per-fold fit on training-portion (raw_prob, outcome) pairs pooled across brackets. Default `cfg.use_isotonic_recal=True`.

**Bias-corrected verdict (post-#14, router strategy):**

| Station | Strat | brier_model | brier_ndfd | Δ vs NDFD | Δ from #13 (pp) | Verdict |
|---|---|---|---|---|---|---|
| KLAX | RAW | 0.0507 | 0.0995 | **+40.8%** | -1.7 | ✅ clears (was +42.5% pre-isotonic) |
| KMIA | RAW | 0.0542 | 0.0594 | **+8.9%** | -1.1 | ✅ clears (was +10.0% pre-isotonic) |
| KDEN | NGR | 0.0984 | 0.0964 | **−2.1%** | **+19.7** | 🟡 boundary (was -21.8% pre-isotonic — biggest single-PR jump on the board) |
| KJFK | NGR | 0.0779 | 0.0762 | **−2.6%** | +1.5 | 🟡 boundary (was -4.1% pre-isotonic) |
| KAUS | NGR | 0.0775 | 0.0653 | **−20.4%** | -2.8 | ❌ fails (slightly worse — isotonic over-corrects at well-fit stations) |
| KMDW | RAW | 0.0798 | 0.0586 | **−51.1%** | +16.0 | ❌ fails (improved 16pp but still deepest gap) |

**Bar status:** still 2 of 6 cleanly clear ≥ 2-3% (KLAX, KMIA). **KDEN and KJFK are now within sample-overlap noise of the boundary** (~-2pp at the rolling-origin-step=1 effective n of ~1140; ±2pp is plausibly noise).

**Per-bracket-band post-isotonic:**

| Station | Center Δ% | Center abs delta | Wing Δ% | Wing abs delta |
|---|---|---|---|---|
| KLAX | +32.9% | +0.065 | +76.5% | +0.025 |
| KMIA | +7.5% | +0.009 | +30.9% | +0.002 |
| KDEN | **+10.3%** | **+0.018** | -50.6% | -0.017 |
| KJFK | -8.6% | -0.011 | +14.6% | +0.005 |
| KAUS | -8.3% | -0.013 | -68.2% | -0.020 |
| KMDW | -29.5% | -0.034 | -155% | -0.028 |

KDEN flipped center +10% (was +18% pre-isotonic — slight over-correction on the favorable side), with wings still bad as expected. **Wings remain the dominant gap at every failing station** — the case for skew-normal NGR (item #4) survives the isotonic landing, just with smaller expected absolute gains than originally projected.

**What's left to close:**
- **KDEN and KJFK** — borderline; skew-normal at the wings should push them across.
- **KAUS** — small over-correction; may also benefit from skew-normal but could need targeted attention.
- **KMDW** — deepest structural gap; skew-normal alone won't close it. Item #6 (GEFSv12 reforecast training) likely required.

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
