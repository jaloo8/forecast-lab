# Executed strategy-family evidence — October 19, 2026

Read [the results](../../STRATEGY-FAMILY-RESULTS-2026-10-19.md) and [research register](../../RESEARCH-REGISTER.md) first. This directory contains aggregate research evidence, not licensed raw inputs, credentials or broker fills.

## What ran

- 28 ETF policies (five controls) across three costs and three fresh-account windows, plus 27 whole-SPY diagnostics: 279 completed paths. None reaches at least 10% in every complete year. All annual vectors and failures are retained.
- Six funded cash reconstructions of three previously sampled SPY option spreads. Every case loses money. These are not annual simulations or reproductions of the missing original Yahoo input.
- A new threshold audit of 3,368 existing scenario records /58,112 annual rows. It does not rerun the old strategy engines. Zero of 3,218 records with at least ten complete years pass; 54 very short passes remain explicit.
- GET-only recovery of 11 retained SPY jobs /44 verified vendor files, 994,646,413 bytes and 6,032,360 records. $0 new acquisition charges; no replacement submission or streaming fallback. Public job labels are anonymous ordinals; original account-linked IDs stay private.

## Evidence map

`stock-results.json`, `stock-comparisons.json`, `stock-selection.json` and `stock-trial-index.json` are byte-identical copies of run aggregates. `stock-run-started.json` and `stock-run-manifest.json` record inputs, timing, source and private ledger hashes. Registration and pre-performance warmup amendment are in docs/research; their hashes are enforced by the runner. The pre-performance review and fixture receipt were saved before performance.

`stock-accounting-independent-review.json` reconciles all 279 accounts against original CSVs without importing the study engine. It checks accounting with recorded targets; policy formulas, breakout state and warmup counts are outside that check. Static mapping review and causal fixtures have separate scopes. Mutation, comparison-arithmetic and results-summary receipts are retained separately.

`recovered-options-summary.json` and `options-independent-cash-check.json` disclose reconstruction and raw-selection limits. `prior-target-rescreen.json` and its independent review preserve old-result threshold mappings. `option-data-cost-estimates.json` contains free estimates, not acquired quotes or a new funded study. `validation.json` records 2,597 passing tests, 25 explicit skips and one integration test deselected by the repository default.

## Reproduce or inspect

A clone alone lacks private inputs. Read root HANDOFF.md; install pinned dependencies with `uv sync --frozen`. Obtain the owner's frozen stock wrapper through private transfer and verify SHA256 `4df237cec1ddc6049c628887108cf247f9d2e1041abbf36bc4fa7406d70b2f70`. Use a new output directory; do not overwrite the executed evidence.

```powershell
uv run --frozen python -m scripts.run_stock_family_study --archive data/private-transfer/frozen-data-wrapper.zip --output data/replay-new/stock-family
uv run --frozen python -m scripts.check_stock_family_accounting --archive data/private-transfer/frozen-data-wrapper.zip --run data/replay-new/stock-family --output data/replay-new/accounting-review.json
```

The original full run contains 558 compressed daily/ledger files and six JSON files. The private QuantLab checkpoint also carries losslessly decompressed copies of those 558 CSVs, with original/compressed and transferred/uncompressed hashes in its stock-account-transfer.json. Its source snapshot is a delta, not a complete checkout. Credentials and recovered Databento raw payloads are excluded from both Git and that ZIP.

Options reconstruction requires the retained job layout and runs offline:

```powershell
uv run --frozen python -m scripts.replay_recovered_options --root data/private-transfer/recovered-batches --output data/replay-new/recovered-options
```

Use `scripts.recover_databento_batches --help` to inspect the GET-only recovery command. Its credential file stays outside the repository, and each inventory/download output must be new. Recovery availability is limited by Databento retention; absent direct-stream payloads are not silently reacquired. No new billable request is approved by running a cost estimate. The owner authorized frugal free-credit use; current remaining balance/expiry and a bounded request plan are still needed before spending.

`manifest.json` hashes every published payload in this directory except itself, plus the related source/protocol files. Verification establishes exact files, not profitability, statistical independence, execution eligibility or untouched historical data. Scoped Git attributes preserve the executed source/protocol bytes, including the existing CRLF data loader, so the independent checker can verify the original run across Windows and Linux checkouts. The loader change in this commit is byte preservation only; its Python statements are unchanged.
