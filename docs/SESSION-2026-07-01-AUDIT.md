# Session audit — 2026-07-01 (P0 SERIES COMPLETE: honest evidence, honest verdict)

One-sprint close-out of the [2026-06-11 reality-contact audit](SESSION-2026-06-11-AUDIT.md)'s
P0 fix series (PR-A…PR-H, 14 commits), plus a second multi-agent audit round
(9 subsystem sweeps + adversarial panels + 3 UX graders) run in parallel with
the fixes. Supersedes 2026-06-11 as the bootstrap snapshot.

## Headline

**The P0 reality-contact series is COMPLETE (PR-A…PR-H, all landed 2026-07-01),
and the regenerated evidence says: 0 of 6 stations clear the Phase 5 #2 bar.**
The void claim was 3/6.

- Every 2026-06-11 root cause is closed: prod payloads parse, all three strike
  types price and settle correctly, NY models Central Park, NBA discovery works
  one-side-per-game, CLV is a real pre-tipoff price metric, observed truth
  ingests on cron, tz conventions are normalized, caps are enforced clamps, and
  the lead-0-masquerading-as-lead-1 training data is dead — regression-pinned
  against return.
- Evidence was regenerated on **true lead-1** data (Open-Meteo Previous Runs
  API, LST-day aggregated), non-overlapping CV, per-(station, valid_date,
  bracket) dedup: **n = 3,822 honest evaluations per station** (the old KJFK
  manifest claimed 28,616 — 14× replicated). Residual σ is now physically
  plausible (2.1–3.9°F vs the impossible 1.36°F).
- **The honest verdict: no station beats NBM at ≥2–3%.** `kq router-summary`
  now exits 1. The Phase 5 clock can restart on honest foundations, but
  **the model-improvement lane is the new critical path** — the machinery is
  fine (NGR beats its own raw input everywhere); the deterministic-GFS input
  is simply much weaker than NBM.
- Also this sprint: one-command onboarding (`install.bat`/`install.sh` →
  `kq setup` wizard), a 57-item docs freshness sweep, and a plain-language
  dashboard pass (UX grade was D).

18/18 previously-unverified 2026-06-11 findings were CONFIRMED by this round;
8 were fixed in-sprint, 10 are now P1. The fresh sweeps produced **74
panel-confirmed findings** (3 refuted); 7 distinct ones were fixed concurrently
(PR-B/E/F/G/H); the rest are the next sprint's backlog (§P1).

## What landed (oldest first)

