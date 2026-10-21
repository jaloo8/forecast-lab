# Local paper accounting contract — October 20, 2026

Status: **implementation contract for accounting preparation**. The owner chose
“Prepare locally for now; A8 can wait.” This defines a separate, bounded local
accounting foundation. It does not activate a strategy, price collector, scheduler,
broker adapter or a second writer for an existing account. Creating templates and
testing artificial events is useful preparation; creating empty $1,000 books alone
would not establish a running experiment.

The initial design was written before review of its new implementation. Source and
test results must be reported separately, with exact hashes and actual commands.
No results from the prior research are imported into a prospective account.

## Scope and evidence boundary

Each future experiment starts with its own **$1,000 of virtual USD**, at its actual
registration time, in a new local directory. No shared balance, deposits, resets,
borrowing or migration of A8's old $100 books are part of this contract.

Version 1 permits cash-funded purchases and sales of previously owned whole stock
shares or integer long standard US option contracts. It does not permit shorts,
short options, spreads, fractional options, margin, exercise or assignment. The
historical SPY debit-spread study therefore cannot be activated by this foundation.
A long option is a different exposure and needs its own frozen prospective rule.

All events are labeled **local input simulation**. A synthetic fixture remains a
software test. A supplied quote and a local simulated fill are not a vendor-verified
market observation, broker acknowledgement, broker fill or reconciled brokerage
position. Source IDs and supplied SHA-256 values establish claimed provenance and
byte identity only; they do not authenticate the provider or prove that the stated
quote existed. No LLM output sets a price, an account balance or a probability.

The component has no network, secret discovery, subprocess, broker or model API
interface. It accepts explicit local input and records deterministic transitions.
The old A8 plan, research registrations, all 200 century rules and frozen QuantLab
execution fingerprints remain unchanged.

## Registration and account identity

An immutable registration fixes the following before an intent can be accepted:

- Schema version, unique book ID, strategy ID and strategy-content SHA-256.
- Simulation-only mode, USD denomination and initial cash `1000.00`.
- A single asset kind and finite instrument allowlist. Stock quantities are whole
  shares; option quantities are whole contracts.
- Exact option identity: underlying, call or put, strike, expiration, last
  tradable UTC time, multiplier `100`, standard unadjusted deliverable, and a
  definition-evidence hash. A symbol suffix alone does not verify the deliverable.
- Allowed source identifiers, price and quantity precision, fixed fees/slippage,
  maximum quote age, maximum capture delay and maximum entry debit.
- A local host identity and the initial source/registration digest. A writer on a
  different host refuses mutation; this is not a distributed lease or protection
  against someone copying and modifying a database.

Registration is stored once with its hash. An existing destination is never reset
or silently reused with another registration. A new strategy or changed cost/risk
rule requires a new version and book. The account identifier is not a filesystem
escape: traversal, absolute child paths, linked destinations and overlapping book
directories must be refused by the preparation interface.

No executable registration is implied for the four old preparation lanes.
MOM_05 still needs a defensible mapping from industry research baskets to actual
instruments. The options lane still needs a frozen tradable rule and qualified
contract/feed evidence. Blank or placeholder hashes cannot establish readiness.

## Public interface

The agreed operations are `create_book`, `submit_intent`, `observe_quote`,
`fill_intent`, `cancel_intent` and `inspect_book`. Concrete field names and example
templates belong with the implementation. Their required semantics are:

| Operation | Required behavior |
|---|---|
| `create_book` | Validate and persist a new immutable registration and initial cash event; refuse overwrite. |
| `submit_intent` | Persist a unique buy or sell instruction, funding/position reservation and local commit time atomically. |
| `observe_quote` | Append a uniquely identified quote observation with its claimed source, payload digest, event time and receive time; no trade follows automatically. |
| `fill_intent` | Use one qualified quote observed after the already committed intent; append the simulated fill and accounting changes atomically. |
| `cancel_intent` | Close an unfilled intent and release only its own reservation; do not erase the intent or previous failures. |
| `inspect_book` | Reconcile the registration/event history and report cash, reservations, positions, marks, unknowns and deployment blockers without trading. |

Public operations use the actual local UTC clock. There is no public `now`,
`as_of` or initialization-date override for changing accounting history. Tests may
replace the internal clock function and must be labeled artificial. The local
clock is not a trusted external timestamp service; regressions relative to the
last persisted event are refused, and clock uncertainty blocks activation.

