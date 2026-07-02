# Strategy — scaling forecast-lab into a serious, reliable operation (2026-07-01)

Written the same day the P0 series + P1 wave 1 merged and the honest verdict
landed (0/6 stations clear the Phase 5 #2 bar). Synthesizes the prior research
corpus — [`PASS-1-FEASIBILITY.md`](PASS-1-FEASIBILITY.md),
[`PASS-2-EQUITIES-AGENT.md`](PASS-2-EQUITIES-AGENT.md),
[`RENAISSANCE-DEEP-DIVE-2026-05-08.md`](RENAISSANCE-DEEP-DIVE-2026-05-08.md),
[`THREE-WORKSTREAMS-2026-05-13.md`](THREE-WORKSTREAMS-2026-05-13.md),
[`STRATEGY-PANEL-2026-06-11.md`](STRATEGY-PANEL-2026-06-11.md) — with the
post-sprint state. This is the planning spine for everything after v1
operations; ROADMAP links here.

## 1. Asset/liability statement (honest)

**Assets:** production-grade infrastructure (~1,400 hermetic tests, strict
types, honest metrics, `kq doctor` reality diagnostics, one-command deploy);
the honesty loop itself (audit → adversarial verify → regenerate → gate) —
the 0/6 verdict is this asset *working*; a codified new-market playbook
(probe venue reality → anchor/benchmark → honest backtest → paper gate →
ramp); AI-assisted iteration velocity (2026-07-01: two sprints, ~150 findings
closed, evidence regenerated, in one day).

**Liabilities:** zero proven edge today (weather 0/6 vs NBM on honest lead-1;
NBA never honestly traded); hard capacity ceilings (weather ~$75–105k/day
total notional, $25k/market position limit, $5k moves a bracket); one
operator, one box, one bankroll.

Grade: **A− engineering, incomplete alpha.** Correct build order — but the
hard part starts now.

## 2. Where the edge is (ranked) — and is not

1. **Settlement-window nowcasting** — by 2–3 PM local the daily high is often
   known within ~1°F while brackets lag (Pass-1 §1b, the best-documented
   retail edge). Structural: out-*watching*, not out-modeling. The METAR/OU
   nowcast machinery exists; the work is wiring it into intraday repricing
   and measuring edge specifically in the final ~4 hours.
2. **Execution discipline as alpha** — fees peak 3.5%/side at midprice;
   maker-first + fee-aware Kelly (shipped) + refusing coin-flip prices beats
   most model improvements.
3. **Coverage + always-on automation** — all ladders, all cities, every tick.
4. **Sharp-anchor arbitrage (NBA/NFL)** — never out-predict Pinnacle (>2%
   CLV vs their close is not achievable — Renaissance doc); trade Kalshi's
   divergence from the devigged anchor in specific windows (injury timing,
   early morning, less-watched games at 3–5¢ off).
5. **Meta-edge: iteration velocity with honesty** (see §3).

**Not the edge:** out-forecasting NBM at lead-1+ from public model output
(0/6, proven); LLM-as-predictor (Pass-1 disqualification stands); beating
Pinnacle; anything requiring speed against professional MMs.

## 3. AI/ML doctrine

| Use | Verdict |
|---|---|
| AI as engineering force multiplier (agents building/auditing the system) | ✅ the #1 AI advantage — hypothesis→test→verdict at 10–50× solo speed |
| Small calibration-first ML: LightGBM quantile post-processing (post-500-trades), NBA totals meta-labeling (LightGBM as confidence filter, +0.5–1.5% CLV target), analog ensembles w/ CMA-ES weights | ✅ sanctioned, scoped, benchmarked vs honest baselines |
| LLM as information extractor: NWS Area Forecast Discussion text → structured features; injury news; Fed statements (if econ markets added) | ✅ underused today; extraction only, numbers never reach bet sizing |
| LLM as auditor/ops brain (doctor, adversarial panels, doc sweeps) | ✅ proven 2026-07-01 |
| LLM/deep nets as probability estimator | ❌ permanent (Pass-1 §1d/2c/2f; DRN needs ~100k pairs, we have ~12k) |

Renaissance lesson (deep-dive Part V): the advantage was what they computed,
not FLOPs — discipline, calibration, many small uncorrelated bets, execution.
All replicable on the CPU box. Their non-replicables (leverage structures,
microstructure speed) are explicitly not attempted.

## 4. Phased roadmap

| Phase | Window | Content | Gate |
|---|---|---|---|
| **A — Operate & re-verify** | now → ~8 wks | Box runs regeneration runbook; cron accumulates honest settled trades. Code lane: panel's #1 re-test (reforecast-NGR on GEFSv12 substrate — likeliest verdict flip; the only strategy that ever passed calibration was judged against lead-0 cheaters), contested isotonic verification, ECMWF previous-day coverage, nowcast-window edge study | 200–500 settled; read Brier/reliability/CLV, not P&L |
| **B — Season & categories** | overlap → NBA opening night (late Oct) | Honest CLV pipeline warm for NBA (only vertical that can statistically prove +1pp: 1,230 games/yr); NFL lane (calendar complement, ~110–135 trades/season, W2 window); more weather cities (config-only, capacity-additive). PGA stays shelved (no sharp anchor → CLV undefined) | pre-registered per-category bars |
| **C — Bridge vertical: Kalshi index brackets** | months 2–4 | Panel Seat 3's wedge: S&P/Nasdaq range brackets. HAR-RV as the NDFD-analog benchmark, market-implied distribution as the Pinnacle-analog. Equities-adjacent, still CFTC event contracts — compliance envelope unchanged | same playbook gates |
| **D — Real-money gate** | months 4–9 | Phase 5 criteria on honest evidence; live ramp at 10% bankroll per BANKROLL-PLAN. External prerequisites done FIRST: CPA (§1256), NVIDIA outside-activities disclosure | all 10 criteria |
| **E — Scale decision** | months 9+ | Grow multi-category book ($25–100k working capital) OR productize signals (v3; counsel+LLC) OR bank track record as career capital | evidence, not hope |

**Dollar honesty** (Pass-1 numbers still govern): year-1 on $3–5k: −5% to
+15% most likely. A proven multi-category operation 2+ years out: ~$10–40k/yr
sustained. Capacity-limited by construction — not quit-NVIDIA money. The
compounding assets are the skills, infrastructure, and verifiable calibration
track record.

## 5. Category-expansion playbook (standing)

For ANY new market: (1) live venue-reality probe — payload, semantics,
settlement source (the 2026-06-11 lesson, now codified in `kq doctor`);
(2) identify the anchor (sharp book) or public benchmark (NBM-analog) — no
anchor/benchmark → no honest CLV → shelve (PGA rule); (3) liquidity/fee
check vs Pass-1 thresholds; (4) honest backtest vs the benchmark; (5) paper
gate with pre-registered N and bar; (6) ramp. Ranked queue: NFL → more
weather cities → index brackets → econ indicators (CPI/Fed vs public
nowcasts). Explicitly not: PGA (shelved), elections (no public-data edge),
crypto (non-goal).

## 6. The equities arm — three tiers

1. **Kalshi index/econ brackets** (trade): the honest "stock market arm" v1 —
   same machinery, no securities-law surface. Phase C.
2. **Pass-2 research agent** (inform): briefings/anomaly alerts, never
   recommends or executes; ~$1–2/day. Build per PASS-2 design in v2.
3. **Long-horizon thematic investing** (invest): NOT quant alpha — a
   thesis-driven process with the calibration loop applied. Design:
   [`THESIS-LEDGER-DESIGN.md`](THESIS-LEDGER-DESIGN.md). A stock-picking
   alpha bot remains a non-goal (retail public-data equity "alpha" ≈ beta +
   overfitting; Renaissance doc: retail equities Sharpe >2 claims are
   "almost certainly overfit").

## 7. Standing governance rules

- Venue reality first; CLV/Brier over P&L; pre-registered bars; per-category
  kill criteria; FDR-corrected signal acceptance (Renaissance §8);
  no new deps/fee-model/cap changes without owner sign-off (CLAUDE.md §9).
- Overfit tripwires from THREE-WORKSTREAMS stand: distrust >+2.5% sustained
  CLV, >55% meta-selective hit rate, Sharpe >1.5, >25%/yr.
- Compliance checkpoints before any live dollar: CPA engaged, NVIDIA
  disclosure filed, state availability re-verified.
