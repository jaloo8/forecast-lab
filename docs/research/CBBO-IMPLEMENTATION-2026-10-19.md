# Backtest evidence and implemented CBBO schema probe

The earlier stock study actually executed 279 account paths from 28 policies (five controls), with $1,000 starting capital and 10/25/50 basis points per traded side. All paths missed 10% in at least one complete year. This follow-up checked the original outputs: all 563 manifest hashes matched, including 558 compressed daily/ledger files containing 935,766 daily rows and 49,881 ledger rows. The [artifact check](evidence/2026-10-19-cbbo-implementation/backtest-artifact-check.json) records this read-only verification; it is not another backtest run.

At primary cost in fresh 2014–2025 accounts, training-selected SPY ten-month trend returned 6.85% CAGR with a −22.11% worst year and −27.16% event drawdown. QQQ ten-month trend returned 14.29% CAGR, −8.46% worst year and −28.05% event drawdown. These are historical simulations with overlapping windows and known history. The separate six options cash reconstructions cover three previously known dates, not an annual options NAV: starting $1,000 ends at $983.20, $971.20 or $959.20 depending on added slippage. [Complete prior results and limitations](STRATEGY-FAMILY-RESULTS-2026-10-19.md).

## What is now implemented

- `src/kq/clients/databento_schema_probe.py` and `scripts/acquire_cbbo_schema_probe.py` implement a separate acquisition path for the exact nine registered requests. Default authenticated mode obtains free quotes only; offline/status modes need no key.
- The dedicated persistent catalog enforces a $0.50 cumulative reservation budget, upward-rounded 20% quote buffers, exact request identity and fresh credit evidence. Vendor inventory is checked for existing matching jobs before a new submission. Quote age is rechecked after that lookup.
- Intent and uncertainty are durable before the single submission POST. Lost responses require lookup/reconciliation; known jobs resume with GET only. Vendor file sizes/hashes are verified and cached. An absent local catalog plus an existing matching vendor job stops for recovery rather than buying it again.
- `src/kq/equities/cbbo_schema.py` and `scripts/inspect_cbbo_schema.py` stream private CSV/gzip inputs, check matching metadata/decimal encoding, inventory flags and quote defects, report interval gaps, and inspect dated contract definitions. Future, conflicting and invalid latest definitions cannot silently provide earlier contract knowledge. Input fingerprints are checked before and after inspection.

The reader preserves the distinction between interval labels, last-trade timestamps and unknown quote-update time. Pre-March 28, 2023 OPRA timestamps receive a separate evidence classification. Minute quotes do not prove freshness or atomic fills. [Databento CBBO schema](https://databento.com/docs/schemas-and-data-formats/cbbo), [historical OPRA limitations](https://databento.com/docs/knowledge-base/datasets/opra-pillar).

The old pilot, replay, stock rules and broker modules remain unchanged. This implementation does not calculate CBBO strategy returns or activate an agent/broker service.

## Commands and remaining acquisition requirement

From a complete checkout with its existing environment:

```powershell
.venv/Scripts/python.exe -m scripts.acquire_cbbo_schema_probe --offline
.venv/Scripts/python.exe -m scripts.acquire_cbbo_schema_probe --status --root PRIVATE_CACHE
.venv/Scripts/python.exe -m scripts.acquire_cbbo_schema_probe --credentials PRIVATE_KEY_FILE --output NEW_QUOTE_RECEIPT
```

The authenticated command was exercised against the real free metadata API. All nine estimates succeeded; buffered reservations remain $0.2726, below $0.50. [Fresh receipt](evidence/2026-10-19-cbbo-implementation/fresh-cost-estimates.json). No billable job was submitted by this checkpoint.

Actual submission additionally uses `--submit-approved --index N --root SAME_PRIVATE_CACHE --credit-evidence PRIVATE_CREDIT_JSON`. Each invocation submits at most one request, indexed 0–8. Reuse that root and complete/reconcile the current job before moving on. Resume with `--resume --index N --root SAME_PRIVATE_CACHE --credentials PRIVATE_KEY_FILE --license-evidence OWNER_LICENSE_REFERENCE`; `--reconcile-job-id EXISTING_ID` is allowed only with resume.

The private credit JSON needs exact `available`, original `observed_at`, an unexpired `expires_at`, `verified: true`, `cash_budget_usd: "0"`, `outstanding_usage_reconciled: true`, and nonempty `license_evidence`; `deduct_imports: true` subtracts charges completed after that observation. The existing five-minute freshness check remains. Do not refresh the observation automatically or promote the owner's approximate $116/April 2027 statement to verified evidence.

The public vendor OpenAPI schema exposes billing dashboard/credit views requiring portal authentication; the saved historical key has not established that access. [Primary schema](https://api.databento.com/openapi.json), [inspection receipt](evidence/2026-10-19-cbbo-implementation/billing-source-check.json). Current portal balance evidence remains necessary at submission. This is a missing input, not a request to authorize research again. The local ceiling is not a vendor-enforced billing guarantee.

After delivery, run `scripts.inspect_cbbo_schema --help` and inspect each quote file with its matching vendor metadata and same-day definition file. Reconcile inspected row counts with vendor counts and preserve all defects. Stop at the registered schema-quality verdict; an annual options study still needs separately registered policies, funded cash/collateral, integer contracts, daily marks, costs and lifecycle handling.

## Validation scope

The new suites contain 29 acquisition-control and 21 reader tests using explicitly artificial fixtures. These tests validate software behavior; they are not market backtests. Independent source review, full regression results and exact source fingerprints are recorded in this checkpoint's evidence directory. No raw historical CBBO file was acquired or inspected, no new strategy performance was generated, and no credit was spent.

Full repository regression: **2,647 passed, 25 skipped, one integration test deselected** in 419.27 seconds. The 50 new fixtures are included in that total. Full-repository Ruff, formatting of six new files, and mypy across 217 source files passed. [Validation receipt](evidence/2026-10-19-cbbo-implementation/validation.json), [independent review](evidence/2026-10-19-cbbo-implementation/independent-code-review.json).
