# Forecast Lab branch consolidation — October 19, 2026

**Status: COMPLETED.** Reviewed 120 feature branches. Keep `main`; merge zero branches because their contributions are already integrated. Deleted all 120 remote feature-branch pointers; GitHub now has one branch, `main`.

## Why there were so many branches

The repository accumulated completed feature/fix branches and a large chain of stacked stock-research branches. GitHub automatic deletion after merging was disabled. Many original stacked PRs were closed without individual merges because their exact commits were integrated together through PR #214. Fourteen other tips used older commit identities after squash/rebase integration. Neither an old date nor a closed PR was used alone as a deletion reason.

Corrected inventory: 121 actual remote branches, including main. An initial local count included the symbolic origin/HEAD alias and was one too high. The corrected count was independently matched against GitHub and git ls-remote.

## What was actually read

The review covered original branch contribution patches, including code, tests, documentation, fixtures, model changes and removed lines. It used the original stacked PR bases or explicitly reconstructed contribution ranges, not just branch names or reverse differences from today's main. Parallel reviewers read assigned contributions; this report combines their recorded findings. Identical inherited text was deduplicated. Legacy sections that exactly matched the earlier full repository read used verified file hashes and contiguous line mappings; every unmatched historical range was read separately. Generated JSON values were reviewed through lossless compact views and exact-subtree mappings. This is not a claim to have reread every repeated line independently on all 120 branches.

Per-branch receipts record exact tip/base hashes, content summaries, files, read ranges, patch hashes and integration evidence. The companion JSON points to each full receipt. Prior full repository coverage remains in ../annual-profit-audit-20261019/review-coverage.json. Preliminary mapping files explicitly marked superseded are not the final coverage evidence.

## Conservation and verification

- 106 feature tips are exact ancestors of main; 14 have equivalent integrated patches. No unique implementation was found that required a new merge.
- A verified complete-history Git bundle preserves all 121 original remote tips; a separate ZIP preserves all 11 dirty/untracked source files.
- Cleanup checks current GitHub branch protection, open PRs, default branch, remote tip identity and current local file hashes. Deletion uses one atomic push with an exact expected-SHA lease per branch.
- Main stays at e1e1f4bc43e19ca862e1425ff637e7fa0d124db1. The local research/annual-profit-audit-20261019 branch and its 11 unfinished source changes remain intact.
- No strategy/backtest reruns were needed for branch-pointer deletion. Historical performance and A8 deployment statements were reviewed as historical records, not revalidated as current runtime evidence.
- No remote auto-deletion setting was changed. Other computers' local branch names and deployments were not modified.

## Recovery

Local owner backup: `../../../exports/ForecastLab-before-branch-cleanup-20261019.bundle`. SHA256: `666af1dbc465fe8a8160c66350f166f2d0a44452452bd4b8d87d0fe3ea26712f`.

For example, from this forecast-lab checkout, recover a deleted tip locally with:

```powershell
git fetch ../exports/ForecastLab-before-branch-cleanup-20261019.bundle refs/remotes/origin/codex/options-pilot-results:refs/heads/restored-options-pilot-results
```

This restores a local branch only. The original exact tip is also in the inventory. The bundle is an owner-local recovery backup of existing Git history; it is not included in the sanitized portable audit ZIP.

## Branch-by-branch decisions

### 1. codex/adaptive-signal-dashboard

**Decision:** Deleted redundant remote pointer. Tip `3bef81301f721179acfbdae2b8d1f46948a90be2`.

**Content reviewed:** Adds read-only advisory dashboard, current-vs-stale action withholding, source/reference chronology and AppTests.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 2. codex/adaptive-signal-guards

**Decision:** Deleted redundant remote pointer. Tip `80f614baadaa71afed1d11f4ff833e6659ba4c86`.

**Content reviewed:** Corrects valid entry exclusions to WATCH while quarantine waits; rejects synthetic flag corruption and retains invalid-JSON attempts; adds boundary and hostile-evidence tests.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 3. codex/adaptive-signal-journal

**Decision:** Deleted redundant remote pointer. Tip `e165d239748bc2bdb9fec7249943201e91de8140`.

**Content reviewed:** Adds immutable advisory SQLite decisions/attempts with hashes, freshness/reference/session validation, revision refusal and read-only latest loader.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 4. codex/adaptive-signal-runner

**Decision:** Deleted redundant remote pointer. Tip `8ffc5e9d9487d0245988f7f3fb3782d0ad5f43e1`.

**Content reviewed:** Adds advisory CLI with mirror refusal, failed-input journaling and read-only original-pilot position adapter; tests isolation and invalid references.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 5. codex/adaptive-signal-validation

**Decision:** Deleted redundant remote pointer. Tip `9e859e43a3a20c51cdb81ed65df13e9c394266cf`.

**Content reviewed:** Adds stale/corrupt advisory panel tests and records manual A8 deployment evidence, unchanged existing databases, and unverified first scheduled run.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 6. codex/adaptive-stock-signal-design

**Decision:** Deleted redundant remote pointer. Tip `162425cab9d5a5a2aaae78520a108945c69b285a`.

**Content reviewed:** Documents fixed 20/60-session relative-momentum/volatility hypothesis, action band, evidence limitations, implementation sequence and deferred execution.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 7. codex/adaptive-stock-signals

**Decision:** Deleted redundant remote pointer. Tip `37c979d9578bc88f7dbac0917d780657dc8d3eaa`.

**Content reviewed:** Implements pure frozen adaptive scorer, 61 aligned sessions, explicit 2026 closure calendar, freshness/entry filters and arithmetic/invalid-data tests.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 8. codex/company-research-pilot

**Decision:** Deleted redundant remote pointer. Tip `02db162a4baa46f1486483ae7dde525aa76bcbfb`.

**Content reviewed:** Company research pilot with source-backed financial and moat notes, a feature CSV, watchlists and private narration drafts. The enterprise/retail and payments/chips cases distinguish reported fundamentals from a prospective stock-selection rule. The small named-company sample and creator-feasibility notes do not establish a point-in-time investable edge. No publication or trading action is required to preserve this work.

**Why:** The reviewed tip is an exact ancestor of main via 31abd9aa569cf06a1a21f523a84256e069d0f7bc; its contribution is preserved in history and no missing branch-only work was found.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 9. codex/databento-pilot

**Decision:** Deleted redundant remote pointer. Tip `e67c715bd386fb84c074b46e19bcacab80e2c3e5`.

**Content reviewed:** Adds bounded CSV batch transport, durable uncertainty before submission, a transactional $9.99 run ceiling, verified vendor job/file identities, host validation, SHA256/size checks, and reusable downloads.

**Why:** Preserve the transport and no-duplicate-spend safeguards in main; this completed branch adds no remaining work.

**Evidence:** [branch-review-options.json](branch-review-options.json) — SHA256 `626d7b297aa726955806e84be0cd44157ad49f037497d97ebac5d71846a05cd4`.

### 10. codex/databento-pilot-cli

**Decision:** Deleted redundant remote pointer. Tip `679fe3b74ac6308b4c983d6f685fc1ba572e6552`.

**Content reviewed:** Adds the seven-request pilot operator and approved plan. Exact unrounded request bounds and unlimited-record job parameters are checked; estimates, submissions and deliveries receive separate receipts; known jobs resume without resubmission.

**Why:** The working acquisition entry point and plan are integrated; retaining an extra old branch would not preserve additional functionality.

**Evidence:** [branch-review-options.json](branch-review-options.json) — SHA256 `626d7b297aa726955806e84be0cd44157ad49f037497d97ebac5d71846a05cd4`.

### 11. codex/expanded-stock-audit-20261018

**Decision:** Deleted redundant remote pointer. Tip `a5dfc02fd0ebdf32e4350b9116e859ace37e8fef`.

**Content reviewed:** Bounded stock replay implementation, protocol, source register and the A8 research checkpoint. The replay enforces the documented candidate and cost choices and retains incomplete cases rather than filling missing held-stock prices. The checkpoint separates survivor-selected stock evidence, execution limitations and recovered research artifacts. The implementation, tests and negative or incomplete evidence are already in main.

**Why:** The reviewed tip is an exact ancestor of main via 31abd9aa569cf06a1a21f523a84256e069d0f7bc; its contribution is preserved in history and no missing branch-only work was found.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 12. codex/free-stock-factor-screen

**Decision:** Deleted redundant remote pointer. Tip `86cfff3c8f49d925e4e768ff30ba285f47f697fa`.

**Content reviewed:** Reproducible screen of published French stock-factor portfolios, archived inputs, annual/block metrics, runner and tests. Published portfolio returns are screening evidence, not a point-in-time company selection and execution system. Losing years remain visible; the operating-profitability result does not satisfy a positive annual floor. The code and source/metrics artifacts are integrated.

**Why:** The reviewed tip is an exact ancestor of main via 31abd9aa569cf06a1a21f523a84256e069d0f7bc; its contribution is preserved in history and no missing branch-only work was found.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 13. codex/integrate-research-20261018

