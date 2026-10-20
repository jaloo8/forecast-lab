# Resume forecast-lab on another computer or account

Checkpoint: October 19, 2026. Active handoff branch: `research/annual-profit-audit-20261019`. Base main commit: `e1e1f4bc43e19ca862e1425ff637e7fa0d124db1`. The current checkout commit is obtained with `git rev-parse HEAD`; it is not embedded inside a file that would change its own commit hash.

## Latest: credit estimate and bounded next data check — October 19

The owner reports approximately **$116** in free credits, expiring around **April 2027**. This updates the former unanswered balance question without inventing an exact balance or expiration day. Read the [credit plan and schema correction](docs/research/DATABENTO-CREDIT-PLAN-2026-10-19.md). Nine registered schema requests were freshly quoted for $0.226768702267; planned buffered reservations are $0.2726 within a $0.50 ceiling. No data was acquired and no new performance was computed in this follow-up.

The current OPRA documentation clarifies publisher-flag meaning and pre-2023 timestamp limitations. Preserve the frozen results; the existing event-quote reader and pilot allowlist do not support this minute schema. Implement/review that separate path before acquisition. Keep the verified-credit, reservation and uncertain-submission guards; get exact current billing evidence when a purchase is ready, not repeated estimates while engineering is unfinished.

## Previous: retained data recovery and actual strategy tests — October 19

The owner cannot transfer the old Databento cache and supplied a local key, authorizing frugal free-credit use. This supersedes older transfer-only directions. Retained batches were recovered with GET requests: **11 SPY jobs, 44 vendor-verified files, 994,646,413 bytes and 6,032,360 records; $0 new acquisition charges**. Original direct-stream payloads and catalog are still missing. Credentials and downloaded payloads remain outside Git and portable exports.

Read the [research register](docs/research/RESEARCH-REGISTER.md), [frozen study](docs/research/STRATEGY-FAMILY-STUDY-2026-10-19.md) and [results](docs/research/STRATEGY-FAMILY-RESULTS-2026-10-19.md). The new study completed **28 ETF policies / 279 cost-window-account paths**, including 27 whole-SPY diagnostics. Every path had at least one complete year below 10%. Five policies are controls; repeated mechanisms and cost scenarios are not new independent algorithms. The chronological training choice was SPY ten-month trend; its fresh 2014–2025 fractional result was 6.85% CAGR, −22.11% worst year and −27.16% event drawdown at 25 bp/side. None was promoted.

The separate recovered-options reconstruction ran six cash/flag/slippage cases on three previously known dates. $1,000 ended at $983.20 baseline, $971.20 at an extra cent per leg/side and $959.20 at two extra cents. This uses recovered EQUS.MINI bars, not the missing original Yahoo input, and is not annual performance. All 18 cash rows were independently reconciled. A new threshold audit of 3,368 old scenario records checked 58,112 annual rows; none of 3,218 scenarios with at least ten complete years passes. The 54 shorter passes cover only one or three years.

The [new evidence directory](docs/research/evidence/2026-10-19-strategy-families/) links to frozen registrations and contains complete aggregate trial results, comparison/selection records, data-recovery scope and independent reviews. Daily/transaction files and licensed inputs are private. The frozen stock wrapper is unchanged. Preserve the registration/amendment bytes; the runner verifies their SHA256 values before execution. The study has finished; do not rerun or extend it simply to force a historical winner. Fresh validation: 2,597 tests passed, 25 skipped and one integration test deselected; Ruff and mypy passed. The independent checker reconciled all 279 accounts, 935,766 daily rows and 49,881 ledger rows. Scope and limits are in the new validation receipt.

## Current objective and result

The owner wants 10–20% profit in **every calendar year**, with **$1,000** as the practical reference. No result demonstrates that future annual floor. Keep CAGR, downside, costs and feasibility visible; do not silently replace the objective with benchmark outperformance or average annual growth.

Completed work:

