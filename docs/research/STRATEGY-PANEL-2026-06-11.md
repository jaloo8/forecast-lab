# Strategy panel — 2026-06-11 (audit-aware R&D synthesis)

Four-seat strategy panel run immediately after the [reality-contact audit](../SESSION-2026-06-11-AUDIT.md),
with the audit's 11 confirmed root causes injected as context so recommendations
are grounded in the actual state of the system (no model R&D on top of a broken data layer).
Each seat read the relevant repo research docs. Verbatim agent output, lightly formatted.


---

## Seat 1 — VP Research, Weather

### Honest assessment

[C1] As of this audit, forecast-lab has ZERO valid evidence of weather forecasting edge. Every positive verdict in ROADMAP.md — the 3/6-beat-NDFD table, KLAX +40.8%, the isotonic +19.7pp KDEN jump, the router config, the maker/taker P&L — was computed on training/backtest data that is ~lead-0 analysis data with fabricated as_of (residual std 1.3F vs true lead-1 ~4.6F), then pseudo-replicated ~14x by step=1 rolling-origin CV. [C2] The signature was visible in retrospect: center-bracket Brier of 0.05-0.08 against CLAUDE.md's own stated raw-GEFS baseline of 0.20-0.22 implies a ~3x skill jump over the entire field of operational NWP — that is a look-ahead artifact, not edge. [C3] Simultaneously, the system has never actually traded on prod: prices parse as None (*_dollars fields), 4/6 brackets per station are invisible (B-between regex gap), low-tail markets are inverted, the NY lane models the wrong city station, and settlement can never fire (no weather_observed ingest). The honest Phase 5 status is: gate #2 evidence NOT STARTED, gate #1/#4 clocks NOT RUNNING despite ROADMAP claiming they started 2026-05-30. [C4] The redeeming facts: (a) the repo already contains the one asset needed for honest re-derivation — the GEFSv12 reforecast archive (2015-2019 x 5 members, 53,994 rows) is real lead-1 data with a working end-to-end pipeline (PR #19/#21/#22 + Path B); (b) a telling clue that the audit's framing is right is that weather_reforecast_v1 — the only model trained on honest data — was the ONLY strategy that ever passed the reliability bar (3/6 stations, ROADMAP Phase 5 #3 row), while every corrupted-data model failed calibration at 0/6; well-calibrated-but-'worse-Brier' against a cheating comparator is exactly what an honest model looks like next to a leaky one. [C5] Realistic expectations after re-derivation: honest center-bracket Brier ~0.15-0.22; expect 0-2 of 6 stations to beat NDFD initially, not 3-4; NDFD/NBM is a genuinely strong benchmark and beating it at 4/6 may take the full reforecast-NGR + AnEn + nowcast stack plus a season of prospective data. [C6] The re-test ordering by P(verdict flips) x decision value is: (1) reforecast-NGR 'tied-or-worse' — most likely wrong, the comparison was rigged against the only honest model (it carried true 4.6F lead-1 uncertainty while its competitor cheated with 1.3F data, and the 'cross-model-family mismatch' diagnosis was confounded with a cross-LEAD mismatch); (2) the 3/6 NDFD verdict itself — certainly wrong in magnitude, unknown in direction, and it IS the gate; (3) the negative analog-ensemble verdict — doubly invalid (corrupted comparator AND a strawman single-predictor implementation, vs the 6-9-predictor CMA-ES design in THREE-WORKSTREAMS Part 1 that was never built); (4) isotonic/skew-normal magnitudes — direction probably survives, magnitudes will not; (5) the KMDW 'structural gap' diagnosis — mechanism reasoning (lake-effect, convection) remains plausible but the -51% magnitude and the no-trade-KMDW decision must be re-derived; (6) climatology-blend-negative-at-lead-1 — most likely to HOLD (literature supports blending only at long leads); (7) NBM qmd Phase 2 deferral — needs no re-test, it was an engineering verdict (767MB files, no MaxT element), orthogonal to the data corruption. [C7] The KNYC fix is a correctness fix, not an optimization: Central Park and JFK Tmax routinely differ 2-6F under sea-breeze/marine regimes, so every NY probability ever produced was for the wrong random variable; the urban-park edge hypothesis (less airport-MOS-anchored competition) is plausible but unverifiable until live order books accumulate — treat it as a free option, not a thesis. [C8] Strategic bottom line: the fastest path to maximum accuracy is not new models — it is (i) reality contact, (ii) honest substrate, (iii) re-run the existing, already-shipped model stack on that substrate, (iv) only then spend R&D on AnEn, the one genuinely new technique with literature support at true lead-1. Total estimated effort to a defensible gate-#2 reading: 4-6 weeks of work plus one season of prospective accumulation. Do not let the sunk 26-PR Phase 2 arc anchor expectations — the project is methodologically back at Phase 2 day 1, with much better infrastructure.

### Recommendations


#### [P0] Restore reality contact: prod price parsing, bracket coverage, settlement truth, UTC

**Rationale:** [C9] Audit items 1, 2, 10, 11 mean the system cannot trade, cannot see 4/6 brackets per station, inverts low-tail semantics, can never settle (no scheduled weather_observed ingest), and stores local-wall-clock timestamps in 5 repositories. [C10] No accuracy work has any value until forecasts can be expressed as correctly-priced, correctly-oriented positions on the markets that actually exist: gate #1 (500 settled trades) and #4 (3-week P&L) clocks are stopped at zero despite ROADMAP claiming they started 2026-05-30. [C11] Concrete scope: parse *_dollars string fields in the Kalshi client; extend src/kq/clients/kalshi/_ticker_parser.py to B-between tickers and fix T-less low-tail direction (add prod-fixture golden tests captured from live GET responses, replacing the 'best guess from Pass 1' fixtures the parser was built on per ROADMAP PR K); add a cron'd ACIS/CF6 weather_observed ingest so the settlement loop fires; normalize the 5 repositories to UTC with a one-time migration. [C12] This is the audit's own framing: the first accuracy lever is fixing reality contact.

**Expected impact:** [C13] Not a Brier improvement — an existence improvement: trades go from structurally-impossible to flowing; bracket universe per station goes from 2/6 visible to 6/6; settlement loop goes from never-fires to firing daily. Every downstream gate metric becomes measurable for the first time.

**Effort:** 1-2 weeks. Parser + price fields ~3 days with live-captured fixtures; observed-truth cron ~1 day; UTC migration ~2-3 days including backfill audit of existing rows.

**Risks:** [C14] Live-fixture capture requires prod API discipline (read-only, rate-limited). UTC migration on already-corrupted local-time rows risks double-shifting — must tag rows by provenance before converting. B-between settlement semantics (inclusive/exclusive bounds) must be read from rules_primary, not guessed, or we reintroduce inverted-semantics risk at the bracket edges.


#### [P0] Quarantine fabricated lead-0 data; make GEFSv12 reforecast the canonical training substrate; start honest as_of capture

**Rationale:** [C15] Audit item 6: the 'lead-1' training/backtest table is ~lead-0 Open-Meteo archive data with fabricated as_of (residual std 1.3F vs true lead-1 ~4.6F) — it is not fixable, only quarantinable. [C16] The GEFSv12 reforecast rows already in DuckDB (model='gefsv12_reforecast', 2015-2019 x 5 members, 53,994 rows, plus the 2000-2019 pull mechanism from PR #19/#21/#22) are the only true lead-1 data in the repo and become the canonical training set. [C17] Simultaneously start operational forecast capture where as_of is set at fetch time by the ingest process (never backfilled from archives), so a clean prospective evaluation set accrues from day 1. [C18] Add two permanent tripwires: an ingest-time assert rejecting any row whose as_of is not within tolerance of wall-clock fetch time, and a residual-std alarm (if any 'lead-1' model fits with residual std < ~2.5F, fail loudly — that sharpness is physically implausible and was the smoking gun here).

**Expected impact:** [C19] Foundation for every number that follows; no direct Brier effect. Honest center-bracket Brier will rise from the fabricated 0.05-0.08 to a realistic 0.15-0.22 — this is the correction, not a regression. The tripwires make a recurrence of finding 6 structurally detectable.

**Effort:** ~1 week: provenance column + quarantine filter ~2 days; extend reforecast pull to 2000-2014 if fuller sample wanted (~25GB, mechanism exists) 1 day of wall time; tripwires + tests ~2 days.

**Risks:** [C20] Reforecast-only training means the operational model family (GFS-via-Open-Meteo) differs from the training family — the Path A migration (operational GEFS-family source) becomes load-bearing rather than optional; budget for it. Quarantine will orphan the existing manifests and dashboard panels; they must display 'evidence reset' rather than stale numbers, or the project's memory (CLAUDE.md §14 concern) silently rots in the other direction.


#### [P0] Fix evaluation statistics (CV de-replication) and re-derive the NDFD baseline verdict on clean data — gate #2 hard reset

**Rationale:** [C21] Audit item 7: step_size=1 with 14-day windows pseudo-replicates each day ~14x in every manifest statistic; ROADMAP itself half-acknowledged this ('effective n ~1140... +/-2pp is plausibly noise') yet boundary verdicts (KDEN -1.9%, KJFK -2.0%) were narrated as 'one push from crossing'. [C22] Fix: step = test-window length (or dedupe to one evaluation per (day, bracket)), report effective n, and attach station-level block-bootstrap CIs to every Brier delta in the manifest. [C23] Then re-run the full existing strategy grid (raw, NGR, skew-NGR, isotonic stack, reforecast-NGR, router) on the clean substrate and publish a new NDFD verdict table — this is re-test priority #2 in the ordering, and it is the gate-#2 number itself. [C24] Also verify the benchmark side: confirm the NBM-deterministic rows are true T-1 issuances (real issue-time as_of) and not archive lead-0 data, else the comparison is corrupted from the other direction.

**Expected impact:** [C25] CIs widen by ~sqrt(14) ~ 3.7x; expect the honest verdict to be 0-2 of 6 stations beating NDFD at >=2-3% with CI support, down from the claimed 3/6. A worse number with valid error bars is strictly more decision-useful than the current invalid one — gate #2 integrity is the deliverable.

**Effort:** ~1 week given P0 item 2 lands first: CV change ~2 days, bootstrap CIs ~1 day, grid re-run ~1 day CPU, manifest/dashboard/ROADMAP rewrite ~2 days.

**Risks:** [C26] Morale risk: the honest table will look bad; pre-commit to publishing it unedited (pre-registered protocol) so there is no temptation to re-tune until it flatters. Sample risk: clean evaluation on reforecast-era data is retrospective; final gate evidence must be prospective (see P2 protocol item).


#### [P0] Settlement-station audit for all 6 series; build the KNYC (Central Park) pipeline to replace KJFK

**Rationale:** [C27] Audit item 3 confirmed: src/kq/clients/stations.py:36 maps KXHIGHNY to KJFK, but prod rules_primary settles on Central Park (KNYC) — every NY probability ever produced was for the wrong random variable; KNYC-vs-KJFK daily Tmax routinely differ 2-6F under sea-breeze and marine-flow regimes. [C28] The same failure class must be checked for the other 5 series by parsing rules_primary from prod: 'Austin' NWS climate-of-record is Camp Mabry (ATT), not Bergstrom (KAUS), and 'Chicago' could reference Midway or O'Hare — if either mapping is wrong, part of the KAUS/KMDW persistent 'fail' verdicts may be a wrong-station artifact, not model deficiency. Pin the verified settlement station per series in code with a test against the live rules text. [C29] KNYC pipeline needs: new Station row (KNYC, ~40.779N, -73.969W, EST); NWS ACIS observed-truth backfill (ACIS supports KNYC directly — Central Park is a ThreadEx/climate-record site, arguably with LONGER and cleaner record than KJFK); Open-Meteo + GEFSv12-reforecast extraction at Central Park lat/lon (grid-point change only, mechanism unchanged); METAR/nowcast review (KNYC ASOS exists but is sparser than airport METAR — the intraday Bayesian nowcast may need degraded-cadence handling); refit all NY models. [C30] Urban-park edge hypothesis: Central Park's sensor sits under tree canopy in a park interior — NWP 0.25-degree grids and airport-anchored MOS guidance represent it poorly, and retail competition likely prices off airport-app forecasts; a station-specific bias correction trained on KNYC truth is exactly the kind of unsexy local knowledge that can be edge. Treat as a testable bonus, not the justification — the justification is correctness.

**Expected impact:** [C31] NY lane: from systematically mis-located (multi-degree-F errors on regime days, i.e., unbounded Brier damage on the days markets pay most) to correct-by-construction. Cross-series audit: cheap insurance with a real chance of explaining part of one station's chronic failure. Urban-park edge: speculative 0-3% Brier-vs-NDFD beyond the correctness fix; do not book it until measured prospectively.

**Effort:** Audit of 6 series' rules_primary: 1 day. KNYC pipeline: ~1 week (station row + ACIS backfill 1-2 days, reforecast grid-point extraction 1 day, nowcast/METAR handling 2 days, refits + tests 2 days).

**Risks:** [C32] KNYC METAR sparsity may force the nowcast off for NY initially. Central Park's tree-canopy siting has a documented instrumentation-history quirk (sensor relocations/shielding changes) — backfill truth must come from the official climate record (ACIS), not raw METAR, or training labels drift from settlement values. If the cross-series audit finds Austin/Chicago mis-mapped, scope grows by one pipeline each — that would be good news disguised as work.


#### [P1] Re-test #1: reforecast-NGR, now same-family AND same-lead — promote to default baseline if it wins

**Rationale:** [C33] The 'tied-or-worse at every station, the router would never pick it' verdict (ROADMAP Path B, 2026-05-01) was the only honest model evaluated against competitors cheating with lead-0 data: reforecast-NGR carried true ~4.6F lead-1 uncertainty while skew-NGR's apparent sharpness was fabricated — the -38pp KJFK and -35pp KLAX 'collapses' attributed to cross-model-family mismatch are at least partly a cross-LEAD artifact. [C34] This is the single most likely verdict to flip, and the prior evidence already hints at it: weather_reforecast_v1 was the only strategy passing the reliability bar (3/6 stations) while every corrupted-data strategy failed at 0/6. [C35] Protocol: train on GEFSv12 reforecast 2000/2015-2019, evaluate leave-one-year-out within the reforecast archive AND prospectively against honest operational ingest; revisit Path A (operational GEFS-family source via Open-Meteo) so train and operate share a model family — the HHW2008 reforecast benefit requires it, and with the lead confound removed Path A's expected payoff must be re-estimated rather than written off.

**Expected impact:** [C36] Realistic: 5-15% CRPS/Brier improvement vs raw ensemble at lead-1 (HHW2008 gains are largest at longer leads; lead-1 is the modest end), with the largest gains plausibly at the regime stations (KMDW, KDEN) where 20 years of analogs of rare events matter. Versus NDFD: unknown — this re-test produces the first honest reading.

**Effort:** ~3-5 days; the entire mechanism (weather_reforecast_v1 strategy, engine pre-fit, router leg) is already shipped — this is a re-run plus Path A evaluation (~1 week extra if pursued).

**Risks:** [C37] If NDFD still wins broadly after the honest re-test, that is a real (not artifactual) signal that NBM-class benchmarks are simply strong at lead-1 — the correct response is to compete where NDFD is weakest (regime days, tails, intraday updates), not to keep stacking recalibrators. Cross-family penalty may persist for the operational lane until Path A lands; flag results as retrospective-only until then.


#### [P1] Re-test #2: analog ensembles per the full THREE-WORKSTREAMS Part 1 design — the negative verdict is doubly invalid

**Rationale:** [C38] The 'WORSE at all 6 stations' verdict (2026-05-25) is the second-most-likely flip, invalid for two independent reasons: (a) measured against corrupted lead-0 comparators whose 1.3F sharpness no empirical k-NN CDF could ever match — at true 4.6F residuals the comparison is fair for the first time; (b) the implementation tested was a strawman — ROADMAP itself notes 'one predictor + small pools', whereas the designed system (docs/research/THREE-WORKSTREAMS-2026-05-13.md Part 1) specifies 6-9 station-specific predictors (e.g., 925-T2m inversion at KLAX, 700hPa T/u at KDEN, 850 T/thickness at KMDW), CMA-ES-learned CRPS weights, Gaussian DOY kernel, k~50 over the 20-year x 5-member reforecast pool (~36K candidates/station), and CRPS-optimal convex blending into NGR. [C39] AnEn is the one technique in the backlog whose literature support is specifically at true lead-1 with reforecast archives, and whose mechanism (empirical CDFs of analog OUTCOMES) targets exactly the regime/tail days where parametric NGR fails — the KMDW lake-effect and KDEN Chinook failure modes named in docs/research/KMDW-STRUCTURAL-GAP.md. [C40] Sequence it AFTER re-test #1 so the comparator baseline is honest, and use the doc's own effect-size table as the pre-registered bar.

**Expected impact:** [C41] Per the design doc's honest estimates (derived for true lead-1 reforecast use, so they survive the audit): 2-4% CRPS vs a strong NGR baseline on median days, 5-10% on regime-transition days at 24h; KMIA 0-2% (weak synoptic forcing — do not over-promise); KDEN regime-stratified trees add another 2-4%. If it clears that bar at KMDW/KDEN/KAUS, it is the first credible lever on the stations that have never passed.

**Effort:** 2-3 weeks: predictor extraction from reforecast GRIBs (new fields beyond tmax_2m — the main cost), CMA-ES fit (~2h/station CPU, quarterly job), cKDTree + blend integration into the existing analog router leg. Note: cma (pycma) is a new dependency requiring CLAUDE.md §9 approval; scipy-only fallback (Nelder-Mead with restarts) exists but is weaker.

**Risks:** [C42] Pulling 6-9 upper-air fields per station from the reforecast archive multiplies the GRIB bandwidth/parse cost ~8x vs the tmax-only pull (~tens of GB, CPU-bound days of wall time). Curse-of-dimensionality if feature discipline slips past d~10. The blend can silently absorb AnEn to near-zero weight (BMA pathology) — use the CRPS-convex SLSQP blend per the doc, never EM.


#### [P1] Re-test #3: isotonic + skew-normal stack on the clean baseline; rebuild the router; make silent substitution fail loudly

**Rationale:** [C43] Isotonic's measured magnitudes (+19.7pp KDEN, KMIA fail-to-pass flip) are corrupted-data artifacts, but the direction likely survives — isotonic recalibration is distribution-agnostic and the honest baseline will be MORE miscalibrated (real 4.6F errors), giving it more signal to correct; expected honest gain 2-8% Brier where the base model is miscalibrated, possible small negative at well-fit stations (the KAUS overcorrection pattern was probably real). [C44] Skew-normal's wing gains never reproduced even on corrupted data (Allen 2023's 8-15% did not materialize); on honest data expect ~0-3% — keep it only if it survives the CI bar, else simplify. [C45] The router must be rebuilt from clean manifests because every current decision derives from invalid evidence, and audit item 9 (runtime router silently substituting the calibration-FAILING raw model when 'reforecast' is chosen for KDEN) is a correctness landmine independent of data quality: a config-vs-runtime divergence that no metric would ever surface. Fix: fail-loud on unfulfillable strategy, plus a contract test asserting runtime strategy == router_config decision per station.

**Expected impact:** [C46] Mostly evidence hygiene: 2-8% Brier from isotonic where applicable; the router rebuild prevents negative-selection (currently it can route a station to a model chosen on fabricated evidence and then silently swap in a third model at runtime). The fail-loud fix is worth more than any single modeling gain because it protects all future verdicts.

**Effort:** ~1 week total: re-runs are config flips on the clean substrate (2 days); router rebuild + fail-loud + contract tests (2-3 days).

**Risks:** [C47] Per-fold isotonic on de-replicated CV has fewer training pairs per fold (the 14x replication was inflating its training set too) — pool across brackets per the existing design and enforce min-n before trusting a fit. Risk of over-pruning: keep skew-normal code shipped-but-default-off if it fails the bar, consistent with prior negative-result discipline.


#### [P2] Gate #2 integrity protocol: pre-registered evaluation, prospective-first evidence, manifest provenance stamps

**Rationale:** [C48] Findings 6-9 share one root cause: the project graded its own homework with self-produced retrospective data and no protocol freeze. Codify: (a) gate #2 is decided on a pre-registered protocol (strategy set, CV scheme, effective-n CI rule, NDFD benchmark provenance) committed BEFORE results are computed; (b) retrospective reforecast results select candidates, but the binding gate evidence is PROSPECTIVE — the live weather-CLV tracker (src/kq/backtest/weather_clv.py) consuming honest-as_of operational data over >=1 season; (c) every manifest carries a data-provenance stamp (substrate id, quarantine version, effective n) so a future audit can reject stale evidence mechanically; (d) port the NBA-CLV lesson sideways: any 'edge' metric must be conditioning-free — the weather analog of audit item 8 is grading only brackets where we traded, which conditions on our own selection. [C49] This is what makes the Phase 5 #2 checkbox mean something — the criterion text in CLAUDE.md §5 survives, but its evidentiary standard is currently undefined and was exploited (unintentionally) once already.

**Expected impact:** [C50] Zero Brier effect; converts gate #2 from a number anyone can accidentally fabricate into an auditable claim. Prevents the next 26-PR arc from building on sand — the highest expected-value-per-line-of-code item on this list after the P0s.

**Effort:** 2-3 days: a protocol doc + manifest schema fields + a CI check that gate-relevant manifests carry provenance stamps and effective-n CIs.

**Risks:** [C51] Prospective-first means gate #2 cannot be declared for at least a season of clean live data — this must be communicated as the cost of the audit, not as schedule slip. Over-bureaucratization risk for a solo project: keep the protocol to one page.


#### [P2] NBA lane integrity fixes (gate #5): pagination + series filter, per-side dedup, true pre-tipoff CLV

**Rationale:** [C52] Out of the weather scope but in the gate-integrity scope: audit items 4, 5, 8 mean the NBA lane sees 0 prod markets, would double-expose every game if it saw any, and its gate metric (mean_signed_clv) is outcome-conditioned |edge| that a zero-skill favorite-leaning model passes, with in-play Pinnacle quotes leaking outcomes into the 'closing' anchor. [C53] Fixes: cursor pagination + series_ticker filter on NBA market queries; canonicalize one ticker per game-side pair; redefine CLV as side-signed (close_prob - fill_prob) using the last PRE-TIPOFF Pinnacle quote (filter on commence_time), and recompute any accumulated history. [C54] Ranked below all weather items because the question's accuracy mandate is weather, but gate #5 is as invalidated as gate #2 and the fix is small.

**Expected impact:** [C55] Gate #5 goes from unpassable-and-meaningless to measurable-and-meaningful; the corrected CLV metric will likely show near-zero skill for the current Elo (the honest prior for a public-data Elo vs Pinnacle), which is the truth the gate exists to surface.

**Effort:** ~1 week: pagination/filter 2 days, dedup 1 day, CLV redefinition + pre-tipoff filter + tests 2 days.

**Risks:** [C56] Recomputing CLV history requires stored pre-tipoff snapshots — if only in-play quotes were stored, history is unrecoverable and the gate-#5 clock restarts from zero. Free-tier Odds API quota (500 req/mo) constrains snapshot cadence near tipoff.


#### [P3] Low-priority re-tests and standing deferrals: climatology blend, KMDW no-trade decision, NBM qmd, LightGBM

**Rationale:** [C57] Climatology blend at lead-1: most likely to HOLD negative — the literature basis (blend helps at lead 5-7+, hurts sharp short-lead forecasts) is independent of our data corruption, though the measured -8 to -24pp magnitudes were inflated by the fabricated 1.3F sharpness; re-run is a config flip on the clean substrate, do it for completeness only. [C58] The KMDW 'structural gap' memo conclusion (no-trade KMDW for v1) was reasoned from invalid magnitudes; the lake-effect/convective mechanism argument stands, but re-decide after re-tests 1-2 — if reforecast-NGR + AnEn move KMDW materially, the 5-of-6 bar reformulation may be unnecessary; if not, the memo's option (c) stands with honest numbers behind it. [C59] NBM qmd Phase 2 stays deferred — its blockers (767MB files, no daily-MaxT element in the public qmd bucket) are physical/engineering facts untouched by the audit; do not reopen. [C60] LightGBM quantile regression remains correctly gated behind 500 calibrated trades per CLAUDE.md §2 — and on the honest substrate (effective n ~1-2K days/station, not the fake 12K+) the overfit risk that justified the gate is even larger than previously believed.

**Expected impact:** [C61] Climatology re-run: expected confirmation of a negative, value is closing the loop honestly. KMDW re-decision: determines whether v1 trades 5 or 6 stations — a bankroll-allocation decision, ~0 Brier effect either way. The deferrals avoid spending the scarcest resource (solo R&D weeks) on ruled-out or premature levers.

**Effort:** Climatology re-run: hours. KMDW re-decision: 1 day of analysis after P1 re-tests land. Others: zero (explicit non-action).

**Risks:** [C62] Main risk is doing these too early: every one of them is sequenced behind the P0 substrate and the P1 re-tests, and pulling them forward recreates the original failure mode — ranking levers on evidence that does not yet exist.


---

## Seat 2 — VP Research, Sports (NBA / NFL / PGA)

### Honest assessment

The sports lane's problem is not model quality — it is that the system has never actually touched a market and its referee was rigged. The NBA flow has seen 0 prod markets (unpaginated, unfiltered query), would double-trade both per-side tickers if it ever did see them, cannot parse prod prices at all, and the Phase 5 #5 gate metric is not CLV: mean_signed_clv is outcome-conditioned |disagreement|, which a zero-skill model leaning 3pp toward favorites passes at +1.02pp, and its anchor query will happily leak in-play quotes. ROADMAP's 'Phase 3 code-complete end-to-end' and 'code is no longer the bottleneck' claims are therefore false in the only sense that matters; every historical NBA CLV number must be voided alongside the weather backtest evidence. The honest good news: the edge thesis itself (devig a sharp anchor, trade the Kalshi gap, measure true CLV) is sound and requires no model R&D to test — the entire realistic 0-2pp budget lives in reality contact (P0), anchor freshness and adverse-selection avoidance (+0.3-1.0pp), maker execution (+1-2pp per filled trade), and an injury veto (+0.3-0.8pp); the glamorous items (Elo context wiring, season regression, ref crews) are fallback-path hygiene worth <=0.1pp of portfolio CLV and must not be allowed to masquerade as the plan. Strategically: NBA (1,230 games/yr) is the only vertical that can statistically prove the >=+1pp bar and it is dark until late October; NFL (272 games, ~110-135 trades/season, week-clustered) is a calendar complement that can deliver a valid late-window CLV verdict 4-7 weeks into September but never a tight estimate within one season; PGA fails the anchor premise outright — no Pinnacle, 37% overround, 4 events/year — and should be shelved with explicit revival triggers rather than half-built; totals meta-labeling is a real +0.5-1.5pp opportunity that must wait behind 100 honest settled moneyline trades, with only its data collection (cheap, irreversible-if-skipped) starting now. The sequencing test for every future PR in this lane: does it move a number that survives the P0-B metric definition? If not, it is theater.

### Recommendations


#### [P0] P0-A: Restore NBA market contact — pagination + series_ticker query, *_dollars price parse, one-trade-per-event dedupe

**Rationale:** [C1] The flow sees 0 NBA markets on prod: src/kq/flows/paper_nba_trade.py:318-334 makes a single list_markets(status='open') call (limit 200, no series filter) and greps tickers client-side; prod has thousands of open markets, so KXNBAGAME tickers never appear in page 1. Fix exactly as the weather fix did (commit b2c98dd): query by series_ticker=KXNBAGAME with pagination. [C2] Prices: prod returns *_dollars string fields; the parser reads retired integer-cent fields, so yes_bid/yes_ask arrive as None and the evaluator can never size a trade — shared fix with the weather lane. [C3] Double exposure: Kalshi lists two per-side tickers per game; the loop at lines 188-249 evaluates every ticker independently, so one game generates two correlated positions (and with any model/anchor disagreement asymmetry, potentially both sides of the same game). Group by event_ticker, evaluate the game once, trade at most one side. [C4] All timestamps to UTC and persist commence_time per market — prerequisite for the pre-tipoff filter in P0-B; the audit's finding #11 (host-local wall clock in 5 repositories) corrupts every time join this plan depends on. No CLV gain is claimable from any other item until this lands; current expected CLV of the NBA lane is exactly 0.00% because it cannot trade.

**Expected impact:** Unlocks the entire NBA vertical (currently 0 markets visible, 0 trades possible). Halves per-game variance by removing double exposure. Enables every downstream measurement.

**Effort:** 2-4 days including prod verification of ticker format and a paginated-fetch integration test against prod read-only.

**Risks:** Low. Mirror of the already-shipped weather fix. Main risk is per-side ticker semantics (yes_is_home mapping) differing from the parser's assumption — verify against live prod markets before enabling cron.


#### [P0] P0-B: Replace mean_signed_clv with true price-based CLV + closing-line capture (the corrected Phase 5 #5 metric)

**Rationale:** Deliverable 1. [C5] The current metric (src/kq/backtest/nba_clv.py:273-276) is mean(|edge| if correct_side else -|edge|) — outcome-conditioned absolute disagreement, not CLV. A zero-skill model that outputs Pinnacle's own fair shifted 3pp toward the favorite has |edge|=0.03 always and correct_side true whenever the favorite wins (~67% of NBA games), scoring 0.03*(0.67-0.33) = +1.02pp — it PASSES the ≥+1pp Phase 5 #5 gate with literally no information beyond Pinnacle's quote. [C6] The anchor query (paper_nba_trade.py:295-310 and the backtest flow) takes ORDER BY fetched_at DESC LIMIT 1 with no commence_time filter: if odds ingest runs during games, the 'latest' quote is in-play and already reflects the score — direct outcome leakage of unbounded magnitude. All historical values of this metric are void. CORRECT DEFINITION: for each executed trade t on side s — CLV_t = p_close(s) - p_entry(s), where p_entry = fee-adjusted fill price in probability units ((fill_price*qty + taker_fees)/qty) on the Kalshi contract actually held, and p_close = proportional-devigged Pinnacle h2h probability of the equivalent side from the LAST snapshot with fetched_at <= commence_time (UTC), snapshot age <= 30 min before tipoff (older = trade excluded from the CLV aggregate and counted as no_valid_close), booksum sanity-checked in [1.00, 1.08], same devig method at every point in the pipeline. No realized outcome appears anywhere in the formula; it is computable at tipoff, before settlement. Aggregates: mean CLV (gate: >= +1.0pp), close-beat rate (share of trades with CLV_t > 0, target > 55%), and a cluster-robust 95% CI clustered by game date (NBA) / week (NFL); report n plus all exclusion counts. Closing snapshots land in a one-way clv_facts table the training/feature pipeline cannot read (THREE-WORKSTREAMS-2026-05-13.md §2.7 already specifies this — implement it as written). For signal-only backtests, p_entry = Kalshi ask at decision time; never use Pinnacle-at-entry as the entry price (that measures Pinnacle drift, not our execution). [C7] Power: with per-trade CLV std ~2-3pp for hours-before-tipoff NBA entries, a true +1pp mean is distinguishable from zero (one-sided 95%) in ~25-95 trades; the existing 100-settled-games Phase 3 exit criterion is therefore statistically adequate once the metric is honest.

**Expected impact:** Converts the Phase 5 #5 gate from a rubber stamp that certifies zero-skill models into the single honest evidence stream for the whole sports lane. Every other recommendation is measured through this.

**Effort:** 3-5 days: clv_facts schema + pre-tipoff close selector + fee-adjusted entry recorder + aggregation with clustered CI + regression tests (including a zero-skill-model test that MUST score ~0).

**Risks:** Hourly odds cron may miss a true close (snapshot >30 min stale at tipoff) and shrink usable n — mitigated by P1-A's pre-tipoff cadence bump. Requires honest acceptance that no prior NBA CLV number survives.


#### [P1] P1-A: Pinnacle anchor freshness — pre-tipoff snapshot cadence + staleness gate (NBA accuracy lever #1)

**Rationale:** Deliverable 2, rank 1. For a Pinnacle-anchored strategy the model IS the anchor, so anchor staleness is the dominant accuracy lever. [C8] NBA moneylines move 2-6pp on a star scratch; news typically breaks 30-90 min pre-tipoff. Trading Kalshi against a >1h-old Pinnacle snapshot after news is out is pure adverse selection: the 'edge' is the news, and we are on the wrong side of it. Gate signal emission on snapshot age (<= 15-30 min within 2h of tipoff; raise ingest cadence to 15-min in that window — quota math: ~5-8 games/day * 8 extra polls = well inside the 500/mo free tier off-peak, marginal at NBA peak, $30/mo tier is the fallback). Expected effect +0.3 to +1.0pp mean CLV, achieved by deleting the worst negative-CLV trades rather than by adding skill — the largest single lever available, bigger than any model change. [C9] Execution adjunct: Kalshi NBA spreads run 2-4 cents; posting maker instead of lifting the ask is worth +1-2pp per filled trade mechanically, larger than every modeling lever below — instrument maker fill rate vs taker in the paper executor and report both, since unfilled maker orders are the offsetting cost.

**Expected impact:** +0.3 to +1.0pp mean CLV from staleness gating; up to +1-2pp per trade from maker fills (discounted by fill rate). In a 0-2pp professional ceiling, this is most of the realistic budget.

**Effort:** 2-3 days (cadence config + age gate + maker/taker instrumentation).

**Risks:** Tighter gates reduce trade count, slowing the path to 100 settled; tune the age threshold to keep trade rate >= ~40% of eligible games. Odds API quota overage at peak cadence.


#### [P1] P1-B: Wire the dead Elo machinery — GameContext, season-boundary regression, injuries-as-veto (NBA accuracy levers #2-#4)

**Rationale:** Deliverable 2, ranks 2-4. These fix real dead code but mostly improve the FALLBACK path, so size expectations honestly. [C10] Rank 2 — injuries beyond CSV: late scratches are the dominant NBA line mover; Pinnacle prices them in minutes, Kalshi retail lags. Use real-time injury polling (the Phase 3 plan's hourly + 15-min-final-3h cadence; current PR #45 is CSV-import only) as a trade VETO/timing signal — suppress signals in the window between a scratch and the next anchor refresh. Expected +0.3 to +0.8pp CLV via avoided adverse selection. As a model feature on top of Pinnacle it is worth ~0pp — Pinnacle already prices it. [C11] Rank 3 — GameContext is dead at runtime: paper_nba_trade.py passes elo_context=None (line 208) and _compute_elo_state folds history with ctx=None (line 274), so the B2B/travel/altitude adjustments in nba_elo.py never execute. A back-to-back is -46 Elo = ~6.6pp win probability at parity, and ~30% of games have at least one team on a B2B — the fallback is systematically wrong by several pp on a third of games. Wire schedule-derived B2B flags and great-circle travel distances (TRAVEL_PENALTY_PER_MILE is hard-coded 0.0 and needs a real rate, 538's ~-0.045/mi) into both the live flow and the rating-history fold. [C12] Rank 4 — season-boundary regression is dead code: regress_to_baseline() exists (nba_elo.py:98) but _compute_elo_state never calls it, so ratings cross off-seasons un-regressed and early-season (Oct-Dec) fallback probabilities are overconfident in last season's rosters by ~1-2pp win prob. One-line fix plus season-break detection in the chronological fold. Portfolio CLV effect of C11+C12 is small (<= +0.1pp) because they touch only the Pinnacle-missing fallback share of trades (<10%), but they cut fallback Brier by ~0.005-0.01 and make the Elo a legitimate sanity gate on anchor disagreements. [C13] Rank 5 — ref crews: crews are announced ~9am ET game day and have real pace/total tendencies, but for MONEYLINES vs a sharp anchor the effect is <= +0.1pp CLV (crews move totals, and Pinnacle prices crew news anyway). Defer ref-crew ingestion to the totals stack (P2-B) where THREE-WORKSTREAMS §2.5 already lists it as a primary+meta feature.

**Expected impact:** +0.3-0.8pp CLV from the injury veto; fallback-path Brier -0.005 to -0.01 and early-season error -1-2pp from C11+C12; ref crews ~0 for moneylines (deferred).

**Effort:** 4-6 days total (injury polling wiring 2-3d; GameContext plumbing + travel distances 2d; season regression 0.5d).

**Risks:** Injury-feed reliability (nbainjuries upstream changes); travel-distance data adds a small static dataset. Do not let this expand into model R&D — the anchor strategy does not need a better Elo to clear Phase 5 #5.


#### [P1] P1-C: Start collecting NBA totals + opening/closing snapshots NOW (data only — no model)

**Rationale:** The only 'build now' component of meta-labeling that is justified (see P2-B for the deferral of everything else). [C14] Historical totals lines cannot be backfilled from the free Odds API tier; every un-collected game is training/CLV data lost forever, and the meta-labeling design needs opening AND closing totals quotes (§2.5 lists Pinnacle opening total as a feature and closing strictly as target). Add markets=h2h,totals to the existing ingest call — note Odds API bills credits per market*region, so this doubles draw to ~240-600/mo, inside the 500 free tier at off-peak cadence but likely requiring the $30/mo tier at NBA-peak + 15-min pre-tipoff cadence (already budgeted in CLAUDE.md §11 as the only-if-quota-exceeded line). Write into the same clv_facts one-way pipe from P0-B so closing totals are physically unreachable by any future training code.

**Expected impact:** Zero immediate CLV; buys 1+ season of totals line history so that if/when P2-B unblocks, the meta stack trains on real data instead of waiting a year.

**Effort:** 1 day.

**Risks:** Quota overage (~$30/mo); trivially reversible.


#### [P2] P2-A: NFL paper lane with two fixed entry windows and week-clustered CLV accounting (ready by September)

**Rationale:** Deliverable 3. Foundation library (devig, Odds API NFL key, ticker parser) is shipped on feat/multi-sport-nfl-pga; remaining work is the deferred §7 list (nfl_odds table, ingest flow, /scores settlement, crosswalk, paper flow) — all patterned on NBA, BUILT ON the fixed substrate from P0-A/B, plus prod verification of the KXNFLGAME per-team suffix which the design doc flags as unverified. ENTRY TIMING with sample-size math: [C15] 272 regular-season games (32*17/2) + ~13 playoff games; at a 40-50% min-edge trade rate that is ~110-135 trades/season — 4.5x less sample than NBA's 1,230 games. [C16] Two fixed windows: (W1) post-Wednesday practice report (~Thu), per-trade CLV std ~4-5pp because 3+ days of news flows through the position; (W2) T-60min after official inactives (90 min pre-kickoff), std ~1.5-2pp. Detecting a true +1pp mean at one-sided 95%: W2 needs ~(1.645*1.75)^2 = 8-11 trades nominal, realistically 25-40 after clustering; W1 needs ~(1.645*4.5)^2 = 43-68. A tight +-0.5pp CI at W1 variance needs (1.96*4.5/0.5)^2 = ~310 trades = 2-3 full seasons. [C17] Clustering: ~16 games settle each Sunday with shared shocks (weather, league-wide news), so use week-clustered standard errors over ~17-21 weekly clusters/season; effective n is 20-40% below nominal. RECOMMENDATION: paper-trade W2 only until W2 mean CLV >= +1pp with CI lower bound > 0 (~4-7 weeks of season), then A/B W1 against it — W1 is where the larger Kalshi-lag edge plausibly lives (thin early-week Kalshi books lag Pinnacle openers) but it cannot be the proving ground at its variance. [C18] Strategic framing: NFL CANNOT independently prove the Phase 5 #5-style bar within a season at tight confidence; it is a calendar complement (Sep-Feb) to NBA (late Oct-Jun), not a substitute. No NFL Elo for v1, per the design doc — Pinnacle quotes next season early, so the anchor never goes missing the way NBA's does.

**Expected impact:** Fills the Sep-late-Oct sports gap with ~110-135 honest CLV observations/season; W2-first sequencing yields a statistically valid CLV verdict ~4-7 weeks into the season.

**Effort:** 5-8 days for the deferred §7 NFL items on the fixed substrate, before the September kickoff deadline.

**Risks:** KXNFLGAME ticker format unverified on prod until NFL markets list; thin early-week Kalshi books may make W1 fills mostly hypothetical; Odds API quota stacking with NBA+totals cadence (budget the $30/mo tier).


#### [P2] P2-B: Totals meta-labeling — defer the build behind an explicit moneyline-CLV gate

**Rationale:** Deliverable 5: build AFTER, with one carve-out (P1-C collection). Reasons: [C19] Same broken substrate — pagination, dollars parsing, double-sided exposure, local-clock timestamps, and no pre-tipoff close all corrupt totals exactly as they corrupt moneylines; building a second model stack now manufactures more invalid evidence, which is precisely the failure mode the audit just caught (fabricated lead-1 as_of, pseudo-replicated CV, outcome-conditioned metrics). [C20] Evidence logic: the moneyline anchor strategy is strictly simpler (no model) and exercises the identical infrastructure the meta stack needs (odds ingest, crosswalk, closing-line capture, CLV math). If the no-model strategy cannot show mean CLV >= 0 on fixed infrastructure, a Glicko-2-pace + LightGBM-meta stack will not rescue it — and its CV could not be trusted anyway until the purged-by-season scheme (§2.6) is implemented with more rigor than the rolling-origin CV that just failed audit (finding #7, ~14x pseudo-replication). [C21] Realistic payoff per the design doc's own numbers: 51% primary -> ~52.5% selective hit rate, sustained CLV +0.5-1.5pp, with >+2.5pp flagged overfit-suspect — real but not so large that a 1-2 quarter deferral costs much, especially with P1-C banking the data meanwhile. [C22] Calendar: NBA is at the Finals now; the meta stack could not paper-trade until late October regardless. GATE (concrete): begin the build when >= 100 settled NBA moneyline paper trades exist on post-P0 infrastructure with true mean CLV >= 0 and the close-capture pipeline validated (or the NFL W2 equivalent this fall). When it builds, take the §2.4 Kelly-with-flip machinery as written but keep the flip path DISABLED until the meta-model's out-of-fold reliability diagram passes the same n-aware bar weather uses — false-confident flips are the documented P&L destroyer (§2.4 practical gates).

**Expected impact:** When built on proven infrastructure: a second NBA market with +0.5-1.5pp realistic CLV and ~doubled trade count toward the 500-settled Phase 5 #1 criterion. Built now: negative expected value (more invalid evidence, opportunity cost against P0/P1).

**Effort:** 0 now (gate-keeping decision) + 2-3 weeks when the gate opens (Glicko-2 pace, efficiency model, LightGBM meta, season-purged CV, flip-gated Kelly).

**Risks:** Main risk of deferral is losing 2026-27 early-season totals data — eliminated by P1-C. Risk of building early is repeating the exact evidence-fabrication pattern the audit found.


#### [P3] P3: PGA — shelve paper trading; keep the library; revisit only with a sharp anchor (honest verdict: not viable as designed)

**Rationale:** Deliverable 4. [C23] The edge thesis ('the sharp book is the model') fails for golf at the first premise: the Odds API golf feed has NO PinNACLE (verified live 2026-05-24 in MULTI-SPORT-NFL-PGA-DESIGN.md §3); the best available anchors are lowvig/betonlineag at booksum ~1.375 — a 37%+ overround spread across ~94-117 players. [C24] Devigging that is modeling, not measurement: the power-vs-multiplicative method choice alone moves longshot fair probabilities by >2x, and even on tournament favorites (8-12% win prob) the method spread is ~1-2pp — equal to or exceeding the ENTIRE 0-2pp professional CLV ceiling. The anchor's error bars are wider than any edge it could detect. [C25] There is no sharp close, so true CLV (P0-B definition) is unmeasurable for golf — not noisy, undefined. Any 'CLV vs sharpest retail book' number would be the same category of pseudo-evidence the audit just invalidated. [C26] Sample size is hopeless regardless: 4 Majors/year; even 10 contracts per event is ~40 settled trades/year, and those would pollute the Phase 5 #1 500-trade criterion with junk volume. [C27] The expensive remaining work is exactly the part not to build: the player-name crosswalk (the design doc's own 'hard part'). VERDICT: shelve the paper-trade follow-ups; KEEP the shipped foundation (devig_outright is property-tested and reusable for any future N-way market). Revisit triggers, either of: (a) a true model-based golf anchor — DataGolf's API (~$30/mo) is the industry-standard fair-probability source; new dependency + spend requires owner approval per CLAUDE.md §9; Betfair-exchange devigged closes are a second-best alternative; or (b) Kalshi lists 2-way golf structures (head-to-head matchups, top-10) where the existing 2-way devig and a thinner overround restore measurability.

**Expected impact:** Zero CLV foregone (there is no measurable golf edge to forgo with current data). Saves the crosswalk build (~1-2 weeks of the hardest, least-reusable work) and protects Phase 5 evidence quality.

**Effort:** 0 (decision + one ROADMAP line moving PGA follow-ups to deferred-with-triggers).

**Risks:** Owner disappointment — golf was owner-requested; mitigate by framing the DataGolf trigger as the concrete unlock path rather than a kill. Minor risk that Kalshi golf microstructure is so soft that even a weak anchor finds gaps — but we could never prove it, which is the point.


---

## Seat 3 — CSO, Equities Wedge

### Honest assessment

[H1] The ETF-vol-distribution wedge from the Renaissance deep-dive is directionally right and I confirm it — but as written it under-specifies the venue, and the venue is where this org just discovered all its failures live. My modification: same forecasting target (daily index close-to-close distribution via a realized-vol engine), but first expression on Kalshi index event brackets rather than ETF options, because that reuses the (post-fix) execution/settlement/fee/calibration stack near-1:1, keeps compliance surface at zero, and gives Brier/reliability measurement identical to the weather pipeline. The single most important unknown — whether Kalshi index markets exist in 2026 with usable liquidity and what exact print they settle on — is deliberately framed as G0 step one rather than assumed, because assuming it is exactly the KNYC-class error the audit just caught. [H2] The uncomfortable truth about economics: even if everything works, this wedge produces roughly $500-2,500/year on Kalshi-scale capital and maybe $2-3.5k/year on a post-gate options expression — against a realistic Sharpe ceiling of 0.5-1.0 and 15-25% drawdowns. Judged as income it is irrational for an NVIDIA engineer; its actual return is a second independent proof that the calibration + reality-verification stack generalizes, which is the precondition for anything bigger (and for the eventual commercial question in Pass 3). I have priced that honestly rather than letting the wedge be sold internally as a money-maker. [H3] The deepest finding I can offer as CSO: the audit demonstrates the org's only durable moat is discipline — every model insight here is replicable from public literature in weeks, but the willingness to verify settlement semantics against the venue, pre-register gates, run null-model must-fail tests, and invalidate one's own flattering evidence is rare at any scale. The equities wedge is designed to exploit exactly that: a domain (vol forecasting) where the public baselines are strong, the truth is public, and the winner is whoever measures honestly. [H4] Honest probability assessment: I'd put roughly 40-55% odds on beating HAR-RV by >=5% CRPS within a year (it is a heavily-studied baseline), but near-certainty that the attempt — run under Gate E — produces a true answer either way, which is more than the prior weather backtests can claim. The kill criterion is built in: if E3 fails after 250 events, the wedge dies cleanly and cheaply (~$10/mo data cost, ~6 weeks of build) with the platform improvements retained. [H5] Final sequencing reality: none of this starts until the 11 audit findings' P0 fixes land and a weather paper trade actually settles end-to-end on prod. The equities wedge inherits whatever platform exists; building vertical two on a platform that cannot parse a prod price would be the same mistake wearing a new ticker.

### Recommendations


#### [P0] Sequencing precondition: no equities work until v1 reality-contact is fixed and weather paper loop demonstrably trades on prod

**Rationale:** [C1] The 2026-06-11 audit found 11 confirmed reality-contact failures (price-field parsing returns None on all prod prices; 4-of-6 brackets invisible to the ticker regex; KNYC-vs-KJFK settlement-station mismatch; NBA flow sees 0 markets and would double-expose; fabricated lead-1 as_of; CV pseudo-replication; outcome-conditioned gate metric; silent router fallback; no truth ingest; local-time timestamps). [C2] Every one of those failure classes has a direct equities twin (settlement-value definition, adjusted-price look-ahead, overlapping-sample CV, in-play quote leakage), so porting the platform before the fixes land would replicate the disease into the new vertical. [C3] CLAUDE.md section 2 already makes equities a v1 non-goal, and the audit pushed the Phase 5 clock back to zero because the prior backtest evidence (lead-0 data masquerading as lead-1, residual std 1.3F vs true 4.6F) is invalid — so there is no schedule pressure to start equities now. [C4] The single cheapest equities action available today is zero code: write the wedge spec and gate doc (recommendations below) so the v2 start is a decision, not a research project.

**Expected impact:** Prevents porting 11 known failure classes into a second vertical; converts the audit's sunk cost into transferable discipline. Equity wedge start date becomes deterministic: after audit P0 fixes merge + first real prod paper trade settles on weather.

**Effort:** Zero engineering (this is a sequencing rule). One paragraph added to ROADMAP.md deferred section.

**Risks:** Motivation risk: owner is ambitious and equities is the long-term goal; total deferral with no visible artifact invites scope-creep workarounds. Mitigate by allowing the two paper artifacts (wedge spec, gate doc) to be written now.


#### [P0] Codify the Venue-Reality Verification Protocol (G0) as a standing repo artifact derived from the 11 audit findings

**Rationale:** [C5] The audit proves the org's durable moat is not any model — it is calibration discipline plus (now hard-won) reality-verification discipline; that moat only compounds if it is written down as a reusable protocol rather than tribal memory. [C6] Proposed docs/PROTOCOL-VENUE-VERIFICATION.md, mandatory before ANY new market (equities, NFL, anything): (G0.1) pull and archive raw prod market objects; pin contract tests to recorded prod fixtures — catches the *_dollars-class field-format failure; (G0.2) write a settlement-semantics memo quoting rules_primary verbatim and independently reproduce >=10 historical settlements from the public truth source before trusting any truth pipeline — catches the KNYC/KJFK-class failure; (G0.3) enumerate ALL live tickers in the target series and prove the parser covers 100% of them — catches the B-between/T-less-class failure; (G0.4) schedule + monitor truth ingestion from day one — catches the settlement-can-never-fire failure; (G0.5) place one end-to-end paper order against prod data within 2 weeks — catches the trader-that-cannot-trade failure; (G0.6) data-provenance proof: every training row demonstrably constructible at its as_of, with archived-at-ingest vendor pulls — catches the fabricated-lead-1 failure; (G0.7) CV protocol with purging/embargo and effective-sample-size reported next to every manifest stat — catches the 14x pseudo-replication failure; (G0.8) pre-register gate metrics and run the null-model test: a zero-skill baseline must FAIL every gate metric by construction — catches the outcome-conditioned-CLV failure; (G0.9) router/fallback behavior must be loud, never silent; (G0.10) UTC + as_of CI lint. [C7] Each item maps 1:1 to a confirmed audit finding, so this is evidence-derived, not speculative process.

**Expected impact:** Turns a one-time audit into a permanent institutional asset; G0 is the gating checklist for the equities wedge and every future vertical. Estimated to catch the failure classes that invalidated ~100% of prior Phase 2 evidence.

**Effort:** 1-2 days of writing; ~2-3 days to wire the CI-able parts (fixture contract tests, null-model test, UTC/as_of lint) as templates.

**Risks:** Checklist theater if not CI-enforced — keep the enforceable subset in CI and the rest as PR-template checkboxes. Protocol must be versioned as new failure modes are discovered.


#### [P1] Wedge decision: calibrated daily index close-to-close DISTRIBUTION forecasts (realized-vol engine), expressed first on Kalshi index event brackets — confirm the vol-distribution wedge, modify the venue

**Rationale:** [C8] The Renaissance deep-dive P5 recommendation (EMOS-for-vol on liquid ETFs; forecast the close-to-close return distribution, not direction; index before single names) is CONFIRMED as the right forecasting target: it is the exact shape of the weather problem — forecast a continuous physical-ish quantity's distribution, score with CRPS, recalibrate, conformalize. [C9] MODIFICATION: the first trading expression should be Kalshi daily index range/close bracket markets (S&P 500 / Nasdaq-100 series), NOT ETF options, because (a) the entire execution/settlement/fee/paper stack transfers near-1:1 to the venue we already painfully understand, (b) bracket contracts give direct Brier + reliability measurement identical to the current weather pipeline, (c) CFTC event contracts carry zero 10b-5 securities surface and the Compliance Addendum explicitly green-lights index products (SPY/QQQ/SMH listed as unrestricted) — the lowest-compliance equities entry that exists for this owner, (d) retail options spreads/fees would consume a 1-2% distributional edge during the evidence phase. [C10] UNVERIFIED CLAIM, must be G0 step one: that Kalshi's index daily markets exist in 2026 with tradeable liquidity, and their exact settlement value definition (which index print: 4pm ET SPX level vs closing auction vs special calc) — this is precisely the KNYC-class question and nothing proceeds until it is answered from prod rules_primary, not memory. [C11] Rejected alternatives: single-name earnings-move distributions (efficient, options-cost-heavy, nonzero MNPI surface for tech names); CEO-succession event alpha (Pass 2 A2 evidence is genuinely mixed, needs PIT fundamentals + brokerage execution); Cohen-Frazzini supply-chain lead-lag (published-anomaly decay 30-50% per McLean-Pontiff, monthly cadence means years-to-evidence); VIX futures term structure (crowded, margin, tail risk). [C12] The wedge's benchmark structure mirrors weather exactly: HAR-RV is the NDFD analog (the free, hard-to-beat public baseline) and the market-implied bracket distribution is the Pinnacle analog (the efficient price you measure CLV against). [C13] Options expression (defined-risk XSP/SPY structures) is the graduation path AFTER the bracket-level gate passes, not the entry.

**Expected impact:** One wedge, decided, with a falsifiable next step (G0 venue verification). Reuses an estimated 70-80% of the platform by module count. Daily cadence yields ~250 scored events/index/year — same evidence velocity as weather.

**Effort:** Spec doc now: 2-3 days. Post-gate implementation: ~4-6 weeks (3 new clients, vol module, calendar handling) given the platform transfers.

**Risks:** Kalshi index market liquidity may be too thin to matter even on paper (G0 answers this; fallback expression is forecast-only scoring vs implied, trade nothing). Vol forecasting is among the most studied problems in finance — beating HAR-RV by >=5% CRPS is genuinely hard and the honest prior is 'maybe'.


#### [P1] Adopt the transfer map: port the fixed platform, build exactly three new data clients, treat the model core as conceptually-transferred-but-fully-refit

**Rationale:** [C14] Transfers near-1:1 (post-audit-fix versions, by module): src/kq/models/ (NGR/skew-NGR -> distributional regression on returns/vol; calibration.py, isotonic_calibration.py, conformal.py, climatology.py as the defensive prior, drift.py, router.py once the silent-fallback bug is fixed, cv.py/cpcv.py once purging/ESS reporting is fixed); src/kq/execution/ (kelly.py, robust_kelly.py, maker_taker.py, paper.py, fees.py re-parameterized for the index fee schedule); src/kq/backtest/ (engine, metrics with Brier/CRPS, brackets.py, bracket_match.py, synthetic_market.py, diagnostics); src/kq/storage/duckdb_store.py + repository pattern (post-UTC fix); src/kq/clients/kalshi/ (post *_dollars and ticker-coverage fixes, plus one new index ticker parser alongside the existing nba/nfl/pga parsers); dashboard, flows/cron scaffolding, health_check, SOPS+age secrets, structlog + as_of discipline. [C15] Genuinely new, all small: (N1) one equity EOD OHLCV client (Tiingo ~$10/mo or Polygon Starter — OHLCV only, NO fundamentals needed for this wedge, which sidesteps the entire PIT-fundamentals trap documented in Pass 2 A3); (N2) realized-vol module (close-to-close, Parkinson/Garman-Klass/Yang-Zhang estimators + HAR-RV baseline — textbook implementations); (N3) settlement-truth client for the official index print Kalshi settles on, with the G0.2 independent reconciliation; plus trading-calendar/early-close handling (weather never needed holidays) and implied-distribution extraction from bracket prices (identical math to the existing weather implied distribution). [C16] The model COEFFICIENTS transfer 0%: every claim about edge must be re-derived on equity data — the audit's core lesson is that 'the framework worked on weather' is not evidence about anything else. [C17] Cost delta: ~$0-10/month (Tiingo dev tier), inside the existing budget posture; CPU-only holds — HAR-RV, NGR, isotonic, conformal are all trivial compute.

**Expected impact:** Bounds the build to ~4-6 weeks post-gate instead of a rewrite; makes the reuse claim auditable module-by-module rather than vibes-based.

**Effort:** The map itself: half a day to commit as docs/research/EQUITIES-WEDGE-TRANSFER-MAP.md. Implementation effort as in C17/C15.

**Risks:** Hidden weather-specific assumptions in 'shared' modules (e.g., bracket structures, settlement cadence, every-day scheduling) surface during port; budget 20% overrun. Fee model for index markets may differ structurally, not just parametrically.


#### [P1] Pre-register Gate E (the equities Phase-5 analog) in the repo BEFORE the first model commit, with a CI-enforced null-model must-fail test

**Rationale:** [C18] The audit showed two gate metrics were broken in ways that flattered the system (outcome-conditioned mean_signed_clv that a zero-skill favorite-leaning model passes; pseudo-replicated CV stats), proving gates must be written and adversarially reviewed BEFORE results exist, not after. [C19] Proposed Gate E, all must hold to size up from paper: (E1) G0 protocol complete, including >=10 independently reproduced historical settlements; (E2) >=250 settled paper events (~1 year of daily forecasts across SPX+NDX); (E3) CRPS skill >=5% vs HAR-RV baseline AND non-inferior vs the market-implied distribution at entry, via Diebold-Mariano on non-overlapping samples with reported effective sample size; (E4) PIT histogram uniform with no decile off by >10pp, and conformal 90% intervals covering 87-93% empirically; (E5) positive paper P&L net of fees over >=3 months under maker-fill realism accounting; (E6) the CLV analog computed ONLY from pre-entry timestamped quotes (the in-play-leak lesson), defined as implied-distribution movement toward our forecast between entry and close; (E7) all flows 30 days unattended without unrecoverable failure; (E8) the null-model CI test passes: a zero-skill climatology-of-returns model must fail E3-E6 by construction; (E9) compliance memo per COMPLIANCE-ADDENDUM (index event contracts: near-zero surface; evidence-trail logging per rule C anyway; NVDA untouched; blackout calendar observed for any future single-name work); (E10) capital plan written: <=2% of risk capital, 0.15x Kelly as hard-coded caps, identical to Phase 5 items 7. [C20] Critically, the gate is forecast-skill-gated, not P&L-significance-gated, because at the realistic Sharpe ceiling (C22) P&L statistical significance takes ~8 years while paired CRPS comparisons resolve in months — gating on P&L significance would either never pass or pass on noise.

**Expected impact:** Makes the equities wedge falsifiable from day one and immune to the two gate-corruption modes the audit actually caught. The null-model CI test alone would have caught audit finding 8 before it reached a Phase 5 criterion.

**Effort:** 2-3 days to write + adversarially review the metric definitions; ~2 days for the null-model test harness (reuses synthetic_market.py).

**Risks:** Pre-registered thresholds may prove miscalibrated to the domain (5% CRPS skill vs HAR-RV may be too strict or too weak); allow amendment only via the same explicit human sign-off rule CLAUDE.md section 9 applies to Phase 5 criteria.


#### [P2] Build baselines and truth before any model R&D: HAR-RV, implied-distribution ingest, and settlement reconciliation are sprint one

**Rationale:** [C21] Order of operations inside the wedge, mirroring what the audit says the org got backwards on weather (model R&D ran for months while truth ingestion didn't exist and the trader couldn't parse a single prod price): sprint one ships (a) the truth pipeline (official index settlement print, scheduled, monitored, reconciled), (b) HAR-RV baseline forecasts logged daily with as_of, (c) Kalshi index bracket implied distributions snapshotted on the existing orderbook cadence, (d) the daily CRPS scoreboard comparing baseline-vs-implied-vs-(later)-model. Only after 4 weeks of clean scoreboard operation does model work (NGR-on-vol, conformal wrap) begin. This is 'contact with reality first, cleverness second' as an engineering sequence rather than a slogan.

**Expected impact:** Guarantees the first model has a live, honest benchmark on day one; converts the NDFD-benchmark and Pinnacle-CLV patterns (already built for weather/NBA) into their equities analogs cheaply.

**Effort:** ~2 weeks, mostly the three new clients from the transfer map.

**Risks:** Four weeks of 'just plumbing' feels slow next to model work; the audit is the standing answer to that objection.


#### [P2] Commit the economics-honesty memo: this wedge buys evidence and discipline, not income

**Rationale:** [C22] Realistic ceiling per the Renaissance doc Part V 5.6 and 8.3: retail systematic equities Sharpe 0.5-1.0 net (AQR's published live factor numbers run ~0.4-0.7); anything claiming >2 at retail is presumptively overfit. [C23] Capital and dollar reality: paper phase $0; first live allocation per Gate E10 is <=2% of risk capital (~$1-2k if risk capital is ~$50-100k), and Kalshi index bracket liquidity likely caps deployable size at hundreds-to-low-thousands of dollars per day — at a 1-2% net edge per contract that is roughly $500-2,500/year of expected P&L. [C24] The options graduation path at $25-50k of defined-risk capital and Sharpe ~0.7 with a 10% vol target implies ~$1.7-3.5k/year expected — with plausible peak-to-trough drawdowns of 15-25% along the way, which is psychologically expensive relative to the dollars. [C25] Time-to-evidence: CRPS-skill evidence vs HAR-RV resolves in ~6-12 months of daily forecasts; P&L Sharpe significance at 0.7 needs t = 0.7 x sqrt(years) -> ~8 years for t~2, hence C20. [C26] Strategic implication: the wedge's real return is (a) a second, uncorrelated proof that the calibration+verification stack generalizes, (b) the institutional asset that makes any FUTURE equities expansion (single names, options, commercial signals per Pass 3) credible. Judged as income against an NVIDIA salary it is irrational; judged as evidence it is cheap.

**Expected impact:** Inoculates the project against the disappointment-driven pivot to higher-risk expressions (leverage, short vol, single names) when the dollar numbers land small — which they will.

**Effort:** Half a day; one doc.

**Risks:** None material. The risk is NOT writing it and discovering the expectations mismatch 14 months in.


#### [P3] Codify the refuse-list as v2 non-goals in CLAUDE.md before the wedge starts

**Rationale:** [C27] Seductive failure modes, each refused with cause: (R1) single-name prediction, especially semiconductor names where domain expertise feels like edge — compliance surface per Addendum rules A/B, plus expertise-is-not-edge in heavily-analyzed names; locked until the index gate passes AND a separate compliance review. (R2) direction calls (up/down) instead of distributions — the Renaissance doc identifies distributional targets as the right Renaissance-style objective; direction is where retail overfits. (R3) LLM/sentiment features — already a v1 non-goal; provenance-unverifiable inputs are precisely the failure class the audit punishes. (R4) backtest shopping / many-variants-one-dataset — the multiple-testing twin of the CV pseudo-replication finding; mandate pre-registration plus deflated-Sharpe reporting (Lopez de Prado) for any strategy comparison. (R5) adjusted-price look-ahead and vendor-overwritten history — the literal equities twin of fabricated as_of; archive raw vendor pulls at ingest, never backfill features from current vendor state (and this wedge deliberately needs NO fundamentals, sidestepping the worst of it). (R6) systematic short-vol 'income' (naked premium selling) — uncapped left tail is incompatible with a calibration shop; only defined-risk structures, only post-gate. (R7) futures/margin leverage (ES, VIX futures) before evidence. (R8) skipping G0 because 'we already know Kalshi' — index series have their own settlement sources, fee schedules, and tick conventions; the audit proves familiarity is not verification. (R9) selling the signal before the gate (Pass 3 CTA/RIA territory, explicitly deferred). (R10) starting any of this before the P0 sequencing rule (C1-C3) is satisfied.

**Expected impact:** Converts five documents' worth of hard-won judgment into standing instructions future Claude sessions and future-Jason actually load; the existing scope-discipline memory note says the owner is ambitious and needs the guardrail written down.

**Effort:** Half a day; CLAUDE.md edit via PR per repo rules.

**Risks:** Over-rigid non-goals can entomb a good idea; mirror the existing pattern — items move off the list only by explicit human sign-off.


#### [P3] Compliance posture for the wedge: index event contracts are the minimal-surface entry; keep the evidence trail anyway

**Rationale:** [C28] Per COMPLIANCE-ADDENDUM: Kalshi event contracts are CFTC instruments, not securities — no 10b-5 surface at all; and index ETFs/products (SPY, QQQ, SMH explicitly listed) are unrestricted for this owner even in securities form, since no person holds MNPI about an index. [C29] The wedge therefore requires no new legal review to PAPER trade, and only the existing Phase 5-style checks (CPA on tax treatment of Kalshi financial contracts, NVIDIA outside-activities check if/when real money) to go live. [C30] Still log every signal with (source_urls[], retrieved_at, generated_at, model_or_method, reasoning) per Addendum rule C — it is free insurance, it is already the repo's pattern, and it becomes mandatory the day single names or commercialization are ever revisited.

**Expected impact:** Removes compliance as a blocker or excuse for the index wedge while preserving the audit trail that any future expansion will require.

**Effort:** Zero new build (evidence-trail logging already exists in the platform pattern); one memo at Gate E9.

**Risks:** Tax treatment of Kalshi index/financial contracts may differ from weather event contracts (1256 question) — flag to the CPA engagement that Phase 5 item 9 already requires.


---

## Seat 4 — CEO-Advisor, Competitive Thesis & Product

### Honest assessment

CONTEXT (claims numbered as requested; sources are repo docs at /Users/jloo/Documents/GitHub/forecast-lab/).

(1) Governing fact: the 2026-06-11 audit (docs/SESSION-2026-06-11-AUDIT.md) found 11 direct-evidence root causes. 1,101 tests green, mypy --strict clean, 82% mutation kill — and neither vertical can place a single prod paper trade: prices parse as None (*_dollars fields), 4/6 weather brackets invisible (B-markets), low-tail semantics inverted, NY models the wrong station (KJFK vs Central Park/KNYC), NBA sees 0 markets and would double-trade both sides, settlement truth is never ingested, and the 'lead-1' backtest data is ~lead-0 with fabricated as_of (residual std 1.3F vs true lead-1 ~4.6F). Every strategic claim below is conditional on fixing this first; today's honest edge estimate is 'unknown, prior evidence invalid.'

PART 1 — WHERE A SOLO STRUCTURALLY WINS VS QUANT FIRMS.
(2) Cannot win: latency, breadth, microstructure. Decimalization (2001) and Reg NMS (2007) compressed stat-arb edges 90%+; surviving Medallion-class edges are short-horizon, market-making-adjacent, and 'not accessible at retail, period' (RENAISSANCE-DEEP-DIVE Part V §5.3). The RIEF/RIDA gap (§5.5) shows even Renaissance's edge mostly does not survive scale or openness.
(3) Can win, structurally, in four stacked conditions (§5.7, §8.4): (a) capacity-limited markets institutions ignore — Kalshi weather is roughly $75k–150k/day notional fleet-wide (see claim 7), i.e. 4–6 orders of magnitude below a Citadel/Jane Street minimum viable opportunity; Shleifer-Vishny limits-to-arbitrage means they structurally will not show up; (b) physical ground truth — weather skill is measurable against reality (CRPS/Brier vs observed Tmax) independent of any market, which sports and equities never offer; (c) new/young markets per Lo's Adaptive Markets Hypothesis — edges live where the participant ecosystem hasn't adapted; (d) settlement-rules arbitrage — the Central Park discovery is the proof-of-class: KXHIGHNY settles on KNYC per prod rules_primary while our own pipeline (and plausibly competitors') models KJFK, which diverges several degrees F on sea-breeze days. Reading rules_primary is itself alpha.
(4) Vertical map. Kalshi weather: WINNABLE — all four conditions stack; sustainable target 1–3% net per resolved contract (deep-dive §8.3, §5.6). NBA: MARGINALLY winnable, only as Pinnacle-anchored arb on Kalshi during liquidity air-pockets (off-peak games trade 3–5c off Pinnacle, PASS-1 §1c); beating Pinnacle's own close by >2% CLV sustained is 'extraordinary' (§5.6) — do not plan on out-modeling it. NFL: same structure (Pinnacle h2h anchor verified live per MULTI-SPORT-NFL-PGA-DESIGN), but only ~285 games/yr; at the ~500-bet minimum to trust results and ~4,300 bets to prove a 3% edge at p=0.05 (PASS-1 §1e), NFL is a 2+ season evidence commitment — breadth test, not a money plan. PGA: NOT currently winnable — golf outrights carry NO Pinnacle anchor (verified live), so there is no truth metric; without a CLV anchor a solo cannot separate edge from variance in 150-player fields. Equities: NOT winnable as trading edge (retail systematic ceiling Sharpe 0.5–1.0 net, §5.6); valuable only as the 12–24-month skill expansion (§8.4 ordering: physical -> sports -> reflexive markets).

PART 2 — MONEY MATH AT TODAY'S LIQUIDITY.
(5) Observed: OI ~3k–25k contracts, ~25k contracts/day volume on a top bracket. Assume per-station all-bracket volume ~35–50k contracts/day x 6 stations = 210k–300k contracts/day; at ~$0.35 avg price = ~$75k–105k/day market-wide notional.
(6) A passive maker can capture ~2–5% of daily volume before becoming the dominant quote and eating adverse selection: 4k–15k contracts/day = ~$1.5k–5k notional/day = ~$0.5M–1.6M/yr turnover over ~330 trading days.
(7) At 1–3% net edge on turnover: $5k–50k/yr gross; central estimate $15k–30k/yr at TODAY's liquidity, with full execution skill. Cross-check against ROADMAP's own numbers: central case 80–120 bps at the 50c centerline = ~+81%/yr on a $1k bankroll at ~2,500 trades/yr; pessimistic 30–60 bps = +31%; and the venue base rate is brutal (Kalshi pre-fee average return −20% per the Whelan/UCD citation in ROADMAP).
(8) Saturation: book depth inside the BBO (roughly $100–$1k refreshing per bracket) binds long before the $25k/market position limit. Marginal edge dollars go to ~zero beyond a ~$15k–40k weather bankroll. Consequence: a $5k bankroll can plausibly compound at 50–150%/yr; a $100k bankroll earns ~5–20% on the identical trades. This is a high-ROI, hard-capped-dollar niche: realistic ceiling $20k–60k/yr if everything works, with free optionality on Kalshi's growth (volume grew >10x in 2025; sports already 89% of Kalshi revenue) — venue growth you don't control but ride for free.
(9) NBA adds capacity but thinner edge: 0.5–1.5% realized CLV-arb on $100k–500k/yr turnover = $1k–7k/yr in years 1–2. Combined year-1 expectation is unchanged from README: −5% to +15% on a $3–5k bankroll. The ceiling figures are year-2/3 outcomes conditional on proven, re-derived edge.

PART 3 — PRODUCT PATH.
(10) Prop trading (own bankroll): legally cleanest for an NVIDIA-employed solo — Kalshi event contracts are CFTC instruments with no securities surface (COMPLIANCE-ADDENDUM); outstanding items are only Phase 5 #9 (CPA, §1256 ambiguity) and #10 (NVIDIA outside-activities disclosure). Economically capped per claim 8.
(11) Signals subscription: capacity-uncapped but behind a real legal cliff — potential CTA/NFA registration, Advisers Act questions, state gambling-advertising rules for sports picks, and tipper liability if any signal touches a name where MNPI exists; PASS-1 §1e.5 and the addendum both require counsel + LLC before charging anyone. It is also economically premature: a signal product sells a verified track record (PASS-1 sets ≥1,500 logged trades as the credibility bar) — and the audit just invalidated all existing evidence. There is currently nothing to sell.
(12) SaaS/tooling (calibration infra, Kalshi data + settlement-rules analytics, no trade recommendations): lowest legal risk, and best aligned with the actually-demonstrated asset (verification infrastructure), but small TAM (hundreds to low thousands of prediction-market quants) — a $10k–100k/yr business at best.
(13) Verdict: prop-first for 12 months. The publicly auditable trade log (source_urls, retrieved_at, as_of — already mandated by the evidence-trail rule) is the embryo of any later product. Decide signals-vs-SaaS at month 12 with counsel only if a clean 500+ settled-trade record with positive P&L exists. Spending on LLC/counsel before edge is proven is buying a storefront with no inventory.

PART 5 — WHAT THE AUDIT TEACHES ABOUT THE MOAT.
(14) The audit IS the moat thesis, demonstrated: every conventional quality gate passed while the system was incapable of trading, because all 1,101 tests mocked an unverified reality. Modeling skill is abundant — NGR/EMOS is public literature and competitors run the same math. The scarce asset is reality-verification discipline: probing live payloads found *_dollars; reading rules_primary found Central Park; checking residual std against physical plausibility found the fake lead-1 data. Each check is simultaneously a bug fix and an alpha source, because at $100k/day market size nobody else's engineer-hours pencil out for that scrutiny — yours do. That asymmetry is the entire business.
(15) This is also the replicable core of Renaissance per the deep-dive's closing assessment: hypothesis-test-verify discipline, calibration as a first-class concern, execution hygiene — not models, not secrets. Institutionalized (recorded-prod fixtures, weekly rules_primary diffing, physical-plausibility assertions on every training dataset, a 'verify the venue's reality first' gate per new vertical), it transfers intact to NFL, PGA, and equities.

BOTTOM LINE: You do not beat quant firms; you operate where they are structurally absent — capacity-capped, physically-grounded, young markets with quirky settlement rules. At today's liquidity that is a $20k–60k/yr-ceiling prop operation with high ROI on small capital, free optionality on Kalshi's growth, and a credibility-based product option at month 12+. As of today, every claim of edge is unproven: the first and only accuracy lever is fixing reality contact and re-deriving all evidence from true lead-1 data (the GEFSv12 reforecast archive already in the repo). The discipline that found these failures is rarer than the modeling that produced them — productize the discipline.

### Recommendations


#### [P0] Months 0-1: Land the P0 reality-contact series (PR-A through PR-G) before any model or strategy work

**Rationale:** Audit claims 1-7/10-11: prices parse as None, 4/6 brackets invisible, inverted low-tail semantics, wrong NY station, NBA sees 0 markets and double-trades sides, no truth ingest, biased gate metric, broken router dispatch. Until these land, annual revenue is exactly $0 and every cron-hour of 'uptime' is fake progress. The ordered fix plan already exists in docs/SESSION-2026-06-11-AUDIT.md.

**Expected impact:** Unblocks 100% of revenue; converts the Phase 5 clock from fictional to real. Without it, all other recommendations are void.

**Effort:** 2-4 weeks solo (7 ordered PRs, mostly parser/flow surgery; no new modeling).

**Risks:** Fixing #1 without #3 would start placing exactly-inverted bets — land PR-A and PR-B together. Scope creep into model R&D during the fix series is the classic failure mode; resist it.


#### [P0] Months 1-3: Re-derive ALL evidence from true lead-1 data and honest statistics

**Rationale:** Audit claims 6-9: training/backtest data was ~lead-0 with fabricated as_of (residual std 1.3F vs true 4.6F); rolling-origin CV with step_size=1 pseudo-replicates every day ~14x; mean_signed_clv passes zero-skill favorite-leaning models and leaks in-play quotes. The '3/6 stations beat NDFD' verdict, router config, and the negative analog/null reforecast verdicts are all invalid. The GEFSv12 reforecast archive already in the repo is real lead-1 — use it, set step_size=test_window_size, dedup per (station, valid_date), and redefine CLV as entry price vs devigged pre-tipoff close.

**Expected impact:** Produces the first honest answer to 'do we have edge at all.' Expect numbers materially worse than the invalid ones; a true 3-8% Brier improvement vs NDFD at 2+ stations would still clear the economic bar in claims 5-8.

**Effort:** 4-8 weeks including full manifest regeneration and re-running every model verdict (analog, reforecast-NGR, router).

**Risks:** The honest re-run may show no edge at some or all stations. That is a success of the process, not a failure — it prevents funding a zero-skill strategy with real money. Sunk-cost attachment to the old verdicts is the risk to manage.


#### [P0] Months 0-12 (permanent): Institutionalize venue-reality verification as the moat

**Rationale:** Claims 14-15: all 11 root causes sat at the code-reality boundary and survived 1,101 green tests. The scarce, transferable, un-replicable-at-this-scale asset is the discipline that found them. The audit's own prescription: recorded-prod-payload fixtures in the test matrix, a weekly live rules_primary diff probe, physical-plausibility assertions on training data (e.g., reject any 'lead-N' dataset whose residual std is physically impossible for that lead), and a mandatory 'verify payload + semantics + settlement source FIRST' checklist gating every new vertical (NFL, PGA, equities).

**Expected impact:** Prevents the entire class of silent reality drift; doubles as an alpha source — the Central Park discovery shows settlement-rules scrutiny finds mispricings competitors inherit. This is the only durable moat a solo operator has.

**Effort:** 1-2 weeks initial (fixtures + weekly probe cron + checklist doc), then near-zero marginal.

**Risks:** Minimal. Main risk is treating it as one-time cleanup instead of standing infrastructure.


#### [P1] Month 1: Audit all 6 stations' settlement sources; add KNYC/Central Park end-to-end

**Rationale:** Claim 3d/4: KXHIGHNY settles on Central Park, not KJFK — and only Chicago/Midway was confirmed matching. Pull rules_primary for all six series, diff against pipeline station keys, add KNYC (Open-Meteo coords, ACIS, METAR), retrain NY. Offensively: any competitor still modeling KJFK misprices KXHIGHNY on every sea-breeze divergence day — this is the most concrete, immediately-monetizable edge identified all year.

**Expected impact:** Fixes one of six stations outright (~17% of weather surface); potential recurring edge on NY divergence days worth several percent on that station's volume.

**Effort:** ~1 week (PR-C in the audit fix plan) plus NY retrain after the lead-1 data fix.

**Risks:** KNYC METAR/forecast data quality differs from airport stations (park siting); verify ACIS coverage before trusting the retrain.


#### [P1] Months 2-6: Accumulate 500+ settled paper trades on the FIXED pipeline; gate any real money on clean-evidence Phase 5 criteria with the tiered ramp

**Rationale:** Claims 7-9: README/PASS-1 sample-size math stands — ~500 settled trades minimum before any result is trustworthy, ~4,300 to prove 3% edge at p=0.05. The Phase 5 truth table says the clock restarts only after P0s. If gates pass on re-derived evidence, ramp per PASS-1 §2f: month 1 at 10% of intended bankroll, then 25/50/100% only while live Brier and CLV match paper within tolerance, with the coded kill-switches (daily -3%, weekly -8% halts) made true hard caps (audit found 0.15x Kelly is currently a default, not a limit).

**Expected impact:** Converts the project from 'invalid evidence' to a defensible track record — the prerequisite asset for both real-money scale-up and any future product per claims 11-13.

**Effort:** Mostly elapsed time + cron uptime; ~days of code for hard-cap enforcement and paper-summary label fixes.

**Risks:** Honest paper results may land in README's -5% to +15% band — i.e., indistinguishable from zero in year 1. Pre-commit to the statistical bar so a lucky quarter doesn't trigger premature sizing.


#### [P2] Months 4-12: NBA with the honest CLV metric through next season; NFL as paper-only breadth test from September; PGA stays shelved

**Rationale:** Claim 4: NBA is winnable only as Pinnacle-anchored air-pocket arb (3-5c gaps on off-peak games), measurable only after the CLV metric is rebuilt price-based with a pre-tipoff anchor and one-side-per-game dedup (audit #5/#6/#10). NFL has a verified Pinnacle anchor and the multi-sport library already shipped, but ~285 games/yr means evidence takes 2+ seasons — run it as paper-only validation of the verify-first checklist. PGA has no sharp anchor (verified), hence no truth metric, hence no disciplined way to trade it: explicitly deferred until an anchor exists.

**Expected impact:** NBA: $1k-7k/yr realistic in years 1-2 (claim 9) plus the larger option on Kalshi sports liquidity (89% of venue revenue). NFL: zero year-1 dollars, but proves the playbook generalizes. PGA: $0 by design — avoiding an unmeasurable vertical is positive expected value.

**Effort:** NBA fixes are inside PR-D/PR-E (~1-2 weeks); NFL paper wiring ~2-3 weeks off the existing branch, in season.

**Risks:** Honest CLV may show the prior NBA 'edge' was entirely the metric bias. Sports-state legal availability (CA currently green) can change; re-check before any live sports dollar.


#### [P3] Month 12: Commercialization gate review (signals vs SaaS) with counsel — not before; keep the auditable public trade log as the product seed

**Rationale:** Claims 10-13: prop trading is the only path that is legally clean today for an NVIDIA-employed solo. Signal-selling triggers CTA/NFA, state gambling-ad rules, and tipper-liability questions (PASS-1 §1e.5 + COMPLIANCE-ADDENDUM: counsel + LLC required before charging anyone), and there is nothing to sell until a verified 500-1,500-trade record exists. SaaS tooling is legally lighter but small-TAM. The evidence-trail log (source_urls, retrieved_at, as_of) being built anyway IS the future product's credibility layer — publishing a verifiable, timestamped forecast log (free, no paywall) builds the audience and the proof simultaneously with zero legal surface.

**Expected impact:** Preserves full option value on a capacity-uncapped product while spending $0 on legal structure before edge exists; a verified public log is the rarest marketing asset in this niche (claim 11: competitors' win-rate claims are unaudited marketing).

**Effort:** Near-zero until month 12 (the log already exists by mandate); then one counsel engagement (~$2-5k) if gates pass.

**Risks:** Publishing even free signals while holding MNPI on a specific name creates tipper risk — the addendum's narrow rule must gate the publisher. NVIDIA outside-activities disclosure (Phase 5 #10) should be cleared before anything public-facing.


#### [P2] Ongoing: Right-size capital and expectations to the saturation math; do not add bankroll past ~$25k for weather; ride venue growth as free optionality

**Rationale:** Claims 5-8: edge saturates at a $15k-40k weather bankroll because BBO depth ($100-$1k per bracket) binds far below the $25k position limit; ceiling $20k-60k/yr at today's liquidity. The correct posture is small capital at maximum ROI, not raising stakes into a capacity wall. Kalshi volume grew >10x in 2025 — if weather liquidity follows sports, the same pipeline's ceiling scales with zero additional work; if it doesn't, capital wasn't over-committed.

**Expected impact:** Prevents the most common solo-quant capital error (scaling a thin-market edge until it disappears); keeps day-job income (claim from PASS-1: this is not a path to quitting NVIDIA) as the actual bankroll engine.

**Effort:** Zero code; one paragraph in BANKROLL-PLAN.md and discipline.

**Risks:** Opportunity cost if Kalshi weather liquidity 10x's suddenly — mitigated by re-running the saturation math quarterly from live book snapshots already being collected.
