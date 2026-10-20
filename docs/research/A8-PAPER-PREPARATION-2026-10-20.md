# A8 paper preparation — October 20, 2026

The new work is a local, deterministic preparation tool and a disabled experiment
registry. It does not start a service, call a model API, log into A8, collect prices,
open a database, place an order, or alter a scheduler. Each planned experiment has
its own **$1,000 virtual starting balance**. Existing A8 accounts are preserved.

## Existing implementation and what it establishes

The inspected stock writer is a prospective daily-bar simulator. Its SQLite tables
contain forecasts, simulated orders/trades, immutable capture identities and price
anchors. Entries use a regular-session opening strictly after the recorded
instruction; later completed bars recognize simulated fills. This is not a broker
acknowledgement, broker fill or reconciled brokerage position.

The old code fixes capital at $100, not $1,000:
[`ledger.py`](../../src/kq/equities/ledger.py) lines 23–25, 265–351 and 356–403
fix cash/tickets, compute liquidation-value summaries and simulate fractional
shares. Its five-position limit is at lines 599–634. The nine
[`portfolios.py`](../../src/kq/equities/portfolios.py) protocols hash $100 initial
cash, $10 orders, 10 bp per side and the existing loss pause into their definitions
(lines 21–39, 77–88). Changing a displayed balance or multiplying old P&L would not
create a new $1,000 account.

Useful patterns already exist in
[`portfolio_runner.py`](../../src/kq/equities/portfolio_runner.py):
separate `portfolio_id/paper.sqlite` files, immutable launch specifications and
captures, a durable in-progress record, a local exclusive writer lock, per-account
failure records, and same-capture retry handling. Reuse these patterns in a new
version; do not change old protocol IDs, seed cash or saved fills.

Authority is partly operational, not a distributed lock. The old stock CLI and
parallel runner reject a `READ_ONLY_MIRROR.txt` marker; a machine without that
marker is not cryptographically prevented from writing a new directory.
The separate strategy-lab [`authority.py`](../../src/kq/equities/strategy_lab/authority.py)
also pins hostname A8 and an old release path. That check is not automatically
present in every stock entry point. A future writer needs one explicit host/release
identity and an independently reconciled ownership lease.

The last cited live A8 inspection is **October 18**, not this preparation:
[`STOCK-A8-AUDIT`](STOCK-A8-AUDIT-2026-10-18.md) lines 3–38 recorded clean
account integrity and an available dashboard, but failed/unverified unattended
collection and scheduler commands. Collection depended on a desktop authenticated
connector. A public-price probe was not an authorized replacement of old forward
inputs. Current A8 health, installed commit, running processes and account
integrity were **not checked in this task**. Historical host paths in
[`STOCK-PAPER-LAB`](../STOCK-PAPER-LAB.md) are discovery evidence, not instructions
to overwrite a current checkout.

The options cache/CBBO inspectors and bounded historical replays are research
components. They do not establish a continuously funded forward options account.
The latest [sample inspection](evidence/2026-10-20-allocation/cbbo-sample-inspection.json)
retains legacy timestamp and undefined multiplier limits. Minute snapshots do not
prove exact quote age or atomic multi-leg execution. A new options account needs
integer contracts, verified deliverables/multipliers, funded premium/collateral,
daily marks, fees, expiry/exercise/assignment handling and an unresolved-exit state.
No real-money order or leveraged/naked exposure follows from this preparation.

## Tool delivered now

[`scripts/research_floor.py`](../../scripts/research_floor.py) uses the Python
standard library. It has no network client, subprocess launcher, dynamic module
loader, database connector, model-provider client or order interface.

- `template` emits a disabled registry to standard output. It creates no account.
- `review-digests` emits hashes to bind role reviews to exact experiment contents.
- `check` reads explicit local evidence and emits blockers and a deterministic
  five-role task queue. Exit 2 means blocked; exit 0 means evidence is ready for
  **manual review**, never permission or technical readiness to execute.

```powershell
python -m scripts.research_floor check --root . --registry docs/research/a8-paper-plan-2026-10-20.json
python -m scripts.research_floor review-digests --registry docs/research/a8-paper-plan-2026-10-20.json
python -m scripts.research_floor template --experiment new-stock:stock --experiment new-options:options
```

Run from the repository root with its existing environment. The commands above
print JSON only. Saving their output is a separate, explicit file operation.
They require no API key.

The supplied [plan](a8-paper-plan-2026-10-20.json) names four preparation lanes:
T01 SPY trend, A02 allocation, MOM_05 instrument mapping, and defined-risk SPY
options. These are references for engineering, not four newly approved strategies.
MOM_05 used French industry research portfolios; mapping those to actual securities
is a new experiment requiring registration. The options lane has no newly selected
trade rule. All four remain disabled and blocked. Four isolated virtual balances
would total $4,000; there is no shared $1,000 account or real capital allocation.

The [current preflight](evidence/2026-10-20-a8-paper/current-preflight.json)
preserves the actual local result. Missing evidence is explicit; background
backtests are not counted as prospective registrations or forward-paper contracts.

The checker verifies:

- $1,000 per experiment, finite unexhausted trial caps, zero external spend and
  disabled writers;
- separate, non-overlapping, nonexistent account destinations under
  `paper-experiments/`; no reset of existing accounts;
- exact bytes of registration/source/data/validation artifacts, including every
  locally enumerated member of a data manifest;
- five named role decisions tied to the exact experiment digest, with an
  independent reviewer distinct from the implementer;
- a separate implemented paper contract and validation receipts tied to its
  registration; additional stock and options accounting requirements;
- a hash-pinned A8 read-only receipt no older than 24 hours, matching deployed
  commit, preserved old accounts, one writer, empty new destinations, an
  independently verified feed/calendar and an observed unattended completed run;
