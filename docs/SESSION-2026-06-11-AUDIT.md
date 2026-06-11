# Session audit — 2026-06-11 (REALITY CONTACT: full-fleet code audit)

Multi-agent distinguished-engineer audit (8 subsystem deep-reviews + adversarial
verification + direct evidence probes against the live Kalshi prod API and the
committed manifests). Supersedes the rosy "clean waiting-on-operations resting
state" verdict of [`2026-05-26`](SESSION-2026-05-26-AUDIT.md) /
[`2026-05-30`](SESSION-2026-05-30-AUDIT.md).

## Headline — the paradox

**Code hygiene is best-in-class. Reality contact is broken.**

- 1,101 tests green, mypy --strict clean (117 files), ruff clean, money path
  mutation-tested (82% kill), suite hermetic. Every conventional quality gate passes.
- And yet: **neither vertical can currently place a paper trade on prod**, the
  Phase 2 backtest evidence is **invalid**, the Phase 5 #5 gate metric is
  **mathematically biased toward passing**, and the NY pipeline models **the
  wrong physical station**.

Every defect cluster sits at the boundary between the code and the real world:
prod API payload formats, actual contract semantics, the actual settlement
station, actual data lead times, the actual metric definition. The 1,101 tests
pass because they all mock a reality that does not exist. **The lesson for every
future vertical: verify the venue's reality FIRST (payload, semantics, settlement
source), then build.**

## How this audit was run

1. 8 parallel deep-review agents, one per subsystem (money path, backtest+leakage,
   calibration/stats, sports math, flows/timezone, clients, storage, ops/dashboard).
2. Adversarial 3-lens verification panels per finding (code-trace, test-contradiction,
   production-impact). Rate limits cut verification short; 2 findings fully panel-confirmed.
3. **Direct evidence verification by the lead** for the 11 root causes below:
   live `curl` probes of `api.elections.kalshi.com` public market endpoints,
   committed-manifest arithmetic, and line-level code reads. These are not
   agent claims; each was confirmed against primary evidence.

## Confirmed root causes (direct evidence)

### A. Production blockers — nothing can trade

| # | Finding | Evidence |
|---|---------|----------|
| 1 | **Kalshi market parser reads retired integer-cent fields (`yes_bid`, `yes_ask`, `last_price`); prod returns `*_dollars` strings (`yes_bid_dollars: "0.0500"`). All prod prices parse as `None` → `evaluate_market` skips every market.** The weather vertical silently cannot trade; cron looks green. | Live prod payload for `KXHIGHLAX-26JUN11-T79` vs [`_parsers.py:15-31`](../src/kq/clients/kalshi/_parsers.py). Prod also returns `open_interest_fp`/`volume_fp` (strings), not the fields we read. Orderbook endpoint likewise moved to `orderbook_fp` dollar-string ladders (agent-verified). |
| 2 | **4 of 6 open weather brackets per station are `-B<x>.5` between-markets — invisible to the ticker regex (`-T<int>` only).** The B-markets are the *center* brackets, where most volume and most model edge lives. | Live prod: KXHIGHLAX open book = `T79`(greater), `T72`(less), `B78.5`, `B76.5`, `B74.5`, `B72.5`. Regex at [`_ticker_parser.py:50-52`](../src/kq/clients/kalshi/_ticker_parser.py). |
| 3 | **Low-tail `-T<n>` markets are `strike_type: less` (YES = below cap), but the parser treats every `-T<n>` as greater → trade evaluation AND settlement would be exactly inverted.** Currently masked by #1 (no prices → no trades). If #1 were fixed without this, the system would start placing inverted bets and settling them backwards. | Live prod: `KXHIGHLAX-26JUN11-T72` has `strike_type: "less"`, `cap_strike: 72`, title "71° or below". Parser has no strike_type concept. |
| 4 | **KXHIGHNY settles on CENTRAL PARK (KNYC), not JFK.** Our entire NY pipeline — Open-Meteo forecasts, METAR, NGR training, ACIS truth, settlement — is keyed to KJFK. Central Park vs JFK differ by several °F on sea-breeze/marine-layer days. We are modeling the wrong physical location for one of six stations. | Live prod `rules_primary`: "the highest temperature recorded in **Central Park, New York** ... as reported by the National Weather Service's Climatological Report (Daily)". (`KXHIGHCHI` = Midway ✓ matches us.) |
| 5 | **NBA flow sees 0 markets on prod**: `list_markets(status="open")` fetches ONE unpaginated page of 200 arbitrary markets across all of Kalshi (no cursor handling exists anywhere in the client), then filters client-side. Verification panel probed prod live: first page (even at limit 1000) contains zero `KXNBAGAME` markets while `series_ticker=KXNBAGAME` returns active Finals markets. PR #97 fixed exactly this for weather; NBA was missed. | Panel-confirmed 3/3 incl. live API probe. [`paper_nba_trade.py:318-334`](../src/kq/flows/paper_nba_trade.py), [`client.py:81-105`](../src/kq/clients/kalshi/client.py). |
| 6 | **NBA flow trades BOTH per-side tickers of each game** (Kalshi lists YES-home and YES-away markets per game): doubled Kelly exposure per game and double-counted settled trades toward Phase 5 #1/#5. | Panel-confirmed 2/2. No per-game dedup in the submit loop. |
| 7 | **Weather settlement can never fire: no scheduled ingest of observed truth.** `docs/SCHEDULED-RUNS.md` has a 16:00 UTC settle pass but no cron entry ingesting `weather_observed` (ACIS). Truth is ~a year stale on the box. | Cron doc grep; settle pass reads a table nothing refreshes. |

