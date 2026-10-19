# Recovered options reconstruction: frozen before this run

Registered October 19, 2026, before inspecting recovered quote outcomes. The
original three pilot outcomes are already known; this is an integrity and
small-account feasibility exercise, not a new holdout or strategy search.

Use only the recovered, already-paid seven pilot batch deliveries: SPY EQUS.MINI
minute bars from March 28, 2023 through October 16, 2026; SPY OPRA definitions
for October 8, 14 and 15, 2026; and the existing two-call CMBP-1 deliveries for
each of those three full regular sessions. Verify the vendor file size/SHA256
and exact job parameters locally. Four recovered early-extension definition
jobs do not supply extension quotes. Do not recreate the original cache catalog,
credit ledger, missing Yahoo capture or streaming deliveries.

Reconstruct signals using EQUS.MINI and the unchanged opening-range adapter.
The original pilot used a Yahoo capture that is unavailable here, so equal
outcomes would not establish byte-identical reproduction of original inputs.
Retain the adapter's complete-session eligibility restriction explicitly as a
retrospective data-quality filter. No inference of full historical calendar
coverage or live eligibility is permitted.

Use the existing causal dated-chain selection, one $1-wide standard SPY call
spread expiring the next calendar day, and existing signal/entry/exit schedule.
Do not substitute another strike if the recovered contracts differ from that
selection. Preserve entry refusals and unresolved exits. Separate-leg quotes
remain hypothetical fills, not evidence of an atomic executable spread.

Run exactly six separate accounts: strict publisher flags and the existing
explicit publisher-flag sensitivity, each at baseline and an additional 1 or
2 cents adverse slippage per leg per side. The sensitivity is not a resolution
of the historical flag's meaning. Baseline costs remain $0.65 commission per
contract per side and one cent adverse slippage per leg per side, plus observed
bid/ask crossing. Each cost scenario recomputes entry eligibility.

Each account starts with $1,000 cash, no deposits, borrowing or fractional
contracts. At most one spread is entered on each of the three dates. Limit
entry debit including entry commissions plus a $1.30 exit-commission reserve
to the lesser of $100 and available cash. Process dates chronologically; a
closed exit restores its net proceeds before the next sampled date. These
dates are separate business days; broker settlement/permission is not verified.
An unresolved exit retains its debit and reserve and blocks all later entries.
Never replace it with zero profit, assumed exercise, assignment or settlement.

Report each trade's evidence/status, cash before/after, realized closed-trade
net, unresolved entry debit, reserve and available cash. Terminal account return
is reported only if no economic position remains unresolved; it is the return
across three sampled dates, never an annual return. Do not calculate daily NAV,
intraday drawdown or CAGR without the missing marks/lifecycle evidence. Retain
all six cases, including negative and no-fill results. No strategy promotion,
new acquisition, broker call or external model call is part of this protocol.