**Decision:** Deleted redundant remote pointer. Tip `c3687485ccbb7a6b66ef0957943fa4b60a302b20`.

**Content reviewed:** Integration of the sector/company research stack with updated stock direction, opening-range diagnostics, options feasibility, money guards and operational documentation. Reviewed the actual first-parent contribution into the mainline integration, including the cumulative research and guardrail changes. The opening-range study is an underlying-price diagnostic; the options documents still require quote and execution evidence. README and scope updates remove obsolete blanket statements and optimistic framing. Overlapping research and code sections are explicitly deduplicated against their originating branches.

**Why:** The reviewed tip is an exact ancestor of main via 31abd9aa569cf06a1a21f523a84256e069d0f7bc; its contribution is preserved in history and no missing branch-only work was found.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 14. codex/inverse-vol-study

**Decision:** Deleted redundant remote pointer. Tip `21a8fb5dc15f88c572bf3188c9932b14a007dbc7`.

**Content reviewed:** Inverse-volatility sizing variants, study runner, implementation and paired cost-sensitive tests/results. The recorded variants give up CAGR across the paired comparisons and reduce some sector drawdowns. The negative outcome is retained and does not justify strategy promotion or further tuning during cleanup. The full contribution is integrated through PR 225.

**Why:** The reviewed tip is an exact ancestor of main via 8ed1e3a72d887853e503ba9aa5d11836a3bc229a; its contribution is preserved in history and no missing branch-only work was found.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 15. codex/options-cache-evidence

**Decision:** Deleted redundant remote pointer. Tip `e47783a5f6a31fb0881c2902502804d9d2369fdb`.

**Content reviewed:** Publishes authenticated metadata/cost evidence and the limits of the then-empty cache. Adds interruption-after-publish/catalog, low-precision budgeting, cost-overrun, stale credits, unknown-job restore, corruption repair and SQLite-sidecar regressions.

**Why:** Keep the audit evidence and adversarial tests in main, including the historical no-download checkpoint; the branch pointer is redundant.

**Evidence:** [branch-review-options.json](branch-review-options.json) — SHA256 `626d7b297aa726955806e84be0cd44157ad49f037497d97ebac5d71846a05cd4`.

### 16. codex/options-cache-implementation

**Decision:** Deleted redundant remote pointer. Tip `3c31e9969b8d9405a7949547e08ed7702fbc9bc4`.

**Content reviewed:** Adds a free-only metadata GET allowlist, private-key loading, sanitized errors, explicit bounded symbols/time, outward-rounded Decimal estimates and canonical request hashes, with mocked transport tests.

**Why:** Free discovery remains useful and is integrated, with later record-count support; there is no unmerged implementation to recover.

**Evidence:** [branch-review-options.json](branch-review-options.json) — SHA256 `626d7b297aa726955806e84be0cd44157ad49f037497d97ebac5d71846a05cd4`.

### 17. codex/options-cache-ledger

**Decision:** Deleted redundant remote pointer. Tip `a2fbdb59037ab04c6c6e1ed6ce76fe9180c2b386`.

**Content reviewed:** Adds the SQLite acquisition ledger: immutable budget, per-symbol interval coverage verified against bytes, serial reservations, durable unknown/submitted states, immutable completed imports and local-only replay/backup/restore.

**Why:** The core offline state and spending controls are retained in main; later extension changes build on this exact implementation.

**Evidence:** [branch-review-options.json](branch-review-options.json) — SHA256 `626d7b297aa726955806e84be0cd44157ad49f037497d97ebac5d71846a05cd4`.

### 18. codex/options-cache-plan

**Decision:** Deleted redundant remote pointer. Tip `c62a24704e43f71982c7cd55795acd3b1cf724f3`.

**Content reviewed:** Registers separate acquisition versus offline replay, narrow-window/session cost comparison, durable raw/catalog/derived/runs layout, staged credit budget, unresolved submission recovery and verified backups.

**Why:** Preserve the historical design and its limitations in main. Its early suggested ceiling is historical context, not a reason to keep a development branch active.

**Evidence:** [branch-review-options.json](branch-review-options.json) — SHA256 `626d7b297aa726955806e84be0cd44157ad49f037497d97ebac5d71846a05cd4`.

### 19. codex/options-cache-regressions

**Decision:** Deleted redundant remote pointer. Tip `c2530c0178b0e1016226a6d5620d497f66747400`.

**Content reviewed:** Adds full cache regressions for subset/adjacent interval reuse, per-symbol/schema/version isolation, corrupted data refusal, durable uncertainty, stale/unknown credits, exact cumulative ceiling, immutable corrections, backups and competing reservations.

**Why:** These useful regression contracts are integrated; delete only the pointer, retaining tests and commit history.

**Evidence:** [branch-review-options.json](branch-review-options.json) — SHA256 `626d7b297aa726955806e84be0cd44157ad49f037497d97ebac5d71846a05cd4`.

### 20. codex/options-cache-storage

**Decision:** Deleted redundant remote pointer. Tip `b0d2b2932d956dba91ffc55c374f56604707b48c`.

**Content reviewed:** Adds canonical Request/CreditSnapshot/RawFile/Job objects, atomic verified file publication with corruption quarantine, manifest path checks, consistent SQLite backup and validated restore; adds value-object tests.

**Why:** The storage primitives remain in main. Current dirty Windows portability fixes are separate local work and must be preserved; deleting the remote branch does not replace them.

**Evidence:** [branch-review-options.json](branch-review-options.json) — SHA256 `626d7b297aa726955806e84be0cd44157ad49f037497d97ebac5d71846a05cd4`.

### 21. codex/options-credit-extension

**Decision:** Deleted redundant remote pointer. Tip `e17d6cfdf847b0badac90ae0378f215ee94c6aa6`.

**Content reviewed:** Adds explicit approved extension scope, $17 cumulative reservation ceiling from $7 prior reservations plus $10 extension, fresh five-minute credit evidence with subsequent imports deducted, bounded serial repricing/resume operator and refusal tests.

**Why:** The approved historical acquisition workflow is integrated. No new spending permission follows from retaining or deleting this branch.

**Evidence:** [branch-review-options.json](branch-review-options.json) — SHA256 `626d7b297aa726955806e84be0cd44157ad49f037497d97ebac5d71846a05cd4`.

### 22. codex/options-data-source-study

**Decision:** Deleted redundant remote pointer. Tip `e830238ee16a6278dbf8483ba72a8a3e6550e4b0`.

**Content reviewed:** Documents why the OptionsDX sample cannot score the fixed rule; compares historical sources, timestamp/expiry limitations and bounded acquisition protocol; corrects the roadmap to acknowledge PR214 integration.

**Why:** The exact contribution was squash-merged in PR215. The one graph-unique commit is not unique content; do not merge it again. Preserve the historical source audit in main.

**Evidence:** [branch-review-options.json](branch-review-options.json) — SHA256 `626d7b297aa726955806e84be0cd44157ad49f037497d97ebac5d71846a05cd4`.

### 23. codex/options-device-handoff

**Decision:** Deleted redundant remote pointer. Tip `ed74fb14dceb8c79dec5c020f07e6afd824e3712`.

**Content reviewed:** Adds full closed-trade cost attribution, private raw-cache transfer and strict/conditional replay handoff. The second commit changes direct script invocation to python -m so imports work portably.

**Why:** The handoff is still useful and is at current main via PR234; deleting the branch pointer retains these latest instructions. Git is not a backup of the private raw cache.

**Evidence:** [branch-review-options.json](branch-review-options.json) — SHA256 `626d7b297aa726955806e84be0cd44157ad49f037497d97ebac5d71846a05cd4`.

### 24. codex/options-estimate-command

**Decision:** Deleted redundant remote pointer. Tip `b4c3ea831b92d35f91b0a4191386a47cf2c21f6d`.

**Content reviewed:** Adds metadata-only CLI receipts, refusal of reused outputs/malformed plans, and implementation plan; also records owner-supplied trading-repository and optional dashboard relevance/license assessment.

**Why:** Both the estimator and the additional research notes are integrated. Review includes these non-title side contributions; no outstanding change requires merge.

**Evidence:** [branch-review-options.json](branch-review-options.json) — SHA256 `626d7b297aa726955806e84be0cd44157ad49f037497d97ebac5d71846a05cd4`.

### 25. codex/options-extended-plan

**Decision:** Deleted redundant remote pointer. Tip `d20832b5010a28218f6bcbb0079e035576d47508`.

**Content reviewed:** Adds cached session census, strictly lagged volatility/trend labels, outcome-independent first/last cost samples, next-calendar-day provisional symbols and contiguous-only definition plans. Follow-up subtracts all verified definition coverage before replanning.

**Why:** The planning code and protocol are retained with the cache-reuse correction; completed downstream study supersedes its pending-status text without losing the original record.

