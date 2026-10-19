# Longer options study: cached evidence and acquisition proposal

October 18, 2026 Pacific. No additional credits spent or market data downloaded
in this pass. The longer options backtest is **not yet run**: the cache contains
SPY minute bars across March 28, 2023–October 16, 2026, but option quotes for only
three dates. The unchanged pilot replay again produced **−$16.80** after costs.
This is a feasibility experiment, not evidence of profitable execution.

## Frozen scope and cached census

Keep the [original candidate](OPTIONS-CANDIDATE-2026-10-18.md): opening-range
breakout, delayed entry, one standard $1-wide SPY call spread expiring the next
calendar day, underlying-triggered exit or 15:30 New York exit. No parameter
search, Friday-to-Monday substitution, overnight hold or strategy promotion.
Use EQUS.MINI for the extended underlying decisions; the pilot keeps its
original Yahoo capture. All seven overlapping decision schedules agreed.

The verified cache has 893 supplied dates: 566 signals, 318 no-signal dates and
nine incomplete/short sessions retained as unscored. Of the signals, 119 target
a weekend expiry; three have cached pilot quotes. **444 new weekday candidates**
remain, before holiday, dated-listing and data-quality checks:

| Year | New candidates |
| --- | ---: |
| 2023, from March 28 | 90 |
| 2024 | 120 |
| 2025 | 134 |
| 2026, through October 16 | 100 |

Report both calendar years and fixed, lagged regimes: previous 20 observed
close-to-close price returns' sample volatility, annualized by sqrt(252),
below 15%, 15%–25%, and at least 25%; previous close above/below its trailing
60-session average. Current/future closes cannot enter either label. Preserve
warmup and missing values rather than filling or dropping them. Candidate
counts are low 351, medium 68, high 14, warmup 11. High-volatility evidence will
remain sparse. Raw prices include dividend effects; these labels are not
total-return estimates or real-time historical source vintages.

The underlying-only diagnostic across all 566 signals, at 5 bp per side:

| Year | Signals | Mean net share return per signal |
| --- | ---: | ---: |
| 2023 partial | 115 | +0.00723% |
| 2024 | 155 | −0.07969% |
| 2025 | 165 | −0.09081% |
| 2026 partial | 131 | −0.09655% |

These are neither option returns nor portfolio annual returns. Option outcomes
for the extension remain unknown, but underlying outcomes and pilot outcomes
have already been viewed: this is a fixed-rule retrospective test, **not a
pristine holdout**. No claim of complete exchange-calendar coverage: eight
excluded dates resemble early closes; October 21, 2024 has incomplete bars.
OPRA metadata additionally flags June 3, 2024 and October 22, 2025 degraded.
Both are no-signal dates here. Keep degraded dates visible and quarantine them from primary options results
unless product-specific completeness is established before scoring.

## Costs before acquisition

**Targeted definitions: $7.500509172682**, summing all 245 free interval estimates
covering the 444 candidate dates. Including estimated selected quotes, the
planning total is **about $8.30 additional credits**. Proposed approval cap:
**$10 additional historical credits, $0 cash**, stopping before a submission
whose conservative reservation would exceed that cap. Exact quote pricing is
still a second-stage gate, not implied permission to spend this estimate.
The alternative of buying every missing date's SPY definitions costs
**$15.001460909844**; the three cached definition days are already subtracted.
Prefer the candidate-date-only version, without buying gaps between dates.

For quotes, first/last dates within each year/volatility/trend cell were selected
without looking at returns. Of 37 sampled dates, 36 priced; November 26, 2025's
provisional November 27 pair failed resolution and remains unpriced, not free.
The 36 dates total $0.072764801979 at enclosing 10-minute estimation bounds.
Cell-weighted extrapolation to 444 candidates is **$0.798023933149**; using each
cell's sampled minimum/maximum instead gives $0.700802–$0.895246. This is a
planning scenario range, **not a confidence interval or a cost upper bound**.
Exact contracts must be selected from causal dated definitions and re-priced.

Quote requests cover only ten seconds before each decision through one second
after it; replay still refuses observations after the decision. The extra second
avoids precision loss at an exclusive 10-minute boundary during estimation.
The nearest integer strike is only a cost probe, never proof of a listed chain.
No complete-chain quote download, subscription or cash charge is proposed.

