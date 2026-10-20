# Fifty complete years: registered monthly research

The [machine registration](long-history-registration-2026-10-20.json) was saved
at **2026-10-20 15:47:05 UTC**, before this study's account performance.
Its SHA-256 is
`28a1a2d1236f2349f0fb73f256667a214e068211e119139e392c7bb5e6a3998e`.
The [pre-performance clarifications](evidence/2026-10-20-long-history/pre-performance-clarifications.json)
and [independent review](evidence/2026-10-20-long-history/pre-performance-review.json)
record accounting and validation corrections made before execution.
This explanatory document was written afterward; it is not falsely backdated
as the original registration.

## Objective and honest trial counts

The owner's new request is a broad search for positive annualized growth:
100 relatively stable candidates, 50 above 10%, and 50 above 25%. The owner
defined stable as **less drawdown than the stock-market benchmark**.
These requested counts are aspirations, not results we may manufacture.
The former 10% minimum in every calendar year remains a reported diagnostic.

This experiment contains **200 configured policies in 20 related families**,
with ten predetermined configurations per family. It does not contain 200
independent algorithm inventions. Four controls are separate. Each policy
receives three time windows, three cost assumptions and two information lags:
**204 × 3 × 3 × 2 = 3,672 funded index-proxy simulations**.
The 3,600 candidate scenarios and 72 controls are not additional strategies.
Exact duplicate computed return paths are reported separately.

Families and their precise formulas are in the registration and
[primary-source dossier](LONG-HISTORY-SOURCE-DOSSIER-2026-10-20.md).
Momentum, trend and risk-scaling families share economic exposures. Neither
different names nor many passing scenarios establish independent evidence.

## Data and tradability

Inputs are the value-weighted monthly section of the
[French 49-industry portfolios](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_49_ind_port.html)
and matching [market/RF series](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_factors.html).
The downloaded files identify the **202608 CRSP database vintage**.
The first complete common warmup used is July 1969. No observation after
December 2025 enters a signal or result. Missing sentinels, duplicate months,
missing calendar months, nonfinite values and returns at or below −100% are
rejected, not filled.

Gross market return is Mkt-RF plus RF. RF is a research cash-return proxy,
not a promise of broker interest. No additional dividend credit is added.
The [library's revision notes](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html)
explain reconstructed history and the CIZ methodology transition.
The frozen files are not historical point-in-time releases.

These industry portfolios are **not 49 ETFs or executable baskets for $1,000**.
Internal constituent turnover, index reconstruction, corporate-action
execution, minimum commissions, taxes and historical basket replication are
outside the model. The same SPY/BIL strategy from the previous daily study
cannot literally trade those ETFs before inception. Monthly market/RF CPPI
here is an explicitly different proxy adaptation, not a 50-year extension
of its original execution record.

## Account chronology and costs

Every account starts from fresh $1,000 cash. Training is January 1976 through
December 2010 (420 months), later evaluation January 2011 through December 2025
(180 months), and the continuous full account January 1976 through December
2025 (600 months). No training wealth or peak is inherited by fresh evaluation.
Current-vintage and already-known historical data do not become an untouched
holdout merely by splitting dates.

For invested month t, **primary lag two uses observations through t−2**.
There is one entire intervening month. Lag one is an idealized sensitivity
using observations through t−1. Synthetic month-end `as_of` labels identify
the last included observation, not original vendor publication time.

At the start of each modeled month, risky target values and transaction fees
are funded from existing account wealth:

`NAV_after + cost_rate × sum(abs(target_values − old_values)) = NAV_before`.

Targets invest at most 98%; residual cash earns that month's realized RF.
No later RF enters the allocation decision. CZERO earns zero; CRF holds cash;
CMKT buys a 98% market sleeve once and lets it drift; CEQ49 rebalances equal
industry weights monthly. Candidates rebalance monthly. Risky trade costs are
10, 25 and 50 basis points per side, with **25 basis points primary**.
Initial and final liquidation costs are included. Cash movements carry no fee.
These scenarios do not prove the cost assumptions cover every historical broker.

CPPI exposures use the same account's delayed closing wealth and peak.
They cannot share a frictionless signal portfolio's wealth across cost cases.
The floor is an exposure-rule input; gaps and delayed rebalancing can breach it.
There is no leverage, shorting, borrowing or artificial increase of exposure
to reach a return quota.

## Selection, screens and multiple testing

All training scenarios finish before the training choice is saved.
At primary cost and lag, the selection lists up to five relatively stable
positive-return policies, up to five policies above 10% CAGR, and up to five
above 25%. Empty groups remain empty. Later performance cannot rewrite this
selection.

The robust positive screen requires positive full-period and later-period CAGR
under **all six cost/lag combinations**. The stable screen additionally requires
strictly smaller drawdown than the identically dated, identically costed market
control in all twelve comparisons. The 10% and 25% threshold counts require the
threshold in both primary full and later periods; cost sensitivity remains
separate. These groups overlap. Their counts must not be summed to claim
200 distinct successes. No screen is a broker qualification.

The registered centered stationary-block bootstrap compares all 200 candidates'
later primary monthly net returns against the matching market control.
Each resample uses the same calendar indices across policies, mean block length
six months, 2,000 replicates and fixed seed 20261020. The maximum centered mean
across candidates supplies a family-wise selection diagnostic.
See [the statistical sources and assumptions](LONG-HISTORY-SOURCE-DOSSIER-2026-10-20.md).
It does not correct every prior project search, nonstationarity, missing
information timestamps or an invalid execution model. The tested statistic is
mean monthly excess return, not CAGR or future profitability.

## Regime explanation and independent evidence

Four regime labels combine lagged twelve-month market excess performance with
lagged volatility relative to its expanding historical median. Labels use no
future observations. Fixed decade and crisis slices are also reported.
Conditional mean returns, risky exposure, cash gains, risky gains and fees
help explain accounting outcomes. They do not identify a headline's causal
effect or establish a future regime forecast.

Drawdown observes pre/post-cost and month-end/terminal marks only. Daily and
intramonth losses can be larger. Reported growth is nominal, after modeled
trading costs but before taxes, inflation and recurring service costs.

Each account preserves its monthly ledger and all fifty post-rebalance risky
values. The independent checker parses original data separately, reconstructs
all signals and accounts, verifies regime and selection calculations, and
repeats the statistical calculation. Artificial software fixtures, historical
proxy simulations, prospective news observations and broker execution remain
different evidence levels.

All rejected configurations, errors and complete results are retained. Raw
inputs and ledgers stay in the owner's private transfer kit; code, aggregate
results, source receipts and handoff are published on the existing Git branch.
No paid data, model API or broker order is needed for this study.
