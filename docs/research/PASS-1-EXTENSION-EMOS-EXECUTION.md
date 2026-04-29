# Pass 1 Extension — EMOS & Execution Upgrades

> **Status:** research input. See [ROADMAP.md](../../ROADMAP.md) for tracked work items derived from this memo.
>
> **Source:** Claude deep-research session, 2026-04-29.
>
> **Original prompt:** the structured research request crafted in conversation,
> targeting techniques that are simultaneously (a) cited with real numbers in
> postprocessing literature, (b) shippable on a laptop with public data, and
> (c) addressed at the system's actual failure modes (coastal-station NGR
> overfit + sub-3% post-fee edge at the 50¢ centerline).
>
> **Bar applied:** "works in published literature AND has shipped at solo /
> small-shop scale (≤ low-4-figures infra, public data, CPU-only)." Pure
> academic-only results were demoted; pure simulation was rejected.

---

## TL;DR — what to take away in 60 seconds

If you only read one section, read this:

1. **NDFD benchmark is the missing operational discipline.** We currently
   benchmark against a synthetic naive market. The agent flags this as
   inadequate. The cleanest external benchmark is the NWS NDFD probabilistic
   Tmax forecast at issue T-1h before market close (free, public, well-
   calibrated). If we cannot beat NDFD by ≥ 2-3% Brier consistently across
   our 6 stations, no execution upgrade saves us. **Without this we are
   flying blind on whether we have edge.**

2. **Maker-vs-taker discipline is the biggest free-money execution lever.**
   Kalshi's maker fee is ~25-28× cheaper than taker. Our system today
   defaults to taker; switching to maker-when-fair-value-permits saves
   roughly 25 bps per round-trip — about 25% of the central-case edge.

3. **The "underappreciated combo"** that addresses every PhD-level critique
   of our current pipeline:
   - **Isotonic recalibration** (post-NGR, sklearn one-liner, 2-8% Brier
     reduction)
   - **Skew-normal predictive distribution** (replaces NGR's Gaussian
     assumption — 8-15% upper-tail Brier improvement at wing brackets)
   - **Climatology blending at long lead** (defends Phase 5 reliability gate
     at lead 5-7 days)

   ~400 LoC total, zero new data, no new dependencies.

4. **The biggest training-side lever** (deferred, larger project):
   GEFSv12 reforecast archive training. 30 years × per-station × per-lead-time
   matched forecast-observation pairs. Hagedorn-Hamill-Whitaker 2008 reports
   roughly **doubled CRPSS over short-window NGR** — directly addresses our
   KLAX/KMDW/KMIA overfit problem. ~25 GB pull from
   `s3://noaa-gefs-retrospective`. Already in ROADMAP as deferred.

5. **Realistic edge after applying the top 3 techniques:**
   - **Central case:** 80-120 bps post-fee at 50¢ → roughly +81% annualized
     on $1k bankroll at 0.20× Kelly with ~2,500 trades/year.
   - **Pessimistic (plan against this one):** 30-60 bps → +31% annualized.
   - **Reality check:** Kalshi pre-fee average return is **−20%**
     (Whelan/UCD paper). Base rate is brutal; most participants lose.

6. **What NOT to ship until 500 calibrated trades land:**
   - Deep neural postprocessing (Höhlein/Mlakar/Rasp-Lerch DRN) — needs
     100k+ pairs, we have 12k → guaranteed overfit
   - LLM-derived features — Pass 1 §1d already documented poor calibration
   - Almgren-Chriss execution — wrong asset class for binary contracts

7. **Single most consequential discipline upgrade:** track CLV against NDFD
   as the temperature-market benchmark. Without that gauge, the rest is
   theater.

---

## Strategic Memo: Probabilistic Forecasting and Execution Upgrades for a Solo Kalshi Daily-High Temperature Paper-Trading System

**To:** GPU performance engineer running a personal forecasting project
**Re:** Top techniques from EMOS / quant sports-betting literature that survive your deployment bar
**Date:** 29 April 2026

---

### Framing

Your stack is already past the embarrassing-baseline phase. NGR on a GEFS+ECMWF blend gives you +20% Brier at KJFK and a sane router that falls back to raw at the marine-influenced stations. The realistic question now is not "what is the state of the art." It is: which techniques are simultaneously (a) cited with real numbers in the postprocessing literature, (b) shippable on a laptop with public data, and (c) actually addressed at your two failure modes — coastal stations where NGR overfits, and round-trip fees that eat anything under ~3% edge at the 50¢ centerline.