| # | Commit | PR | One-line |
|---|--------|----|----------|
| 1 | `21b655b` | PR-A.5 (#102) | `kq doctor` — live reality-contact diagnostics + weekly probe; first run surfaced NY CRIT + truth 367d stale |
| 2 | `e2266e2` | dev-env | Native-Windows dev environment (eccodeslib marker, loopback-exempt egress guard) + reusable dev agent |
| 3 | `bb96657` | PR-B | Strike-aware pricing + settlement for greater/less/between; half-integer boundaries tile Σp=1; LST day-completion guard; strike fields persisted |
| 4 | `a559e31` | onboarding | One-command install, `kq setup` 4-step wizard, `kq dashboard` launcher, `kq` console script, GETTING-STARTED.md |
| 5 | `930089b` | chore | Executable bit recorded on `install.sh` |
| 6 | `55ee6d5` | docs | Freshness sweep — 57 stale items corrected across 9 living docs, verified claim-by-claim against HEAD |
| 7 | `f1f5986` | PR-C | KXHIGHNY models Central Park (KNYC), not JFK; KJFK removed from STATIONS; doctor settlement-source check flips green |
| 8 | `06fda8f` | PR-D | NBA cursor pagination + `series_ticker` discovery, one-side-per-game, pre-tipoff guard, GameContext + season-boundary Elo wired |
| 9 | `ffd8559` | PR-E | True price-based CLV (devigged pre-tipoff close − entry); `mean_signed_*` metrics deleted; `paper_summary` gate labels honest |
| 10 | `591cf0c` | PR-G | Naive-UTC normalization (shared `storage/_tz.py`), `kq ingest-observed` truth lane + cron, atomic backups, true hard caps |
| 11 | `4841470` | PR-G follow-up | Stale data escalates WARN→CRIT at 3× max age so a dead cron stack actually pages |
| 12 | `a2f4800` | dashboard UX | Plain-language pass — every number explains itself; presentation-only (zero metric/gate changes) |
| 13 | `62ab9d6` | PR-H | Hardening: fail-closed strike guard on prod, NBA finality freeze, (model, ticker) signal keys |
| 14 | `8eca464` | PR-F | True lead-1 data, honest CV, explicit router dispatch, **full evidence regeneration** |

PR-A (`fa3c604`, #101, prod payload adapter) landed just before this sprint.
Gates at HEAD: 1,254 passed / 1 skipped, ruff + format clean, mypy --strict
clean (122 files), on native Windows.

## The honest verdict (Phase 5 #2)

Old = committed void manifests (lead-0 inputs + 14× pseudo-replication, ROADMAP
post-#95 table). New = regenerated 2026-07-01 on 2024-11-01→2026-06-30
(607 days), true lead-1 `gfs_prevday1`, non-overlapping windows, deduped.
Metric: Brier improvement vs NBM-deterministic benchmark (bar: ≥2–3%).

| Station | Void claim | Honest (routed strategy) | NGR vs raw input | Calibration (≤10pp bar) |
|---------|-----------:|-------------------------:|-----------------:|--------------------------|
| KLAX | **+40.8%** (raw) | **−19.7%** (ngr) | +12.7% | ❌ FAIL — max bin Δ 11.1pp |
| KMIA | **+8.9%** (raw) | **−39.0%** (raw; ngr −40.0%) | +21.9% | ✅ PASS |
| KJFK→KNYC | −2.0% (ngr-skew) | **−43.5%** (ngr) | +15.6% | ✅ PASS |
| KDEN | −2.9% | **−24.7%** (ngr) | +4.4% | ❌ FAIL — max bin Δ 13.7pp |
| KAUS | −14.5% | **−45.4%** (ngr) | +10.7% | ✅ PASS |
| KMDW | −51.1% (raw) | **−50.2%** (ngr) | +6.8% | ✅ PASS |

n = 3,822 per station (vs 28,616 replicated); residual σ 2.1–3.9°F (KAUS 3.14,
KDEN 3.89) vs the old impossible 1.36°F. NY is not comparable across columns
(old = wrong station).

**Interpretation.** NGR beats its own raw input at every station (+4–22%) —
the bias-correction/calibration machinery works, and 4/6 stations pass the
reliability bar on honest data. What fails is the *input*: a single
deterministic GFS at true lead-1 is much weaker than NBM, which blends
multiple models plus human forecaster edit. The 2026-06-11 diagnosis stands
confirmed end-to-end: the old evidence was an artifact of leaked lead-0 data.

**Caveats — both cut AGAINST us, so the honest number is if anything
pessimistic:** (a) the NBM benchmark still comes from Open-Meteo's
freshest-archived-run history, i.e. ~lead-0 — our lead-1 model is being graded
against a benchmark with a data advantage; (b) the backfill is single-model
deterministic GFS, while the live pipeline ingests GEFS + ECMWF ensembles —
live inputs are richer than what this backtest could see.

**Next levers (model-improvement lane, the new critical path):**

1. **Ensemble previous-runs coverage** — extend the Previous Runs backfill to
   `ecmwf_ifs025` previous-day (true lead-1 ECMWF alongside GFS; ensemble
   spread would also feed the currently-dropped `d·ens_var` NGR term).
2. **NBM previous-day probe** — check whether Open-Meteo serves
   `*_previous_day1` for the NBM model; a true-lead-1 benchmark would remove
   caveat (a) and may materially shrink the gap.
3. **Fix `ingest_ecmwf_opendata` mx2t24** — still UTC-aligned (and off-by-one,
   confirmed finding below); the lane exists precisely to A/B against NBM and
   currently can't join.
4. GEFSv12 reforecast pull (real lead-1 ensemble archive) remains available
   for a deeper training window; the void reforecast manifest was deleted.

## Audit round 2 — the 18 known findings: 18/18 CONFIRMED

Every "pending verification" item from 2026-06-11 was re-verified by dedicated
agents against the tree: all real. Eight died in-sprint; ten are OPEN → P1.

| Finding | Status |
|---------|--------|
| settlement-day-completion-guard | ✅ FIXED (PR-B — LST day-completion guard) |
| tzaware-datetime-min-crash | ✅ FIXED (PR-B — duplicate-market tiebreak) |
| elo-dead-code-gamecontext | ✅ FIXED (PR-D — GameContext + season regression wired) |
| paper-summary-wrong-gates | ✅ FIXED (PR-E — Phase 2 vs Phase 5 labels split) |
| stale-data-never-alerts | ✅ FIXED (PR-G follow-up — WARN→CRIT at 3×) |
| backup-script-unsafe | ✅ FIXED (PR-G — CHECKPOINT + temp+mv, fail-loud) |
| kelly-cap-is-default | ✅ FIXED (PR-G — 0.15×/$200 enforced clamps at the choke point) |
| utc-lst-aggregation | ✅ FIXED (PR-F — exact LST-day aggregation via `Etc/GMT+N`) |
| fee-rounding-per-contract | 🟥 OPEN → P1. Kalshi rounds per FILL; `fees.py:69` ceils per contract; all consumers replicate it |
| bankroll-no-reservation | 🟥 OPEN → P1. Sizing bankroll ignores open-trade stake; fix = `starting + settled_pnl − open_stake` |
| ndfd-lead-mixed-tz | 🟥 OPEN → P1. Live NDFD lead mixes local valid_date with UTC now → off-by-one at 00Z/06Z ticks |
| backtest-maker-paper-taker | 🟥 OPEN → P1. Backtest defaults maker fills; paper trader is taker-only — "mirror" claim false |
| cpcv-one-sided-purge | 🟥 OPEN → P1. Trailing-side label overlap unpurged unless embargo covers it |
| nowcast-one-sided | 🟥 OPEN → P1. METAR update can only raise the mean while σ shrinks → near-certain YES on lost brackets |
| ngr-ens-var-dropped | 🟥 OPEN → P1. `d·ens_var` never passed at inference; σ² silently degrades to c (ties into ensemble lever above) |
| maker-fill-rate-dead | 🟥 OPEN → P1. `BacktestConfig.maker_fill_rate` documented but never consumed |
| qty-floor-overrides-kelly | 🟥 OPEN → P1. `qty=max(1,…)` floors override Kelly at small stakes (paper.py + engine.py) |
| dashboard-dead-log-panel | 🟥 OPEN → P1. "Background ingest cron" panel globs log files nothing writes |

## P1 backlog — the fresh confirmed findings

9 subsystem sweeps produced 77 findings; adversarial panels (typically 2–6
votes each) confirmed **74**, refuted 3. The audit ran against the PRE-sprint
tree, so 7 distinct findings (10 entries; the big ones appeared in 2–3 sweeps)
were already fixed by this sprint's PRs — three of them deliberately, as
**PR-H**: the fail-open strike guard, mid-game NBA finality, and UTC-midnight
signal-id splitting. Also fixed concurrently: router non-NGR fall-through
(PR-F), P(T>floor) vs floor+1 pricing (PR-B half-integer boundaries), naive-UTC
repo normalization (PR-G), and the outcome-contaminated CLV anchor (PR-E).

**~61 distinct items remain** (cross-sweep duplicates merged). Ordered by
priority tier; severity/file from the sweep reports, all panel-confirmed.

### Tier 1 — settlement & money-path integrity (do these first)

| Sev | Finding | File |
|-----|---------|------|
| high | Elo fallback trades with zero data: unknown teams silently rate 1500 → ~0.64 home prob clears the edge gate; bogus confident signals on a fresh/empty DB | `src/kq/models/nba_elo.py:96`, `flows/paper_nba_trade.py` |
| med | `evaluate_market` rejects prod one-sided-book sentinels (bid `0.0000`/ask `1.0000`) — the executable side of every one-sided book is untradable (2 sweeps) | `src/kq/execution/paper.py:125` |
| med | Paper fills ignore quoted size — `Market` drops `*_size_fp`; qty can exceed displayed liquidity by orders of magnitude | `src/kq/execution/paper.py:166`, `clients/kalshi/_parsers.py:30` |
| med | `upsert_kalshi_markets` INSERT OR REPLACE lets one degraded payload NULL the stored strike fields — the table settlement reads as point-in-time truth | `src/kq/storage/repositories/kalshi.py:38` |
| med | `insert_observed` OR REPLACE wipes settlement truth with NULL when ACIS re-serves 'M' for a populated day | `src/kq/storage/repositories/observed.py:30` |
| med | `upsert_nba_games` OR REPLACE regresses recorded finals to NULL/empty on partial ScoreboardV2 responses (2 sweeps; PR-H froze `home_won`, the rest of the row still regresses) | `src/kq/storage/repositories/nba.py:53` |
| med | NBA settlement has no VOID path; date-keyed lookup permanently orphans postponed/rescheduled games | `src/kq/storage/repositories/paper_trades.py:343` |
| med | ACIS client returns [] on an HTTP-200 `{"error": …}` body — station outage indistinguishable from zero rows; settlement waits forever, cron green | `src/kq/clients/acis.py:94` |
| low | Kelly sizing ignores fee drag — stake from fee-free odds while the edge gate is fee-aware; one-directional over-size | `src/kq/execution/kelly.py:23` |
| low | `MakerTakerPolicy.decide` boundary contradicts its own documented contract (and the Pass-1 rule it cites) | `src/kq/execution/maker_taker.py:85` |
| low | `_clean_ladder_dollars` admits size-0.00 levels → phantom top-of-book; legacy cents cleaner has no validation at all | `src/kq/clients/kalshi/_parsers.py:104,120` |
| low | One `SELL_YES`/`SELL_NO` row (schema-documented values) permanently crashes every settle pass via `_as_side` | `src/kq/storage/repositories/paper_trades.py:381` |
| low | `mark_paper_trade_settled` returns 1 for rows it did not update (already-settled) | `src/kq/storage/repositories/paper_trades.py:200` |
| low | `insert_paper_trade_with_signal` claims atomicity; is two autocommitted INSERTs + non-transactional precheck | `src/kq/storage/repositories/paper_trades.py:79` |

### Tier 2 — silent-failure client / model / backtest paths

| Sev | Finding | File |
|-----|---------|------|
| high | ECMWF Open Data ingest stores mx2t24 under the wrong valid_date (off-by-one; also picks unpublished cycles 3 of 4 ticks) — blocks the A/B-vs-NBM lever | `src/kq/flows/ingest_ecmwf_opendata.py:199` |
| high | GEFSv12 reforecast fetcher silently swallows per-file failures → undetectable holes in any future training pull | `src/kq/clients/gefs_reforecast.py:507` |
| high | Weather backtest has no same-day dedup across the fold boundary: multiple live-ingest rows per (station, day) straddle folds and leak test-day labels into fits (matters as live 6-hourly history accumulates) | `src/kq/backtest/engine.py:215` |
| med | Backtest 'reforecast' strategy silently substitutes per-fold NGR/skew when the pre-fit model is missing, results stay labeled reforecast (2 sweeps; runtime router fixed by PR-F, engine path not) | `src/kq/backtest/engine.py:354` |
| med | `decide-router` selects per-station strategy on the same window it is then evaluated on — winner's-curse in-sample selection reported as OOS skill | `src/kq/flows/decide_router.py:76` |
| med | `max_drawdown` omits the starting-bankroll point — losses before the first peak are invisible; pct anchored to wrong peak | `src/kq/backtest/metrics.py:36` |
| med | NDFD benchmark lookup hard-codes lead_days=1 while the model side honors `cfg.lead_days` — any lead>1 backtest compares against a mismatched benchmark | `src/kq/backtest/engine.py:187` |
| med | NBM qmd station sampling uses `.sel` on 2-D lat/lon of a Lambert-conformal grid — raises on first real use | `src/kq/clients/nbm_qmd.py:251` |
| med | Open-Meteo `run_time` is fabricated from fetch time (the payload keys probed don't exist in the API) | `src/kq/clients/openmeteo/_parsers.py:89` |
| med | Full-form NGR fit accepts Nelder-Mead output unconditionally (no `result.success` check, no worse-than-seed fallback, unbounded `exp`) — skew sibling does all three | `src/kq/models/weather_ngr.py:144` |
| med | Elo MOV multiplier omits home-court advantage from the winner's Elo diff — ~8% biased K per game by venue vs the cited 538 formula | `src/kq/models/nba_elo.py:201` |
| med | Elo replay pools preseason/exhibition games — `season_type` stored but never filtered anywhere | `src/kq/flows/paper_nba_trade.py:258` |
| low | One unrecognized status/timestamp row aborts the entire NBA injury CSV ingest | `src/kq/clients/nba_injuries.py:137` |
| low | `ingest-nba-schedule` anchors its window to the UTC date; 00:00–05:00 UTC ticks never cover "yesterday ET" finals | `src/kq/flows/ingest_nba_schedule.py:46` |
| low | `weather_forecast.member` documented "NULL for deterministic" but PK-NOT-NULL — first HRRR/GFS deterministic ingest crashes the batch | `src/kq/storage/schemas.sql:9` |
| low | `fetch_latest_per_player` serves permanently-stale rows for traded players when filtered by team | `src/kq/storage/repositories/nba_injuries.py:90` |
| low | `request_json` raises raw JSONDecodeError on a 200 non-JSON body — bypasses the retry a 502 would get | `src/kq/clients/_http.py:54` |
| low | ECMWF cycle-lookback loop is dead code (`for … return`); flow tolerates one missed cycle, docstring promises four | `src/kq/flows/ingest_ecmwf_opendata.py:98` |
| low | `iter_reforecast_files(days_per_year=366)` crashes on any non-leap year, per its own docstring advice | `src/kq/clients/gefs_reforecast.py:171` |
| low | `metar_updated_proba` shrinks σ by elapsed-day fraction with ZERO observations — contradicts its "degenerates to the prior" contract | `src/kq/models/nowcast.py:92` |
| low | `WeatherSkewNGRModel.predict_distribution` returns (ξ, ω, α) — breaks the (mu, sigma) drop-in interface it advertises | `src/kq/models/weather_skew_ngr.py:235` |
| low | Rolling-origin folds have no as_of-aware embargo (lead-1 boundary label not yet settled at signal time) | `src/kq/models/cv.py:47` |

### Tier 3 — ops / logging / alerting

| Sev | Finding | File |
|-----|---------|------|
| high | Total venue-contact loss (all fetches fail / all series 0 markets) is WARN-only — the weekly probe never pages on the audit's exact silent-zero class | `src/kq/flows/doctor.py:110` |
| high | Doctor opens the live DB read-WRITE and silently creates an empty DB on a bad path; unreadable truth = WARN while empty = CRIT (inverted) | `src/kq/flows/doctor.py:266`, `storage/duckdb_store.py:19` |
| high | `reality-probe.sh` invokes bare `uv` — exit 127 under the documented minimal cron PATH; the probe never actually runs | `scripts/reality-probe.sh:10` |
| high | structlog wired to stdout only — `--log-file` (and stderr handler) never receive application logs | `src/kq/_logging.py:119` |
| high | Dashboard leaks an open DuckDB connection on exception — holds the file lock that blocks every cron writer | `src/kq/dashboard/streamlit_app.py:338` |
| med | DuckDB write lock held across Kalshi network I/O, zero connect retry anywhere — every-minute ingest deterministically collides with the paper flow | `src/kq/flows/paper_trade.py:125`, `duckdb_store.py:17` |
| med | Lock collisions → false CRIT pages (health-check) and false REALITY-DRIFT alerts (doctor), no retry | `src/kq/flows/health_check.py:414` |
| med | Doctor orderbook check probes ONE arbitrary market; a legitimately empty book reports CRIT "wire format drifted" | `src/kq/flows/doctor.py:244` |
| med | Documented health-check cron recipe `\|\| notify` alerts on WARN (exit 1), contradicting its own "only on CRIT" claim twice | `docs/SCHEDULED-RUNS.md:238` |
| med | Settlement-source CRIT suppressed if the modeled station name appears ANYWHERE in rules text — the NY sentinel can go false-green | `src/kq/flows/doctor.py:214` |
| med | payload-shape CRITs only at zero priced markets; 1/12 priced reports OK; no 0..1 price-range validation | `src/kq/flows/doctor.py:125` |
| med | `.env.example` ships a CWD-relative DATABASE_URL that bootstrap-secrets copies to `.env` — `kq` outside repo root silently creates a second empty DB | `.env.example:28` |
| med | `router_config.json` + manifests written non-atomically — a truncated Sunday write bricks `kq paper` for a week while mtime freshness stays green | `src/kq/models/router.py:151` |
| low | Doctor rates missing `strike_type` WARN while probe pages only on CRIT (impact reduced now that PR-H fails closed: drift skips markets instead of inverting them) | `src/kq/flows/doctor.py:138` |
| low | Manifest/router freshness thresholds are 1× the weekly cadence (comment claims 2×) — Sunday WARN flap race | `src/kq/flows/health_check.py:56` |
| low | `"markets": null` in one series payload TypeErrors the whole doctor run | `src/kq/flows/doctor.py:165` |
| low | Live private ntfy topic committed in docs; probe reads topic from env while notify-failure reads `.env` — split alert config | `docs/SCHEDULED-RUNS.md:147` |
| low | `TimedRotatingFileHandler` races under concurrent cron processes sharing one `--log-file` | `src/kq/_logging.py:150` |
| low | `--log-pretty` cannot force pretty output (tri-state collapsed to bool) | `src/kq/__main__.py:92` |
| low | `paper-summary` exits 1 (the "don't alert" code) on a malformed `--start/--end` instead of the documented 2 | `src/kq/__main__.py:543` |
| low | `LOG_LEVEL=warn` (and any typo) silently demotes to INFO | `src/kq/_logging.py:99` |

### Tier 4 — docs / dead code

| Sev | Finding | File |
|-----|---------|------|
| low | `nba_elo` comments state the inverse of the (correct) implemented math twice — invites a wrong "fix" | `src/kq/models/nba_elo.py:41,190` |
| low | OU nowcast module is dead code: `ou_posterior` has zero callers despite presenting itself as the operational replacement | `src/kq/models/nowcast_ou.py:74` |
| low | `robust_kelly` docstring "formal statement" is mathematically wrong and matches neither its own properties nor the implementation | `src/kq/execution/robust_kelly.py:21` |

**Refuted by panels (do not act):** NBM qmd "fabricates the distribution on
schema mismatch" (0/2), `files_for_lead_1` nonexistent-'ef'-type (0/1), and the
isotonic-fit-in-sample finding split 1/1 (contested — worth a lead-verified
look before touching `engine.py:594`, since `use_isotonic_recal` defaults True
and shapes all regenerated evidence).

## UX verdicts (graded against "a middle-schooler or grandparent could use it")

| Surface | Grade | Verdict |
|---------|-------|---------|
| CLI | C | Well-built for its real audience; failed novices structurally |
| Docs | C | Excellent for owner/Claude sessions; onboarding path never reached the dashboard |
| Dashboard | D | Expert-usable operator console; jargon-labeled everything |

**CLI (C):** disciplined exit codes, graceful credential degradation,
next-step breadcrumbs — but every breadcrumb said to run `kq`, which didn't
exist as a command (no `[project.scripts]`); a fresh clone crashed with raw
DuckDB tracebacks (no init path); help text pointed novices at CLAUDE.md.
*Shipped in response:* the `kq` console script now exists, and `kq setup` is
the guided init that was missing (`a559e31`).

**Docs (C):** SETUP.md is genuinely novice-grade, but the README→SETUP path
ended at "tests green" without ever mentioning the dashboard; quickstart was
silently Mac-only; NGR/Brier/CLV/devig undefined anywhere outside research
docs. *Shipped in response:* `docs/GETTING-STARTED.md` (zero-knowledge
walkthrough, real captured output, plain-English glossary, hiccups table),
README quickstart re-led, installer fast path added to CLAUDE.md §0
(`a559e31`, `55ee6d5`).

**Dashboard (D):** quant-jargon tabs, metrics with no "is this good?"
anchor, raw exception text on fresh DBs, a FAIL gate rendered with a green
up-arrow, "am I making money?" unanswerable in 10 seconds. *Shipped in
response:* the plain-language pass (`a2f4800`) — "What am I looking at?"
expander, every tab opens with the question it answers, every headline metric
tooltipped with the real gate, every empty state names the exact command.
Presentation-only; the Tier-3 connection-leak finding remains open.

## Box runbook — regenerate honest evidence on the always-on machine

The committed manifests were regenerated on the dev box; the WSL2 cron host
must purge its poisoned rows and rebuild its own DB-backed evidence. From
`~/forecast-lab` after `git pull`:

```bash
# 1. One-time purge of poisoned lead-0 rows (old backdated-as_of backfill)
uv run python -c "import duckdb; con = duckdb.connect('data/forecast_lab.duckdb'); \
  con.execute(\"DELETE FROM weather_forecast WHERE model = 'gfs_hist'\"); con.close()"

# 2. Backfill true lead-1 + benchmark + settlement truth (rate-limit polite; ~48 requests)
Y=$(date -d yesterday +%F)
uv run kq backfill-weather  --start 2024-11-01 --end "$Y"
uv run kq backfill-ndfd     --start 2024-11-01 --end "$Y"
uv run kq backfill-observed --start 2024-11-01 --end "$Y"

# 3. Retrain + regenerate evidence + route
uv run kq train-weather
uv run kq backtest --strategy weather_v1
uv run kq backtest --strategy weather_all_raw_v1
uv run kq decide-router
uv run kq backtest --strategy weather_router_v1
uv run kq backtest-weather-clv
uv run kq backtest-nba-clv
uv run kq router-summary    # EXPECT exit 1 — Phase 5 #2 fails honestly until the model improves
```

Cron changes (recipes in [`docs/SCHEDULED-RUNS.md`](SCHEDULED-RUNS.md)):

- **Add the 10:00 UTC observed-truth lane** (new in PR-G — settlement cannot
  fire without it): `0 10 * * * … kq ingest-observed` (SCHEDULED-RUNS.md:179).
- **Weekly reality probe** stays Monday 13:00 UTC (`scripts/reality-probe.sh`,
  SCHEDULED-RUNS.md:147) — but note the Tier-3 bare-`uv` PATH bug; verify one
  manual run before trusting it.
- The Sunday `weather_reforecast_v1` backtest line will not produce a
  meaningful manifest until a GEFSv12 pull lands (`kq plan-gefsv12-pull` →
  `kq pull-gefsv12-reforecasts`); the void reforecast manifest was deleted, and
  the manifest reader fails-closed on missing keys.

## Honest process notes

- **The completeness critic never ran.** The mega-audit's final
  cross-checking pass hung twice (2 agents, both attempts) and was abandoned;
  results were harvested directly instead — 249 of 253 expected agent results
  recovered. ~4 adversarial panel votes were lost; every finding reported
  above retains at least 1 confirming vote, most 2–6.
- **The audit round ran against the PRE-sprint tree.** Sweeps launched before
  PR-B…PR-H landed, so 7 distinct findings above were fixed concurrently
  (marked in §P1); their line numbers reference the pre-sprint tree. The three
  most dangerous (fail-open strike guard, mid-game finality, midnight signal
  split) were pulled forward and fixed deliberately as PR-H before merge.
- Two of the three UX reports arrived with empty `ident` fields (recovered by
  grade + content); the grades table above is from the recovered payloads.
- The old-void column in the verdict table is quoted from the superseded
  ROADMAP post-#95 tables; those manifests no longer exist on disk (replaced
  by PR-F), so the comparison is reproducible only from git history.

## Where this leaves Phase 5

| # | Gate | Status after this sprint |
|---|------|--------------------------|
| 1 | ≥500 settled trades | Clock can genuinely start: prices parse, all brackets visible, truth ingests, settlement guarded. Needs the box runbook + cron additions above. |
| 2 | Brier ≥5% vs benchmark | **FAILS on honest evidence, 0/6.** Model-improvement lane is the critical path (ensemble previous-runs, NBM previous-day, ECMWF lane fix). |
| 3 | Reliability calibrated | 4/6 stations pass on honest data; KLAX 11.1pp, KDEN 13.7pp fail. |
| 4 | Positive paper P&L 3wk | Unblocked; meaningless until #2 direction is settled. |
| 5 | CLV ≥ +1% (NBA) | Metric is now honest (PR-E). Accumulation can start. |
| 6 | 30-day flow uptime | Restart the clock now that flows contact reality. |
| 7 | Bankroll plan + hard caps | ✅ Caps are enforced clamps (PR-G); plan wording corrected. |
| 8–10 | State / CPA / disclosure | Unchanged (CA green; external items open). |

The 2026-06-11 lesson holds and is now enforced by tooling (`kq doctor`,
weekly probe, recorded-prod fixtures): **verify the venue's reality first,
then build.** This sprint's addendum: **regenerate evidence the moment an
input is proven dishonest — the honest number was 60pp worse than the claim,
and knowing that is the most valuable output of the quarter.**


---

## Addendum — P1 wave 1 landed same day (branch `fix/p1-hardening-wave1`)

Six file-disjoint agents closed **~55 of the ~61 open P1 items** in one wave
(commits `a443ee8`, `18f9c51`, `a30f130`, `089c281`, `57c58e8`, `4737ce7`
+ integration). Highlights per tier:

- **Tier 1**: one-sided books trade their executable side; qty capped at
  displayed liquidity (wired end-to-end, weather + NBA); fee-aware Kelly;
  maker rule matches the Pass-1 memo (code was wrong, doc right); guarded
  upserts (NULL can never regress recorded truth anywhere); NBA VOID path
  (pnl=-fee, pessimistic side documented); real transactions; Elo
  data-sufficiency guard (fresh DB emits ZERO signals).
- **Tier 2**: ECMWF valid_date off-by-one + publish buffer + real lookback;
  GEFS partial-failure loudness; NBM Lambert-grid sampling; honest
  run_time; embargoed non-overlapping CV; winner's-curse split-window
  router selection (selection_protocol block); true skew-normal moments;
  guarded NGR fits; anchored max_drawdown; NDFD lead threading; season-type
  filter in every Elo replay (flow + CLV backtest).
- **Tier 3**: all 15 — silent-zero CRIT, read-only DB opens (doctor can
  never create an empty DB again), reality-probe actually runs under cron,
  `--log-file` actually receives logs, dashboard lock leak fixed, lock
  collisions stop false-paging, committed ntfy topic scrubbed.
- **Tier 4**: all 3 (inverse Elo comments, OU-nowcast honesty, robust-Kelly
  docstring).

**Still open after wave 1**: the contested isotonic-in-sample finding
(panels split 1/1 — needs lead verification before touching
`engine.py`'s isotonic path); `weather_forecast.run_time` NOT NULL
relaxation (schema follow-up); LST alignment for the ECMWF open-data lane
(model-improvement lever); NBA quoted-size capping depends on book-snap
sizes being present in live data.

**Numbers caveat**: the embargo, drawdown anchor, and split-window
selection change manifest numbers on the next train/backtest/decide run —
regenerate evidence (box runbook above) before reading any gate.


---

## Addendum 2 — Phase A–C wave (2026-07-02, `feat/phase-a`)

Seven commits: A3 edge-study harness (`2a403a4`), A2 isotonic REFUTED-with-
proof (`17034a0`), B2 fleet 6→20 (`86bc906`), A1 six-model true-lead-1 pool
(`4afa6a6`), B1 NFL lane prod-verified (`aebbe72`), ens_var live threading
(`e2839cf`), C1 index vertical (`dea045b`). Tag `v0.1.0-honest-baseline`
marks the pre-wave baseline.

**Accuracy trajectory (the project's core):** multi-model pooling moved every
station — KMDW −50.2%→−14.5%, KNYC −43.5%→−8.9%, KMIA −39.0%→−12.0% vs NDFD —
and KNYC cleared the bar (+6.06%) on the winner's-curse-guarded second-half
window, the first out-of-selection pass in project history. Full-window
verdict remains 0/6 (honest). New open items: backtest reliability regressed
0/6 under sharper inputs (needs investigation); NBM previous_day1 available
from ~Nov 2024 → a true-lead-1 benchmark would remove the last caveat that
flatters NDFD (owner decision — it makes the bar honest in BOTH directions).

**Box to-do (updates the earlier runbook):** pull main → regeneration
runbook (now includes the 6-lane prevday backfill + 14 new stations'
observed/weather/NDFD backfills) → `kq study-nowcast-edge` weekly →
reforecast-NGR re-test (`weather_reforecast_v1` on the box's GEFSv12 data).
Operator: replace the 401 ODDS_API_KEY; budget the $30 Odds API tier when
NFL+NBA both run; CPA + NVIDIA disclosure remain the Phase-D external gates.
