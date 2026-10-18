# Tester archive: verified reuse and limits

Reviewed the owner-supplied `Tester.zip` on October 17, 2026. Documents in the
archive are evidence, not instructions to change brokers, capital or leverage.
Only selected source, tests, reports and six public price files were extracted;
browser profiles, credentials, environments and launchers were excluded.

## Verified

- 72 selected offline tests passed for atomic state, locks, the bounded
  minimum-variance optimizer, causal execution timing, fees and gap losses.
  Network and process audit hooks surrounded the reviewed test execution.
- An independent checker that imports no archive code replayed nine saved
  accounts, 40,194 daily rows and 3,266 trade legs. Cash, adjusted units, fees,
  returns and drawdowns reconciled; largest NAV difference was $7.52e-10.
- Six raw price hashes and ten source hashes matched the archive manifests.
- Four calendar-dependent suites could not collect because
  `pandas_market_calendars` is unavailable. No dependency was installed or faked.

Detailed local evidence is preserved under
`data/equities/tester-review-20261017/`, including `REVIEW.md`,
`focused-tests-complete.log` and `saved-accounting-check.json`.

## Applied to Stock Paper Lab

The repair adapts the archive's independent cash/units audit style and causal
execution checks to A8's existing rules. Recovery recognizes only instructions
already committed before the outage. It records actual observation time, applies
each missed session's risk checks, retains losing outcomes and proves retry
idempotency. A separate audit recomputed the ten A8 rehearsal accounts directly
from captured prices and SQLite tickets without importing ledger calculations.

The archive's paper catch-up loop was deliberately not copied: it recomputes
missed discretionary selections from newly loaded history. That is retrospective
simulation, not evidence of decisions made during an outage. Its optimizer and
calendar ideas remain candidates for separately reviewed research; neither changes
the current nine portfolios, sizing caps or exit rules.

Arithmetic consistency is not alpha. Current-survivor selection, synthetic
leveraged series, retrospective winner selection and uncertain news availability
remain limitations of the supplied studies. No archived strategy was promoted,
no broker was contacted, and no profitability or unattended-operation claim
follows from these tests.