**Evidence:** [branch-review-options.json](branch-review-options.json) — SHA256 `626d7b297aa726955806e84be0cd44157ad49f037497d97ebac5d71846a05cd4`.

### 26. codex/options-extended-results-final

**Decision:** Deleted redundant remote pointer. Tip `81aa486f0315d3fa9cc8452eccc4154792d61765`.

**Content reviewed:** Publishes the negative extended study, strict versus publisher-flag sensitivity, all coverage/refusal/unresolved counts, cost stress and verification evidence; replaces obsolete roadmap notices while preserving protocol history.

**Why:** Preserve rejected-strategy results and caveats in main. Negative performance is not a reason to erase evidence; only the merged development pointer is redundant.

**Evidence:** [branch-review-options.json](branch-review-options.json) — SHA256 `626d7b297aa726955806e84be0cd44157ad49f037497d97ebac5d71846a05cd4`.

### 27. codex/options-extension-replay

**Decision:** Deleted redundant remote pointer. Tip `a62ed42bf322384a93b40b501dc69d16916be1e8`.

**Content reviewed:** Adds causal dated-chain selection, overlapping quote-window coalescence, offline all-session report, year/regime grouping, cost affordability rechecks, unresolved debits and five-session exploratory intervals. Raises coalesced stream limit to40 minutes. Follow-up preserves X-Warning headers instead of reading the wrong header.

**Why:** Both replay and receipt correction are integrated; no remaining branch-only fix exists. This is independent one-spread research, not a funded annual portfolio.

**Evidence:** [branch-review-options.json](branch-review-options.json) — SHA256 `626d7b297aa726955806e84be0cd44157ad49f037497d97ebac5d71846a05cd4`.

### 28. codex/options-pilot-replay

**Decision:** Deleted redundant remote pointer. Tip `d6b1a1485d237da193b502d30d2be170e0b2aee4`.

**Content reviewed:** Adds chunked causal receive-time CMBP quote/definition adapter, same-local-day chain checks, standard multiplier confirmation, nanosecond freshness/synchronization, invalid-latest refusal and explicit unresolved exits.

**Why:** These causal and missing-exit safeguards are integrated. The source parent also contains the separate inverse-volatility contribution, already in main via PR225; it is not duplicated as this branch work.

**Evidence:** [branch-review-options.json](branch-review-options.json) — SHA256 `626d7b297aa726955806e84be0cd44157ad49f037497d97ebac5d71846a05cd4`.

### 29. codex/options-pilot-results

**Decision:** Deleted redundant remote pointer. Tip `42b5ff0099ec4aeee9ef931f352440a4d6154c92`.

**Content reviewed:** Beyond its report title, adds the actual offline pilot runner: hash-verified Yahoo input, causal standard-call selection, original contract reproduction, local cached payload use, underlying overlap diagnostics and null unresolved-only totals; publishes the three-trade negative result.

**Why:** Keep runner, selection regressions and evidence in main. The branch carries no remaining data or code; private licensed quotes were never stored in it.

**Evidence:** [branch-review-options.json](branch-review-options.json) — SHA256 `626d7b297aa726955806e84be0cd44157ad49f037497d97ebac5d71846a05cd4`.

### 30. codex/options-publisher-flag-study

**Decision:** Deleted redundant remote pointer. Tip `607bd056c136802fc3ead1d5eebf6fd2cebb2351`.

**Content reviewed:** Keeps strict bit2 refusal by default, introduces explicit separately labeled sensitivity only for OPRA publisher30/rtype177, preserves all other flag/quote guards, and records the selected quote policy in each report with tests.

**Why:** Both policies and the unresolved publisher meaning are preserved in main. Branch deletion neither endorses the sensitivity nor resolves vendor semantics.

**Evidence:** [branch-review-options.json](branch-review-options.json) — SHA256 `626d7b297aa726955806e84be0cd44157ad49f037497d97ebac5d71846a05cd4`.

### 31. codex/options-stream-extension

**Decision:** Deleted redundant remote pointer. Tip `52a76d4a25e442476550a73ed0b9f02409b22c65`.

**Content reviewed:** Adds explicit bounded stream acquisition using aligned intervals and independent metadata record counts, local hashes, no automatic retry, conservative reservation accounting and abandoned-attempt charges without coverage; supports HTTP200/206 with tests.

**Why:** The streaming path and uncertainty evidence are integrated; PR231 subsequently preserves X-Warning and extends coalesced windows. No unfinished stream work remains on this pointer.

**Evidence:** [branch-review-options.json](branch-review-options.json) — SHA256 `626d7b297aa726955806e84be0cd44157ad49f037497d97ebac5d71846a05cd4`.

### 32. codex/reel-strategy-checks

**Decision:** Deleted redundant remote pointer. Tip `14d36718ac82d886444bab4129fd91eef198011a`.

**Content reviewed:** Causal KO/PEP pair replay with costs and capture tests, plus an SPY one-day-to-expiry call-spread pricing kernel and specification. The long historical pairs example finishes essentially flat after its modeled costs. The spread kernel is not a completed historical options backtest; atomic fills, listed contracts and lifecycle behavior remain implementation constraints. These limitations and tests are preserved in main.

**Why:** The reviewed tip is an exact ancestor of main via 31abd9aa569cf06a1a21f523a84256e069d0f7bc; its contribution is preserved in history and no missing branch-only work was found.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 33. codex/sector-portfolio-engine

**Decision:** Deleted redundant remote pointer. Tip `5d682e80c6699113d87744ef1aec1935acbd7fae`.

**Content reviewed:** Pure sector portfolio replay engine and tests for timing, costs, account conservation and input validity. The original fixed-rule implementation applies causal signals and next-open execution with self-financing transaction costs. Historical lines that differ from later inverse-volatility extensions were reviewed through verified line mappings and direct unmatched reads. No branch-only implementation remains.

**Why:** The reviewed tip is an exact ancestor of main via 31abd9aa569cf06a1a21f523a84256e069d0f7bc; its contribution is preserved in history and no missing branch-only work was found.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 34. codex/sector-strategy-results

**Decision:** Deleted redundant remote pointer. Tip `614a33026d9650b241a3ee3051b5e394857c3d81`.

**Content reviewed:** Sector study runner, report tests, annual and block tables, reproducibility audit and interpretation. The fixed five-strategy study at three cost levels keeps losing years and implementation caveats visible. It does not establish 10 percent in every calendar year. Its result artifacts and reporting logic are already integrated, including the unsuccessful cases.

**Why:** The reviewed tip is an exact ancestor of main via 31abd9aa569cf06a1a21f523a84256e069d0f7bc; its contribution is preserved in history and no missing branch-only work was found.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 35. codex/sector-strategy-study

**Decision:** Deleted redundant remote pointer. Tip `de70b9f14a340e5d15537ed0676e28242821179c`.

**Content reviewed:** Primary-literature dossier and preregistered five-strategy sector study protocol and implementation plan. The protocol fixes the 2006–2025 comparison, causal ranking/skip-month rules, next-open fills, fees and input guards before the recorded results. This is the research specification underlying the subsequent engine and results branches, all preserved by the integration merge.

**Why:** The reviewed tip is an exact ancestor of main via 31abd9aa569cf06a1a21f523a84256e069d0f7bc; its contribution is preserved in history and no missing branch-only work was found.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 36. codex/stock-20year-refresh

**Decision:** Deleted redundant remote pointer. Tip `45de9575aa5960b8a7d361d91c5e9cbbac86c15d`.

**Content reviewed:** Records refreshed 189 long-history comparisons plus archived QQQ/BIL return provenance, independent replay and bounded unactivated follow-on proposals.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 37. codex/stock-broad-replay

**Decision:** Deleted redundant remote pointer. Tip `18d6e4acdb2b3188157bfcdecddd3a4224bcdc8d`.

**Content reviewed:** Adds reproducible broad-study source assembly, original capture/hash validation, declared stock universe, protected output paths and source assembly tests; records A8 deployment.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 38. codex/stock-broad-scan

**Decision:** Deleted redundant remote pointer. Tip `3caf2e2e99463458ef0d2d61256a6a5f24c4180c`.

**Content reviewed:** Adds broad captured-history validator with complete per-candidate coverage statuses and configurable explicit historical-study universe without changing default rules.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 39. codex/stock-broad-verification

**Decision:** Deleted redundant remote pointer. Tip `7d6ed3b61764d38dc2fe22b63b21dfabef3ba159`.

**Content reviewed:** Adds broad scanner coverage/quarantine tests for omitted, missing, malformed, duplicate, synthetic and unrequested source data and output protection.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 40. codex/stock-ci-format-1

**Decision:** Deleted redundant remote pointer. Tip `1189e3da1ed21bbc2b62ce2f45a91349b31ca982`.

**Content reviewed:** Formats broad/forward scripts, challenger and coverage display; renames requests dictionary to request_sources to remove Bandit false positive.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 41. codex/stock-ci-format-2

**Decision:** Deleted redundant remote pointer. Tip `b2b04b167d733e080604da49206ee1afccd725b2`.