## Money, funding and fill convention

Money and price inputs are finite decimal strings. Floats, booleans masquerading
as numbers, NaN, infinity, negative quantities and quantities outside the registered
precision are refused. Arithmetic uses `Decimal`; unit prices retain the declared
precision. Cash debits round upward to cents and credits round downward to cents.
No binary floating-point cash balance or favorable rounding adjustment is allowed.

The initial reference convention is:

| Asset | Simulated buy price | Simulated sale price | Commission per side |
|---|---|---|---|
| Stock | Ask plus 10 basis points | Bid less 10 basis points | $0.00 per order |
| Standard long option | Ask plus $0.01 per underlying unit | Bid less $0.01 per underlying unit | $0.65 per contract |

These are assumptions for validating the accounting foundation, not measured
broker costs. Any configurable implementation must freeze its accepted values in
the registration; it must not silently choose different values after outcomes.
Stock maximum entry debit cannot exceed the account's $1,000. The options reference
budget is **$100 per entry including entry commission and reserved exit commission**,
matching the distinction preserved in the three-session study. This does not say
that a contract costing over $100 is unaffordable for the whole account.

A pending buy reserves its maximum funded debit plus the exit commission reserve.
Multiple intents cannot spend the same cash. A pending sale reserves already owned
units; it cannot oversell units reserved by another instruction. Filling a buy
debits actual premium/notional and entry commission, releases unused reservation,
and retains its exit commission reserve. Filling a sale removes owned units,
credits net sale proceeds and releases the corresponding exit reserve. Reservations
are restrictions on existing cash, not extra assets or additional debits.

There is no settlement calendar or settled-cash adapter in this preparation.
Sale proceeds remain explicitly restricted from subsequent purchases until a
separately reviewed settlement mechanism exists. Merely increasing total cash
does not establish spendable cash. Restricted proceeds are not a loss, and neither
restricted proceeds nor fee reservations may be counted twice in net assets.

For a stock arithmetic fixture, buying two shares at ask `100.10` with 10 bp
slippage debits `200.41`; selling them at bid `109.90` with the same slippage credits
`219.58`, giving `19.17` net profit under the cent-rounding rule. For an option
fixture, one contract bought at ask `1.20` debits `121.65`, and a sale at bid `1.50`
credits `148.35`, giving `26.70`. The option buy must be rejected under a $100 entry
budget; that arithmetic case is tested only with a separately declared larger
fixture budget. These are hand-calculated examples, not executed market results.

## Quote qualification and causal ordering

A quote carries a unique observation ID, instrument ID, allowed source ID,
SHA-256 of its claimed source payload, explicit raw bid/ask, side sizes, source
event time, received time and an explicit quality classification. Receipt and
event times are timezone-aware UTC. The local append time is assigned by the
engine; a caller cannot overwrite it. If raw payload bytes are not checked by the
component, its report must say so rather than call the hash independently verified.

For a fill all of the following are required:

1. The intent committed before the quote's source event time, and the quote was
   appended after the intent. A quote already known at intent creation cannot
   become a future fill by changing an ID or copying a file.
2. Source event time is no later than received time; received time is no later
   than the current local clock. Event-to-receive delay is at most five seconds,
   and event-to-fill age is at most sixty seconds under the reference convention.
3. The quote is raw bid/ask with known timestamp semantics. Indicative, modified,
   delayed, interval-ambiguous, stale, crossed, zero-tradable-side, nonfinite or
   unknown-quality observations cannot produce a fill.
4. The instrument and standard option metadata match the immutable allowlist.
   A usable quote has enough visible quantity on the relevant side for the entire
   intent, with units explicitly normalized to shares or contracts.
5. Limit/budget, cash reservation, owned-quantity and option cutoff checks still
   pass at fill time. Nothing fills past the registered option cutoff.

The fill is all-or-none; no partial-fill queue or market-impact model is claimed.
The same observation cannot fill multiple distinct intents in one book. Separate
books are independent experiments, not a demonstration that their combined orders
could all obtain the quoted liquidity. Bid/ask crossing and added slippage are
model assumptions, not evidence of an obtained fill or queue priority.

An invalid fill attempt leaves holdings and cash unchanged and records a refusal
reason when the request can safely be attributed to a valid book. Malformed input
or a corrupt ledger may fail before an event is appended; such failure must never
be reported as a persisted rejection or a successful trade.

