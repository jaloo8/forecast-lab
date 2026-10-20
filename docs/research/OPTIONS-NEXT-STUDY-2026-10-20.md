# Options: executable research scope, data costs and next study

Reviewed and executed October 20, 2026. The registered experiment completed
at **$0 in new data fees**: all nine spread configurations lost money across
the three sampled dates, while all nine long-call configurations stayed in
cash because entries exceeded the fixed $100 trade budget. A $1,000
starting account is distinct from that entry-and-exit-reserve limit.
This is execution and feasibility evidence from known dates, not a new
discovery of an edge.

## What is actually available

The recovered pilot contains six SPY call contracts: two adjacent strikes on
each of October 8, 14 and 15, 2026, with full regular-session CMBP-1 files
containing **5,468,765 records**, dated chains and **460,609 EQUS.MINI
one-minute bars**. All seven original pilot deliveries have vendor hash/size
receipts. Four additional early-2023 recovered deliveries contain definitions,
not option quotes. They cannot extend a strategy replay by themselves.

The old three-session reconstruction already reported $1,000 ending at
$983.20, $971.20 and $959.20 across its three cost cases. These are known
results and must not be advertised as newly unseen validation. Its original
Yahoo capture is unavailable here; the recovered reconstruction uses EQUS.MINI.
The original longer options extension's published losses and unresolved
exits remain historical evidence, but its full raw stream archive is not
on this machine and has not been rerun. See the [reconstruction protocol](RECOVERED-OPTIONS-PROTOCOL-2026-10-19.md),
[preserved summary](evidence/2026-10-19-strategy-families/recovered-options-summary.json),
and [earlier extension results](OPTIONS-RESULTS-2026-10-18.md).

The separate April 2, 2013 schema probe has **2,716 definition records and
51,604 opening-envelope CBBO records**, at recorded historical credit cost
$0.01224264502525. Only two of nine planned requests were acquired; no
closing envelope exists in this sample. Its 19 minute labels, historical
timestamp semantics, quote flags and undefined multipliers require a
separate adapter. This sample has not produced a strategy backtest.
[Aggregate inspection](evidence/2026-10-20-allocation/cbbo-sample-inspection.json).

## Registered experiment

The [frozen execution protocol](OPTIONS-EXECUTION-PROTOCOL-2026-10-20.md)
specifies **18 accounts / 54 session decisions**: two structures × three
delays (0/1/5 seconds) × three cost settings. These are configurations of two
structures, not 18 independent algorithms. The original $1-wide debit spread
and its lower-strike long call use identical existing signals and planned
exit times. There is no new strike search, outcome-driven timing adjustment,
or increased budget to force long-call participation.

The separate runner records cash, costs, reserves and whole-minute
hypothetical liquidation NAV. Missing marks stay unknown; a missing exit
preserves the position and blocks subsequent entries. The separate checker
reconciles saved snapshots and every account transition without calling the
simulator. Independent review pins the protocol, runner, checker, tests and
upstream adapters before the historical run; changes invalidate approval.
Detailed per-contract evidence stays private.

## Actual results and independent checks

The approved implementation processed all 18 accounts and 54 session
decisions. Ending cash for the **debit spread**, starting with $1,000:

| Delay applied to entry and exit | 1-cent slippage / leg / side | 2 cents | 3 cents |
|---|---:|---:|---:|
| 0 seconds | $983.20 | $971.20 | $959.20 |
| 1 second | $982.20 | $970.20 | $958.20 |
| 5 seconds | $979.20 | $967.20 | $955.20 |

Every spread configuration closed three hypothetical trades. Across these
sampled dates, account returns range from **−1.68% to −4.48%**. The three
zero-delay cases reproduce the preserved prior cash balances exactly after
removing floating-point rounding noise; they are not three new strategy
discoveries. No further delay, strike or cost setting was selected after
viewing these outcomes.

Every long-call configuration recorded three skips and ended with $1,000:
**27 configuration-level refusals** because entry debit plus commissions
and the exit reserve exceeded $100. This does not establish that a call
cost more than the entire $1,000 account, and zero cash return from no
positions is not profitable trading evidence.