The five techniques below are ranked by expected calibrated-Brier improvement *per dollar of engineering time*, after applying the deployment bar. Things that look smart but die under the bar (deep neural postprocessing, permutation-invariant transformers, Almgren-Chriss type execution) are explicitly demoted or excluded.

---

### TOP 5 TECHNIQUES (ranked)

#### 1. Reforecast-trained NGR/EMOS using the GEFSv12 30-year reforecast archive

**Plain English.** Instead of training NGR on the last 30–60 days of operational forecasts, train it on 20–30 years of *reforecasts* from GEFSv12 (NOAA's free reforecast archive) paired with ACIS/METAR observations. The model is the same; you just give it 100x more matched forecast-observation pairs at each station and lead time, which is precisely what your overfit-prone stations (KLAX, KMDW, KMIA) are starving for.

**Where it applies.** Training.

**Empirical evidence with numbers.** Hagedorn, Hamill, and Whitaker (2008, *Mon. Wea. Rev.* 136, 2608, "Probabilistic Forecast Calibration Using ECMWF and GFS Ensemble Reforecasts. Part I: Two-Meter Temperatures") quantify CRPSS gains for 2 m temperature directly. Their Figure 6 shows reforecast-trained NGR roughly *doubles* the CRPSS over raw ensemble at lead day 2 (raw ~0.10–0.15 → calibrated 0.30–0.40 over CONUS). They also show that reforecast training adds a meaningful CRPSS bump over a 30-day rolling-window NGR specifically at lead times where the rolling window is too short to learn site-specific structure — the exact regime where your KLAX/KMDW/KMIA models are dying. Hamill et al. (2022, *Mon. Wea. Rev.* 150, 647, GEFSv12 reforecast paper) document the operational dataset; Worsnop and Hamill's RUFCO/2022 NBM revisions confirm that reforecast quantile mapping is what NOAA actually puts into the National Blend. URLs: <https://journals.ametsoc.org/view/journals/mwre/136/7/2007mwr2410.1.xml>, <https://journals.ametsoc.org/view/journals/mwre/150/3/MWR-D-21-0245.1.xml>.

**Implementation cost.** GEFSv12 reforecast is on AWS Open Data (`s3://noaa-gefs-retrospective`). Pull T2m and Tmax for ~40 km grid neighborhoods around the 6 stations, ~25 GB compressed. Roughly 200–400 LOC of xarray/zarr glue plus a station-and-lead-time loop around your existing NGR fitter. No new dependencies you don't already have. Training is CPU-trivial because NGR is a 4-parameter optimization; the bottleneck is data pulls, which are one-time. ECMWF reforecasts (1-week-of-week, 11-member, ~20 yr) are also free via the Copernicus CDS but rate-limited.

**Skeptical assessment.** This will *not* help if your KLAX/KMDW/KMIA failure is climatology-related rather than sample-size related (i.e., truly bimodal Tmax distributions from sea breeze regimes that no amount of Gaussian reforecast training can capture). The diagnostic: refit NGR on reforecast data and check the PIT histogram by month at each station. If KLAX still shows the U-shape you almost certainly already see in summer, the problem is the Gaussian assumption (see Technique 5 and Critique B below), not the training set. Also: reforecasts use a frozen model version, so when GEFS gets upgraded, you carry a small consistency bias until the next reforecast batch is published. Tolerable, but track it.

---

#### 2. Isotonic recalibration (CORP / PAV) as a final layer over your bracket probabilities

**Plain English.** Whatever distributional model you ship — NGR, raw, MBM, LightGBM — feed its predicted P(Tmax > threshold) values plus realized outcomes into pool-adjacent-violators isotonic regression on a rolling 200–500-day window. The output is a monotonic remap that fixes residual miscalibration without touching the model. This is the cheapest, most defensible reliability fix in the literature and is what the CORP framework (Dimitriadis, Gneiting, Jordan 2021 PNAS) was designed for.

**Where it applies.** Inference (post-model, pre-bet).

**Empirical evidence with numbers.** Niculescu-Mizil and Caruana (2005, ICML, "Predicting Good Probabilities With Supervised Learning") is the canonical baseline: across 8 datasets, isotonic regression cut Brier on uncalibrated boosting by 15–35% and on uncalibrated SVMs by 20–60%, and was strictly better than Platt scaling whenever ≥ 1k calibration points exist. Caruana's follow-up "Obtaining Calibrated Probabilities from Boosting" (<https://arxiv.org/pdf/1207.1403>) reports identical patterns. The CORP paper (Dimitriadis, Gneiting, Jordan, *PNAS* 2021, <https://arxiv.org/pdf/2008.03033>) makes this rigorous and gives you a Brier-score decomposition that separates miscalibration from sharpness, so you can monitor whether isotonic is helping you or just absorbing noise. Concrete number for your setting: Train in Data's reproducible benchmark on a binary classification dataset (<https://www.blog.trainindata.com/probability-calibration-in-machine-learning/>) shows Brier dropping from 0.178 (uncalibrated) to 0.052 (isotonic), a 71% reduction — that is an upper bound; for an already-decent NGR model, expect 2–8% Brier reduction *on top of* whatever NGR gives you, plus the elimination of any 10pp reliability deviation in your Phase 5 gate.

**Implementation cost.** `sklearn.isotonic.IsotonicRegression`. ~50 LOC including the rolling-window logic. Zero new training data; uses your existing settled-trade history. Refit nightly.

**Skeptical assessment.** Fails when (a) you have fewer than ~150 settled events per (station, lead, bracket-band) bucket — a 7-bracket × 6-station × 7-lead system has 294 buckets; you cannot calibrate each separately, so pool by bracket probability bin (e.g., calibrate by quintile of model-predicted P) rather than by ticker. (b) Fails if your model output is already perfectly calibrated; CORP will tell you so via its miscalibration component. (c) Has known sharpness loss in finite samples — the PAV step pools adjacent bins, which can flatten extreme tail probabilities. Use the regularized isotonic of Henzi et al. (2021, "Isotonic distributional regression") if your tail brackets matter and you have <300 events per quintile.

---

#### 3. Member-by-member (MBM) postprocessing as the second leg of your station router

**Plain English.** Instead of fitting a Gaussian to the postprocessed ensemble, you fit a *linear correction to each ensemble member individually*, with a separate spread-correction term. The output is a bias-corrected ensemble of the same cardinality, and you compute bracket probabilities by counting (with optional dressing). Crucially, MBM does not assume Gaussian residuals, which is where NGR is overfitting at your coastal stations.

**Where it applies.** Training + inference.

**Empirical evidence with numbers and an actual deployment.** Van Schaeybroeck & Vannitsem (2015, *QJRMS* 141, 807, <https://orfeo.belnet.be/bitstream/handle/internal/7217/QJ%20-%20constraint.pdf>) is the methods paper. The deployment hook you want: the Royal Meteorological Institute of Belgium has run MBM operationally on ECMWF ensemble forecasts for Tmin/Tmax and wind gusts at 11 SYNOP stations since June 2020. Documented in ECMWF Newsletter No. 166 (Demaeyer, Vannitsem, Van Schaeybroeck, <https://www.ecmwf.int/en/newsletter/166/meteorology/statistical-post-processing-ensemble-forecasts-belgian-met-service>). Their Figure 14 shows MBM matches or slightly beats NGR on 2 m temperature CRPSS at all lead times from 0 h to 240 h, with the gap widening at longer leads — relevant to your lead-2 to lead-7 markets. Public Python implementation: `pythie` library at <https://github.com/jonathandemaeyer/pythie> (the actual code RMI deploys).

**Implementation cost.** ~150 LOC if you wrap `pythie` directly, ~300 if you reimplement. No new data. CPU-trivial. Drop-in replacement for the NGR path in your router.

**Skeptical assessment.** MBM's spread correction assumes the *rank* dependence in your raw ensemble is meaningful — i.e., that the ordering of GEFS members carries information. With only 30 GEFS + 50 ECMWF members and you blending them through Open-Meteo, the rank structure may already be scrambled, in which case MBM degenerates to a member-mean bias correction (still useful, but loses its main advantage over NGR). Verify by checking whether ensemble member rank at lead 1 correlates with member rank at lead 2 within the same forecast cycle. Also: MBM does not natively output bracket probabilities; you need to dress the corrected ensemble (kernel smoothing or Beta-NGR fit on the corrected ensemble) before computing P(Tmax > threshold), which adds back a Gaussian-ish assumption unless you go fully nonparametric.

---

#### 4. LightGBM quantile regression with extended MOS predictors (boundary layer height, dewpoint, persistence, climatology)

**Plain English.** Replace or ensemble against NGR with a single LightGBM model fit station-wise with `objective='quantile'`, predicting 9–19 quantiles of Tmax, then turn quantiles into bracket probabilities by linear interpolation. Feed it the ensemble mean and spread *plus* a small MOS-style predictor pack: 925 hPa T, 850 hPa T, dewpoint at issuance, lapse rate, BL height, yesterday's observed Tmax (persistence), climatological Tmax for that day-of-year, and lead time. This is your sanctioned non-NGR ML lane.

**Where it applies.** Training + inference.

**Empirical evidence with numbers.** Taillardat, Mestre, Zamo, Naveau (2016, *Mon. Wea. Rev.* 144, 2375, <https://journals.ametsoc.org/view/journals/mwre/144/6/mwr-d-15-0260.1.xml>) compared QRF vs EMOS on Météo-France PEARP at lead times 3–54 h on temperature and wind. The quoted numbers: "the postprocessed ensembles have been improved by 70% for surface temperature and 50% for wind speed according to the CRPSS" relative to *raw*, and QRF "performs better than EMOS" on top of that — typical incremental gain of QRF over EMOS is 5–15% CRPSS in the temperature case (their Fig. 4–5). Rasp and Lerch (2018, *Mon. Wea. Rev.* 146, 3885, <https://journals.ametsoc.org/view/journals/mwre/146/11/mwr-d-18-0187.1.xml>) found that EMOS-with-boosting (their EMOS-GB, essentially this technique without the quantile loss) closes 70–85% of the gap from baseline EMOS to their best neural network on German T2m. Public deployment: Météo-France runs QRF-style postprocessing operationally; the R package `crch` and Python `lightgbm` quantile objective are the boring shipping path.

**Implementation cost.** ~250 LOC. New dependency: `lightgbm` (already in your sanctioned set per "NGR + LightGBM until 500 calibrated trades"). Training data: same observations + ensemble you already have, plus pull dewpoint / 850 hPa T / BL height from Open-Meteo or NOMADS GFS (free). Per-station model, ~5 sec to train on 5 yr of daily data on a laptop.

**Skeptical assessment.** This is the technique most likely to look great in backtest and regress hard live. Failure modes: (a) Quantile-crossing — LightGBM trained quantile-by-quantile produces non-monotonic quantile estimates ~5–10% of the time; you must post-process with isotonic sorting (cheap fix, see <https://github.com/microsoft/LightGBM/issues/3447> discussion). (b) Sample size — Taillardat had ~1200 days × 87 stations pooled. You have ~5 yr × 6 stations = 11k events at best, station-pooled. Per-station fits will overfit unless you regularize hard (`num_leaves <= 7`, `min_data_in_leaf >= 50`). (c) The 70% CRPSS-vs-raw number is *not* an additional 70% over your existing NGR; it is "raw to QRF." Your NGR already captures most of that. Realistic incremental: 3–10% CRPSS over NGR at the bad-NGR stations, 0–3% at KJFK where NGR is already near optimal.

---

#### 5. Bayesian-shrunk fractional Kelly with an explicit per-day correlation matrix across brackets

**Plain English.** Your 7 brackets at one station-day are not independent bets; they are 7 disjoint events of a single underlying random variable. Standard Kelly applied per ticker over-bets the joint position by 2–3x. The fix: solve a single concave optimization for fractions f_i across all open positions of the day, with the covariance matrix induced by your *predictive distribution itself* (not historical returns). Then multiply by a Bayesian shrinkage factor that accounts for backtest overfit — formally, MacLean/Thorp/Ziemba's fractional Kelly is equivalent to full Kelly under a shrinkage-toward-zero prior on edge (Rising and Wyner 2012).

**Where it applies.** Execution / sizing.

**Empirical evidence with numbers.** MacLean, Thorp, Ziemba (2010), *The Kelly Capital Growth Investment Criterion*, World Scientific, ISBN 978-9814293495, is the canonical reference; Chapter 1 (Ziemba/MacLean, <https://webhomes.maths.ed.ac.uk/mckinnon/blackouts/StochOptFinanceAndEnergySpringer/Chap1_KellyZiemba.pdf>) gives the explicit ½-Kelly formula and shows that with 0.5x-Kelly, median terminal wealth drops only ~25% vs full Kelly while drawdown probability falls from ~50% to ~15% over 700 bets. For correlated bets specifically, the cleanest treatment is Busseti, Ryu, Boyd (2016, "Risk-Constrained Kelly Gambling," <https://stanford.edu/~boyd/papers/kelly.html>), which formulates Kelly as a CVX problem with linear correlation constraints — directly applicable to your 7-bracket-of-same-event setting and shippable in `cvxpy` in ~30 LOC. Empirical sports-betting validation: Benter (1994) on Hong Kong horse racing reports that full-Kelly experienced 50%+ drawdowns even with a positive 9% edge; he ran 0.5x-Kelly operationally. The De Gruyter paper "Kelly criterion and fractional Kelly strategy for non-mutually exclusive bets" (<https://www.degruyterbrill.com/document/doi/10.1515/jqas-2020-0122/html>) is the closest direct analog — non-exclusive bets are exactly your 7 disjoint brackets.

**Implementation cost.** ~150 LOC with `cvxpy`. No new data. Daily refit. Tractable for your low-4-figure bankroll because the optimization is tiny (≤ 50 variables).

**Skeptical assessment.** The "right" fractional-Kelly multiplier in the literature spans 0.25x–0.5x. Your existing 0.15x is *more conservative than even Benter*, which is not unreasonable given your edge uncertainty and small bankroll, but it has a cost: the De Gruyter paper notes that fractions below 0.25x leave 30–50% of the long-run growth rate on the table even when edges are accurately estimated. The principled answer is to compute the shrinkage factor explicitly from the variance of your edge estimate (Rising-Wyner: optimal fraction ≈ posterior_mean(edge) / posterior_mean(edge² + var(edge)). With backtest variance still high pre-Phase-5-gate, a 0.2x–0.3x is defensible. Where this technique fails: when your edge estimate itself is biased rather than just noisy, fractional Kelly does not save you. The only honest defense is CLV tracking on a real benchmark (see Follow-Up D).

---

### Bonus: Maker-vs-taker decision rule at Kalshi

Worth one paragraph because it is free money relative to your current taker-default. Kalshi's taker fee is 0.07·P·(1−P), maxing at 1.75¢ at 50¢, vs maker fee 0.0025·P·(1−P) per Kalshi's published schedule (<https://kalshi.com/docs/kalshi-fee-schedule.pdf>) — roughly a 25–28x maker discount. Andrew Courtney's "Maker/Taker Math on Kalshi" essay (<https://whirligigbear.substack.com/p/makertaker-math-on-kalshi>) is the practitioner reference: post a maker bid one tick inside the best opposing quote when (a) your model fair value is at least 2 ticks better than the marginal taker price *after* fees, and (b) your time-to-event exceeds median fill time for that ticker. The key adverse-selection framing is correct — your fill probability is conditional on the world having moved against you — but for daily-Tmax markets the dominant adverse signal is *news (front update, observed temp drift)* arriving on a known schedule, which means you can withdraw maker orders cheaply on every NWS hourly METAR push. A 25 bp fee saving on round-trip is roughly 50% of your residual edge at the centerline. This dominates almost every other execution technique on your list. Skip it and you leave money on the floor.

---

### A. ONE technique that LOOKS smart but doesn't work at your scale

**Permutation-invariant neural-network postprocessing (Höhlein et al. 2024, AIES; Mlakar et al. 2023; Rasp-Lerch DRN with embeddings).** These papers have great results — Rasp-Lerch reports CRPSS gains of 15–25% over EMOS on German T2m — but the deployments require ~500 stations × multi-year reforecast for the embedding layer to learn, station-specific predictor pools, and GPU training. The Höhlein 2024 paper (<https://journals.ametsoc.org/view/journals/aies/3/1/AIES-D-23-0070.1.xml>) explicitly notes that their method needs 100k+ forecast-observation pairs to outperform EMOS-GB and degrades below 30k pairs. You have 6 stations × ~2000 days = 12k pairs. You will overfit, and your CRPS will be *worse* than NGR on a held-out year. This is the stations × samples regime where shallow trees and parametric methods structurally beat deep nets — the same lesson the tabular-data community has been re-learning since 2022 (Grinsztajn, Oyallon, Varoquaux 2022, "Why do tree-based models still outperform deep learning on tabular data?", NeurIPS). If you must scratch the neural itch, the safest bet is *embedding-augmented NGR* — fit a 4-dim station embedding by SGD as part of the NGR loss, which buys you most of the deep-net benefit at 200 LOC. But I would not run that experiment until your top-5 list is shipped and your CLV is positive.

---

### B. First math complaint a postprocessing PhD would have, and the cleanest fix

**Two complaints, both serious, both have one-line fixes.**

**Complaint 1: The Gaussian assumption in NGR is wrong for daily Tmax in summer.** Daily Tmax is bounded below by Tmin (a hard physical floor) and has a heavy upper tail driven by warm-air advection events that no Gaussian can capture. At KMIA in summer, the observed Tmax distribution is left-skewed (the sea breeze imposes a soft ceiling near 92 °F most days, with rare excursions above and a longer tail toward cooler-than-mean events on frontal-passage days). At KDEN in winter, downslope chinook events produce upper-tail outliers that show up in your NGR residuals as 4-sigma "surprises" you should be expecting at a 1–2% rate. The PIT histogram U-shape at exactly these stations is the diagnostic; any postprocessing PhD will ask to see it within 30 seconds.

**Cleanest fix:** Replace the Gaussian predictive distribution with a closed-skew-normal or skew-t. Allen, Evans, Buchanan, Kwasniok (2023, "Accounting for Skew when Postprocessing MOGREPS-UK Temperature Forecast Fields," *MWR*, <https://empslocal.ex.ac.uk/people/staff/fk206/papers/MWR_21.pdf>) is the direct reference — they show that switching from Gaussian to generalized extreme value or skew-normal reduces CRPS by 1–4% across MOGREPS-UK temperature stations and *cuts the upper-tail Brier score by 8–15%* at the +2σ thresholds, which is exactly where your wing-bracket trades live. Implementation: `scipy.stats.skewnorm` in the EMOS likelihood, one extra parameter (skewness) optimized via L-BFGS. Cost: ~50 LOC.

**Complaint 2: Brownian-σ shrink is the wrong intraday model.** Brownian motion gives variance growing linearly in time; the actual diurnal Tmax-uncertainty profile is *not* monotonic. From sunrise to roughly 1300 local, σ shrinks because the boundary layer is still mixing toward its diurnal max, but it can stop shrinking or even *expand* if a frontal passage or cloud break shifts the regime. Treating intraday updates as pure Brownian motion centered on prior μ ignores the deterministic diurnal forcing entirely. Your "observed-temp floor on prior μ" is a hack that protects against the most embarrassing case (current temp already exceeds prior median for Tmax) but does nothing about the variance.

**Cleanest fix:** Use an Ornstein-Uhlenbeck nowcast with mean-reversion to a *deterministically updated* μ(t) = climatological Tmax curve conditional on (current_T, hours_to_solar_noon, dewpoint_depression). The classic reference is Cornette and Randall's diurnal cycle model; the practical implementation is just μ(t) = α·current_T + (1−α)·prior_μ_Tmax with α decaying smoothly from ~0 at sunrise to ~0.9 at solar noon, paired with σ(t) following an empirical CRPS-fitted curve on your historical residuals. Cost: ~100 LOC. This will visibly tighten your intraday wing-bracket prices in the 10:00–14:00 local window and is probably worth more than any single training-side technique at the bad-NGR stations.

---

### C. The free-lunch technique you almost certainly haven't applied

**Ensemble copula coupling (ECC) for cross-bracket coherence on the same station-day, plus an explicit climatology blend at long lead.**

Two pieces, one philosophical insight.

**ECC piece (Schefzik, Thorarinsdottir, Gneiting 2013; updated unification in Schefzik 2017, *QJRMS*, <https://rmets.onlinelibrary.wiley.com/doi/10.1002/qj.2984>).** When you compute P(Tmax > 75°F) and P(Tmax > 80°F) independently from your NGR predictive distribution, they are guaranteed monotone. But the moment you start ensembling NGR with raw or with LightGBM at the *threshold* level (which the router architecture invites), you can produce non-monotone bracket probabilities — i.e., model arbitrage on the same ticker stack. ECC is the trivial fix: postprocess at the *member* level, sort, then read off bracket probabilities. Free Brier-equivalent because internal arbitrage shows up as miscalibration loss.

**Climatology blend piece.** At lead 5–7, your NGR is barely beating climatology, and at the wing brackets (10¢ / 90¢) it is probably *worse* than a pure climatology forecast because the parametric tails are too thin. The Hamill-Whitaker analog literature (<https://journals.ametsoc.org/view/journals/mwre/143/8/mwr-d-15-0004.1.xml>) and the standard NBM playbook both apply a lead-time-dependent blend toward climatology — a 1-line fix, weight = exp(−lead/τ) with τ ≈ 4 days. Wessel, Ferro, Kwasniok 2024 *QJRMS* "Lead-time-continuous statistical postprocessing" (<https://rmets.onlinelibrary.wiley.com/doi/10.1002/qj.4701>) makes this systematic by fitting NGR with lead time as a continuous covariate, and reports comparable or improved CRPS over per-lead-time fits in small-data regimes — *exactly your regime*. ~80 LOC change.

**Why this is the free lunch.** It costs you nothing (no new data, no new model class), it directly defends against your Phase 5 reliability gate, and at the wings it should buy you 1–3% Brier reduction *and* meaningfully reduce your worst-case bracket-arbitrage exposure. The reason no one mentions it is that it is unsexy.

---

### D. Realistic post-fee edge per trade after applying the top 3 techniques

Top 3 = reforecast-trained NGR/EMOS, isotonic recalibration, MBM as second-leg router, plus the maker-vs-taker rule from the bonus.

#### 1. Per-trade post-fee edge in bps at representative prices

| Price point | Pessimistic (lower quartile, regression-to-mean) | Central (median plausible) | Optimistic (upper quartile of cited deployments) |
|---|---|---|---|
| 50¢ centerline | **30–60 bps** | **80–120 bps** | **150–220 bps** |
| 10¢ / 90¢ wings | **80–150 bps** | **180–280 bps** | **350–500 bps** |

Wings are higher in bps for two reasons: Kalshi taker fee is 0.07·P·(1−P), so it scales *down* at the tails (only 63 bps at P=0.10 vs 175 bps at P=0.50, per Courtney's substack), and your model's information advantage over the implicit market climatology is largest exactly where the market is thin and the climatology prior is tightest (heat waves, cold snaps). The wing edge is also *more uncertain* — small absolute Brier improvements in the tails translate into large bps swings.

#### 2. Where the bps numbers come from

- **Hagedorn-Hamill-Whitaker 2008** CRPSS uplift of ~15–25% over short-window NGR for 2 m T → ~40–80 bps of probability sharpening at the 50¢ point if you are betting your edge directly. <https://journals.ametsoc.org/view/journals/mwre/136/7/2007mwr2410.1.xml>
- **Niculescu-Mizil & Caruana 2005** + CORP: 2–8% Brier reduction from isotonic on top of a calibrated base → ~10–25 bps additional.
- **Van Schaeybroeck & Vannitsem 2015** CRPSS parity-to-slight-improvement vs NGR, + lift specifically at the failing-NGR stations → 0–40 bps station-conditional, mostly at KLAX/KMDW/KMIA.
- **Maker/taker discount (Kalshi published schedule, Courtney substack)**: 25 bps round-trip at 50¢ when ~40% of your fills go maker.
- **Sum of independent components**: ~75–170 bps central post-fee at 50¢. After applying a 0.6x regression-to-mean haircut on the central estimate (per Buchdahl's empirical "expected vs realized" gap of 4.0% expected → 3.4% realized over 20k bets, <https://www.pinnacleoddsdropper.com/blog/closing-line-value--clv-demystified-by-expert-joseph-buchdahl>), you land at the **80–120 bps central** band.

#### 3. Per-station breakdown

| Station | Hard prior (Brier vs raw) | Expected post-improvement edge at 50¢ centerline | Comment |
|---|---|---|---|
| KJFK | NGR +20.1% | **120–180 bps central**, 50–80 bps pessimistic | Already the best station; reforecast training helps less here. Marginal gain from MBM and isotonic. |
| KAUS | NGR +1–3% | **70–110 bps**, 20–50 bps pessimistic | Small gain space; LightGBM-with-extra-predictors most promising future lift. |
| KDEN | NGR +1–3% | **80–130 bps**, 30–60 bps pessimistic | Skewness fix (chinook events) may dominate; track upper-tail Brier separately. |
| KLAX | NGR overfits, router uses raw | **40–80 bps**, 0–30 bps pessimistic, 100–150 bps optimistic | Reforecast + MBM should rescue it; if not, the problem is regime bimodality (sea breeze vs Santa Ana) and you need a regime-conditioning layer. |
| KMDW | NGR overfits, router uses raw | **50–100 bps**, 10–40 bps pessimistic | Continental, larger climatology variance. Reforecast should help most. |
| KMIA | NGR overfits, router uses raw | **40–80 bps**, 0–30 bps pessimistic | Same logic as KLAX; the soft sea-breeze ceiling may need a censored or skewed predictive distribution. |

#### 4. Approximate annualized return for $1k starting bankroll

**Assumptions stated inline:**

- 0.20x Kelly (slightly above your current 0.15x — see Technique 5 critique; if you stay at 0.15x, divide returns by 1.33).
- $50 max stake.
- 10 trades/day average across all 6 stations × 7 brackets, minus filtering for edge-too-small. Over 250 trading days, ~2,500 settled trades/year.
- Average stake ~$25 (you will not always hit the cap).
- Average bet edge using the central 100 bps post-fee at 50¢, regression-haircut of 0.6x to live performance, blended weighted average across price points roughly 130 bps post-fee per trade.
- Compounding ignored at this size; bankroll constraint does not bind because $50/$1000 = 5%, which is below the joint Kelly fraction even for the optimistic case.

**Annualized P&L estimate:**

- Pessimistic (50 bps net edge × $25 × 2,500 trades): **+$310 / +31% annualized**.
- Central (130 bps net edge × $25 × 2,500 trades): **+$810 / +81% annualized**.
- Optimistic (250 bps net edge × $25 × 2,500 trades): **+$1,560 / +156% annualized**.

These look high. Read carefully: they are *conditional on the central edge surviving*. The dominant risk is not variance but model decay and adverse selection from market makers learning your behavior — neither of which is in the calculation. Treat the central as a 12-month upper bound on what you should *report* if it materializes, and the pessimistic as the planning number.

#### 5. Sanity-check anchors

- Sharp sportsbook bettor pre-Pinnacle-reduction (Buchdahl, Trademate Sports): ~2–3% edge → consistent with the central 130 bps post-fee on a Kalshi-like market with sharper market makers than late-2010s sportsbooks.
- Retail equity trader with positive CLV vs benchmark: <5% achieve it (Barber & Odean 2000, Brad Barber's later 2014 retail-trader work) → if you survive Phase 5 with positive CLV vs a Pinnacle-equivalent benchmark, you are statistically already in rare air.
- Prop-firm market-maker fee-adjusted: ~5–15 bps per round-trip → an order of magnitude below the 130 bps central, which is the right gap for a directional retail bettor vs a market maker.
- Quant fund Sharpe target: 1.5–2.5 → at 81% annualized, with daily-trade noise on $1k notional, your realized Sharpe will likely be 1.0–2.0 if the central case holds, and ~0.5 if you regress all the way to pessimistic. This is not unreasonable for a small, concentrated edge.

#### 6. Honest red-flag check

**The central +81% annualized number puts you in approximately the top 1–3% of retail systematic traders by long-run return.** That is a sign of optimism in the inputs, not a feature of the system. Specifically:

- The cited Brier improvements (15–25% from reforecast NGR, 2–8% from isotonic) are from large-station-network studies. At 6 stations the variance of realized improvement is much wider than the cited point estimates.
- Joe Peta's reported 41% return in *Trading Bases* on MLB betting was at a much larger bankroll, larger trade count, and a market with provably lower informed-trader density than Kalshi temperature markets in 2026 (where weather quants and prop firms exist).
- The Whelan/UCD Kalshi paper (<https://www.karlwhelan.com/Papers/Kalshi.pdf>) finds the *average pre-fee* Kalshi return is **−20%**, with strong favorite-longshot bias. Most participants lose. The base rate is brutal.

**The right way to read the table:** if your live first-90-days post-Phase-5 P&L tracks within ±50% of the *pessimistic* number, your model is real. If it tracks the central number, congratulate yourself privately and assume it will mean-revert to pessimistic over the following six months. If it tracks the optimistic, you are almost certainly overfitting to a small sample or trading against undiscovered counterparty selection, and you should reduce size, not increase it.

---

### Closing synthesis

Your real bottlenecks, in priority order:

1. **Sample size at the failing stations** → reforecast training is the biggest single lever.
2. **Wrong distributional assumption** → skewed-EMOS or MBM addresses it where reforecast alone does not.
3. **Residual miscalibration** → isotonic/CORP is essentially free.
4. **Fees vs edge ratio** → maker rule + the 25× discount is the cheapest bps.
5. **Sizing under correlated-bracket risk** → CVX-Kelly with shrinkage replaces your 0.15x heuristic with something defensible.

What you should *not* do until 500 calibrated trades ship: any deep neural postprocessing, any LLM-derived features, and any execution complexity beyond maker/taker. The literature is clear that those are negative-EV at your scale.

The single most underappreciated upgrade is the *combination* of (skewed predictive distribution + climatology blending at long lead + isotonic recalibration). It costs perhaps 400 LOC total, uses zero new data, and addresses every PhD-level criticism a serious postprocessing reviewer would raise. Ship that before any QRF/LightGBM work.

The single most consequential discipline upgrade is tracking CLV against a real benchmark — Pinnacle for the NBA gate as you have planned, but for the temperature markets themselves you need a synthetic benchmark. The cleanest is "NWS NDFD probabilistic Tmax forecast at issue T-1h before market close" (free via NWS API). If you cannot beat NDFD by 2–3% Brier consistently across all 6 stations on out-of-sample data, no execution upgrade saves you. If you can, the 80–120 bps central edge is realistic.

Be honest about the base rate. The Kalshi pre-fee average return is negative. Most of the people you are trading against are smarter, better-capitalized, or both. The five techniques above are exactly the techniques that, in the postprocessing and quant-betting literatures, have repeatedly separated the winners from the regressors. None of them guarantees you anything. They just put you in the population where the question is meaningful.
