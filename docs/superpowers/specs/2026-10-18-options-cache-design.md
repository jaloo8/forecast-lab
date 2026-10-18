# Options data acquisition and reusable local cache

Status: proposed design, October 18, 2026. No downloader implemented and no
Databento credits spent. Owner authorized the free-credit route and requested
planning/storage before acquisition. Out-of-pocket budget remains **$0**.

Scope: support the fixed [SPY candidate](../../research/OPTIONS-CANDIDATE-2026-10-18.md)
and make repeated tests independent of vendor calls. Source selection and
historical limitations remain in the [source audit](../../research/OPTIONS-DATA-SOURCES-2026-10-18.md).
No broker, live feed, new dependency, fee change or strategy optimization.

## Acquisition choice

Compare these using free cost estimates, before any data submission:

| Approach | Benefit | Limitation |
| --- | --- | --- |
| Narrow entry/exit windows for the selected two contracts | Smallest targeted purchase | Cannot test arbitrary alternative exits or strikes later |
| Session history for those two contracts | Reusable for alternative intraday exits and diagnostics | More records; still not a full chain |
| Whole SPY option chain over many years | Broadest reuse | Unbounded relative to this experiment; reject for the initial credit budget |

Recommend estimating the first two for the same sessions. Prefer session
history where it fits the staged budget; otherwise acquire the narrow windows
and explicitly record their limits. Do not buy broad data merely because a
credit will expire. A different contract, date, or missing time range can
still require a new purchase; caching cannot manufacture that evidence.

Acquire reusable SPY one-minute bars first, including all expected sessions
and original price units. Then discover dated contracts and select eligible
legs using only information available at the signal time. Estimate instrument
definitions as well: they are time-series data, not automatically free merely
because metadata and symbology requests are free. Preserve holidays, early
closes, corporate-action metadata and absence of eligible expirations.

## Credit controls

Suggested allocation if the account actually has $125 available:

- Up to $5 for a small integration sample, including its required inputs.
- Up to $80 additional for the frozen main study, including bars, definitions
  and quotes. This is a ceiling, not an estimated price or guaranteed coverage.
- Leave at least $40 unused for corrections and later questions. Do not
  release this reserve automatically. If credits are lower, shrink the plan.

Before retrieval, verify current credits, existing usage, expiration, licenses
and the account's historical limit. Use one downloader and reserve each job's
conservative cost in a persistent ledger before submission. Reconcile actual
charges and in-flight jobs before the next request; unknown usage stops work.
Keep additional margin for estimates and other account activity. A billing
period rollover does not reset this experiment's cumulative budget.

The vendor's monthly limit blocks requests after usage exceeds the limit;
it is not documented as an atomic per-request spending guarantee. Estimates
are not exact for arbitrary time windows. Do not represent either mechanism
alone as proof of zero paid charges. Use conservative enclosing ten-minute
windows for quote estimates and full days for definitions, fresh balance
checks, small sequential batches and account controls. Stop if the available
controls cannot establish that the next job is covered by credits.

## Storage and replay

Use a durable research directory outside disposable Git worktrees:
`C:\Users\jloo1\Documents\MarketData\databento`.

- `raw/`: immutable downloaded payloads, partitioned by dataset/schema/date.
  Preserve timestamps, conditions, original units and symbol mappings.
- `catalog.sqlite`: request identity, coverage intervals, job ID/state,
  estimates, reserved and actual usage, retrieval time, file sizes, SHA-256,
  completeness, and license evidence. SQLite is in the standard library.
- `derived/`: locally generated tables, rebuilt from raw files without API
  calls. Link every output to source hashes and transformation versions.
- `runs/`: frozen experiment inputs, code version, coverage and results.

Encoding is chosen after sample validation using existing libraries. Prefer
compact original files where supported; otherwise lossless CSV/JSON plus local
compression. Compression reduces disk/network size, not Databento's metered
uncompressed-binary data charge. Never discard source precision to save space.

An acquisition planner canonicalizes explicit symbols, dataset, schema,
UTC half-open time range, symbol mapping, encoding and protocol version.
It queries verified coverage first and requests only missing intervals.
A request catalog match is insufficient without an intact file and matching
hash. Different schema/normalization versions never silently share entries.
Zero-record responses retain the requested coverage and vendor conditions;
they are not automatically proof that a contract did not exist.

The backtest receives a local data reader with no API key or network fallback.
Missing data produces an explicit coverage failure. Replaying a complete
cached experiment therefore makes zero vendor requests. New acquisition is a
separate command with an explicit cost plan; ordinary testing cannot spend.

## Crash recovery and backup

Prefer batch jobs. Persist the planned request and cost reservation before
submission, then persist the returned job ID. If submission times out, inspect
existing vendor jobs and reconcile the uncertain state; never blindly resubmit.
An ambiguous match requires intervention. Download to a temporary file, verify
integrity/completeness, then atomically publish it and update the catalog.
Interrupted or record-limited files remain incomplete, never valid history.

A retry downloads the existing job's files rather than creating another job.
Databento provides a 30-day batch redownload window; that is a delivery window,
not evidence of a local retention deadline or perpetual license. Confirm the
account's dataset terms before bulk archiving. Keep vendor data and credentials
out of GitHub. Put code, documentation and permitted derived summaries in Git.

Maintain a hash-verified backup on a separate owner-controlled disk or A8 only
where the applicable terms permit it. Do not report backup success until a
restore/hash check passes. Avoid fetching the same dataset separately on A8;
transfer the permitted local cache instead. Preserve old versions when a
vendor correction is acquired; do not silently change prior experiment inputs.

## Required verification before spending

Tests must establish: cache-hit replay with network disabled; subset coverage
reuse; a missing interval requested only once; concurrent/duplicate request
reservation refusal; no paid auto-retry after uncertain submission; corrupt
or truncated file rejection; recovery after a crash at each commit boundary;
no future-quote joins; explicit gaps; budget exhaustion and expired/unknown
credits refusing submission; no secret in manifests or errors. A small real
sample must then validate timestamp/size semantics before the longer purchase.

The initial local key template is still empty as of this design. Account
credits, request prices, retention terms, sample quality and the final download
scope remain unverified. No full-history claim follows from this document.

## First-party references

- [Historical API](https://databento.com/docs/api-reference-historical?historical=http):
  metadata/symbology costs, estimate granularity, repeated streaming charges,
  batch jobs and recovery window.
- [Billing controls](https://databento.com/docs/portal/billing): remaining credits,
  account limits and their documented post-limit behavior.
- [Pricing](https://databento.com/pricing): encoding/compression billing basis.
- [User agreement](https://databento.com/legal/databento-user-agreement):
  archive the applicable account/dataset terms before assuming retention rights;
  the public page did not expose readable agreement text in this inspection.
