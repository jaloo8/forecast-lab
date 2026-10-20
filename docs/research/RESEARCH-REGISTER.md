# Strategy research register

The owner's current question is whether a strategy can produce 10–20% net profit in every calendar year, starting with $1,000. Years above 20% are reported, not rejected. No historical test establishes a future annual floor. Research is not a search that stops recording failures once a winning historical chart appears.

## How trials are counted

A policy is one fixed trading rule. Cost settings, dates, leverage levels and fresh-start accounts are scenarios of that rule, not independent algorithm discoveries. Different studies can reuse the same mechanism; their counts must not be added into an invented total of unique strategies. Every material new rule is registered before its new performance is computed. Known historical data are not an untouched holdout.

Each new study must preserve the specification, data and source hashes, every trial (including failed or incomplete ones), annual returns, drawdown, costs and execution assumptions. A claim that a test ran requires its output and validation receipt. Reviewing a paper, an AI response or an existing result is not a new backtest.

## Existing evidence

These are preserved results, not fresh reruns in the latest session.

| Study | Recorded scope | What it establishes |
|---|---|---|
| [Annual-profit audit](ANNUAL-PROFIT-AUDIT-2026-10-19.md) | 8 stock policies × 3 costs = 24 paths, 2006–2025; 4 published options indices, 2009–2025 | None achieved at least 10% in every year; stock model used $10,000 fractional adjusted units; indices are not retail net implementations. |
| [Original options pilot](OPTIONS-PILOT-2026-10-18.md) | 3 fixed SPY call spreads; 7 acquired batches | Documented net −$16.80; too small and short for annual-return evidence. |
| [Extended options study](OPTIONS-RESULTS-2026-10-18.md) | 893-session census; strict and publisher-flag sensitivity | Negative totals; unresolved exits; independent trade sums are not returns on a funded $1,000 account. Original streamed inputs remain unavailable here. |
| [Pairs study](REEL-STRATEGY-REVIEW-2026-10-18.md) | KO/PEP, 9 cost cases | No useful demonstrated edge; original five-bot claims remain unverified. |
| [Expanded stock audit](STOCK-A8-AUDIT-2026-10-18.md) | 54/60 scenarios complete; 6 unscored | Historical current-universe selection bias and missing held prices remain visible. |

The owner's separate QuantLab workspace preserves the 63-policy high-return study, 10-rule timing study and 12-policy combination study. Their thousands of account scenarios are not thousands of distinct algorithms. Their prior objectives, leverage conventions and data limitations remain attached to those results; they are not silently reclassified as current-target passes. They are not all contained in this public repository.

The October 19 [threshold audit](evidence/2026-10-19-strategy-families/prior-target-rescreen.json) newly checked the saved annual rows of all 980 high-return, 2,100 timing and 288 combination main scenario records. Of 3,368 records, 3,218 span at least ten complete years; **none** reaches 10% in every complete year. The 54 shorter-window passes comprise 40 META cases covering only 2013 and 14 TSLA cases covering 2011–2013. These are not long-history successes. An [independent check](evidence/2026-10-19-strategy-families/prior-target-independent-review.json) verified all source hashes and 58,112 annual rows. This recalculates a threshold from old results; it does not rerun their engines, count short fresh-start cohorts as full calendars, or establish independent algorithms.

## Current work

- [Credit/schema follow-up](DATABENTO-CREDIT-PLAN-2026-10-19.md): approximate owner balance $116, expiry April 2027; nine schema requests newly priced at $0.226768702267 under a planned $0.50 ceiling. No acquisition or new backtest. OPRA timestamp/flag clarification is recorded without changing frozen results.

- Recovered 11 retained Databento SPY batches at no new acquisition charge. [Recovery receipt](evidence/2026-10-19-strategy-families/data-recovery-summary.json) records verified files and scope. This does not restore the missing original streaming cache or its accounting catalog.
- Completed the [stock/ETF family study](STRATEGY-FAMILY-RESULTS-2026-10-19.md): 28 policies, 279 cost/window/account paths including 27 whole-SPY diagnostics. None passed the annual 10% floor. All daily/transaction accounting paths independently reconciled; every trial and the chronological training selection are preserved.
- Reconstructed the short options diagnostic under its [frozen protocol](RECOVERED-OPTIONS-PROTOCOL-2026-10-19.md). All six cases close three trades: $1,000 ends at $983.20 baseline, $971.20 at an extra 1 cent per leg per side, and $959.20 at an extra 2 cents. Strict and publisher-flag sensitivity coincide on these dates. The [summary](evidence/2026-10-19-strategy-families/recovered-options-summary.json) and [independent cash check](evidence/2026-10-19-strategy-families/options-independent-cash-check.json) preserve scope. This is an EQUS.MINI reconstruction, not reproduction of the absent original Yahoo input; no annual claim.

This register is updated with actual output paths after execution. It is not itself evidence that a pending test ran.

## Deliberately separate research lanes

| Lane | Required evidence before a credible performance claim |
|---|---|
| Daily ETF trend, momentum, breakout, reversal and allocation | Causal signals, later execution, funded ledger, costs, all-year outcomes; adjusted units distinguished from actual shares. |
| Options spreads | Listed historical contracts and quotes, integer contracts, cash/collateral, bid/ask and fees, unresolved-exit handling and funded account NAV. |
| Broad individual-stock selection | Historical universe membership, delistings and corporate actions; present-day winners alone are insufficient. |
| News, fundamentals and social signals | Original availability timestamps and permitted historical inputs; current web summaries cannot be inserted into past decisions. |
| ML or agent-generated strategies | Frozen training procedure and search budget, leakage checks, complete trial history, reproducible deterministic accounting and prospective validation. More agents do not establish an edge. |

## Cost and repository discipline

Use retained downloads and verified existing inputs before buying data. The owner authorized frugal free-credit use on October 19; cash spending and subscriptions remain unauthorized. Keep credit balance/expiry evidence and a bounded request plan before billable retrieval. Do not run the old acquisition scripts against an empty catalog as a recovery shortcut.

Keep one active integration branch and draft PR #235. Preserve source, specifications and aggregate evidence in Git; keep credentials, licensed raw inputs, local databases and account download URLs private. A clean clone must explain both what it can reproduce and which private inputs it still needs. No broker activation or new paper writer follows from this research.

## October 19: CBBO software implemented; no new performance trial

Separate reader/operator implemented and reviewed with 50 artificial fixture tests. Original 279 stock and six options cash outputs verified again, not rerun. Nine real free quotes succeeded at $0.2726 buffered reservation total. Fresh exact credit evidence is pending; no billable job or real historical CBBO inspection. See [implementation](CBBO-IMPLEMENTATION-2026-10-19.md).