The separate checker reconciled **3,861 saved marks**, all 54 decisions,
all cash/fees/reserves and all 18 summaries. Nine marks were unknown: the
same October 15, 17:16 UTC minute in each spread configuration failed the
one-second leg synchronization rule. The complete sampled-mark drawdown
is therefore **unknown for every spread case**. Observed-mark lower bounds
range from **4.88% to 7.58%**; they also omit between-minute extremes.
All scheduled exits had acceptable evidence, so there was no unresolved
exit and terminal modeled cash is known. Synthetic tests separately cover
unresolved exits and blocked later entries.

All **27 synthetic tests** passed, as did formatting/lint checks. Independent
review approved exact hashes before performance. The runner checked those
hashes again afterward. The checker uses independent arithmetic and quote
validation, but does not independently reconstruct signals/chain selection
or rescan every raw message to prove snapshot extraction. No obtained
market execution, early-assignment path, or broker account permission was
verified. [Frozen review](evidence/2026-10-20-options-execution/pre-performance-review.json),
[all 18 derived results](evidence/2026-10-20-options-execution/summary.json),
[accounting receipt](evidence/2026-10-20-options-execution/accounting-review.json),
[test scope](evidence/2026-10-20-options-execution/tests.json).

The private run contains the raw selected snapshots and ledger/mark files.
Its manifest SHA256 is
`e434df3a83fcdf0e629464384489cf499c5c9b9f7d2474e8679c9a76405b392c`.
Only derived aggregates and hashes are published. CSV-only backups preserve
the data but do not satisfy the original recovery adapter's additional
vendor-manifest verification requirements; do not silently replace those
original bytes or publish private vendor metadata.

## Funding and lifecycle limits