- Reviewed the base checkout: 631 nonempty files / 120,658 lines and five empty files. The lockfile was structurally inspected; encrypted secrets were not decrypted. The [coverage receipt](docs/research/evidence/2026-10-19/review-coverage.json) records scope and hashes.
- Reproduced 24 fixed stock/cost paths on common 2006–2025 dates. None passes 10% every year. All four published option indices also fail in their common 2009–2025 window. These index histories are not retail net backtests, and the stock study's original $10,000 fractional-unit model is not evidence of $1,000 execution. See the [annual audit](docs/research/ANNUAL-PROFIT-AUDIT-2026-10-19.md).
- Corrected independent percentage/dollar drawdown maxima, Windows long raw-cache paths, and overstated hypothetical-return dashboard wording. Existing full-suite evidence is 2,563 passes / 25 skips; the later audit guard and current 13-test focused verification are recorded separately in [validation](docs/research/evidence/2026-10-19/validation.json).
- Reviewed and deleted 120 redundant GitHub branch pointers: 106 exact ancestor tips plus 14 byte-equivalent integrated contributions. No new merge was needed. The [cleanup record](docs/research/evidence/2026-10-19/branch-cleanup/branch-cleanup-report.json) and reviewer receipts preserve the decisions. Main was unchanged. This active handoff branch is new work, not another stale branch.
- Investigated agent trading frameworks and the owner-provided trading-skills repository. Read the [source review](docs/research/AGENT-TRADING-SOURCE-REVIEW-2026-10-19.md), [pinned skill/code review](docs/research/TRADERMONTY-REVIEW-2026-10-19.md), and [proposed architecture](docs/research/AGENT-RESEARCH-FLOOR-2026-10-19.md). The [read receipt](docs/research/evidence/2026-10-19/tradermonty-review-receipt.json) records 43 targeted third-party files and exact ranges; it does not claim all 2,150 files were reviewed. No third-party skill, agent daemon or provider budget gateway was installed or activated.

## Framework follow-up — October 19

The owner supplied a Gemini summary and TradingAgents/Vibe-Trading links. The [pinned code review](docs/research/AGENT-FRAMEWORK-CODE-REVIEW-2026-10-19.md) records 51 files / 10,534 distinct lines, with exact full/partial ranges and hashes in a [separate evidence manifest](docs/research/evidence/2026-10-19-frameworks/manifest.json). This is static source review, not vendor execution or new performance. TradingAgents evaluates independent recommendations rather than funded NAV; Vibe-Trading's inspected options path is synthetic and one window diagnostic is not a fresh out-of-sample experiment. Borrow bounded research patterns, preserve deterministic accounting, and use the existing process-pilot proposal. No external framework, runtime or broker was activated.

## Clean-clone continuation

These commands create a new checkout. For an existing checkout, inspect `git status --short` and preserve local work before fetching/switching; do not use a hard reset or overwrite another machine's changes.

```powershell
git clone --branch research/annual-profit-audit-20261019 --single-branch https://github.com/jaloo8/forecast-lab.git forecast-lab
cd forecast-lab
git rev-parse HEAD
git status --short
```

Read this file, `PROJECT_STATE.json`, `AGENTS.md` and `CLAUDE.md`. A public clone does not require the original Codex account. Pushing requires a GitHub identity with write permission; API credits and local credentials do not transfer with Git.

Use Python 3.12 and the existing lockfile. If the machine already has `uv`, the environment command is `uv sync --frozen --group dev`; it installs the repository's existing pinned dependencies, not the third-party skills collection. No market-data API key is needed for the offline test command:

```powershell
uv run --frozen python -m pytest tests/test_annual_target_audit.py tests/test_options_cache_io.py tests/test_backtest.py::test_max_drawdown_dollar_and_percentage_maxima_can_differ -q
```

The normal test configuration excludes real-API integration tests. Do not run a broker, scheduler, installer that configures production, or acquisition command to establish research continuity.

## Inputs that Git intentionally does not carry

