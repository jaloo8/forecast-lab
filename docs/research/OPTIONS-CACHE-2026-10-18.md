# Options cache: implementation and authenticated cost estimates

**Later October 18 update:** the owner-approved pilot was acquired for $0.41967466473580 in credits and replayed from verified local storage. [Current results and validation](OPTIONS-PILOT-2026-10-18.md). The no-download statements below describe this earlier metadata-only checkpoint.

October 18, 2026. The saved key authenticated successfully to free historical
metadata and symbology endpoints. **No batch job, time-series retrieval, data
download, subscription, or credit-consuming call was made.** The owner reports
$125 in credits; the API calls here did not verify the account balance, credit
expiry, license agreement or historical spending limit. Production/A8 unchanged.

## What is implemented

- `databento_metadata.py`: explicit free GET allowlist, header authentication,
  bounded requests, no redirects/retries, sanitized transport/body errors.
- `estimate_options_data.py`: metadata inspection or pricing of a JSON plan;
  timestamped receipts include exact parameters and hashes. Existing receipt
  paths are refused before any request. No submit/download interface exists.
- `options_cache.py` and `_options_cache_io.py`: local SQLite acquisition ledger,
  canonical request identity, per-symbol interval coverage, verified file reuse,
  immutable source versions, atomic imports and hash-checked backup/restore.
  A backtest asks for local files; missing/corrupt coverage raises an error.
- Reservations are cumulative and exact, survive restart, allow only one
  unresolved job, and require fresh caller-verified credit evidence. Unknown
  submission cannot silently retry. Actual charges count toward the ceiling;
  later reservations are refused if they would exceed that cumulative budget.

These are acquisition primitives, not an automated downloader or decoded
quote reader. Import completeness, expected hashes, conditions, credit evidence
and licenses must come from independent delivery/account evidence. The cache
does not establish those facts itself or guarantee a vendor's final charge.
No payload timestamp parser, point-in-time quote join, or longer options
backtest has been completed. Existing spread-kernel causal tests remain separate.

## Observed coverage and costs

Authenticated metadata reports OPRA CMBP-1 from **2023-03-28** through
2026-10-17 exclusive (last included date October 16). CBBO-1s starts
**2025-02-20** in this response, despite the older announcement's broader date.
The dataset's 2013 start is not the start of every schema. Minute CBBO still
does not establish the separate five-second quote freshness required here.

Costs below are USD estimates returned by `metadata.get_cost`, not charges.
Quote estimates use enclosing ten-minute boundaries and definitions use whole
UTC days. These parameters, including symbols and dates, are saved locally.

| Request | Estimated cost |
| --- | ---: |
| SPY minute bars, EQUS.MINI, 2023-03-28 to 2026-10-17 | $0.288271576166 |
| SPY dated definitions over that same period | $15.067671239376 |
| All SPY option quote updates over that same period | $10,847.991853117943 |
| Entire SPY option chain, October 15 regular session | $17.634097063541 |
| Two selected calls, October 8 full regular session | $0.023711061478 |
| Two selected calls, October 14 full regular session | $0.013581562042 |
| Two selected calls, October 15 full regular session | $0.027900135517 |
| Same six contracts, only enclosing entry/exit windows | $0.006361651420 |
| SPY definitions for those three dates | $0.066210329533 |

The three-session sample plus **all reusable underlying minute bars** totals
**$0.419674664736**. Prefer full sessions for the selected contracts: the extra
cost over entry/exit windows is about six cents and permits later exit
diagnostics locally. The whole-chain requests are pricing comparisons only;
they are excluded from the acquisition plan. Do not extrapolate three days
into a firm multi-year options price. The all-history definitions and bars
subtotal is $15.355942815542, before the actual selected-contract quote plan.

The six example contracts were derived from already-stored October 8–16
underlying signals and resolved with free symbology. They are candidate pricing
inputs, not proof of contemporaneous eligibility. They expire October 9, 15
and 16, with strike pairs 775/776, 776/777 and 768/769 respectively. These are
already-viewed diagnostic dates, not untouched evaluation history or stress
coverage. Dated definitions and quote semantics still require validation.

