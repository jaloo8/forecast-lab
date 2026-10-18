# Parallel $100 stock paper portfolios

Status: owner requested multiple tests within the three proposed families and delegated the test count. Implement nine frozen variants; no portfolios are started by this document.

## Purpose and options

Compare a small, fixed set of funded virtual portfolios on future observations. Each starts with $100 of independent virtual cash. This addresses the owner's request for parallel simulations without counting repeated copies of one strategy as new evidence.

Recommended: nine separate ledgers in three families driven by one shared, timestamped capture. This supports different holding periods and a fair earnings-filter comparison while reusing the existing execution accounting. Simply cloning the current ledger is quicker but reproduces the same strategy and inherited trades. A large parameter sweep offers more variations but encourages choosing a lucky historical winner and is deferred.

## Fixed initial comparison

| Portfolio family (three variants each) | Selection | Exit |
| --- | --- | --- |
| Momentum 5 | Existing liquidity-filtered momentum comparison | Fifth held session close |
| Momentum 20 | Identical selection rule | Twentieth held session close |
| Earnings 20 | Existing earnings/momentum challenger | Twentieth held session close |

Each family has fixed 10-, 20-, and 60-session momentum-lookback variants (nine portfolios total). All nine use the same captured catalogue/earnings-calendar intersection, public observations, 20-session liquidity requirements and common start capture. Each lookback requires its own complete aligned history, with at least 21 bars for liquidity; missing history remains explicit. A name lacking history is ineligible in that variant. Compare matching lookbacks between families and disclose varying history coverage within families. Therefore Momentum 5 vs Momentum 20 tests holding duration, while Momentum 20 vs Earnings 20 tests the earnings filter. The universe remains event-conditioned, not the entire stock market. News/filing context retains its first-seen timestamp; no sentiment score or new predictive signal is introduced.

Freeze the existing screen rules before launch. Select up to three eligible names in its existing deterministic order when account capacity allows; never duplicate an active symbol within a portfolio. Re-evaluate once per daily capture. Keep cash when no eligible name exists. Names can coincide across portfolios; disclose that their results are correlated. Do not backdate the start or copy historical positions into a new account. The original $100 pilot remains separately visible with its own start date and history.

## Accounting and evidence

Retain current per-account controls: $10 per order, at most five pending/open positions, 10bp entry/exit friction and pause additions at $10 loss from initial marked equity. Each account has its own cash, reservations, trades, marks and pause state; no transfers, cross-account spending, leverage or replenishment. Nine portfolios represent $900 total simulated starting capital, not a single real $100 balance. Existing risk controls are not loosened.

Use the first regular New York open strictly after recorded order creation; recognize a fill only when its completed daily bar arrives. Marks update daily; realized profit requires an exit. Maintain a passive $100 SPY reference from the shared launch date, explicitly showing active portfolios' cash exposure, plus matched SPY returns for each completed trade with the same assumed costs. A full-investment reference is not risk-matched to the cash-heavy portfolios. Do not annualize tiny samples or rank portfolios on realized P&L while ignoring open losses.

Store immutable portfolio ID, strategy/version hash, launch time, holding period and source capture hashes. Refuse reopening a ledger with different settings. Repeated capture imports are idempotent. Reject future observations, revised anchored prices and inconsistent histories. Missing expected weekdays retain the existing explicit unverified-calendar limitation; do not invent sessions or present affected results as validated. Preserve all losing, empty and invalid outcomes.

## Components and operation

Add a validated portfolio protocol and a thin adapter from the existing challenger screen to ledger inputs. Generalize only the ledger's fixed holding-period/selection boundary, preserving its original default behavior. Store new accounts beneath a dedicated parallel-books directory, each with a separate SQLite database and report. A runner validates the shared capture first, updates each account transactionally and records individual successes/failures; retries cannot duplicate fills. A failed account cannot silently appear current beside successful accounts.

A8 remains the sole writer. Extend the existing daily refresh after tests and review, collect one common snapshot including every open/pending symbol across all accounts and SPY, and mirror consistent backups. Keep actual capture/order timestamps and all original inputs. This does not add independent A8 authentication or intraday execution; the existing Codex collection dependency remains visible.

Add a read-only dashboard comparison showing launch date, strategy, holding period, equity, available/reserved cash, realized/unrealized profit, drawdown, exposure, open/closed counts, benchmark comparison, data freshness and pauses. Show the existing pilot separately. Pending/unmeasured results must never become zero-return successes.

## Validation and evaluation

Meaningful tests must demonstrate independent balances and pauses, identical initial selections in the two momentum books, exits only at their respective horizons, earnings exclusion using information available at capture, next-open timing, fee arithmetic, idempotent retries and visible partial-run failures. Include a losing path and an open-loss dashboard case. Retain legacy ledger regression tests and run repository lint, format, types, security and coverage gates. Verify the A8 deployment with paper-only isolated fixtures and unchanged original ledger hash.

Report all nine attempted variants, without discarding losers or calling the best observed result a validated winner. Review forward evidence after 60 completed trading sessions from common launch, reporting distinct entry dates and overlapping exposure; this is an initial comparison window, not proof of profitability or permission for real money. Freeze rules during that window; any later strategy revision receives a new version and new forward record. Shorter holds provide earlier exits but cannot accelerate the passage of market time.

No options account, new dependency, paid feed, live brokerage execution, or long-term-return promise is included. Historical options quote/lifecycle coverage remains a separate prerequisite. Implementation should be split into the repository's small reviewed PRs, then tested/deployed on the isolated A8 stock release.