Published [aggregate evidence](docs/research/evidence/2026-10-19/README.md) supports inspection of the results and review decisions. A clone alone cannot reproduce missing private market data. [Private input inventory](docs/research/evidence/2026-10-19/private-inputs.json) records transfer requirements and the stock wrapper's exact hash.

1. **Databento inputs:** the owner cannot transfer the original cache. Retained SPY batch recovery and a short reconstructed replay are now complete, as described above. The private recovery destination on this PC is the user's Documents/MarketData/databento folder. A new computer can use its locally configured key to inspect retained batches with `scripts.recover_databento_batches`; this issues GET requests only. Retained downloads expire after the vendor's 30-day window, and direct-stream payloads cannot be restored this way. Do not run `acquire_options_pilot` or an extension submission command against an empty catalog as recovery. A new acquisition needs current credit balance/expiry evidence, a bounded quote and local reservation controls.
2. **Stock replay wrapper:** privately transfer the previously generated `frozen-data-wrapper.zip` (3,933,510 bytes, SHA256 `4df237cec1ddc6049c628887108cf247f9d2e1041abbf36bc4fa7406d70b2f70`) into an owner-chosen local path. It embeds raw price histories and is not published here. The audit's `prepare --source ..` command assumes a separate QuantLab workspace; it is not a valid assumption for a standalone clone.
3. **Related QuantLab workspace:** older 2000-start, high-return and combination studies plus broker state remain in the owner's private portable workspace. This repository does not contain that entire workspace or transfer authority to run its broker. The latest strategy-study follow-up is preserved in the owner-local `QuantLab-strategy-family-checkpoint-20261019.zip`; its adjacent verification receipt carries the final hash. Earlier archives remain historical snapshots. It is a snapshot, not a distributed lock or live sync.

With the verified stock wrapper at `data/private-transfer/frozen-data-wrapper.zip`, choose a **new** output directory and run the frozen code:

```powershell
uv run --frozen python -m scripts.run_sector_study --archive data/private-transfer/frozen-data-wrapper.zip --output data/replay-new/sector
uv run --frozen python -m scripts.run_inverse_vol_study --archive data/private-transfer/frozen-data-wrapper.zip --baseline data/replay-new/sector --output data/replay-new/inverse-vol
uv run --frozen python -m scripts.audit_annual_target screen --run data/replay-new/inverse-vol --output data/replay-new/annual-screen
```

Do not overwrite original outputs. Hash verification and a successful replay are separate from statistical validity or real execution. Published evidence is historical; no market refresh was performed for this handoff.

## Exact next actions

1. Read the complete new results and validation receipt; no tested path meets the every-year target. Keep the 28-policy registration and all failed cases frozen. Use `scripts.run_stock_family_study --help` for an independently requested replay into a new directory; it needs the private stock wrapper, not a key. `scripts.check_stock_family_accounting` independently checks the saved ledgers against that wrapper.
2. The owner has reported approximately $116 / April 2027. Preserve that uncertainty and implement the bounded CBBO schema pilot described above; obtain exact current portal evidence when ready to submit. The owner authorized frugal credit use, not cash charges or subscriptions. Twelve earlier free cost probes plus the nine new schema quotes are saved; no new billable acquisition occurred. Older OPRA minute quotes may support a bounded new study, but existing CMBP replay code does not automatically validate that different schema or a funded multi-year options account.
3. Register the next materially distinct, data-qualified hypothesis and its finite trial/cost budget before outcomes. Do not keep tuning this batch's thresholds, dates or weights after seeing failures. Individual-stock fundamentals need historical membership/delistings and original publication times; news/agent research needs timestamped inputs and a separately bounded model budget.
4. Before any annual options claim, verify integer positions, funded cash/collateral, overlapping trades, daily marks and lifecycle/uncertain-exit handling. Three closed pilot trades cannot establish an annual floor. No live orders, subscription, automatic broker migration or second paper writer follows from this checkpoint.

Keep GitHub code/docs/aggregate evidence current on the existing integration branch and draft PR #235. Raw data, credentials, local environments and the full private QuantLab workspace do not travel through this repository.