**Content reviewed:** Formats event archive, forward study/panel, health, historical study, research scanner and universe CLI without changing the reviewed expressions.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 42. codex/stock-ci-format-3

**Decision:** Deleted redundant remote pointer. Tip `6c2c23030b1c08fa359bee34dce4505f9cc16f84`.

**Content reviewed:** Formats broad/challenger/coverage/dashboard/event tests and preserves existing assertions.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 43. codex/stock-ci-format-4

**Decision:** Deleted redundant remote pointer. Tip `530e3cd46a0dba9ac926cd07224c9f9dc350d382`.

**Content reviewed:** Formats forward-panel/study, health, research and universe tests without substantive behavior changes.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 44. codex/stock-ci-format-5

**Decision:** Deleted redundant remote pointer. Tip `ba0be5358f94344c39735e7eab2b8d45afa3c7ba`.

**Content reviewed:** Completes workflow/replay-test formatting and records a dated read-only A8 operational sweep plus local validation, with scheduled execution still unverified.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 45. codex/stock-collection-health

**Decision:** Deleted redundant remote pointer. Tip `e1cd0f97fefa36bf200721e3e6a5f9cf848d01be`.

**Content reviewed:** Adds read-only collection-health reporting that distinguishes committed import, expected session, event freshness and actual scheduler success; tests missing/future/corrupt/stale states.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 46. codex/stock-coverage-dashboard

**Decision:** Deleted redundant remote pointer. Tip `2aa2dc342ec2fca77bf0f062a7232392ee100dd8`.

**Content reviewed:** Adds read-only catalogue/coverage, broad-study outcomes and archived-event dashboard. Retains missing/unranked names and negative 5/20-session results; no mature 126-session outcome or trading action is implied.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 47. codex/stock-direction-engine

**Decision:** Deleted redundant remote pointer. Tip `103d8cdbc22547bdc8706c708d12512039390b94`.

**Content reviewed:** Adds the pure directional study: S20 continuation, S5 reversal and L12-1 momentum, seven horizon pairs, next-session opening entries, exact opening exits, costs and explicit pending/excluded/unavailable rows. Tests causality, arithmetic and endpoint handling. Bearish labels still report long-holding returns, not short-sale profits.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 48. codex/stock-direction-report-tests

**Decision:** Deleted redundant remote pointer. Tip `1f015d288605884d65ebd7bab6f60873078832a9`.

**Content reviewed:** Adds directional reporting regressions for pending/missing/bearish long losses, neutral versus unscored groups, cross-boundary cohorts, strict JSON, three costs and refusal of existing output before archive access.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 49. codex/stock-direction-results

**Decision:** Deleted redundant remote pointer. Tip `26e69d0c80c271a6ee5d6624528adc8f8da5a880`.

**Content reviewed:** Publishes the 10/25-bps aggregate directional CSVs: seven rule/horizon pairs, four signal categories and six epoch/status groups per cost, retaining zero-count and unresolved rows. These descriptive overlapping cohorts are not account CAGR.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 50. codex/stock-direction-runner

**Decision:** Deleted redundant remote pointer. Tip `759afcc365449b2ed099b68493487e05fa190850`.

**Content reviewed:** Adds the offline directional archive runner: bounded symbol/manifests, SHA validation, safe ZIP paths, adjusted opening proxies, cutoff and all seven pairs/three costs. Refuses existing output and records source/code/protocol identities; tests tampering, traversal and missing SPY.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 51. codex/stock-direction-verdict

**Decision:** Deleted redundant remote pointer. Tip `744e94c26633c8dfe768cc44a71e78449da8782f`.

**Content reviewed:** Publishes 50-bps groups, complete negative directional verdict, run hashes and independent same-source arithmetic audit. All seven direction controls underperform the always-up diagnostic; untested earnings/social/relationship arms and survivor/current-vintage limitations remain explicit. Does not promote a strategy.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 52. codex/stock-discovery-coverage

**Decision:** Deleted redundant remote pointer. Tip `45de9575aa5960b8a7d361d91c5e9cbbac86c15d`.

**Content reviewed:** Alias at exactly the stock-20year-refresh tip. Its final commit documents archived QQQ ten-month trend/BIL provenance and independent signal/account replay, contrasting CAGR with losing calendar years and refusing promotion; the complete two-commit contribution is also read under stock-20year-refresh.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 53. codex/stock-earnings-screen

**Decision:** Deleted redundant remote pointer. Tip `f778cfa5e18bbf0e3a5b853842695ea4395cdf59`.

**Content reviewed:** Implements fixed prospective earnings/momentum screen with 21 aligned SPY sessions, price/liquidity gates, captured verified recent EPS beat, same-universe momentum ablation and top-three deterministic ranking. Rejects conflicting quarters, future actuals, invalid timestamps and synthetic flag types; tests retain exclusion reasons.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 54. codex/stock-event-archive

**Decision:** Deleted redundant remote pointer. Tip `ed5d093dd49d4c175a25508d327e699d88201d77`.

**Content reviewed:** Adds isolated immutable SQLite news/filing event versions and observations, publication/retrieval/first-seen chronology, atomic validation and backdate watermark. Read-only as-of queries preserve revisions; foreign/paper databases and conflicting batches are refused, with regression tests.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 55. codex/stock-evidence-hardening

**Decision:** Deleted redundant remote pointer. Tip `1eccccb8ef361c9d59c4e52cb6a8097726cb3dce`.

**Content reviewed:** Hardens universe output extensions against overwriting databases and adds event-history tests for restored text, metadata corrections, idempotency watermarks and legacy observation migration.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 56. codex/stock-evidence-study

**Decision:** Deleted redundant remote pointer. Tip `d1fe31431694fe872b8185aa7978c99ddbcf8ad4`.

**Content reviewed:** Registers seven fixed directional price comparisons and future event-enhancement gates before performance work; documents historical/universe/social data feasibility and an independent saved-Tester-ledger arithmetic audit. Research plans and limitations are preserved, without activating strategies or platform collectors.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 57. codex/stock-forward-dashboard

**Decision:** Deleted redundant remote pointer. Tip `065bd018c0ac316b67f12b9cc564d90cc9f05c81`.

**Content reviewed:** Adds forward research and collection-health dashboard, with stale/failed scheduler warnings, invalid outcomes withheld, exclusion reasons and read-only tests. Records dated EPS-source limitations and manual A8 evidence; scheduled or independent-feed operation remains unverified by those records.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 58. codex/stock-forward-outcomes

**Decision:** Deleted redundant remote pointer. Tip `8cece91a1e316c9447f9c36db822b4155ed636e1`.

**Content reviewed:** Adds write-once actual-time forward decisions and matched SPY 20-session outcomes using next regular open. Anchors and prior observations reject changed history; missing weekday/calendar coverage yields explicit invalid status. Tests show losing/pending outcomes and immutable decisions.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 59. codex/stock-forward-plan

**Decision:** Deleted redundant remote pointer. Tip `976c178dba07d2aed4ce4515cdca531462808f5a`.

**Content reviewed:** Freezes the prospective earnings-versus-momentum ablation, health checks and implementation/acceptance plan. Separates hypothetical cohorts from the existing paper account and makes source/timestamp/automation limitations explicit.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 60. codex/stock-lab-archive

**Decision:** Deleted redundant remote pointer. Tip `73b7ecdafc3d81dfb50d4bccc4810ae67f0fcbc3`.

**Content reviewed:** Adds dated archive validation, source hashes, duplicate/adjustment checks and complete-grid exclusions; enforces A8 isolated-release research output authority. Tests cover provenance, invalid OHLC and escaped output paths.

**Why:** Complete original contribution is already reachable in main through integration PR #214. The original stacked PR was closed without individual merge; that does not imply lost work. No unique commits remain; deleting this branch pointer leaves main and its history intact.

**Evidence:** [branch-review-root.json](branch-review-root.json) — SHA256 `5cb2d1893cfae7977521c046c0631bb114fb7142d935fc310893d32933f48fcd`.

### 61. codex/stock-lab-artifacts

**Decision:** Deleted redundant remote pointer. Tip `9516ed2ad38a35fbe63e588ae193b162fb8e51ef`.

**Content reviewed:** Registers source/code/configuration manifests before comparison, publishes immutable artifacts and hashed latest pointers, retains failed attempts; adds A8 CLI and interruption/no-overwrite tests.

**Why:** Complete original contribution is already reachable in main through integration PR #214. The original stacked PR was closed without individual merge; that does not imply lost work. No unique commits remain; deleting this branch pointer leaves main and its history intact.

**Evidence:** [branch-review-root.json](branch-review-root.json) — SHA256 `5cb2d1893cfae7977521c046c0631bb114fb7142d935fc310893d32933f48fcd`.

### 62. codex/stock-lab-cohort-tests

**Decision:** Deleted redundant remote pointer. Tip `51a9731026d4fd868b7400e4a00d7796e0abb199`.

