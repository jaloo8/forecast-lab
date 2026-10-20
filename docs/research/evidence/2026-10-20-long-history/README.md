# Evidence map: fifty-year study

Start with `summary.json`, `validation.json` and the narrative results two
directories above. All counts describe configurations or account scenarios,
not independent algorithm discoveries or broker fills.

- `results.jsonl`: all3,672 account summaries, including every annual return.
  Parsing its lines produces the exact objects in the private `results.json`.
- `classification.json`: every candidate's overlapping screening flags.
- `selection.json`: training choices saved before evaluation/full performance.
- `regimes.json`: all204 policies' fixed decades, stress intervals and lagged states.
- `bootstrap.json`: all200 mean-excess statistics and adjusted/unadjusted diagnostics.
- `path-uniqueness.json`: exact float64 primary full return-path fingerprints.
- `started.json`, `manifest.json`, `signal-index.json`: original run receipts,
  complete private-output hashes and observation-date definitions.
- `independent-accounting.json`: complete target/account/summary/statistic reconciliation.
- `pre-performance-*`: registration-bound independent source gate and clarifications.
- `input-acquisition.json`: original source URLs, retrieval dates, bytes and hashes.
- `data-sources.json`, `news-source-review.json`: primary-source review scopes.
- `news-fetch-receipt.json`, `news-validation.json`, `news-review.json`: actual
  one-shot observation capture and separate software/quality verification.
- `interpretation-review.json`: scoped independent explanation/number checks.
- `publication-manifest.json`: hashes of published source, tests, documents
  and evidence; excludes itself to avoid a circular fingerprint.

The owner-private companion archive contains a7,366-file byte-exact kit:
all5 original input files,7,355 run files and6 original news files.
Public Git intentionally omits raw source/news payloads and per-month ledgers.
Restoring the kit is not a new backtest; consulting these summaries is not an
engine rerun. No API key is required for offline reproduction.

After restoring those original inputs to a full Git clone and setting up its
pinned Python environment, use a new output directory:

```powershell
python scripts/run_long_history.py --source data/long-history-20261020/raw --output data/long-history-reproduction-new --review docs/research/evidence/2026-10-20-long-history/pre-performance-review.json
python scripts/check_long_history.py --source data/long-history-20261020/raw --run data/long-history-reproduction-new --output data/long-history-reproduction-check-new.json
```

The frozen source/registration review gate must still match. Do not overwrite
the original run or silently revise rules to fit its now-known results.
