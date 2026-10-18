# Twenty-year exploratory stock comparisons

Owner direction: September 30 UTC, expand the approved component/blend proposal to long-history research before further forward paper experiments. The owner requests continued research, not a guarantee that a minimum number of winners exists. Existing accounts, scheduler, caps and source reviews stay frozen.

## Evidence and alternatives

1. Use existing public Robinhood daily data now for a explicitly survivor-selected exploratory stress study (chosen first delivery). Preserve synthetic/pre-listing exclusions; this is not all-market validation.
2. Obtain a licensed delisted-inclusive price/total-return and filing-vintage dataset for broader validation. Research available providers without purchasing or installing anything; see the separate data audit.
3. Repeatedly optimize on the existing six-month sample. Rejected: its outcomes have already been inspected and many variants reuse the same evidence.

The long-history probe succeeds when the 20 years are split into two requests. The provider rejects one daily request beyond 5,000 estimated bars. Delisted LEH/BSC were unresolved in this probe; this does not prove all delisted coverage is absent. CNXC includes synthetic pre-listing rows which must not become observations.

## Frozen first study

Before collecting the main sample, select 100 current candidates from the existing verified September 29 Nasdaq catalogue by ascending SHA256 of `long-study-v1:` plus symbol. This deterministic selection is independent of measured returns, but still conditions on current survival and catalogue eligibility. Include SPY as benchmark, not as a candidate. Preserve catalogue identity, selection rule and exact requests in an immutable collection manifest.

Fetch split-adjusted regular daily prices from 2006-09-30 through 2026-09-30 UTC midnight in two nonoverlapping ten-year chunks. Save full raw MCP wrappers, actual UTC retrieval times, request bounds, not_found, errors and SHA256. Every requested symbol must be accounted for per chunk. Only real positive-volume regular bars count. Never infer prices before listing, interpolate missing sessions, or project legacy session repairs into this study. Cap study dates at the latest genuine SPY session.

Use seven fixed arms: intermediate momentum excluding the latest week (M), five-session reversal (R), low twenty-session volatility (V), equal-percentile blends MR, MV, RV and MRV. Exact formulas follow STOCK-METHOD-EVIDENCE-2026-09-30.md. All arms share one point-in-time eligible set with 61 aligned observations, price >= $5 and last-20-session median dollar volume >= $20m. Require at least five names. Percentile ranks use ascending average rank divided by eligible count; final ties use symbol ascending. No optimized weights, fitted parameters, positive-signal gates or winner selection.

Cross seven arms with selection sizes 1/3/5, holds 21/63/105 observed genuine SPY sessions, and cost assumptions 10/25/50 bp each side: 63 selection/hold rules and 189 cost-scenario summaries. These are correlated comparisons. Fixed 60-session warm-up and nonoverlapping cohorts per horizon; later cohorts start only after earlier exits. Each cohort is a separate hypothetical $100 research budget with $10 all-in per stock (maximum $50 deployed) and idle cash at zero interest. It is not a sequential $100 account, does not model the operational loss-pause path, and cannot support account CAGR or peak-to-trough drawdown claims. Live paper caps remain unchanged.

Enter next benchmark session open, exit at horizon close. Missing held bars make the cohort unavailable; never drop the losing/missing name or move to its next available price. Synthetic days never count toward holding periods. Require benchmark validity. Exclude malformed optional observations at their own dates with explicit invalid-bar evidence; any trade needing them remains unavailable. Reject malformed benchmark bars, duplicate symbol/dates, ambiguous adjustment and missing batches. This data-quality clarification followed the preserved HTB validation refusal, before any strategy outcomes were examined. IPO histories enter only after enough actual observations; do not require an entire 20-year stock history. Preserve incomplete and cash-only cohorts.

## Evaluation and limits

Retain selections, scores, source/actual retrieval times, simulated feature as_of, every cohort and all results. Compute net mean/median cohort return and matched SPY excess using the same invested/cash budget, both costs and dates; show worst cohort and unavailable counts. Partition outcomes by fixed decision-year periods 2006-2012, 2013-2019, 2020-2025 and 2026, excluding cross-boundary outcome intervals from individual-period aggregates while retaining them overall. This is chronological descriptive replay, not a fitted walk-forward model or a pristine holdout. Do not promote an apparent winner from this first study.

Data are current survivors, split-adjusted price returns without dividends/delisting outcomes, historical availability assumptions and hypothetical fills. A contemporary price/liquidity gate applied to split-adjusted history is a proxy, not recovered historical dollar eligibility. Missing exchange sessions shared by every stock are not detected by the SPY-observed calendar; do not claim a fully verified 20-year exchange calendar. Statistical tests and confidence intervals require an appropriately long, dependent-return-aware series and the complete trial log; do not manufacture confidence from a few cohorts.

## Isolation and completion

New pure loader and engine modules; no imports of account writers. A8-only CLI under the isolated stock release publishes manifest before computation, immutable success/failure artifacts, source hashes and a separate `long-history` result pointer. Never overwrite the existing short-history report. Use no new dependencies. Code/test artifacts may be local; durable research results are written only on A8 and mirrored after SHA verification.

Finish this first delivery when source coverage is audited, regression/future-leakage/accounting tests pass, the bounded declared study either publishes on A8 or preserves an exact data failure, and results/limitations are reported. Finding a quota of profitable rules is not a stopping condition. Stronger candidates need a separately frozen validation protocol and future observations; no new paper accounts activate automatically.