**Content reviewed:** Pins next-open entry, 5/20-session exits, both trading costs, cash for empty slots, missing-outcome rejection, future-invariant selection and all 600 registered scenarios.

**Why:** Complete original contribution is already reachable in main through integration PR #214. The original stacked PR was closed without individual merge; that does not imply lost work. No unique commits remain; deleting this branch pointer leaves main and its history intact.

**Evidence:** [branch-review-root.json](branch-review-root.json) — SHA256 `5cb2d1893cfae7977521c046c0631bb114fb7142d935fc310893d32933f48fcd`.

### 63. codex/stock-lab-cohorts

**Decision:** Deleted redundant remote pointer. Tip `b974df48272c292a6bdda5bc66447ba54a23e095`.

**Content reviewed:** Implements normalized cohort budgets, next-session opening entry, closing exits, explicit pending/unavailable outcomes and matched cash/SPY/universe controls; withholds aggregate returns after missing mature observations.

**Why:** Complete original contribution is already reachable in main through integration PR #214. The original stacked PR was closed without individual merge; that does not imply lost work. No unique commits remain; deleting this branch pointer leaves main and its history intact.

**Evidence:** [branch-review-root.json](branch-review-root.json) — SHA256 `5cb2d1893cfae7977521c046c0631bb114fb7142d935fc310893d32933f48fcd`.

### 64. codex/stock-lab-collection

**Decision:** Deleted redundant remote pointer. Tip `db879cb6a600d5c388c0fdb38f37b43dbeb9693a`.

**Content reviewed:** Implements immutable sorted <=10-symbol capture plans, preserved raw attempts/errors, request/time/membership validation, resume, digest checking and explicit distinction between transport completion and usable coverage.

**Why:** Complete original contribution is already reachable in main through integration PR #214. The original stacked PR was closed without individual merge; that does not imply lost work. No unique commits remain; deleting this branch pointer leaves main and its history intact.

**Evidence:** [branch-review-root.json](branch-review-root.json) — SHA256 `5cb2d1893cfae7977521c046c0631bb114fb7142d935fc310893d32933f48fcd`.

### 65. codex/stock-lab-collection-checks

**Decision:** Deleted redundant remote pointer. Tip `2313d2179d7680bf71f8682f28e7caa5e1759906`.

**Content reviewed:** Tests capture recovery, tampering, duplicate/foreign/missing responses, provider errors and interrupted writes; documents sampled financial/filing/option capabilities and missing point-in-time or executable evidence.

**Why:** Complete original contribution is already reachable in main through integration PR #214. The original stacked PR was closed without individual merge; that does not imply lost work. No unique commits remain; deleting this branch pointer leaves main and its history intact.

**Evidence:** [branch-review-root.json](branch-review-root.json) — SHA256 `5cb2d1893cfae7977521c046c0631bb114fb7142d935fc310893d32933f48fcd`.

### 66. codex/stock-lab-comparison-ui

**Decision:** Deleted redundant remote pointer. Tip `6d8f1b94976a6f69b69f73fa672055a1395ec9e1`.

**Content reviewed:** Adds read-only hash/path/schema verification and all-600-scenario filtering/downloads, explicit survivor/fill limitations and tests for unavailable evidence and navigation.

**Why:** Complete original contribution is already reachable in main through integration PR #214. The original stacked PR was closed without individual merge; that does not imply lost work. No unique commits remain; deleting this branch pointer leaves main and its history intact.

**Evidence:** [branch-review-root.json](branch-review-root.json) — SHA256 `5cb2d1893cfae7977521c046c0631bb114fb7142d935fc310893d32933f48fcd`.

### 67. codex/stock-lab-dashboard

**Decision:** Deleted redundant remote pointer. Tip `b9e7a369f7f6e31109bd6ead3f727853c796feef`.

**Content reviewed:** Introduces Paper accounts, Strategy comparisons, Scanner and Data health tabs while retaining pilot and parallel accounts; adds scanner UI tests that withhold stale, failed or invalid evidence.

**Why:** Complete original contribution is already reachable in main through integration PR #214. The original stacked PR was closed without individual merge; that does not imply lost work. No unique commits remain; deleting this branch pointer leaves main and its history intact.

**Evidence:** [branch-review-root.json](branch-review-root.json) — SHA256 `5cb2d1893cfae7977521c046c0631bb114fb7142d935fc310893d32933f48fcd`.

### 68. codex/stock-lab-release-notes

**Decision:** Deleted redundant remote pointer. Tip `12b260ed726ce91c24fa2ca89ec5fb3833c1322a`.

**Content reviewed:** Records the historical 600-scenario A8 result, 128 positive means and seven unresolved price conflicts; marks delivered plan items while retaining blocked recurring scanner activation. These dated operational statements are not new live-host verification.

**Why:** Complete original contribution is already reachable in main through integration PR #214. The original stacked PR was closed without individual merge; that does not imply lost work. No unique commits remain; deleting this branch pointer leaves main and its history intact.

**Evidence:** [branch-review-root.json](branch-review-root.json) — SHA256 `5cb2d1893cfae7977521c046c0631bb114fb7142d935fc310893d32933f48fcd`.

### 69. codex/stock-lab-scanner

**Decision:** Deleted redundant remote pointer. Tip `a7cfa5a5e6cd7d81906bcfacf6c5323164c32b22`.

**Content reviewed:** Adds immutable completed-session scans, exact requested/candidate coverage, real SPY target-session requirement, invalid-bar exclusions and success/failure attempt pointers; a failed latest attempt cannot overwrite the prior successful report.

**Why:** Complete original contribution is already reachable in main through integration PR #214. The original stacked PR was closed without individual merge; that does not imply lost work. No unique commits remain; deleting this branch pointer leaves main and its history intact.

**Evidence:** [branch-review-root.json](branch-review-root.json) — SHA256 `5cb2d1893cfae7977521c046c0631bb114fb7142d935fc310893d32933f48fcd`.

### 70. codex/stock-lab-scanner-checks

**Decision:** Deleted redundant remote pointer. Tip `7edd8aec8b958064e49271fbc5a37e8e3383b083`.

**Content reviewed:** Adds authority-first scanner CLI with provenance hashes and tests of target sessions, missing/invalid/duplicate symbols, provider errors, preserved failed attempts and immutable prior outputs.

**Why:** Complete original contribution is already reachable in main through integration PR #214. The original stacked PR was closed without individual merge; that does not imply lost work. No unique commits remain; deleting this branch pointer leaves main and its history intact.

**Evidence:** [branch-review-root.json](branch-review-root.json) — SHA256 `5cb2d1893cfae7977521c046c0631bb114fb7142d935fc310893d32933f48fcd`.

### 71. codex/stock-lab-scanner-ui

**Decision:** Deleted redundant remote pointer. Tip `74e6bd0f9247ee86456dfd74553fb7348bbed666`.

**Content reviewed:** Reads verified scanner and latest-attempt artifacts; rejects mismatched chronology/schema/hash/ranks, withholds matches after failure and exposes dated coverage, exclusions and complete downloads.

**Why:** Complete original contribution is already reachable in main through integration PR #214. The original stacked PR was closed without individual merge; that does not imply lost work. No unique commits remain; deleting this branch pointer leaves main and its history intact.

**Evidence:** [branch-review-root.json](branch-review-root.json) — SHA256 `5cb2d1893cfae7977521c046c0631bb114fb7142d935fc310893d32933f48fcd`.

### 72. codex/stock-lab-scores

**Decision:** Deleted redundant remote pointer. Tip `491037dbaf6ddead8ae833484282896715262718`.

**Content reviewed:** Registers five fixed price-score families x four lookbacks x five sizes; implements dated eligibility with $5 price and $20m liquidity thresholds, deterministic ranks and future-invariance/hand-calculation regressions.

**Why:** Complete original contribution is already reachable in main through integration PR #214. The original stacked PR was closed without individual merge; that does not imply lost work. No unique commits remain; deleting this branch pointer leaves main and its history intact.

**Evidence:** [branch-review-root.json](branch-review-root.json) — SHA256 `5cb2d1893cfae7977521c046c0631bb114fb7142d935fc310893d32933f48fcd`.

### 73. codex/stock-long-comparisons

**Decision:** Deleted redundant remote pointer. Tip `726a7c7c929a434a25150dd2f796bfe5ed3dbbb9`.

**Content reviewed:** Adds 189 fixed component/blend cost scenarios with explicit reset-cohort accounting and missing outcomes.

**Why:** Retain engine/tests in main. These are hypothetical reset cohorts, not annual compounded account returns; no winner promotion is lost by deleting the completed pointer.

**Evidence:** [branch-review-long-vintage.json](branch-review-long-vintage.json) — SHA256 `b7515f29fd1363737629e18668e7b3d9611c26cd09a91476bbccb7b9957b8ce0`.

### 74. codex/stock-long-history

**Decision:** Deleted redundant remote pointer. Tip `05fe6ff4c92d1a654e699e762ab4a3ddb81070e0`.