- an observed session matching the independently expected session. A seven-day
  hard stale-data bound is an additional sanity check, not an exchange calendar.

Credential filenames, absolute/traversing paths, linked evidence and nonfinite or
duplicate-key JSON are refused. Hashes prove byte identity, **not that a supplied
attestation is true or authentic**. The checker does not independently visit A8,
inspect a broker, audit a claimed paper engine, or establish strategy validity.
It always reports `execution_ready: false`. Its zero-dollar fields constrain
this tool's accepted preparation input; they are not a billing gateway for another
program. The tool cannot dispatch jobs or enforce another process's trial budget.

## Deterministic multi-role workflow

Use the existing [research-floor design](AGENT-RESEARCH-FLOOR-2026-10-19.md)
as role guidance, with this task queue as the concrete handoff:

1. **Proposer:** freeze a tradable rule, finite variants, dates, capital and costs.
   Reference existing failures and keep the prior search visible.
2. **Data reviewer:** verify availability timestamps, raw hashes, actual instrument
   identities, calendar, corporate actions and feed continuity.
3. **Implementer:** implement the separate simulator/adapter and record its hashes.
   Keep source capture, signal calculation and account mutation separate.
4. **Independent reviewer:** reconcile causal timestamps, account conservation,
   costs and all rejection/failure paths without reusing the simulator's arithmetic.
5. **Risk reviewer:** inspect $1,000 ticket feasibility, fractional eligibility or
   integer options, collateral and lifecycle/uncertain-state behavior.

The orchestrating coding session archives the registration, every result/failure,
review evidence and actual costs. Changing an artifact or rule invalidates existing
bundle reviews. These are responsibilities, not five continuously running paid
models. Current in-session agent work is not an installed A8 daemon.

Prepare and test the new account engine locally first. Next obtain a bounded
read-only A8 inventory, preserve existing account backups, and stage an isolated
release. An actual unattended capture/import must be observed before claiming
reliable server operation. Prospective accounts begin at their real initialization
time; do not replay old research outcomes into a newly created live history.
Each new workflow records completed-session source age, decision time, immutable
intent, simulated fill convention, cash, reservations, marks and unresolved states.

Broker paper is a distinct later adapter. If that is desired, use an allowlisted
paper endpoint, local credentials, reconciled account/permissions, durable intent
before submission, deterministic client IDs and lookup-only recovery of uncertain
submissions. Broker and local simulated performance must retain separate labels.
An existing private QuantLab adapter/state is not transferred or activated by
this Forecast Lab registry.

## Missing evidence and inputs

No credential or repeated Databento credit-balance question is needed for this
local work. Exact owner credit evidence already exists privately.

Needed before preparing the new simulator: a frozen prospective rule/actual
instrument mapping for each chosen lane, the practical accounting contract, and
validation of that implementation. These are engineering tasks, not reasons to
ask the owner to invent data. Needed before server activation: current read-only
A8 inventory/identity, immutable old-account baseline, independent feed/calendar
evidence, empty new account directories and an observed unattended run.

A broker choice, authenticated local paper account and relevant options permissions
become necessary only for broker-connected paper orders. They are not required
for the deterministic workflow or local simulator preparation. A model API provider
and enforced spend cap become necessary only if a separate autonomous LLM runtime
is deliberately added.

## Current feed choices and economics

The official Alpaca pages checked October 20 describe free Basic data as IEX-only
for stocks and an indicative options feed. Algo Trader Plus is listed at $99 per
month with complete stock coverage and OPRA options data.
[Plan comparison](https://docs.alpaca.markets/us/docs/about-market-data-api).
The options endpoint explicitly says indicative trades are delayed and quotes
modified. Use that free feed for integration tests; it is not evidence of executable
NBBO spreads or a trading edge.
[Endpoint specification](https://docs.alpaca.markets/us/reference/optionlatesttrades).

At the listed price, twelve months costs $1,188, or 118.8% of one $1,000 account,
before trading. Sharing one feed across independent simulated books can reduce
allocated cost per book, but does not reduce the actual subscription bill.
No subscription was bought or enabled. Keep initial work on the existing stack
and separately evaluate actual feed quality and permissions before choosing a
recurring expense.

QuantConnect's paper documentation says paper assets need a supported live-data
provider and live option orders need a third-party options provider. Its documented
default model also assumes no slippage and immediate complete market-order fills.
Installing that framework would not itself solve feed availability or validate
realistic options fills.
[QuantConnect paper documentation](https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/quantconnect-paper-trading).
This was a bounded documentation check, not a vendor account or installed-code test.

## Review and verification scope

This is a targeted local source/document audit. It inspected the legacy portfolio
definitions/runner and ledger entry, sizing, preservation and accounting paths;
stock CLI and research-writer authority; dated A8 operational evidence; current
handoff, long-history interpretation and existing research-floor design.
It is not a new complete-repository review or current server-health audit.

Focused artificial tests exercise changed source/data bytes, invalidated reviews,
malformed reviews, stale/future host receipts, stale capture dates, duplicate and
overlapping accounts, existing-state refusal, $100 versus $1,000 inputs, exhausted
caps, options collateral/integer/mark requirements, broker prerequisites, unsafe
paths, duplicate/nonfinite JSON, CLI behavior and absence of file writes.
These fixtures establish software behavior, not real paper fills or investment
performance. Full-project regression, deployment and Git publication are recorded
separately by the integrating agent.

Local validation of the delivered files: **35 focused tests passed**, Ruff check
and formatting passed, and strict mypy passed for `scripts/research_floor.py`.
The actual disabled plan produced four blocked experiments, $4,000 total planned
virtual capital and twenty pending role tasks. No new performance was computed.
