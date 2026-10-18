# Paper outage recovery and Tester evidence

Owner instruction (2026-10-17): fix paper trading until it runs, then reuse useful
Tester.zip material and test it. This authorizes an explicitly audited recovery
path, superseding the old instruction to stop indefinitely after a missed session.

## Design

Keep A8 the sole writer and retain every account, frozen rule, prior capture,
review, failure and losing outcome. The ordinary importer keeps its strict guard.
An explicit recovery option recognizes only previously recorded instructions,
session by session, at today's observation time. It applies the existing daily
loss pause and fixed holding exits, records delayed recognition in an immutable
journal, and creates no intermediate forecasts or discretionary historical orders.
New decisions use the actual current import time and the latest completed session.
An interrupted or repeated import must not duplicate orders or recovery evidence.

Unavailable, never-held, noncandidate symbols may retain their exact previously
captured historical observations with original source times and explicit missing
coverage. They cannot supply current prices, signals or fills. Required symbols,
unexpected price revisions and unexplained session gaps still fail closed.

Alternatives rejected: resetting accounts loses evidence; replaying historical
strategy selections manufactures prospective decisions; waiting alone leaves the
multi-session rejection permanently unresolved even after genuine prices arrive.

## Implementation and validation

- [x] Reproduce actual source and multi-session failures; preserve raw responses.
- [x] Add transactional recovery tests, chronological processing, durable evidence.
- [x] Add constrained missing-history retention tests and original-time provenance.
- [x] Expose recovery in both import routes; visibly label delayed results.
- [x] Rehearse actual captures against consistent A8 database copies; test replay.
- [x] Run focused tests, full repository gates and source review before deployment.
- [x] Back up authoritative databases; deploy verified source/capture packages;
      recover A8 accounts and refresh independent research lanes where valid.
- [x] Verify actual persisted orders, cash, exits, reports and idempotency; mirror
      through consistent read-only-source backups and verified atomic replacement.
- [x] Update the existing scheduler instructions with this reviewed recovery path;
      keep manual recovery distinct from evidence of scheduled success.
- [x] Review and safely test isolated Tester source/data; retain failed methods and
      only integrate independently tested accounting/causality practices.

## Limits

No live or brokerage-paper orders, new dependency, feed purchase, new scheduler,
strategy promotion, risk-cap change, account reset, or original Kalshi service edit.
Tester documents are evidence, not authorization to adopt their capital, broker or
leverage settings. Missed sessions remain an operational outage even after their
precommitted instructions are reconstructed. No profitability or unattended feed
claim follows from software tests or a successful manual repair.