## Durability, retries and verification

An SQLite transaction or equivalently durable append-only mechanism must commit
intent/reservation together and fill/cash/position changes together. A crash must
leave either the entire transition or none of it. Updates cannot erase history.
The implementation uses an ordered event hash chain bound to the registration,
with canonical serialization, event ID and previous hash. A verifier recomputes
both the chain and accounting state; a correct hash alone is not accounting proof.

Unique caller IDs are idempotency keys. An identical retry returns the existing
result without another reservation, quote or fill. Reusing an ID with different
content fails. A transaction lock and funding check prevent concurrent writers
from overcommitting cash or units. A hash chain detects alteration relative to
its retained head; it does not prevent a privileged user rewriting an entire
database or prove integrity without an independently preserved checkpoint.

Verification reports registration identity, initial cash, current cash,
restricted proceeds, pending commitments, exit reserves, holdings, cumulative
fees and the event head. It checks nonnegative funded/spendable cash and holdings,
reservation conservation, unique IDs, causal ordering and cash reconciliation.
Corrupt or missing state fails closed; there is no automatic repair/reset path.

## Marks, expiration and missing lifecycle support

An inspect result separates known cash from liquidation value. A long position's
qualified mark uses the bid less the registered sale slippage and exit commission.
Cash plus these net liquidation values is the modeled net asset value; subtracting
the same reserved exit commission again would double count that cost.

If any held instrument has a missing, stale, unqualified or expired mark, total
liquidation value and return are **unknown**, not zero and not forward-filled from
an old price. Report the last known observation/time separately. Account drawdown
over incomplete mark coverage is unknown; a minimum observed loss, if displayed,
must be explicitly labeled a lower bound.

An open option at or after its registered last tradable time is
`UNRESOLVED_EXPIRY` (or an equivalently explicit implementation status). Retain
its original position, cost and reservations. Do not erase it, assume zero value,
invent an intrinsic-value settlement or synthesize a stock delivery. New entries
remain blocked while the book has an unresolved lifecycle state. There is no
claim of automatic exercise, funded delivery or a broker's do-not-exercise process.

Corporate actions, dividends, stock splits, delistings, settlement dates, holidays,
early closes, halts, option adjustments and lifecycle resolution remain unimplemented
unless separately evidenced. Their absence is an activation blocker, not a reason
to change a historical strategy or silently repair its account. No claim of
total-return replication follows from a price-only ledger.

## Required independent verification and next release gate

Meaningful artificial cases must cover exact stock/option funding and rounding,
entry refusal under the $100 budget, exit-fee reserves, restricted sale proceeds,
position conservation, stale/crossed/ambiguous quotes, quote-before-intent,
future/regressed clocks, nonfinite and duplicate JSON keys, conflicting retries,
no duplicate fills, cancellation, concurrent overspending, interrupted transactions,
tampered/missing records, wrong host, unknown marks and unresolved expiration.
Tests should independently calculate expected cash rather than import the engine's
arithmetic helper as their oracle. Passing fixtures establish software behavior.

Before a prospective experiment is activated, it separately needs a frozen actual
instrument strategy, reviewed source and account contract, qualified continuously
captured feed and session calendar, corporate-action/settlement/lifecycle behavior,
local authority and a recovery drill. A broker adapter additionally needs its
allowlisted paper host, local authentication, permission checks and reconciliation.
The A8 access decision can wait; none of these prerequisites is supplied by a
successful local unit test or by increasing a displayed account balance.

## Source and review scope

This is a local design derived from the owner's latest instruction and these
inspected repository records at base commit
`a3a16fc163187840ad29b75745ce997b8dbf5800`:

- [A8 preparation](A8-PAPER-PREPARATION-2026-10-20.md): old account identities,
  authority limits, proposed lanes and funded-account/lifecycle gaps.
- [Options execution results](OPTIONS-NEXT-STUDY-2026-10-20.md): separate $1,000
  account/$100 trade budget, unknown marks, contract and lifecycle limitations.
- [HANDOFF](../../HANDOFF.md), [PROJECT_STATE](../../PROJECT_STATE.json) and
  [AGENTS](../../AGENTS.md): current scope and preservation requirements.

No new external vendor claim, research return, live A8 observation, data purchase
or broker permission is established by this contract. Implementation review and
its exact validation receipt must state which requirements were actually delivered.
