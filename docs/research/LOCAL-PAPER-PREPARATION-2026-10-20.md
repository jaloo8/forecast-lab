# Local stock and options paper preparation — October 20, 2026

The owner chose **“Prepare locally for now; A8 can wait.”** The new local
accounting module and CLI prepare separate $1,000 books for whole-share stocks
and purchased standard 100-share options. No actual experiment, market feed,
scheduler, broker connection or new account was started at this checkpoint.
Artificial test prices establish software behavior, not trading performance.

Read the [accounting contract](LOCAL-PAPER-CONTRACT-2026-10-20.md) and
[validation receipt](evidence/2026-10-20-local-paper/validation.json) for the
delivered scope. The earlier [A8 plan](A8-PAPER-PREPARATION-2026-10-20.md),
century research and options-study rules remain frozen.

## What is implemented

- Immutable registration, a new $1,000 virtual balance and separate directories.
- Decimal accounting, conservative cent rounding, cash/position reservations,
  entry limits and reserved option exit fees.
- Separate intent, quote observation and explicit simulated-fill commands.
  Importing a quote does not trade. No command downloads data or starts a bot.
- Qualified later quotes only, display-size checks, stale/bad quote blocking,
  deterministic retry IDs and no caller-supplied clock override.
- Transactional SQLite events with hash-chain and accounting replay checks.
  Writer identity binds the host, absolute path and engine source fingerprint.
- Unknown liquidation value when marks are unavailable; unresolved option
  expiry preserves the position instead of inventing settlement or a zero.

The execution convention is fixed at stock ask/bid plus/minus 10 basis points,
and option ask/bid plus/minus $0.01 per underlying share with $0.65 per contract
per side. These are assumptions, not observed broker costs. The option template
sets a $100 entry cap including entry commission and reserved exit commission.
The engine permits an explicitly registered cap up to $1,000; it never increases
that cap itself. Every account starts at $1,000; the trade cap is separate.

Sale proceeds remain restricted because settlement is not implemented. This
conservative foundation cannot sustain a normal rotating portfolio until that
gap is addressed. Source names and hashes are supplied claims; the module does
not independently authenticate their provider or payload bytes.

## Inspect locally

Run from the repository root after the existing Python 3.12 environment is set up:

```powershell
.\.venv\Scripts\python.exe scripts/local_paper.py --help
.\.venv\Scripts\python.exe scripts/local_paper.py template --asset-type stock
.\.venv\Scripts\python.exe scripts/local_paper.py template --asset-type option
.\.venv\Scripts\python.exe -m pytest tests/test_local_paper.py tests/test_local_paper_cli.py
```

The templates print incomplete JSON and create nothing. Required evidence fields
are null; the engine refuses them. Filling the fields makes a registration
syntactically acceptable, not independently verified or ready for activation.
No API key is needed for these commands. Never use a credential file as input.

## Interface for a future registered experiment

These commands describe the manual interface; they were not used to launch an
account in this checkpoint. `local-paper/` is ignored by Git. Input files must
be ordinary JSON without duplicate keys, nonfinite values or credential fields.
The root directory must already exist and must not contain another book in
its ancestor chain.

```powershell
.\.venv\Scripts\python.exe scripts/local_paper.py create --root local-paper --registration local-paper/registration.json
.\.venv\Scripts\python.exe scripts/local_paper.py intent --book local-paper/BOOK_ID --input local-paper/intent.json
.\.venv\Scripts\python.exe scripts/local_paper.py quote --book local-paper/BOOK_ID --input local-paper/quote.json
.\.venv\Scripts\python.exe scripts/local_paper.py fill --book local-paper/BOOK_ID --intent-id INTENT_ID --quote-id QUOTE_ID
.\.venv\Scripts\python.exe scripts/local_paper.py status --book local-paper/BOOK_ID
.\.venv\Scripts\python.exe scripts/local_paper.py cancel --book local-paper/BOOK_ID --intent-id INTENT_ID
```

One pending intent per book is the deliberate v1 simplification. Use the same
intent/quote IDs for exact retries; conflicting content is refused. Inspect after
an interrupted operation instead of inventing replacement IDs. Initialization
never overwrites an existing directory. On storage/integrity errors, preserve
the book and stop writes; there is no automatic repair or reset command.

Known bad attributable quotes are recorded and prevent fallback to an older
good quote. Other malformed requests and refused fills raise errors without
persisting a rejection event. Successful events and accepted quote-quality
refusals are auditable; this is not a complete durable log of every attempted
command. A nonzero CLI exit indicates refusal, not a trade.

The hash chain does not stop a privileged user from rewriting the whole database
or removing its tail. Preserve external checkpoints. Copying a book to another
host/path is not a supported writer migration; inspection is allowed, mutation
is refused. No distributed lock or cross-machine synchronization is provided.

## What remains before a continuing paper experiment

Freeze actual-instrument rules and practical ticket sizes; connect a reviewed
quote collector and validate time/size/contract semantics; implement settlement,
sessions and corporate actions. Options additionally need lifecycle handling.
Version 1 supports long options only, so it cannot run the earlier debit-spread
study. A8 access and deployment are deferred by the owner.

The [offline research coordinator](../../scripts/research_floor.py) remains a
separate evidence/task checker. The design, implementation and independent test
agents used here reviewed software; no external multi-agent service was launched.
No new strategy backtests or market-return claims arise from this checkpoint.
New data charges, paid model API calls and broker orders are all zero.
