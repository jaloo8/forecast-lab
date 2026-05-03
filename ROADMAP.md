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
| 2 | **Maker-vs-taker decision rule** | ✅ shipped (+ fee-rounding fix in #20) | ~280 | `MakerTakerPolicy` decides per-trade based on edge magnitude: skip if post-taker-fee edge < `min_edge_pct`; maker if edge buffer ≥ 2 ticks above skip threshold; else taker. Maker simulates fill 1 tick inside spread + maker fee (~25% of taker fee per Kalshi's Feb 2026 schedule, verified 2026-04-30). **Brier unchanged (same model); PnL materially better** — bankroll-bleed at KJFK from negative-EV taker fills was masking the model's edge (KJFK final bankroll: -$0.29 → +$219,986 due to bankroll surviving the full window). See [§Post-#17 maker/taker update](#post-17-makertaker-update-2026-04-30). **PR #20 audit (2026-04-30):** verified fee rate against current Kalshi schedule (25% confirmed, NOT 28% as Pass 1 memo cited — memo was stale). Found + fixed a separate maker-rounding bug: existing code applied the discount to the already-rounded taker fee instead of rounding-up per side independently (off by 0.5¢ at C=0.50, inflated reported maker savings). Provenance test added pinning the rate to the published schedule. |
| 3 | **Isotonic recalibration (CORP / PAV)** | ✅ shipped | ~280 | `sklearn.isotonic.IsotonicRegression` post-active-model layer; per-fold fit on training-portion (prob, outcome) pairs pooled across brackets. PIT-correct. Default-on via `cfg.use_isotonic_recal=True`. **Verdict (post-#14 stacked on #13): KMIA pure-NGR flipped fail→pass (-13.8% → +4.4%); KDEN +19.7pp jump (-21.8% → -2.1%, now within sample-overlap noise of the bar); KMDW +14pp (-67% → -52%); KJFK barely moved (-4.1% → -2.6%); KAUS regressed slightly (-17.6% → -20.4%, isotonic over-corrects at well-fit stations).** See [§Phase 2 NDFD verdict — post-#14](#post-14-isotonic-update-2026-04-29). 2 of 6 still clear bar but 2 more land on the boundary. |
| 4 | **Skew-normal NGR predictive distribution** | ✅ shipped | ~290 | Replaces NGR's Gaussian assumption with `scipy.stats.skewnorm`. Addresses bounded-below + heavy-upper-tail shape of Tmax. Multi-start MLE with intercept correction; falls back to Gaussian seed if optimizer doesn't beat alpha=0 on training. Default-on via `cfg.use_skew_normal=True`. **Verdict (post-#15 stacked on #14, router held constant): KAUS center -8.3% → -1.0% (biggest single-station-band improvement of the PR; overall -20.4% → -14.5%); KDEN, KJFK essentially unchanged because isotonic already saturated the recalibratable signal there. Wing-Δ% across stations basically unchanged from PR #14 — Allen 2023's 8-15% upper-tail improvement didn't reproduce at our scale.** See [§Phase 2 NDFD verdict — post-#15](#post-15-skew-normal-update-2026-04-29). |
| 5 | **Climatology blending at long lead** | ✅ shipped (off-by-default) | ~330 | Per-(station, month) Gaussian climatology fit per-fold from training-portion observed; blend = `w*model + (1-w)*clim`, `w = exp(-lead/τ)`. **Empirical finding 2026-04-30: at lead=1 the blend is net-negative at every station (Brier-vs-NDFD regressions of -8pp to -24pp).** The model is sharp at lead=1; pulling sharp-correct predictions toward the diffuse climatology trades sharpness for a wing-defense the v1 backtest doesn't need. The mechanism is implemented + unit-tested at synthetic long-lead — disabled by default until lead 5-7 backtests are in scope. See [§Post-#16 climatology update](#post-16-climatology-update-2026-04-30). |
| 6 | **GEFSv12 reforecast-trained NGR** | ✅ shipped (mechanism + Path B), 🟡 verdict null | ~1300 | Train NGR on reforecasts from `s3://noaa-gefs-retrospective`. All three phases shipped (PR #19/#21/#22) + Path B follow-up (2026-05-01: pulled 2015-2019 × 5 members = 53,994 rows; backfilled 2015-2018 NWS ACIS observed truth so the JOIN actually exercises the full training set). **Final verdict at full sample size: KMIA flipped to passing (-2.6% → +8.2% vs NDFD); other stations moved by ±1-6pp**, no Hagedorn-Hamill-Whitaker doubling-CRPSS. **Cross-model-family mismatch confirmed as the dominant constraint** (training on GEFSv12 reforecast, evaluating on GFS-via-Open-Meteo operational). Reforecast-NGR is tied or worse than skew-NGR at every station — the router would never pick it. Mechanism + data are complete and ready for Path A (GEFS-family operational migration) if KMDW becomes a higher priority. See [`docs/research/GEFSV12-REFORECAST-INTEGRATION.md`](docs/research/GEFSV12-REFORECAST-INTEGRATION.md), [§Post-#22 reforecast verdict](#post-22-reforecast-ngr-verdict-2026-04-30), and [§Path B execution + verdict](#path-b-execution--verdict-2026-05-01) below. |
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

#### Post-#15 skew-normal update (2026-04-29 evening)

Stacked on PR #14 (isotonic). Replaces NGR's Gaussian likelihood with skew-normal (`scipy.stats.skewnorm`). Multi-start MLE with intercept correction so the alpha=±2 starts have the right initial conditional mean; falls back to Gaussian seed if the optimizer doesn't beat alpha=0 on training. **Router config held constant from PR #14** (KMDW=RAW, KMIA=RAW, KLAX=RAW) for clean comparison; auto-`kq decide-router` would have flipped KMDW from RAW to NGR based on Brier-vs-raw improvement, but that flip causes Brier-vs-NDFD to regress (-51% → -59%) — a router-objective-mismatch finding called out separately below.

**Bias-corrected verdict (post-#15, router strategy with router held constant):**

| Station | Strat | brier_model | brier_ndfd | Δ vs NDFD | Δ from #14 (pp) | Δ from #13 (pp, total stack) | Verdict |
|---|---|---|---|---|---|---|---|
| KLAX | RAW | 0.0507 | 0.0995 | **+40.8%** | 0 (RAW unchanged) | -1.7 | ✅ clears |
| KMIA | RAW | 0.0542 | 0.0594 | **+8.9%** | 0 (RAW unchanged) | -1.1 | ✅ clears |
| KDEN | NGR-skew | 0.0986 | 0.0967 | **−1.9%** | +0.2 | **+19.9** ✨ | 🟡 boundary |
| KJFK | NGR-skew | 0.0779 | 0.0764 | **−2.0%** | +0.6 | +2.1 | 🟡 boundary |
| KAUS | NGR-skew | 0.0757 | 0.0660 | **−14.5%** | **+5.9** | +3.1 | ❌ fails (improving) |
| KMDW | RAW (held) | 0.0985 | 0.0589 | **−51.1%** | 0 (held) | +16.0 ✨ | ❌ fails |

**Per-bracket-band post-#15:**

| Station | Center Δ% | Center abs delta | Wing Δ% | Wing abs delta | Δ center from #14 |
|---|---|---|---|---|---|
| KLAX | +32.9% | +0.065 | +76.5% | +0.025 | 0 (RAW unchanged) |
| KMIA | +7.5% | +0.009 | +30.9% | +0.002 | 0 (RAW unchanged) |
| KDEN | +10.6% | +0.018 | -50.6% | -0.017 | +0.3pp |
| KJFK | -7.7% | -0.010 | +14.2% | +0.005 | +0.9pp |
| KAUS | **-1.0%** | -0.002 | -68.2% | -0.020 | **+7.3pp** ✨ |
| KMDW | -29.5% | -0.034 | -155% | -0.028 | 0 (held) |

**Bar status:** still 2 of 6 cleanly clear ≥ 2-3% (KLAX, KMIA). KDEN at -1.9% and KJFK at -2.0% remain on the boundary — within sample-overlap noise (effective independent n ~1140; ±2pp is plausibly noise). **The ≥ 4 of 6 bar is not cleanly cleared, but with two stations within ±2pp it could plausibly cross with one more push.**

**Honest read of the stacked #14+#15 effect:**

- **Isotonic (#14) did the heavy lifting** at KDEN (+19.7pp), KMDW (+16pp held-RAW), KMIA (+18.2pp pure-NGR / +1pp router-RAW).
- **Skew-normal (#15) added meaningful gains at KAUS (+5.9pp center, +5.9pp overall)** — biggest single contribution at any station from this PR.
- **Skew-normal added little at KDEN/KJFK** because isotonic already saturated their recalibratable signal. The remaining gap there is tail/wing-driven, but Allen 2023's claimed 8-15% upper-tail Brier improvement did not reproduce at our scale (sample size, noise floor, or absolute-Brier-tiny denominator effects).
- **Wings remain the dominant gap at every failing station.** Skew-normal didn't help wings as projected. Two interpretations: (a) the deterministic-Gaussian wrap of NBM is *itself* tail-wrong, so both we and NDFD misfire at wings; (b) we need a different upgrade (climatology blend at long lead, item #5; or GEFSv12 reforecast training, item #6) to close wing gaps further.

**Router objective mismatch (new finding):**

When `kq decide-router` runs on the post-#15 manifest, KMDW's `brier_improvement_vs_raw_market` of +6.21% triggers a flip from RAW to NGR — but Brier-vs-NDFD regresses from -51% to -59% under that flip. The router's optimization objective (vs synthetic naive market) ≠ our gate criterion (vs NDFD). Currently the router_config.json carries a manual override holding KMDW at RAW for verdict consistency; the long-term fix is to redesign the router decision criterion to be NDFD-aware. **Tracked as new ship-list item below.**

**Updated ship list after #14+#15:**
- **#5 next (climatology blend at long lead, ~80 LoC):** wing defense at lead 5-7d. Compounds with what we have. Targets the now-visible "wings still bad" residual gap.
- **#2 anytime (maker/taker rule, ~150 LoC):** model-agnostic execution hygiene; orthogonal.
- **NEW: router NDFD-aware decision criterion (~50 LoC):** redesign `kq decide-router` to optimize Brier-vs-NDFD instead of (or in addition to) Brier-vs-raw-market. Surfaced by the #15 KMDW flip. Gates the auto-decide pipeline going forward.
- **Item #6 (GEFSv12 reforecast training):** still likely required for KMDW. Largest absolute gap on the board after #14+#15.

#### Post-#16 climatology update (2026-04-30)

PR #16 ships per-(station, month) Gaussian climatology + lead-time-weighted blend (`w = exp(-lead/τ)`) per Pass 1 ext memo §5. Mechanism is fully implemented, unit-tested, and PIT-correct (per-fold fit on training-portion observed truth only).

**Empirical finding: at lead=1 the blend is net-negative at every station.** Backtest sweep with `use_climatology_blend=True` showed:

| Station | Strat | Blend ON | Blend OFF (#15 baseline) | Δ |
|---|---|---|---|---|
| KLAX | RAW | +32.8% | +40.8% | **-8.0pp** |
| KMIA | RAW | -9.3% | +8.9% | **-18.2pp** (flipped to fail!) |
| KJFK | NGR-skew | -12.6% | -2.0% | -10.6pp |
| KAUS | NGR-skew | -24.6% | -14.5% | -10.1pp |
| KDEN | NGR-skew | -17.0% | -1.9% | -15.1pp |
| KMDW | RAW (held) | -75.0% | -51.1% | **-23.9pp** |

**Why:** at lead=1 our model is sharp; climatology is diffuse (per-month mean ± 4-6 °F). Brier penalizes loss of sharpness on correct predictions more than it rewards damping of incorrect ones at the typical hit-rate. The Pass 1 memo specifically called this out for *lead 5-7d* where parametric tails are too thin — at lead=1 we don't have that problem.

**Decision:** ship the mechanism with `cfg.use_climatology_blend=False` as the default. The code is ready for future lead 5-7 backtests; flipping to `True` becomes correct when we extend the backtest grid beyond lead=1. Documented in the engine config docstring with the empirical numbers so future readers don't have to re-derive the finding.

**Verdict unchanged from #15** since climatology defaults off. Ship list shifts:

- **#2 maker/taker rule (~150 LoC)** moves to top — model-agnostic, lead-1-friendly, expected ~25 bps savings per round-trip per Pass 1 ext memo.
- **NEW: router NDFD-aware decision criterion (~50 LoC)** — surfaced by the #15 audit; misalignment between router optimization target (vs raw market) and gate criterion (vs NDFD).
- **#6 GEFSv12 reforecast training (deferred ⏸ → consider sooner)** — still likely required for KMDW; ~25 GB pull from `s3://noaa-gefs-retrospective`.
- **#5 climatology blend** stays in code, off-by-default; revisit when long-lead backtest is in scope.

#### Post-#17 maker/taker update (2026-04-30)

PR #17 ships the `MakerTakerPolicy` per Pass 1 ext memo §2 + bonus paragraph. Per-trade decision: skip if post-taker-fee edge < 4pp; maker if edge buffer ≥ 2pp above skip threshold; taker otherwise. Maker simulates fill at 1 tick inside spread + maker fee.

**Brier-vs-NDFD numbers identical to #15 — model predictions are unchanged; only execution/fees differ.** P&L materially shifts because bankroll dynamics gate future trades:

| Station | Strat | Pre-#17 PnL | Post-#17 PnL | n_trades | Maker fee savings |
|---|---|---|---|---|---|
| KAUS | NGR-skew | $52,573 | **$67,511** (+$14,938) | 10072 (8581 maker, 1491 taker) | $8,379 |
| KDEN | NGR-skew | $190,013 | **$222,523** (+$32,510) | 20088 (16754 maker, 3334 taker) | $17,358 |
| KJFK | NGR-skew | -$1,000 | **$226,466** (+$227,466) | 1703 → 8554 (7589 maker, 965 taker) | $13,514 |
| KLAX | RAW | -$964 | **-$660** (+$304) | 1750 (1045 maker, 705 taker) | $1,269 |
| KMDW | RAW (held) | $82,594 | **$98,041** (+$15,447) | 9866 (7592 maker, 2274 taker) | $8,436 |
| KMIA | RAW | -$176 | **$2,817** (+$2,994) | 2283 (1431 maker, 852 taker) | $1,051 |

**Why KJFK trade count jumped 1703 → 8554:** legacy taker-only path was net-negative-EV at KJFK; bankroll bled to ≤$0 by trade #1703 and the Kelly `bankroll_usd <= 0` gate skipped all subsequent trades. Maker mode flips per-trade EV positive (1¢-better fill + ~75% fee discount), bankroll survives the full window, and the engine keeps trading. The model's predictions (Brier 0.0779, vs-NDFD -2.0%) are unchanged — execution improvement alone unmasks the model's actual edge.

**Maker fee rate audit (deferred follow-up):** Current `MAKER_DISCOUNT=0.25` in `src/kq/execution/fees.py` reads as "maker is 25% of taker fee" (4× cheaper). Pass 1 ext memo cites Kalshi's published schedule (kalshi.com/docs/kalshi-fee-schedule.pdf) as `0.0025·P·(1−P)` for maker vs `0.07·P·(1−P)` for taker — i.e., maker = 0.036 of taker, a **28× discount**. That's a 7× discrepancy in the maker fee rate, which would compound the savings shown above by ~7×. Per CLAUDE.md §9, fee-model changes need explicit user signoff — flagged here, deferred to a separate small PR after user confirmation of the current Kalshi schedule.

**Phase 5 readiness note:** the dramatic PnL deltas vs. unchanged Brier/CLV are an artifact of the synthetic naive market being a weak counterparty. Real Kalshi market makers won't let us fill at the same edges. The honest read is "fee discipline matters; the model has center-band edge at the stations where Brier-vs-NDFD shows it (KJFK, KLAX, KMIA, KAUS); P&L magnitudes are upper bounds." This pattern was already noted in the manifest's `honest_caveats`; the maker/taker landing reinforces it.

**Updated ship list after #17:**

- **NEW: router NDFD-aware decision criterion (~50 LoC)** — next ship; addresses #15 audit finding.
- **NEW: maker fee rate audit + parameter update (~10 LoC + user signoff)** — small but consequential; surfaced by this PR.
- **#6 GEFSv12 reforecast training (deferred ⏸)** — still the only structural lever for KMDW.
- **#5 climatology blend** — off-by-default, revisit at long lead.

#### Post-#18 NDFD-aware router update (2026-04-30)

PR #18 redesigns `kq decide-router` to optimize the gate criterion (Brier-vs-NDFD) directly rather than the proxy (Brier-vs-raw-market) per the post-#15 audit. Two-pass workflow:

```
$ kq backtest --strategy weather_v1            # all-NGR Brier-vs-NDFD per station
$ kq backtest --strategy weather_all_raw_v1    # all-RAW Brier-vs-NDFD per station (NEW)
$ kq decide-router                              # picks per-station strategy with better vs-NDFD
```

When both manifests are present, decision rule per station: **pick NGR if NGR-vs-NDFD ≥ RAW-vs-NDFD + 1pp; else RAW** (1pp threshold = hysteresis to avoid noise flips). Falls back to legacy `brier_improvement_pct` rule when either NDFD column is missing.

**Per-station NDFD-aware decisions:**

| Station | NGR vs NDFD | RAW vs NDFD | Δ (NGR − RAW) | Decision | Was |
|---|---|---|---|---|---|
| KAUS | -14.54% | -14.47% | -0.07pp | **RAW** | NGR (flipped) |
| KDEN | -1.87% | -7.38% | +5.51pp | NGR | NGR (unchanged) |
| KJFK | -1.96% | -13.06% | +11.10pp | NGR | NGR (unchanged) |
| KLAX | +38.19% | +40.79% | -2.60pp | RAW | RAW (unchanged) |
| KMDW | -58.90% | -51.14% | -7.76pp | **RAW** | RAW (auto, was manual override) |
| KMIA | +4.21% | +8.91% | -4.70pp | RAW | RAW (unchanged) |

**Two notable changes from #17 router_config:**

1. **KAUS flipped NGR → RAW.** Under the legacy rule (improvement vs raw market = +5.3%), KAUS was picked as NGR. Under the NDFD-aware rule, NGR and RAW are tied at -14.5% — RAW wins by the 1pp hysteresis. Brier-vs-NDFD verdict effectively unchanged at -14.5% (same as the prior "NGR" decision).
2. **KMDW manual override removed.** The router now automatically picks RAW at KMDW (NGR -58.9% vs RAW -51.1% → RAW better by 7.8pp) without the manual override `router_config.json` was carrying since #15. This is the cleanup the audit identified.

**Bar status unchanged:** still 2 of 6 cleanly clear (KLAX, KMIA); KDEN/KJFK on boundary; KAUS/KMDW fail. The router redesign aligns the optimization target with the gate criterion — preventing the kind of false-positive disagreement that #15 surfaced — but doesn't change the model's underlying capability.

**Updated ship list after #18:**

- **NEW: maker fee rate audit + parameter update (~10 LoC + user signoff)** — surfaced by #17.
- **#6 GEFSv12 reforecast training (deferred ⏸ → planned)** — the structural lever remaining for KMDW. After #18 the auto-router objective is honest; KMDW's -51% gap is a real model deficit, not a router-design artifact.
- **#5 climatology blend** stays in code, off-by-default; revisit at long lead.

#### Post-#19 GEFSv12 phase 1 update (2026-04-30)

PR #19 ships **phase 1 of 3** for ROADMAP item #6: scoping research, URL builders, key iterators, idx parser, and a `kq plan-gefsv12-pull` dry-run estimator. **No data is downloaded yet** — phase 1 is pure scaffolding so the user can size up the operation before approving phases 2-3 (which add system dependencies).

Verified archive shape via S3 spike (2026-04-30):
- `s3://noaa-gefs-retrospective/GEFSv12/reforecast/{year}/{cycle}/{member}/Days:1-10/{var}_{cycle}_{member}.grib2`
- **Archive depth:** 2000-2019 (20 years frozen at GEFSv12). 2020+ empty.
- **Members:** c00 (control) + p01-p04 (4 perturbations) = **5 total** (not 31; deliberate design for long reforecast set).
- **Variable:** `tmax_2m` ✓ matches our needs.
- **File size:** ~59 MB per (cycle, member, var, days-range).

**Corrected memo's 25 GB estimate:** Pass 1 ext memo cited "~25 GB compressed" but assumed full-file pulls. With byte-range subsetting via `.idx` companions we get only the bytes covering our 6 station grid points — **~913 MB total** for the full 20-year archive at lead 1. Plan output verified by the new dry-run CLI:

```
$ kq plan-gefsv12-pull
GEFSv12 reforecast pull plan (dry run — nothing downloaded):
  archive years           : 2000 → 2019
  unique cycles           :      7,305
  total files indexed     :     36,525
  total HTTP requests     :    255,675
  bytes (.idx files)      :      255.7 MB
  bytes (range records)   :      657.5 MB
  bytes (total)           :      913.1 MB
```

**Phase 2 (PR #21) ✅ shipped 2026-04-30:**

Added `cfgrib` + `xarray` + `eccodeslib` Python deps. **No system `brew install` needed** — `eccodeslib` ships the libeccodes wheel (M1/arm64 supported). Real byte-range fetcher + xarray subset extraction at station coordinates + DuckDB persistence with `model='gefsv12_reforecast'`, member 0..4 (c00..p04). Per-record bandwidth corrected: ~750 KB per record (whole-grid; cfgrib doesn't subset at the GRIB2 layer); phase 1's "913 MB" estimate was wrong (assumed grid-point subsetting). Memo's 25 GB estimate was right at full ensemble × 8 day-1 records.

Smoke pull verified end-to-end: 30 cycles c00 in Jan 2019 → 180 rows in DuckDB, Tmax values climatologically sane (KMDW -1°F..54°F, KMIA 67°F..81°F).

**Phase 3 (PR #22 — next):**

Rewire `kq train-weather` to consume reforecast data; re-run backtest verdict.

Operational prerequisites (no code; users run these):
1. Full reforecast pull: `kq pull-gefsv12-reforecasts --members c00` — ~7,300 cycles, ~30-60 min, ~5 GB DB growth.
2. Observed-truth backfill: `kq backfill-observed --start 2000-01-01 --end 2019-12-31` — uses existing NWS ACIS tool.

Expected impact (Hagedorn-Hamill-Whitaker 2008 doubling-CRPSS): KMDW vs-NDFD plausibly goes from -51% to **+5% to +20%**.

**Bar status (unchanged from #20):** still 2 of 6 cleanly clear. Phase 2 unblocks the path; phase 3 (PR #22) is where the verdict moves.

#### Post-#22 reforecast NGR verdict (2026-04-30)

Phase 3 of #6 ships the NGR rewire (`weather_reforecast_v1` strategy: pre-fit one NGR per station from reforecast×observed pairs, no per-fold refit since reforecast 2000-2019 is all PIT-prior to the 2024+ test window). Tested with the 1-year 2019 c00 pull (~2,183 joint training rows, 99.7% coverage). After fixing an in-sample-evaluation leak (test loop was iterating reforecast rows that were the training data), the honest verdict is:

| Station | Skew-NGR (#15) | Reforecast-NGR | Δ |
|---|---|---|---|
| KAUS | -14.5% | **-12.9%** | +1.6pp |
| KDEN | -1.9% | **-1.2%** | +0.7pp (closer to bar) |
| KJFK | -2.0% | **-42.4%** | -40.4pp |
| KLAX | +40.8% | **+4.1%** | -36.7pp (still passes bar) |
| KMDW | -51.1% | **-66.3%** | -15.2pp |
| KMIA | +8.9% | **-2.6%** | -11.5pp (flipped to fail) |

**This is null-or-slight-negative**, not the Hagedorn-Hamill-Whitaker (HHW) "doubling-CRPSS" the Pass 1 memo predicted. Two root-cause hypotheses (both well-supported):

**1. Cross-model-family mismatch (dominant effect).** HHW2008's doubling result requires training and operational forecasts to come from the same NWP model. We trained NGR on **GEFSv12 reforecast** but applied it operationally to **GFS-via-Open-Meteo** (a different model family with different bias structure). NGR's `T_obs ~ N(a + b*forecast, σ²)` fit absorbs forecast-specific bias; that fit doesn't transfer cleanly across model families. The KJFK/KMDW collapses are consistent with this.

**2. Insufficient training data (compounding effect).** HHW2008 used 30 years × N members ≈ 36k samples per station. Our 1-year c00 pull gives ~365 samples per station — actually FEWER than the operational rolling-origin window (~365 days × ~11 ensemble configs ≈ 4k samples). Single-year-c00 reforecast NGR is *less* informed than the existing skew-NGR.

**Two paths to unlock the full HHW2008 benefit (both deferred to follow-up):**

- **Path A (model-family alignment):** switch operational data source from `gfs_seamless` to a GEFS-based product Open-Meteo also serves; train + operate in the same family. Requires evaluating Open-Meteo's GEFS-equivalent endpoint, possibly re-doing the existing weather_forecast ingest.
- **Path B (more reforecast training):** pull all 5 members + 5+ years (e.g., 2015-2019). 5 years × 5 members × ~365 days ≈ 9k samples per station. Closer to HHW2008 scale. Bandwidth cost: ~22 GB raw, ~30 min wall time, compounded with member iteration.

**What this PR does ship for sure:**
- Verified the full reforecast pipeline works end-to-end (cfgrib parses, DuckDB persists, NGR fits, backtest runs).
- Surfaced the cross-model-family mismatch as a real constraint, not a hypothetical.
- Provides the mechanism for Path A and Path B follow-ups without further engine work — only the training data + ingest source need to change.

**Bar status:** **unchanged at 2 of 6 cleanly clear.** The reforecast strategy is shipped but not the active verdict driver — `weather_router_v1` (#18 NDFD-aware decisions) remains the recommended trading config.

**Updated ship-list:** items #1-#6 are now all shipped or status-final. Open follow-ups for further verdict movement:
- Path A or Path B above (depends on user decision; both unlock the deferred HHW2008 benefit).
- The deferred items #7-#10 (MBM, CVX-Kelly, OU nowcast, LightGBM) — only #10 is post-Phase-5; others can be considered if KMDW remains the priority gap.

#### Path B execution + verdict (2026-05-01)

User approved Path B. Executed: pulled GEFSv12 reforecast `c00,p01,p02,p03,p04` × 2015-2019 (9,130 files, 432k records, 53,994 rows in `weather_forecast`, ~2 hours wall time, CPU-bound on cfgrib parsing). Pull idempotent, completed cleanly with no tracebacks.

**Discovery during evaluation:** the first reforecast×observed JOIN yielded only 396 dates per station — same as the 1-year c00 baseline — because `weather_observed` only covered 2018-12-01+. The Path B pull was working perfectly; the verdict bottleneck was pre-2019 truth coverage, not reforecast coverage. Backfilled NWS ACIS for 2015-2018 (8,580 rows in 10 sec) to actually exercise the full training set.

**Path B at full scale** (per-station NGR fit on 1,825 cycles × 5-member ensemble mean):

| Station | 1y c00 (vs NDFD) | Path B full (vs NDFD) | Δ vs c00 | Skew-NGR (active) | Δ vs skew-NGR |
|---|---|---|---|---|---|
| KAUS | -12.9% | -14.1% | -1.2pp | -14.5% | +0.4pp (tied) |
| KDEN | -1.2% | -2.9% | -1.7pp | -1.9% | -1.0pp (tied) |
| KJFK | -42.4% | -40.3% | +2.1pp | -2.0% | **-38.3pp** |
| KLAX | +4.1% | +5.4% | +1.3pp | +40.8% | **-35.4pp** |
| KMDW | -66.3% | -60.4% | +5.9pp | -51.1% | -9.3pp |
| KMIA | -2.6% | **+8.2%** | **+10.9pp** ✓ | +8.9% | -0.7pp (tied) |

**Path B vs the 1-year c00 baseline:** real but modest. KMIA flipped positive (-2.6% → +8.2%, the only station to cross the bar from below). KMDW improved by ~6pp but remains far from the bar. KJFK, KLAX gained ~1-2pp. KAUS, KDEN regressed by ~1pp.

**Path B vs skew-NGR (active model):** the structural ceiling is unchanged. Reforecast NGR is **tied or slightly worse** at 4 of 6 stations and significantly worse at KJFK and KLAX (cross-model-family penalty dominates). At no station does reforecast-NGR beat skew-NGR meaningfully — the router would never select it.

**Conclusion:** the Hagedorn-Hamill-Whitaker doubling-CRPSS effect did **not** materialize at our 6 stations, lead 1, with cross-model-family training. The "more samples" hypothesis is partially validated (KMIA flip is real, KMDW closes ground); the dominant constraint was confirmed to be **cross-model-family mismatch**, not sample count. Path B is now **complete and not the verdict driver** — `weather_router_v1` (skew-NGR + NDFD-aware routing) remains the recommended trading config. Bar status: **2 of 6 cleanly clear** (KLAX, KMIA — same stations and roughly the same margins as before).

**What's left of the original ship-list:** items #1-#6 are all status-final. The remaining lever for KMDW is now Path A (operational data source migration to GEFS family) — significantly more work than Path B and not justified by the marginal gains seen here. Recommendation: **freeze KMDW as a known structural gap**; pursue Path A only if a v2 lever (item #10 LightGBM, post-Phase-5) doesn't deliver.

#### Pre-merge audit fixes (2026-05-01, post-Path-B)

Before landing the 13-PR stack into `main`, an audit + integration tests caught two pre-existing correctness bugs that had been masked by data coverage:

**1. `TradeRecord.edge_pct` was wrong for `BUY_NO` trades.** The naive `abs(model_prob - fill_price)` formula compares unrelated YES-side probability to NO-side fill price (the canonical schema stores `model_prob` as YES-relative and `fill_price` as the actual side cost). For BUY_NO at extreme prices, this inflated the apparent edge by 7-10x. The same buggy formula was duplicated in `engine.py:650-652`, polluting every backtest manifest's `avg_edge_pct_pre_fee` / `avg_edge_pct_post_fee` summary fields. **Trading gates were unaffected** (those use `prob_at_fill - fill_price_taker` directly, not the property), so live P&L is correct — only the reported edges were wrong. Fixed by adding a `prob_at_fill` property and refactoring the engine summary to use the property (DRY). Regression test: `test_trade_record_edge_pct_for_buy_no_trade` and a symmetry test. Commit `1ceedce`.

**2. Operational strategies were including `gefsv12_reforecast` rows in the rolling-origin CV** once 2015-2018 NWS ACIS truth was backfilled. Pre-existing semantic bug: only `weather_reforecast_v1` filtered reforecast rows from the test set; operational strategies (weather_v1, weather_router_v1, weather_all_raw_v1) silently included 5-7x extra cross-model-family pairs after the JOIN suddenly contributed pre-2019 rows it had been dropping. Fixed by lifting the filter into the initial dataframe filter so it applies uniformly. Regression test: `test_run_backtest_excludes_reforecast_rows_from_test_set`. Commit `0a12340`.

Both fixes commit before the merge so `main` lands with corrected metrics and the regression guards in place. Manifest summary fields were regenerated against the corrected math.

## Phase 3 — NBA 🟡 (started 2026-05-02)

| Item | Status |
|---|---|
| `nba_api` schedule client + ingest flow + `nba_game` schema | ✅ PR 1 (`def83c7`) |
| **The Odds API v4 client + typed dataclasses (HTTP layer only)** | 🟡 PR 3 (this commit) — async client + parser + quota-header tracking, fixture-tested without a key. Construction errors out cleanly when `ODDS_API_KEY` is unset; live calls require `$30/mo` GOAT plan signoff for Pinnacle data. **balldontlie is not a viable Pinnacle fallback** — their odds tier is BetMGM-only ($9.99/mo); for a free fallback we'd need to scrape espn.com (TOS-fragile) or accept BetMGM via balldontlie's paid tier. The honest position: no free Pinnacle alternative exists. |
| `nba_odds` schema + storage repository + ingest flow + cron | ⬜ PR 4 — wires the client into the cron + DuckDB. Gated on `ODDS_API_KEY` being set; flow no-ops with a structured warning when the key is empty. |
| `nbainjuries` polling | ⬜ |
| Vig-strip math (proportional + power devig) | 🟡 PR 2 (open as #34) |
| 538-style Elo fallback model | ⬜ |
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
| 3 | Reliability calibrated (no 10pp deviations) | **Mechanism shipped (PR #25, 2026-05-02).** New `ReliabilitySummary` + `summarize_reliability()` in `src/kq/models/calibration.py` excludes buckets with `n < min_n` (default 100) from the failing-bucket count. Wired into both backtest manifests (`reliability_summary` key on each station's BacktestResult) and the training manifest (`cv.reliability_summary`). The n-aware bar is now machine-readable for cron alerting; pass/fail per station is `stations[ICAO].reliability_summary.passes_bar`. **Empirical post-#25 status (`weather_router_v1`, the active config): 0/6 stations pass.** Worst single-bucket Δ ranges from 13pp (KDEN, KMDW) to 29pp (KLAX). Surprising: `weather_reforecast_v1` clears the bar at **3 of 6 stations** (KDEN +Δ8.4pp, KJFK +Δ9.9pp, KLAX +Δ8.4pp) — the only strategy that passes any station's calibration test, even though it's worse on Brier-vs-NDFD. Calibration ≠ resolution: reforecast NGR is well-calibrated where it has signal but doesn't beat the operational baseline overall. The active strategy still fails, so this criterion remains unmet. |
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
