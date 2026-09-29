# Repair stock price-source reconciliation

Owner instruction: fix the blocked paper workflow and keep testing/pushing changes. This is an explicit, scoped repair of source handling, not permission to change fees, strategy rules, bankrolls or recorded trades.

## Evidence and design

The September 29 13:00 UTC capture reproduces seven baseline and 56 research/parallel differences for September 28. The earlier session-statistics and official-close observations are unchanged in fresh observations of those same endpoints. Of the research differences, 49 concern supplemented bars; seven are later volume-only increases in ordinary daily bars (AMST, EONR, LGCY, LITS, PTN, SCHL, SNX). The endpoints are not interchangeable. The evidence does not establish why opening prices differ or prove either series correct.

Use a narrowly reviewed immutable-vintage compatibility view for existing books. Its finite manifest binds the exact accepted and newly published September 28 bars, original snapshot hash, actual review time, rationale and original supplement evidence hashes. Preserve both observations. Permit only these exact reviewed pairs; reject future unknown revisions, missing historical rows, invalid OHLCV and malformed evidence. This preserves recorded fills/forecasts without presenting old observations as corrected market history. Default existing reconciliation remains strict without an explicit review.

New completed sessions and new scanner research use genuine regular split-adjusted daily bars. Do not add more session-statistics supplements. No intraday aggregation, current UTC session, backdated import or guessed price is allowed. A delayed real daily session remains a data-availability wait, with the existing retries. The scanner receives the primary view, not the legacy compatibility view. Legacy results disclose their preserved price basis and cannot demonstrate execution accuracy.

## Implementation plan

- [ ] Add a pure `session_vintages` module and failing tests. `create_review(prior, published, now, note)` validates old evidence and classifies only supported September 28 differences. `reconcile_daily(snapshot, prior, review, required, now)` checks exact review pairs and full history, returns labelled legacy view while preserving primary evidence hashes; does not write ledgers. `primary_daily(snapshot, required, now)` validates completed daily input without fallback.
- [ ] Add a capture-only CLI with explicit prior/review paths, immutable outputs and complete review/input hashes. Default strict old behavior stays available. Raw capture and ledger/research writer permissions remain separate.
- [ ] Add end-to-end tests: original fill preserved, reviewed source transition survives next-session entry/exit, unknown revisions fail, no duplicate fills on retry, no premature current-session fills. Test exact evidence tampering and original source binding.
- [ ] Display a read-only source-reconciliation notice and reviewed counts in the dashboard. Do not label the morning failed scheduled check successful; record manual repair separately.
- [ ] Review independently, run focused/full gates, then deploy scoped files to isolated A8 with hashes/backups. Fetch fresh primary data, generate exact reviewed manifests from preserved captures, validate baseline/parallel/forward independently. Skip already processed sessions; no duplicate decisions. Publish current primary scanner if valid.
- [ ] Mirror verified records/results. Update the existing heartbeat instructions to use reviewed compatibility inputs for existing lanes and primary-only future sessions, preserving its weekday 6 AM/6 PM/9 PM schedule. No new scheduler or broad recurring scan until a complete scanner publication succeeds.
- [ ] Push small draft PRs and attach them. Keep historical failures and all account/database records. Report actual results and any remaining source limitations, not a profitability claim.

## Review requirements

No floating tolerance may hide a revision. The manifest must retain complete normalized bars, not only changed fields. Original supplement `evidence_hash` must recompute from the retained evidence, and each accepted bar must match the documented construction. Later compatibility captures must retain the original binding. A review must not authorize an unrelated date or unseen future source pair. Every durable account/research write stays on A8; tests use temporary fixtures.