Databento documents [cost estimation](https://databento.com/docs/api-reference-historical/metadata/metadata-get-cost)
at 10-minute boundaries (definitions at 24-hour boundaries), with actual billing
based on bytes. [Symbology resolution](https://databento.com/docs/api-reference-historical/symbology/symbology-resolve)
is free. Fresh authenticated metadata confirms CMBP-1 begins March 28, 2023:
the dataset's 2013 headline cannot supply the required earlier tick quotes.
This test cannot cover 2008, 2020 or 2022. Earlier regimes need another suitable
source, separately priced and validated, not lower-quality bars relabelled ticks.

## Evaluation and evidence contract

Acquire only after owner approval of a fresh credit cap, with a fresh balance
check, per-request estimates, resumable ledger and one serial download at a time.
Keep raw hashes, metadata, conditions and backups; never redownload valid cache
entries. Do not reset the existing cumulative ledger or silently extend its
pilot-specific $9.99 transport permission. The previous pilot cost $0.41967466473580;
this pass spent zero. The last observed balance is historical, not refreshed here.

Retain no-signal, no-expiry, bad-chain, invalid/stale-quote, rejected-entry and
unresolved-exit counts. Keep debits tied up for unresolved exits; never score
missing outcomes as zero profit. Entry at long ask/short bid, exit at long
bid/short ask, existing $2.60 round-trip commissions and $4 slippage per spread;
stress an additional 1 and 2 cents per leg per side, recomputing affordability.
Preserve the existing $100 debit-plus-exit-reserve rule. Report dollar P&L,
drawdown, win rate, exposure and all yearly/regime cells, with pilot dates separate.
Treat the session, not individual legs or quote records, as the inference unit;
use fixed five-session block resampling for exploratory uncertainty. Conditional
leg quotes do not prove atomic combo fills. No promotion from point estimates.

Reproduce the offline census with `python -m scripts.plan_options_extension`
and `--root`, `--pilot-plan`, `--output`. Pass its named plans to the existing
`scripts.estimate_options_data` free-only CLI. Durable evidence is under
`C:/Users/jloo1/Documents/MarketData/databento/runs/20261018-extension-v3/`;
targeted definition receipts are in `20261018-extension-v2/targeted-estimates/`;
the full-history alternative receipt is in `20261018-extension/`.
The repeated original replay is in `20261018-extension-replay/`.
Source SPY payload SHA256:
`58d3fc9528b93d0723594767adaed6695719e0724329851cf3876135593610f5`.

Validation: 119 focused planner/cache/quote/metadata checks pass, including
future-price mutation, missing-value handling, outcome-independent cost sample
selection and gap-preserving date coalescence. Ruff and strict mypy pass.
The cached option replay reproduced all three trades, with zero unresolved exits.
No A8 job, account, trading parameter or production deployment was changed.

## Approved acquisition implementation

Owner approved up to $10 additional credits on October 18. The original seven
$1 ledger reservations stay intact; explicit extension transport caps cumulative
reservations at $17. Only SPY definitions (at most four days) and selected call
quotes (at most eleven seconds) within the frozen study dates are admitted.
The original pilot transport scope and $9.99 default remain unchanged.

Serial runner `python -m scripts.acquire_options_extension` consumes saved
estimate receipts, reprices before every new submission, reserves 12% plus a
small rounding margin, persists uncertainty before POST and resumes known jobs.
It stops on uncertain submissions, exceeded reservations or changed scope.
Fresh portal snapshots expire after five minutes; opt-in reconciliation deducts
all locally imported charges after observation without changing that timestamp.
External account usage is not observable through the local ledger; portal
refreshes and a large verified credit buffer remain necessary. No vendor-side
hard cap is claimed. Four-minute runs yield for a fresh balance check.

Implementation sequence: verify guards, acquire definitions, select exact dated
contracts, reprice quote windows, acquire quotes, replay offline by year/regime,
preserve independent cache backup and report all refusals/unresolved positions.
No additional dependencies, strategy changes, or A8 deployment.

### Direct historical transport refinement

The first four batch jobs completed, but serial preparation takes minutes per
job. Databento's documented `timeseries.get_range` returns the same historical
records immediately. The explicit stream operator uses aligned 24-hour definition
windows and 10-minute quote boundaries (at most 20 minutes per quote request),
within the same estimated/reserved credit budget. It is not an automatic retry
or fallback for uncertain requests. Each full CSV delivery must match a separate
free `metadata.get_record_count` result. Hashes are local integrity checks, not
vendor-signed stream manifests. Streaming lacks the batch redownload guarantee.

The ledger records the entire conservative reservation for streams, explicitly
labelled an upper accounting amount rather than vendor-reported actual cost.
Final billing balance is reconciled separately. A first HTTP 206 response was
closed before consumption because the adapter initially accepted only 200.
The documented partial-symbol success response is now preserved and accepted
only with matching row count. Its $0.0305 possible charge remains in the ledger
as an abandoned attempt, with no cached coverage; manual recovery uses a distinct
source version and a new reservation. No uncertain request is silently repeated.

### Replay implementation

`scripts.prepare_options_extension` selects exact historical strikes from the
verified dated definitions using only the completed signal close. Overlapping
or touching rounded quote windows are coalesced (at most 40 minutes), avoiding
duplicate acquisition. A real-data smoke selected 43 of 45 candidates; two
had no eligible next-day chain. All remain in the census.

`scripts.report_options_extension` replays the unchanged kernel offline and
reports all census sessions by year, lagged volatility and lagged trend. The
three original pilot dates remain separate. Stress adds 1/2 cents per leg per
side and reapplies the existing funding limit. Closed-trade drawdown includes
the initial zero; unresolved debits remain visible. These are independent
one-spread experiments, not a compounded/funded portfolio or annualized CAGR.
A fixed-seed five-census-session block interval describes the mean of resolved
trades; it excludes unresolved outcomes and is exploratory, not promotion proof.
No-execution cells have null profit, not zero-profit performance.

Stream receipts retain the vendor's `X-Warning` header, as used by its official
Python client. Earlier definition receipts recorded null from an incorrect
header name; their independent counts still match, but warning text is unknown.
Those paid requests are not repeated merely to recover warning text.