**Content reviewed:** Adds a hash-verified long daily-history loader with explicit source coverage and exclusions.

**Why:** Keep loader/tests in main. It is an exploratory current-survivor, split-only, observed-SPY-calendar dataset adapter; branch retention cannot supply missing delisted/dividend data.

**Evidence:** [branch-review-long-vintage.json](branch-review-long-vintage.json) — SHA256 `b7515f29fd1363737629e18668e7b3d9611c26cd09a91476bbccb7b9957b8ce0`.

### 75. codex/stock-long-publication

**Decision:** Deleted redundant remote pointer. Tip `f1c2c5c258a4c61bd5197e15cf2fef6158c30ee7`.

**Content reviewed:** Adds isolated A8-only publication of frozen long-history research with manifests and failure receipts.

**Why:** Retain CLI/module/tests in main. Required raw capture, authority and ignored output artifacts are separate runtime prerequisites, not unmerged branch work.

**Evidence:** [branch-review-long-vintage.json](branch-review-long-vintage.json) — SHA256 `b7515f29fd1363737629e18668e7b3d9611c26cd09a91476bbccb7b9957b8ce0`.

### 76. codex/stock-long-research-notes

**Decision:** Deleted redundant remote pointer. Tip `3ceaf805979e4591928bdb23c16851a4dc8855f7`.

**Content reviewed:** Documents the long study protocol, source-access boundaries, component evidence and measured no-winner outcome.

**Why:** Preserve all dated results and negative evidence in main. The described future data/validation needs are roadmap work, not an unmerged implementation at this branch tip; no merge is needed.

**Evidence:** [branch-review-long-vintage.json](branch-review-long-vintage.json) — SHA256 `b7515f29fd1363737629e18668e7b3d9611c26cd09a91476bbccb7b9957b8ce0`.

### 77. codex/stock-observation-journal

**Decision:** Deleted redundant remote pointer. Tip `8c286a33508fea521558a56983df8c4f48e8c889`.

**Content reviewed:** Adds per-decision content-addressed observation journals and CLI. Refuses conflicting/older/tampered captures, evaluates before saving, isolates decision histories and preserves immutable files; tests cover those contracts.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 78. codex/stock-paper-lab

**Decision:** Deleted redundant remote pointer. Tip `7f8c3faa1147155fbafc6a91140de2525c915757`.

**Content reviewed:** Creates the initial six-stock research/report CLI, timestamp and source checks, matched-SPY excess-momentum features, a $100 virtual ledger with reserved cash and next-eligible-open execution, immutable history anchors, 20-session exits, readonly SQLite dashboard data, Streamlit panels and historical cohorts. Also includes two early operations commits distinguishing placeholder station truth and phone-readable scheduled status reports. Later main changes improve the original outage/catch-up restriction; remerging this old branch would add no missing work.

**Why:** All 13 original contribution commits are preserved by exact ancestry through PR #214. This is an obsolete branch pointer, not an unmerged implementation. Keep code, research, tests and later fixes in main; retain the pre-cleanup bundle for recovery.

**Evidence:** [branch-review-bootstrap.json](branch-review-bootstrap.json) — SHA256 `f0f83baeb8fe2ce0eb2f67d27868255ecd4d64442fe92df7bfefa228c8248a5c`.

### 79. codex/stock-paper-outage-recovery

**Decision:** Deleted redundant remote pointer. Tip `241d83d5baa6980fea249ff055d38228480fb940`.

**Content reviewed:** Implements explicit outage-recovery CLI/ledger paths that recognize only precommitted orders and fixed exits chronologically, retain actual observation times, daily loss pauses and recovered marks, and avoid missed-day discretionary selections. Adds mirror refusal, same-session idempotency, delayed-recognition displays and constrained hash-bound retention of unavailable optional history with original timestamps. Regression suites cover atomic rollback, changed/missing/synthetic bars, horizons, cash/fee outcomes and retention proof. Operational results are historical manual-recovery records, not present uptime proof.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 80. codex/stock-paper-validation

**Decision:** Deleted redundant remote pointer. Tip `64312bb8a7762b39383180f515bfd8b303548739`.

**Content reviewed:** Adds four synthetic end-to-end stock workflow tests covering daily import, next-open fills, fee/cash accounting, 5/20-session exits, unready 126-session outcomes and news-as-context chronology. Records dated institutional research and small options capability probes, explicitly not profitable or executable historical options evidence.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 81. codex/stock-parallel-dashboard

**Decision:** Deleted redundant remote pointer. Tip `422a7793fce8674c99a1ae401500b99f66e65512`.

**Content reviewed:** Adds read-only comparison dashboard for all nine independent virtual books, frozen-schema/method checks and withholding stale/invalid amounts. Shows open losses, pauses, partial failures, unequal launches and benchmark limitations; AppTests verify no writes and honest missing/recovered states.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 82. codex/stock-parallel-evidence

**Decision:** Deleted redundant remote pointer. Tip `64844d9ececa61a9efed1513dc4cf4ea45e320fa`.

**Content reviewed:** Adds nine-variant candidate tests for fixed cardinality/method hashes, matched selections, earnings/liquidity/history exclusions, future-bar rejection and ledger compatibility. Documents shared captures, A8-only writer, failed-run recovery and correlated-account limitations.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 83. codex/stock-parallel-protocol

**Decision:** Deleted redundant remote pointer. Tip `38f674696f097f46c5c7f2b8e28c20969632ba06`.

**Content reviewed:** Freezes nine independent $100 portfolios and extends the ledger with immutable holding-period/protocol/launch settings. Legacy populated accounts cannot adopt a different strategy, including on replay. Tests independently verify 5/20-session exits, balances, launch clocks and default behavior; plans warn against best-of-nine significance claims.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 84. codex/stock-parallel-regressions

**Decision:** Deleted redundant remote pointer. Tip `634428ced7cacffae4172b31fdbb1e17f6b43eb6`.

**Content reviewed:** Adds SQLite runner regressions for nine isolated accounts, replay, losing paths, independent horizons, visible partial failure, benchmark revisions/gaps, interrupted publication and recovery of only committed stale accounts.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 85. codex/stock-parallel-runner

**Decision:** Deleted redundant remote pointer. Tip `96bb2b673ce17e9c4572a416a36ebf33a2334e13`.

**Content reviewed:** Adds shared-capture nine-book runner/CLI with immutable launch and input artifacts, per-account transactions/errors, held-symbol coverage, benchmark/calendar checks, writer lock, durable intent and explicit stale committed-result recovery. Records all reports without resetting successful accounts.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 86. codex/stock-parallel-start-time

**Decision:** Deleted redundant remote pointer. Tip `bc43ae4bad986deac89aff58d5e9975e16261630`.

**Content reviewed:** Fixes passive benchmark start to the actual common successful account launch, withholding it for partial/unequal starts. Regression covers first blocked attempt followed by delayed successful creation; dated deployment notes preserve the interpolated-zero-volume rejection.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 87. codex/stock-parallel-variants

**Decision:** Deleted redundant remote pointer. Tip `165a30de060ed3d3e3eef928b85bcf77a685cf1a`.

**Content reviewed:** Implements nine frozen momentum/earnings variants and cash-aware account metrics. Recomputes 10/20/60-session scores with complete positive-volume history, deterministic top-three selection, fixed price/liquidity/EPS guards; tracks realized/open P&L, running drawdown, matched-trade SPY and separate fully invested SPY reference.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 88. codex/stock-pivot-readme

**Decision:** Deleted redundant remote pointer. Tip `444fa8361c9824913aabd815596a33cb543faa17`.

**Content reviewed:** Rewrites README/roadmap around active stock research and separate Kalshi operations, replacing unsupported edge/uptime claims with negative results and evidence boundaries. Keeps historical milestones, staged research requirements and no strategy promotion.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 89. codex/stock-pivot-runbooks

**Decision:** Deleted redundant remote pointer. Tip `6ae30b9784020c25c8206f48d6a56ba8e8209804`.

**Content reviewed:** Aligns agent/playbook/setup/runbook/compliance scope with stock research and unchanged Kalshi gates. Replaces destructive branch-protection test instructions with read-only verification and dated actual versus recommended settings. Historical private-repository/protection statements are not current GitHub state.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 90. codex/stock-research-plan

**Decision:** Deleted redundant remote pointer. Tip `96d227cd3fae987b7589bfe4322275c8758d1ad7`.

**Content reviewed:** Registers dated broad-listing catalogue, strict coverage/quarantine, immutable event archive and unchanged momentum baseline replay. Explicitly separates current-survivor coverage, raw provenance, software verification and unresolved predictive evidence.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 91. codex/stock-session-data-repair

**Decision:** Deleted redundant remote pointer. Tip `97329d53edc0b95709266fef0617a0c44f460797`.

**Content reviewed:** Adds pure session-data fallback from verified regular OHLCV plus official SIP close, only replacing missing/synthetic latest daily observations. Enforces chronology, identifiers, required symbols, prices/volume and prior-fallback revision checks; preserves original captures and tests failures without writing a ledger.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 92. codex/stock-session-import