### B. Evidence integrity — the historical numbers are invalid

| # | Finding | Evidence |
|---|---------|----------|
| 8 | **"Lead-1" training/backtest data is actually ~lead-0.** The Open-Meteo *Historical Forecast* archive serves the freshest archived run for each past day; our parser then **backdates `as_of` to midnight of valid_date−1** ("to make lead_days = 1" — comment in code). Residual std ~1.3°F at "lead 1" (vs ~4.6°F for true lead-1 GEFSv12 reforecast) is the tell. **The Phase 2 "3/6 stations beat NDFD" verdict, the router config, and every committed manifest were computed on information the live system will never have.** Live performance will be materially worse than backtests promised. The negative analog-ensemble verdict and the null reforecast-NGR verdict are also suspect (they were judged against a pseudo-model with leaked data). | [`openmeteo/_parsers.py:121-144`](../src/kq/clients/openmeteo/_parsers.py) ("Backdate as_of to make lead_days = 1"); manifest residual stds; ROADMAP's own KAUS `raw_residual_std_f: 2.997`. |
| 9 | **~14× pseudo-replication in every manifest statistic.** `rolling_origin_splits(step_size=1)` with `test_window_size=14` evaluates every (day, bracket) in up to 14 overlapping test windows. KJFK manifest: `n_evaluated = 28,616` ≈ 7 brackets × 14 × 292 days. All reliability bins (n≥100 gating), Hosmer-Lemeshow, conformal coverage counts, n_traded (8,554), P&L, drawdown are built on duplicated evaluations. | [`cv.py:27-33`](../src/kq/models/cv.py) (default `step_size=1`), `models/backtest_manifest.json` config + counts. |
| 10 | **Phase 5 #5 gate metric (`mean_signed_clv`) is not CLV and is biased toward passing.** It is outcome-conditioned: `mean(+|edge| if picked side won else −|edge|)`, whose expectation is `|edge|·(2p−1)` — positive for any zero-skill model that leans toward favorites. True CLV compares entry price vs (devigged, **pre-tipoff**) closing price. Worse, the anchor query takes `MAX(fetched_at)` with **no pre-tipoff filter** while the odds cron ticks hourly through games — in-play quotes (which embed the realized outcome) leak into the anchor. | [`nba_clv.py:266-276`](../src/kq/backtest/nba_clv.py); [`run_nba_clv_backtest.py:153-166`](../src/kq/flows/run_nba_clv_backtest.py). The weather analog `mean_signed_edge_vs_ndfd` shares the same construction. |
| 11 | **Runtime router silently substitutes the calibration-FAILING raw model for KDEN.** The committed `router_config.json` routes KDEN → `"reforecast"` (chosen because NGR and raw both failed the calibration bar) — but `StrategyRouter.predict_*` dispatches `if strategy == "ngr" ... else raw`. Any non-"ngr" strategy (reforecast, analog) silently falls through to `RawForecastModel(DEFAULT_RAW_SIGMA_F)`. | [`router.py` predict_proba/predict_distribution](../src/kq/models/router.py); `models/router_config.json` KDEN entry. |

Also directly confirmed: **naive-UTC normalization missing in 5 high-volume
repositories** (`forecasts`, `kalshi`, `metar`, `ndfd`, `observed`) while the
NBA-era repos have it — tz-aware datetimes are silently rewritten to host-local
wall clock by DuckDB, mixing conventions in one DB across the Mac/WSL2 hosts.

## High-confidence findings pending verification

The verification fleet was rate-limited; these carry strong evidence (several
were found independently by 2–4 reviewers) but have NOT been panel- or
lead-verified. Treat as probable until checked:

- **UTC vs LST daily-max aggregation**: ensemble Tmax aggregated over UTC days;
  contracts + NDFD settle on local(-standard) days (3 reviewers).
- **Settlement day-completion guard missing**: a partial same-day observed high
  could settle trades early and irreversibly.
- **Nowcast one-sided mean update**: METAR observations can only raise the
  posterior mean while sigma shrinks → near-certain YES on already-lost brackets.
- **Full-form NGR drops `d·ens_var` at paper-trading inference** (ens_var never
  passed) → silently degrades to σ²=c.
- **NDFD live parser lead computation** mixes local-tz valid_date with UTC now →
  off-by-one at 00Z/06Z cron runs.
- **Fee model rounds per contract instead of per fill** (overstates fees at tail
  prices); **bankroll never reserves open-trade stake**; **backtest defaults to
  maker fills while the paper trader is taker-only** despite a "mirror" claim.