EQUS.MINI aggregates component feeds; it is not established here as full SIP
coverage. Compare overlapping underlying bars and trigger sensitivity before
substituting it for the existing Yahoo series. The DBEQ.BASIC full-history
estimate timed out and remains **unpriced**, not zero-cost or unavailable.

## Storage, replay and next acquisition gate

Durable root: `C:\Users\jloo1\Documents\MarketData\databento`, outside Git
and disposable worktrees. Credentials remain in the private configuration
file; neither credentials nor vendor payloads belong in a PR.

The empty durable catalog is initialized: **zero jobs, zero reservations and
zero raw payloads**. Its local snapshot at
`C:\Users\jloo1\Documents\MarketData\databento-backups\20261018-pre-acquisition`
was restored and checked: zero jobs and the same $85 cumulative policy ceiling.
This checks the empty ledger locally, not an off-machine or acquired-data backup.

The proposed cumulative research ceiling remains $85, leaving $40 of the
reported credit for later decisions. It is a ceiling, not approval to spend
$85 now. First acquisition remains separately gated: recheck account credit,
expiry, terms, limit and fresh estimates, then seek authorization for a small
pilot (suggested maximum **$1**, current estimate about $0.42). No purchase
follows automatically from this document. Stop if zero cash spend cannot be
established. The monthly vendor limit is not an atomic per-job guarantee.

Before any submission, a future acquisition command must persist the local
reservation and mark submission uncertain. Reconcile an uncertain request to
its existing vendor job; never create another job to clear the state. Import
only complete verified files, then recheck account usage before the next job.
The offline ledger deliberately has no automatic cancellation or budget reset.
One authoritative ledger is required; backup copies must not acquire in parallel.

`backup()` copies the SQLite ledger and complete raw payloads only. Research
receipts and derived outputs under `runs/` and `derived/` need separate backup.
Tests prove temporary-directory backup/restore; they do not prove a working
off-machine backup, perpetual retention rights, or a production deployment.

Estimate a named JSON list using PowerShell (each output path must be new):

```powershell
uv run python scripts/estimate_options_data.py `
  --credentials "$env:USERPROFILE\.config\forecast-lab\databento.env" `
  --plan "path\to\explicit-plan.json" `
  --output "$env:USERPROFILE\Documents\MarketData\databento\runs\new-estimate.json"
```

Each entry has `name`, `dataset`, `schema`, explicit `symbols` list,
`stype_in`, `start` and `end` with timezone offsets. Omit `--plan` to inspect
free dataset/schema metadata. This command cannot acquire market data.

Local receipts: `20261018-metadata-access.json`, `20261018-initial-estimates.json`,
`20261018-targeted-estimates.json`, `20261018-pilot-definitions-estimates.json`
and `20261018-selected-symbols.json`, under the durable root's `runs/` folder.
The targeted estimate receipt's SHA-256 is
`a86c8f92cc72c6553b6fb84ef3d9c39042e0d4490939c952bdfadea2e46cbf7a`;
the pilot-definition receipt's SHA-256 is
`817aeed5954a483b5068de2b3789a1d08af6d643594b9cbb82b31e6bf6b996aa`.

## Sources and verification boundaries

- [Historical HTTP API](https://databento.com/docs/api-reference-historical?historical=http):
  metadata/symbology are free; estimates have time granularity; repeated
  streaming is billed again; existing batch results have a 30-day redownload
  window. A redownload window does not establish local retention rights.
- [Dataset definitions](https://databento.com/docs/venues-and-datasets):
  EQUS.MINI component-feed construction and schema distinctions.
- [Symbology](https://databento.com/docs/standards-and-conventions/symbology):
  parent-to-instrument-ID and raw-symbol-to-instrument-ID mappings.
- [Billing controls](https://databento.com/docs/portal/billing): account credits
  and limits must be checked before using the proposed pilot budget.

Offline tests cover API refusal, sanitized errors, interval reuse, corruption,
concurrent reservations, budget/credit expiry, process interruption boundaries,
immutable versions and restore hashes. Live evidence is limited to metadata,
costs and symbol resolution. It is not executable quote or fill validation.
All **69 focused tests** pass with network egress blocked. Review regressions
specifically reproduce corrupted-file repair, unverified SQLite sidecars and
string-valued symbol lists before fixing them. Ruff, strict mypy and Bandit's
medium/high severity gate pass. No additional dependency was installed.