**Decision:** Deleted redundant remote pointer. Tip `144837888b845ff0a76074f4c55b1395af4941e4`.

**Content reviewed:** Adds offline session-source wrapper CLI with raw hashes, error/contradiction checks, aware retrieval times, bounded batch span, mandatory prior and exclusive output. Tests prior supplements, later real-history discrepancies and unchanged next-open accounting/idempotency.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 93. codex/stock-session-operations

**Decision:** Deleted redundant remote pointer. Tip `07a19558bf118c23ca6c6ff1fbb52a1bba247903`.

**Content reviewed:** Documents verified manual session recovery, required retained history and source-vintage reconciliation; adds dashboard labels for alternate verified source and manual versus scheduler results. Dated balances and schedule text do not prove current deployment health.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 94. codex/stock-strategy-lab-design

**Decision:** Deleted redundant remote pointer. Tip `ac04b1d2752755da837885deb057d08de6bd8810`.

**Content reviewed:** Registers strategy-lab comparison: five signal families, four lookbacks, five breadths, two horizons and three costs (600 result rows), fixed K slots/cash and next-open timing. Plans separate exploration, broad discovery, source capabilities and future validation; it is a design contribution, not evidence of a winning strategy.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 95. codex/stock-universe

**Decision:** Deleted redundant remote pointer. Tip `11b3e4c8903ab9a4197e69eca07644f68b9baf64`.

**Content reviewed:** Adds offline Nasdaq Trader two-file catalogue parser/CLI preserving every listing and exclusion/review reason with capture/hash provenance. Strict headers, flags, dates, trailers, duplicates and protected inputs are tested; current listings do not imply historical universe, prices or broker tradability.

**Why:** DELETE redundant remote branch after the parent's verified backup: its exact tip and all contribution commits are reachable from current main through merged PR #214; there is no unique commit to merge. The named contribution remains preserved in Git history.

**Evidence:** [branch-review-stock.json](branch-review-stock.json) — SHA256 `e3efea2e1213d2476f7ffb73e7bc4b5054bc5f5238b5cb33b8b7bb4e472cd932`.

### 96. codex/stock-vintage-cli

**Decision:** Deleted redundant remote pointer. Tip `8d78f1af635cda29f50e1539b9577bc133ed6445`.

**Content reviewed:** Adds capture-only primary/review/legacy CLI modes and immutable raw-input/output receipts.

**Why:** Retain CLI and tests in main. This branch does not execute ledger orders; deletion removes only a completed integration pointer. Historical native-path handling is not a claim of universal filesystem portability.

**Evidence:** [branch-review-long-vintage.json](branch-review-long-vintage.json) — SHA256 `b7515f29fd1363737629e18668e7b3d9611c26cd09a91476bbccb7b9957b8ce0`.

### 97. codex/stock-vintage-dashboard

**Decision:** Deleted redundant remote pointer. Tip `1ae4cb2eaa5a3c2434e22f45879db04814d5ffed`.

**Content reviewed:** Adds a read-only dashboard notice backed by verified immutable per-lane source-review evidence.

**Why:** Keep verified disclosure and tests in main; the successor stability fix is integrated too. Private runtime reports remain separately required for displaying a real notice.

**Evidence:** [branch-review-long-vintage.json](branch-review-long-vintage.json) — SHA256 `b7515f29fd1363737629e18668e7b3d9611c26cd09a91476bbccb7b9957b8ce0`.

### 98. codex/stock-vintage-evidence

**Decision:** Deleted redundant remote pointer. Tip `64fa22a61ffec9a0352f10c7a86069ed1e098a00`.

**Content reviewed:** Validates original September 28 session evidence and documents why primary daily prices can differ from supplemented official-close observations.

**Why:** Keep the source policy and evidence module in main; the finite review prerequisite is already retained by exact commit ancestry. Source equivalence or accurate executable fills is not claimed.

**Evidence:** [branch-review-long-vintage.json](branch-review-long-vintage.json) — SHA256 `b7515f29fd1363737629e18668e7b3d9611c26cd09a91476bbccb7b9957b8ce0`.

### 99. codex/stock-vintage-ledger-tests

**Decision:** Deleted redundant remote pointer. Tip `a8e080d3ebb0e859833e9e8ea5ba61c9ea545691`.

**Content reviewed:** Tests reconciliation through the real paper importer and ledger chronology.

**Why:** Keep chronology regression in main. Fixture execution evidence is not a broker-confirmed fill; the completed test contribution needs no additional branch.

**Evidence:** [branch-review-long-vintage.json](branch-review-long-vintage.json) — SHA256 `b7515f29fd1363737629e18668e7b3d9611c26cd09a91476bbccb7b9957b8ce0`.

### 100. codex/stock-vintage-operations

**Decision:** Deleted redundant remote pointer. Tip `4b19f1e6804c33671f6a3a3d01bc52be2db0e7be`.

**Content reviewed:** Records the completed manual A8 repair, immutable observations and revised operating policy.

**Why:** Retain these dated operational records in main. Their September statements that draft PRs were unmerged are historical; current ancestry proves later integration via #214. This review does not revalidate live A8 health.

**Evidence:** [branch-review-long-vintage.json](branch-review-long-vintage.json) — SHA256 `b7515f29fd1363737629e18668e7b3d9611c26cd09a91476bbccb7b9957b8ce0`.

### 101. codex/stock-vintage-review

**Decision:** Deleted redundant remote pointer. Tip `df5a14bc05e4b32d90fde4a83cec54a4450fb411`.

**Content reviewed:** Implements the finite September 28 compatibility view without rewriting accepted observations.

**Why:** Keep the pure reconciliation behavior in main. Its parent evidence dependency and successor tests are integrated; no separate merge or ongoing feature work remains at this pointer.

**Evidence:** [branch-review-long-vintage.json](branch-review-long-vintage.json) — SHA256 `b7515f29fd1363737629e18668e7b3d9611c26cd09a91476bbccb7b9957b8ce0`.

### 102. codex/stock-vintage-test-stability

**Decision:** Deleted redundant remote pointer. Tip `f130de152e2bb9b24b8a940edd336be1601a43a3`.

**Content reviewed:** Fixes a timestamp-sensitive source-review panel assertion.

**Why:** Keep the deterministic regression correction in main; no independent feature or outstanding work requires this pointer.

**Evidence:** [branch-review-long-vintage.json](branch-review-long-vintage.json) — SHA256 `b7515f29fd1363737629e18668e7b3d9611c26cd09a91476bbccb7b9957b8ce0`.

### 103. codex/stock-vintage-tests

**Decision:** Deleted redundant remote pointer. Tip `41b9eb857da35785b7c054ba2dcc459010132917`.

**Content reviewed:** Exercises finite review, evidence integrity, source metadata and later-session inheritance with portable synthetic fixtures.

**Why:** Retain the portable tests, including the correction commit. The old ignored-capture dependence is superseded within this branch before integration.

**Evidence:** [branch-review-long-vintage.json](branch-review-long-vintage.json) — SHA256 `b7515f29fd1363737629e18668e7b3d9611c26cd09a91476bbccb7b9957b8ce0`.

### 104. docs/archive-live-mismatch

**Decision:** Deleted redundant remote pointer. Tip `b46946c9f9efe4ec31fb458f71b5689f8fa6bbc2`.

**Content reviewed:** Records why archive-trained station calibration is invalid for the live forecast feed. The roadmap identifies inadequate matched live forecast/observation evidence and refuses calibration until the minimum sample is available. This is a documented limitation, not missing executable work. Its exact patch is in main through PR 126.

**Why:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 105. docs/money-hardening-roadmap

**Decision:** Deleted redundant remote pointer. Tip `e5d0ae33b707c42772d5314f8aebb63b642c3398`.

**Content reviewed:** Documents exhausted weather-paper capital, money-hardening tasks, bankroll separation and scheduled-job corrections. The files preserve the recorded weather losses and halted state, describe free-capital and duplicate-position protections, and remove a nonworking Windows GEFS reforecast schedule. Historical host observations are not evidence of current machine state. The documentation and schedule/test edits are integrated through PR 132.

**Why:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 106. docs/strategy-integration

**Decision:** Deleted redundant remote pointer. Tip `a868c810057f23ca569d5c1630259e2aa4dabd60`.

**Content reviewed:** Research arcs A–E, scaling strategy notes, thesis-ledger design and agent guidance. The branch supplies planning and evidence-management context rather than an unmerged trading implementation. Its original contribution and later revisions are in main by exact ancestry. Historical operating instructions were read as source material and were not executed.

**Why:** The reviewed tip is an exact ancestor of main via b8ce8990970ccb3c0dfe9581063d4ea92ef3aa73; its contribution is preserved in history and no missing branch-only work was found.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 107. feat/nfl-team-lane-schedule

