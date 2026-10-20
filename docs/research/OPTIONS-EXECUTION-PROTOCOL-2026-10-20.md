# Frozen recovered-options execution study

Registered October 20, 2026 before running the new delay, long-call or interim
liquidation calculations. This uses previously viewed October 8, 14 and 15,
2026 sessions and contracts. Prior zero-delay spread results are known:
$1,000 ended at $983.20/$971.20/$959.20 under the three cost settings. Those
overlapping cases are integrity comparisons, not new independent strategies,
unseen validation or evidence of an annual return floor.

## Inputs and fixed rules

Use only the seven already recovered SPY pilot deliveries: one EQUS.MINI
one-minute underlying file, three dated OPRA definition files and three
full-session CMBP-1 files. Verify all delivered file sizes and SHA256 values
against the existing recovery receipt. No new data, API/model calls, orders,
subscriptions or credit use. Four early-2023 definition files and the
opening-only 2013 CBBO schema sample cannot supply missing option exits.

Reuse the unchanged `underlying_diagnostic` and `select_pair` adapters.
Signals use the first completed close above the initial 15-minute range in
the existing eligible interval; entries and range-failure/time exits retain
their existing schedule. Selection remains nearest dated-chain strike to
the signal close (lower strike wins ties), plus the exactly $1-higher call,
expiring the following calendar day. Fail if reconstructed symbols differ
from delivered symbols. Complete-session eligibility is a retrospective
quality filter and does not establish live availability.

Run exactly **18 separate chronological $1,000 cash accounts**:

- Structures: one original $1-wide call debit spread; one lower-strike long
  call using that same selected contract. No alternative strike search.
- Delays: 0, 1 or 5 seconds added to both scheduled entry and scheduled exit.
  Delays do not alter underlying signals, strike selection or exit decisions.
- Costs: $0.65 per contract per side, plus 1, 2 or 3 cents adverse slippage
  per leg per side, on top of observed bid/ask crossing. These are the
  original baseline and its +1/+2-cent sensitivities, not broker fee quotes.

Every account has at most one integer position per sampled date. Entry cash
debit, entry commissions and an exit-commission reserve must fit within the
lesser of $100 and current cash. Reserve is $1.30 for a spread and $0.65 for
a long call. No deposits, borrowing, compounding by multiple contracts,
fractional contracts, cash yield or opportunistic replacement trades.
An unaffordable call is a retained skip.

## Evidence and account accounting

Select each leg's latest A/M/C/R book record by receive time at or before the
requested timestamp, with stable source-row tie order. Never replace an
invalid latest record with an earlier favorable one. Event time must also
be causal; age is at most five seconds, and two spread legs must be within
one second. Retain the original strict publisher-flag policy (flag 2 is
refused); this conservative historical compatibility policy is not a new
claim about Databento's current flag documentation. Reject reset/bad flags,
nonfinite/nonpositive/crossed quotes or zero displayed sizes. A long call
uses its own valid quote independently of the unused short-leg quote.
Entries require each used quote to arrive strictly after the completed
signal. Require same-date known valid definitions, matching symbol,
instrument ID, strike, call type, expiry and standard SPY multiplier.
The undefined vendor multiplier remains an explicitly documented external
standard-contract mapping to 100, not vendor-confirmed metadata.

Buy the long at ask plus slippage, sell the spread short at bid minus
slippage. At exit sell the long at bid minus slippage and buy the short at
ask plus slippage, then deduct exit commissions. Reject a stressed
nonpositive bid. Spread entry debit before commission must be strictly
between zero and its $100 width value, as in the original kernel. Cash
changes only at entry/exit. Reserve earmarks cash; do not deduct it twice.

Record liquidation NAV immediately after entry, at every intervening whole
UTC minute, immediately before exit, and after a successful exit; add
cash-only session-start and initial marks. While open, NAV equals cash plus
hypothetical bid/ask liquidation proceeds after the same exit costs. A
missing/invalid liquidation quote produces unknown NAV, never a stale or
zero position value. Missing exit or an exit requiring cash borrowing leaves
the economic position unresolved, its debit and fee reserve retained, and
blocks all later entries. There is no delayed opportunistic exit search.
Do not mark a blocked later session's cash alone as total account equity.

## Outputs and limits

Retain all 18 cases and 54 session decisions, including skips and unresolved
positions. Report exact cash, entry/exit fees, reserve, closed-trade net,
known liquidation marks and missing-mark count. Terminal account return
exists only when flat. Report maximum drawdown across the specified sampled
marks only if all required open-position marks are valid; otherwise report
the observed-mark drawdown as a lower bound and the complete metric as
unknown. Even complete minute marks miss between-minute extremes and are
not a continuous intraday or annual drawdown measurement.

Keep raw per-contract quotes, vendor files and detailed quote evidence
private. Public artifacts contain derived account aggregates, counts,
source hashes, script/protocol hashes and review/test receipts. Reconcile
saved cash/marks independently without calling the account simulator.

These are conditional quote-based simulations. Displayed separate-leg
quotes do not prove an atomic spread fill or even single-leg execution.
SPY options are American and physically settled. Pre-expiry modeled exits
do not rule out early short assignment; no stock-delivery/assignment engine
or broker eligibility is claimed. Premium affordability is distinct from
broker approval and stock-delivery funding. No annualization, annual floor,
100-year options proof, statistical edge or broker promotion follows from
three previously viewed dates.