A call's paid premium and a spread's bounded expiration payoff do not prove
that a broker will approve the account or that stock delivery is funded.
SPY options are American style and physically settled. A long call can
require cash to exercise; a short call can be assigned early. The OCC/OIC
describes the bull call spread's lower debit and capped upside, and warns
about assignment and expiration. A modeled pre-expiry exit does not prove
an earlier assignment was impossible. [OIC spread](https://www.optionseducation.org/strategies/all-strategies/bull-call-spread-debit-call-spread),
[OIC long call](https://www.optionseducation.org/strategies/all-strategies/long-call),
[Cboe product comparison](https://www.cboe.com/tradable_products/product_comparison/).

Cboe's cited cash-account spread exception specifically concerns
European-style, cash-settled index options. It must not be extended to SPY.
Broker requirements can be stricter. The account study establishes only
conditional premium affordability and quote arithmetic; it has no broker
permission, assignment-allocation or stock-delivery reconciliation model.
[Cboe margin rules](https://www.cboe.com/us/options/strategy_based_margin),
[OCC disclosure, Chapters II–III and VIII excerpts](https://www.theocc.com/getmedia/a151a9ae-d784-4a15-bdeb-23a029f50b70/riskstoc.pdf).

## Research and open-source assessment

Two original papers were reviewed selectively, not read in full:

- **Santa-Clara and Saretto, _Option Strategies: Good Deals and Margin Calls_,
  November 2004 working paper:** data, strategy definitions, transaction-cost
  and margin sections (§§1–2, 4.1–4.2). Useful lesson: attractive option
  returns can change materially after spread costs, funding constraints and
  forced liquidation. Their S&P 500 futures/index options and notional return
  convention do not replicate this $1,000 SPY account.
  [Original UCLA paper](https://www.anderson.ucla.edu/documents/areas/fac/finance/santa_clara_option.pdf).
- **Goyal and Saretto, _Cross-Section of Option Returns and Volatility_,
  March 2008 working paper:** data/filters, portfolio construction and cost
  analysis (§§2–3.1, 5.2). It motivates explicit selection and stale/crossed
  quote filters and sensitivity to the quoted spread. Its 1996–2005
  cross-sectional straddles/delta-hedged positions and settlement treatment
  are substantially different from the present strategy. No replication or
  expected return is inferred.
  [Original university-hosted paper](https://www.ruf.rice.edu/~jgsfss/goyal_041808.pdf?origin=publication_detail).

The [source receipt](evidence/2026-10-20-options-execution/source-review.json)
records exact section/file scope and access limitations.

**QuantLib** was inspected at commit
[`bf35b19a4f3ffdfa2dcb2f0b48a82ef8a675371b`](https://github.com/lballabio/QuantLib/commit/bf35b19a4f3ffdfa2dcb2f0b48a82ef8a675371b)
(October 20, 2026), including its complete
[BSD-style license](https://github.com/lballabio/QuantLib/blob/bf35b19a4f3ffdfa2dcb2f0b48a82ef8a675371b/LICENSE.TXT)
and three complete source files:
[binomial engine](https://github.com/lballabio/QuantLib/blob/bf35b19a4f3ffdfa2dcb2f0b48a82ef8a675371b/ql/pricingengines/vanilla/binomialengine.hpp),
[American exercise adjustment](https://github.com/lballabio/QuantLib/blob/bf35b19a4f3ffdfa2dcb2f0b48a82ef8a675371b/ql/pricingengines/vanilla/discretizedvanillaoption.cpp)
and [finite-difference engine](https://github.com/lballabio/QuantLib/blob/bf35b19a4f3ffdfa2dcb2f0b48a82ef8a675371b/ql/pricingengines/vanilla/fdblackscholesvanillaengine.cpp).
These supply theoretical valuation/Greeks, American exercise logic and
dividend-model sensitivity. They do not supply historical quotes, obtained
fills, an account ledger or broker reconciliation. License conditions
require notice retention. No library was installed or executed. Recommendation:
keep the deterministic local quote/account engine for this experiment;
consider QuantLib later for separately validated theoretical checks, never
as a substitute for missing historical prices. LEAN and other full trading
frameworks were not audited in this scoped review.

## Frugal data recommendation

Use the owned cache first. If a later study requires more option history,
start with a frozen small data-quality experiment and a fresh provider quote,
then decide whether the measured coverage is worth extending. Existing
Databento integration and receipts reduce setup work; this is not a claim
that Databento is universally cheapest or that its full history fits the
remaining credits. Credit balance/expiry must come from current account
evidence, not the user's approximate recollection or an old quote.

The reviewed products advertise materially different histories:

| Product | Advertised start | Price conclusion |
|---|---|---|
| [Databento OPRA](https://databento.com/docs/knowledge-base/datasets/opra-pillar), [history update](https://databento.com/blog/opra-improvements-coming-soon) | CBBO-1m/definitions April 2013; event CMBP-1 March 2023 | Obtain exact request quote; do not extrapolate one sampled day to a whole chain/year. |
| [Cboe DataShop quote intervals](https://datashop.cboe.com/option-quote-intervals) and [EOD](https://datashop.cboe.com/option-eod-summary) | January 2012 | Symbol/date/field configuration needed; empty $0 subtotal is not free coverage. |
| [OptionMetrics IvyDB US](https://optionmetrics.com/united-states/) | January 1996 EOD | Vendor quote required; no verified numeric public price in this review. |

The 2013–early-2023 Databento minute history has different event/receive-time
semantics from recent event data; a future adapter must not pretend it has
exchange-capture timestamps or use an interval-ending snapshot early.
None of these products establishes a 50- or 100-year US options-chain
replay. From January 1996 through December 2025 there are 30 complete years,
subject to actual data validation, not 100. Long equity/index history or
synthetic theoretical options do not fill that gap.

No purchase, subscription, authenticated download or additional credit use
was performed for this study. Public prices/quotes are in the provider's
stated currency (USD for the local examples); sales taxes and account-specific
charges require checkout/contract evidence. The broader [data-cost dossier](FIFTY-YEAR-DATA-COSTS-2026-10-20.md)
records exact reviewed prices and licensing limitations. Free software and
already owned compute still incur time, electricity and storage costs, which
are not priced here.