**Decision:** Deleted redundant remote pointer. Tip `ccc003f28f10186f5b9524146ca92bdace536a8f`.

**Content reviewed:** NFL schedule/crosswalk/settlement and Sunday pregame paper-lane scheduling, followed by vertical bankroll isolation. The current branch tip includes both the NFL schedule patch from PR 127 and the bankroll patch from PR 128. It is exactly the same tip as fix/vertical-bankrolls. Both patches match main; an old PR head alone would have missed the second contribution. The schedule handles the documented Sunday timing and odds-credit budget.

**Why:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 108. feat/phase-a

**Decision:** Deleted redundant remote pointer. Tip `21264ca49603b8af3614217f8ba29462a0c88baf`.

**Content reviewed:** Broad phase-A addition of station coverage, previous-run model pool, ensemble variance, NFL paper/CLV infrastructure, index HAR-RV scaffolding, nowcast study and dashboard/fixtures. Reviewed source, tests, fixtures and historical generated values, including isotonic honesty and expanded weather models. The index and nowcast material is research scaffolding, not proof of deployable returns. Some historical dashboard language was stronger than the evidence; later main/audit work is the appropriate context, not remerging the old branch. Exact ancestry preserves this entire contribution.

**Why:** The reviewed tip is an exact ancestor of main via b53077ad71b06ddcbe46f8512c1b0147cc8089ba; its contribution is preserved in history and no missing branch-only work was found.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 109. feat/pr-a5-reality-immune-system

**Decision:** Deleted redundant remote pointer. Tip `8286b481a45b5192e096cbf6abbc5b011d91a4ee`.

**Content reviewed:** Doctor command and scheduled reality probe with production payload, strikes, books, settlement station, freshness and timing checks. The diagnostic makes the known New York station mismatch visible until the later strike/settlement correction. It includes Makefile/CLI wiring, scheduling and tests. No network probe was executed during this branch audit. The exact patch is integrated through PR 102.

**Why:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 110. feat/station-calibration

**Decision:** Deleted redundant remote pointer. Tip `53dfdf23f10f6c5bad1d3769a8d112e9f7e4ec21`.

**Content reviewed:** Station bias/sigma calibration with sample gate, model/router integration, CLI flow and tests. The original archive-based calibration input was subsequently corrected by fix/calibrate-live-source. The calibration feature and its refusal behavior are retained in main; merging this historical snapshot would not improve the current implementation. The original contribution matches PR 124.

**Why:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 111. fix/aggregate-exposure

**Decision:** Deleted redundant remote pointer. Tip `8519f18792cdf8dabda985997b987f2f88d73d4d`.

**Content reviewed:** Free-capital accounting and within-run budget decrements across weather, NBA and NFL paper flows. Open committed cost is deducted from starting capital plus realized P&L, and each new intent reduces the remaining run budget. Tests cover aggregate exposure and vertical isolation, preventing repeated reuse of the same reference bankroll. The patch matches PR 131 on main.

**Why:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 112. fix/calibrate-live-source

**Decision:** Deleted redundant remote pointer. Tip `8c7f0dfbd3ed0dd1aaad644d8a431e0edc1ff94c`.

**Content reviewed:** Restricts station calibration to actual live GEFS/ECMWF lead-one forecast snapshots. This removes the archive/live-source mismatch while retaining the matched-pair sample gate and refusal behavior. The tests explicitly distinguish live and archive provenance. Its exact patch is in main through PR 125.

**Why:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 113. fix/double-exposure-nba

**Decision:** Deleted redundant remote pointer. Tip `70dac7af088f9dc1075280766e7481811d68b913`.

**Content reviewed:** Stable ticker-based signal identity and a repository guard allowing one open position per ticker, with adversarial tests. Changing model/version metadata can no longer create duplicate positions for the same market. Two branch commits were combined by the PR 129 squash, so individual git-cherry plus signs are misleading here. The complete base-to-tip patch has the same stable patch ID and identical raw patch SHA-256 as the base-to-squash change on main.

**Why:** The complete reviewed two-commit contribution is byte-identical to the patch integrated by main commit 73c05ff35324c6d769970e7f6b4596ec0b5457ce; no additional merge is needed.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 114. fix/p1-hardening-wave1

**Decision:** Deleted redundant remote pointer. Tip `c2d9ef819b00ba7edc27e622e80bb961a264e49c`.

**Content reviewed:** Wide correctness hardening across sizing, execution, atomic storage, NBA truth, weather provenance, cross-validation, manifests and diagnostics. Reviewed fee-aware Kelly and ticket-cost sizing, one-sided books/depth, atomic signal/trade persistence, observed/final NBA state and unresolved late voids, Elo calculations, no fabricated weather runtimes, ECMWF step/missing-data guards, honest CV/router inputs, zero-cache handling, atomic manifest writes and logging/read-only diagnostics. These are integrated safeguards, not outstanding branch work.

**Why:** The reviewed tip is an exact ancestor of main via 0d7197b11922dbd70898702ca14ab58df5442ada; its contribution is preserved in history and no missing branch-only work was found.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 115. fix/pr-a-kalshi-prod-payload

**Decision:** Deleted redundant remote pointer. Tip `95752319be3b89a045604d395d1170c5b744820a`.

**Content reviewed:** Parses production dollar prices and fractional order books, with schema/migration changes and captured payload fixtures. The temporary greater-only guard prevents inversion of unsupported less-than contracts until the later typed-strike implementation. Production payload parsing and the tests are preserved in main through PR 101, with later extensions reviewed separately.

**Why:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 116. fix/pr-b-strike-aware-pricing-settlement

**Decision:** Deleted redundant remote pointer. Tip `8849097a32c87d79931b5da1734e90e25c1db649`.

**Content reviewed:** P0 correctness series: typed strikes and settlement, station correction, causal weather history, NBA timing/CLV, UTC storage, backup/setup safeguards and regenerated model evidence. Reviewed greater/less/between strike parsing and ticker cross-checks, half-degree pricing and complete local-standard-time settlement, KJFK-to-KNYC correction, pagination, pre-tipoff NBA and one-side-per-game rules, outcome-independent CLV, true lead-one previous-run weather and deduplication, UTC insertion, ACIS truth, atomic backup/checkpoint and sizing caps. The six generated-model diff sections are covered by eleven exact before/after images reconstructed from 805 fully read canonical objects/arrays. New station results are worse than NDFD despite synthetic profit displays; calibration pass labels can rest on few qualifying bins. The removed reforecast artifact includes depleted/negative accounts. This is preserved failure evidence, not a reason to remerge or promote the models.

**Why:** The reviewed tip is an exact ancestor of main via 53179c348b5edfe073cf3b2323c7f38a548c3833; its contribution is preserved in history and no missing branch-only work was found.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 117. fix/pseudo-replication

**Decision:** Deleted redundant remote pointer. Tip `62ee84e092468ecc7c71cbf6d72826d711d401bc`.

**Content reviewed:** Independent-day sample counts for backtest reliability and calibration gates. Multiple brackets for the same station/day no longer masquerade as independent observations. The change adds n_unique_days and uses it in the reliability thresholds while preserving bracket-level results. Tests cover the correlated-sample case. The exact patch matches PR 130.

**Why:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 118. fix/report-minute-42

**Decision:** Deleted redundant remote pointer. Tip `21ad7538de71d1acb26faac19e200904e957916b`.

**Content reviewed:** Moves the status-report schedule from minute 25 to minute 42 with explanatory operational notes. The timing avoids the documented DuckDB/uv writer and settlement windows. This is a source-file schedule correction; the audit did not reschedule a live host. The exact patch is integrated through PR 135.

**Why:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 119. fix/report-signal-quality

**Decision:** Deleted redundant remote pointer. Tip `00a5fc162b9f452ee937b35c9f43e430d1aaaf3b`.

**Content reviewed:** Health-signal semantics, METAR observation-clock freshness, alert-change handling, bounded busy-read retries and report timing. The code distinguishes UNKNOWN busy reads from false critical failures, recognizes the critical marker and avoids repeatedly paging unchanged calibration failures. PR 133 integrated the first commit. PR 134 is closed and unmerged at the current tip, but the extra minute-42 timing commit matches the separately merged PR 135 exactly. Therefore the closed PR does not contain missing work.

**Why:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.

### 120. fix/vertical-bankrolls

**Decision:** Deleted redundant remote pointer. Tip `ccc003f28f10186f5b9524146ca92bdace536a8f`.

**Content reviewed:** Separate weather, NBA and NFL bankroll calculations and paper-flow filters, together with the preceding NFL scheduling commit. Weather losses cannot silently disable another vertical, and market-prefix filtering keeps each paper balance scoped correctly. This tip is identical to feat/nfl-team-lane-schedule and includes both PR 127 and PR 128 patches. Both are already present on main.

**Why:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

**Evidence:** [branch-review-other.json](branch-review-other.json) — SHA256 `0d947f12b9e2dc8cf02b192713a492beffbcafeec274af9208ce36c542477ea8`.