- **CPCV purge is one-sided** (trailing-side label overlap unless embargo covers it).
- **Elo season-boundary regression is dead code**; live flow also passes
  `GameContext=None` so rest/travel/altitude adjustments never fire at runtime.
- **Stale-data (cron-death) failure can never alert**: freshness → WARN,
  `cron-health.sh` pushes only on CRIT.
- **`paper_summary` labels Phase 2 exit numbers (50 settled/14 days) as "Phase 5
  gates"** (Phase 5 #1 is 500); "active days" counts distinct UTC dates, not consecutive.
- **`backup-duckdb.sh` exits 0 on copy failure; DB+WAL copied non-atomically** while
  writers run.
- `BacktestConfig.maker_fill_rate` is documented but dead; `qty=max(1,...)` floors
  override Kelly at small stakes; 0.15× Kelly is a default, not an enforced cap
  (Phase 5 #7 says "hard limits coded"); tz-aware `datetime.min` comparison crash
  lurking in the duplicate-market tiebreak; dashboard "Background ingest cron"
  panel reads log files nothing writes.

Two findings were **legitimately confirmed** by full panels before the rate
limit: #5 (3/3) and #6 (2/2) above.

## Phase 5 truth table (post-audit)

| # | Gate | Pre-audit belief | Post-audit reality |
|---|------|------------------|--------------------|
| 1 | ≥500 settled trades | "clock ticking since prod switch" | **Clock is NOT ticking.** Weather: prices=None, 4/6 brackets invisible, truth never ingested → 0 possible settles. NBA: 0 markets seen. Nothing can trade until P0 fixes land. |
| 2 | Brier ≥5% vs benchmark | 3/6 stations pass | **Evidence invalid** (lead-0 inputs + 14× replication). Must re-derive on true lead-1 (GEFSv12 reforecast archive is real lead-1). All prior model verdicts (incl. negative analog, null reforecast-NGR) need re-testing. |
| 3 | Reliability calibrated | mechanism shipped | Mechanism fine; all prior numbers invalid for the same reasons as #2. |
| 4 | Positive paper P&L 3wk | awaiting data | Blocked by #1 fixes. |
| 5 | CLV vs Pinnacle ≥+1% | code-complete | **Metric itself must be redefined** (price-based, pre-tipoff anchor) before any game counts. |
| 6 | 30-day flow uptime | demo soak accumulating | Cron runs, but "uptime" of a pipeline that cannot trade is not the spirit of the gate. Restart the clock after P0s. |
| 7 | Bankroll plan + hard caps | ✅ | Plan ✅; "0.15× coded as hard limit" is actually a default — small fix. |
| 8 | State availability | ✅ CA green (2026-05-18) | ✅ stands. |
| 9/10 | CPA / NVIDIA disclosure | external | unchanged. |

## Fix plan — the P0 series (ordered)

1. **PR-A: Kalshi prod payload adapter.** Parse `*_dollars` string fields (+
   `orderbook_fp`), read `strike_type`/`floor_strike`/`cap_strike` from the API
   into a typed strike model (greater/less/between). Stop inferring semantics
   from ticker text. Record strike fields in `kalshi_book_snap`.
2. **PR-B: Bracket + settlement correctness.** Price and settle all three strike
   types (P(T>floor), P(T<cap... i.e. ≤cap−1 integer), P(floor≤T≤cap)); settle
   from stored strike fields; add a day-completion guard.
3. **PR-C: Central Park.** Add KNYC station (Open-Meteo lat/lon, NWS ACIS KNYC,
   METAR KNYC); route KXHIGHNY to it end-to-end; retrain NY models.
4. **PR-D: NBA market discovery + hygiene.** `series_ticker=KXNBAGAME` + cursor
   pagination in `list_markets`; one-side-per-game selection; pre-tipoff guard;
   wire `GameContext`; season-boundary Elo regression.
5. **PR-E: Honest metrics.** Price-based CLV (entry vs devigged pre-tipoff
   close); fix `paper_summary` gate labels; drop/replace `mean_signed_*` metrics.
6. **PR-F: Evidence regeneration.** True-lead-1 training data (reforecast archive
   or T−1-cycle pulls); `step_size=test_window_size`; per-(station,valid_date)
   dedup; fix router non-ngr dispatch; **regenerate every manifest + router
   config; re-run all model verdicts.**
7. **PR-G: Ops integrity.** Scheduled ACIS observed-truth ingest; naive-UTC
   normalization in the 5 repos; stale→CRIT escalation; atomic backups;
   UTC-vs-LST aggregation fix.

Then — and only then — restart the Phase 5 clock.

## Baseline quality facts (for the record)

ruff ✅ · format ✅ · mypy --strict ✅ (117 files) · pytest **1,101 passed**,
1 skipped (logrotate absent on Mac), 1 deselected · money path mutation-tested
(82% kill) · suite hermetic (egress-guarded). The infrastructure discipline is
real — it just needs to be pointed at reality. Add to the testing matrix:
**recorded-prod-payload fixtures and a weekly live contract-semantics probe**
(rules_primary diffing) so payload drift can never again be silent.
