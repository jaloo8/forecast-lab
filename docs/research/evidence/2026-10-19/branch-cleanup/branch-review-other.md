# Review of 26 research, documentation, feature and fix branches

Recommendation: delete all 26 remote branch pointers after the parent verifies backup and unchanged tips. No merge is needed; no branch-only work was found. This reviewer performed no branch mutations.

Frozen main: `e1e1f4bc43e19ca862e1425ff637e7fa0d124db1`. Proof: 13 exact ancestors, 12 branches with every unique commit patch-matched to main, and one combined two-commit squash with identical patch bytes.

## What was actually read

The final contribution of every branch was reviewed from its documented base. The 500 file-diff sections have exact hashes and coverage records. The 7,881-line range-review stream was read completely; prior full reads and identical overlapping text were reused through verified hashes and contiguous line mappings. This is not a claim that repeated text was newly reread or that every transient revision was read.

The six PR-B generated sections were additionally reviewed through eleven exact before/after Git images and a lossless 805-node representation, including the removed reforecast file. Every schema and value was read and the source images were reconstructed and verified. The full lockfile retains its structural-review exception; its changed patch here was read.

Receipts: `other-range-coverage.json`, `other-reading-progress.json`, `other-integration-proofs.json`, `prb-model-review.json`, and per-branch raw-diff hashes in `branch-review-other.json`.

## Cases that needed more than a merged flag

- `fix/double-exposure-nba`: two branch commits are represented by one squash. Combined stable patch ID `b3bb2cac0bd942afdb7a9d8f3ae75e3e63f04aa7` and complete patch SHA-256 match PR 129's main change.
- `fix/report-signal-quality`: PR 134 is closed without a merge, but PR 133 and separately merged PR 135 preserve both commits, including the extra minute-42 change.
- `feat/nfl-team-lane-schedule` and `fix/vertical-bankrolls`: identical current tips contain both PR 127 and PR 128; both patches are on main.
- The sector/company PR stack 207–211 is closed without separate merges, but the exact tips are ancestors of the integration merge from PR 214.

## Per-branch findings

### codex/company-research-pilot

Tip `02db162a4baa46f1486483ae7dde525aa76bcbfb`; contribution base `86cfff3c8f49d925e4e768ff30ba285f47f697fa`.

Company research pilot with source-backed financial and moat notes, a feature CSV, watchlists and private narration drafts. The enterprise/retail and payments/chips cases distinguish reported fundamentals from a prospective stock-selection rule. The small named-company sample and creator-feasibility notes do not establish a point-in-time investable edge. No publication or trading action is required to preserve this work.

**DELETE:** The reviewed tip is an exact ancestor of main via 31abd9aa569cf06a1a21f523a84256e069d0f7bc; its contribution is preserved in history and no missing branch-only work was found.

PR metadata: [#211](https://github.com/jaloo8/forecast-lab/pull/211) (closed, unmerged).

Coverage: 10 file sections; exact paths, ranges and hashes in the JSON receipt.

### codex/expanded-stock-audit-20261018

Tip `a5dfc02fd0ebdf32e4350b9116e859ace37e8fef`; contribution base `45de9575aa5960b8a7d361d91c5e9cbbac86c15d`.

Bounded stock replay implementation, protocol, source register and the A8 research checkpoint. The replay enforces the documented candidate and cost choices and retains incomplete cases rather than filling missing held-stock prices. The checkpoint separates survivor-selected stock evidence, execution limitations and recovered research artifacts. The implementation, tests and negative or incomplete evidence are already in main.

**DELETE:** The reviewed tip is an exact ancestor of main via 31abd9aa569cf06a1a21f523a84256e069d0f7bc; its contribution is preserved in history and no missing branch-only work was found.

Coverage: 8 file sections; exact paths, ranges and hashes in the JSON receipt.

### codex/free-stock-factor-screen

Tip `86cfff3c8f49d925e4e768ff30ba285f47f697fa`; contribution base `614a33026d9650b241a3ee3051b5e394857c3d81`.

Reproducible screen of published French stock-factor portfolios, archived inputs, annual/block metrics, runner and tests. Published portfolio returns are screening evidence, not a point-in-time company selection and execution system. Losing years remain visible; the operating-profitability result does not satisfy a positive annual floor. The code and source/metrics artifacts are integrated.

**DELETE:** The reviewed tip is an exact ancestor of main via 31abd9aa569cf06a1a21f523a84256e069d0f7bc; its contribution is preserved in history and no missing branch-only work was found.

PR metadata: [#210](https://github.com/jaloo8/forecast-lab/pull/210) (closed, unmerged).

Coverage: 8 file sections; exact paths, ranges and hashes in the JSON receipt.

### codex/integrate-research-20261018

Tip `c3687485ccbb7a6b66ef0957943fa4b60a302b20`; contribution base `14d36718ac82d886444bab4129fd91eef198011a`.

Integration of the sector/company research stack with updated stock direction, opening-range diagnostics, options feasibility, money guards and operational documentation. Reviewed the actual first-parent contribution into the mainline integration, including the cumulative research and guardrail changes. The opening-range study is an underlying-price diagnostic; the options documents still require quote and execution evidence. README and scope updates remove obsolete blanket statements and optimistic framing. Overlapping research and code sections are explicitly deduplicated against their originating branches.

**DELETE:** The reviewed tip is an exact ancestor of main via 31abd9aa569cf06a1a21f523a84256e069d0f7bc; its contribution is preserved in history and no missing branch-only work was found.

PR metadata: [#214](https://github.com/jaloo8/forecast-lab/pull/214) (merged).

Coverage: 82 file sections; exact paths, ranges and hashes in the JSON receipt.

### codex/inverse-vol-study

Tip `21a8fb5dc15f88c572bf3188c9932b14a007dbc7`; contribution base `679fe3b74ac6308b4c983d6f685fc1ba572e6552`.

Inverse-volatility sizing variants, study runner, implementation and paired cost-sensitive tests/results. The recorded variants give up CAGR across the paired comparisons and reduce some sector drawdowns. The negative outcome is retained and does not justify strategy promotion or further tuning during cleanup. The full contribution is integrated through PR 225.

**DELETE:** The reviewed tip is an exact ancestor of main via 8ed1e3a72d887853e503ba9aa5d11836a3bc229a; its contribution is preserved in history and no missing branch-only work was found.

PR metadata: [#225](https://github.com/jaloo8/forecast-lab/pull/225) (merged).

Coverage: 6 file sections; exact paths, ranges and hashes in the JSON receipt.

### codex/reel-strategy-checks

Tip `14d36718ac82d886444bab4129fd91eef198011a`; contribution base `a5dfc02fd0ebdf32e4350b9116e859ace37e8fef`.

Causal KO/PEP pair replay with costs and capture tests, plus an SPY one-day-to-expiry call-spread pricing kernel and specification. The long historical pairs example finishes essentially flat after its modeled costs. The spread kernel is not a completed historical options backtest; atomic fills, listed contracts and lifecycle behavior remain implementation constraints. These limitations and tests are preserved in main.

**DELETE:** The reviewed tip is an exact ancestor of main via 31abd9aa569cf06a1a21f523a84256e069d0f7bc; its contribution is preserved in history and no missing branch-only work was found.

Coverage: 11 file sections; exact paths, ranges and hashes in the JSON receipt.

### codex/sector-portfolio-engine

Tip `5d682e80c6699113d87744ef1aec1935acbd7fae`; contribution base `de70b9f14a340e5d15537ed0676e28242821179c`.

Pure sector portfolio replay engine and tests for timing, costs, account conservation and input validity. The original fixed-rule implementation applies causal signals and next-open execution with self-financing transaction costs. Historical lines that differ from later inverse-volatility extensions were reviewed through verified line mappings and direct unmatched reads. No branch-only implementation remains.

**DELETE:** The reviewed tip is an exact ancestor of main via 31abd9aa569cf06a1a21f523a84256e069d0f7bc; its contribution is preserved in history and no missing branch-only work was found.

PR metadata: [#208](https://github.com/jaloo8/forecast-lab/pull/208) (closed, unmerged).

Coverage: 2 file sections; exact paths, ranges and hashes in the JSON receipt.

### codex/sector-strategy-results

Tip `614a33026d9650b241a3ee3051b5e394857c3d81`; contribution base `5d682e80c6699113d87744ef1aec1935acbd7fae`.

Sector study runner, report tests, annual and block tables, reproducibility audit and interpretation. The fixed five-strategy study at three cost levels keeps losing years and implementation caveats visible. It does not establish 10 percent in every calendar year. Its result artifacts and reporting logic are already integrated, including the unsuccessful cases.

**DELETE:** The reviewed tip is an exact ancestor of main via 31abd9aa569cf06a1a21f523a84256e069d0f7bc; its contribution is preserved in history and no missing branch-only work was found.

PR metadata: [#209](https://github.com/jaloo8/forecast-lab/pull/209) (closed, unmerged).

Coverage: 10 file sections; exact paths, ranges and hashes in the JSON receipt.

### codex/sector-strategy-study

Tip `de70b9f14a340e5d15537ed0676e28242821179c`; contribution base `6ae30b9784020c25c8206f48d6a56ba8e8209804`.

Primary-literature dossier and preregistered five-strategy sector study protocol and implementation plan. The protocol fixes the 2006–2025 comparison, causal ranking/skip-month rules, next-open fills, fees and input guards before the recorded results. This is the research specification underlying the subsequent engine and results branches, all preserved by the integration merge.

**DELETE:** The reviewed tip is an exact ancestor of main via 31abd9aa569cf06a1a21f523a84256e069d0f7bc; its contribution is preserved in history and no missing branch-only work was found.

PR metadata: [#207](https://github.com/jaloo8/forecast-lab/pull/207) (closed, unmerged).

Coverage: 4 file sections; exact paths, ranges and hashes in the JSON receipt.

### docs/archive-live-mismatch

Tip `b46946c9f9efe4ec31fb458f71b5689f8fa6bbc2`; contribution base `2edebfdd373719d1f31ba9ede7cc07f0d1bb5476`.

Records why archive-trained station calibration is invalid for the live forecast feed. The roadmap identifies inadequate matched live forecast/observation evidence and refuses calibration until the minimum sample is available. This is a documented limitation, not missing executable work. Its exact patch is in main through PR 126.

**DELETE:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

PR metadata: [#126](https://github.com/jaloo8/forecast-lab/pull/126) (merged).

Coverage: 1 file sections; exact paths, ranges and hashes in the JSON receipt.

### docs/money-hardening-roadmap

Tip `e5d0ae33b707c42772d5314f8aebb63b642c3398`; contribution base `e8c1453c8622130f6365adef24e142adf172f078`.

Documents exhausted weather-paper capital, money-hardening tasks, bankroll separation and scheduled-job corrections. The files preserve the recorded weather losses and halted state, describe free-capital and duplicate-position protections, and remove a nonworking Windows GEFS reforecast schedule. Historical host observations are not evidence of current machine state. The documentation and schedule/test edits are integrated through PR 132.

**DELETE:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

PR metadata: [#132](https://github.com/jaloo8/forecast-lab/pull/132) (merged).

Coverage: 5 file sections; exact paths, ranges and hashes in the JSON receipt.

### docs/strategy-integration

Tip `a868c810057f23ca569d5c1630259e2aa4dabd60`; contribution base `0d7197b11922dbd70898702ca14ab58df5442ada`.

Research arcs A–E, scaling strategy notes, thesis-ledger design and agent guidance. The branch supplies planning and evidence-management context rather than an unmerged trading implementation. Its original contribution and later revisions are in main by exact ancestry. Historical operating instructions were read as source material and were not executed.

**DELETE:** The reviewed tip is an exact ancestor of main via b8ce8990970ccb3c0dfe9581063d4ea92ef3aa73; its contribution is preserved in history and no missing branch-only work was found.

Coverage: 4 file sections; exact paths, ranges and hashes in the JSON receipt.

### feat/nfl-team-lane-schedule

Tip `ccc003f28f10186f5b9524146ca92bdace536a8f`; contribution base `b5054ef7549790699a633ec2d2b60a735f02c65e`.

NFL schedule/crosswalk/settlement and Sunday pregame paper-lane scheduling, followed by vertical bankroll isolation. The current branch tip includes both the NFL schedule patch from PR 127 and the bankroll patch from PR 128. It is exactly the same tip as fix/vertical-bankrolls. Both patches match main; an old PR head alone would have missed the second contribution. The schedule handles the documented Sunday timing and odds-credit budget.

**DELETE:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

PR metadata: [#127](https://github.com/jaloo8/forecast-lab/pull/127) (merged).

Coverage: 7 file sections; exact paths, ranges and hashes in the JSON receipt.

### feat/phase-a

Tip `21264ca49603b8af3614217f8ba29462a0c88baf`; contribution base `b8ce8990970ccb3c0dfe9581063d4ea92ef3aa73`.

Broad phase-A addition of station coverage, previous-run model pool, ensemble variance, NFL paper/CLV infrastructure, index HAR-RV scaffolding, nowcast study and dashboard/fixtures. Reviewed source, tests, fixtures and historical generated values, including isotonic honesty and expanded weather models. The index and nowcast material is research scaffolding, not proof of deployable returns. Some historical dashboard language was stronger than the evidence; later main/audit work is the appropriate context, not remerging the old branch. Exact ancestry preserves this entire contribution.

**DELETE:** The reviewed tip is an exact ancestor of main via b53077ad71b06ddcbe46f8512c1b0147cc8089ba; its contribution is preserved in history and no missing branch-only work was found.

Coverage: 87 file sections; exact paths, ranges and hashes in the JSON receipt.

### feat/pr-a5-reality-immune-system

Tip `8286b481a45b5192e096cbf6abbc5b011d91a4ee`; contribution base `fa3c604d6de113e0fcf8990b0ab52be57e97ac91`.

Doctor command and scheduled reality probe with production payload, strikes, books, settlement station, freshness and timing checks. The diagnostic makes the known New York station mismatch visible until the later strike/settlement correction. It includes Makefile/CLI wiring, scheduling and tests. No network probe was executed during this branch audit. The exact patch is integrated through PR 102.

**DELETE:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

PR metadata: [#102](https://github.com/jaloo8/forecast-lab/pull/102) (merged).

Coverage: 7 file sections; exact paths, ranges and hashes in the JSON receipt.

### feat/station-calibration

Tip `53dfdf23f10f6c5bad1d3769a8d112e9f7e4ec21`; contribution base `bc715a95718f153a3ec58d3044596f672006fc27`.

Station bias/sigma calibration with sample gate, model/router integration, CLI flow and tests. The original archive-based calibration input was subsequently corrected by fix/calibrate-live-source. The calibration feature and its refusal behavior are retained in main; merging this historical snapshot would not improve the current implementation. The original contribution matches PR 124.

**DELETE:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

PR metadata: [#124](https://github.com/jaloo8/forecast-lab/pull/124) (merged).

Coverage: 6 file sections; exact paths, ranges and hashes in the JSON receipt.

### fix/aggregate-exposure

Tip `8519f18792cdf8dabda985997b987f2f88d73d4d`; contribution base `73c05ff35324c6d769970e7f6b4596ec0b5457ce`.

Free-capital accounting and within-run budget decrements across weather, NBA and NFL paper flows. Open committed cost is deducted from starting capital plus realized P&L, and each new intent reduces the remaining run budget. Tests cover aggregate exposure and vertical isolation, preventing repeated reuse of the same reference bankroll. The patch matches PR 131 on main.

**DELETE:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

PR metadata: [#131](https://github.com/jaloo8/forecast-lab/pull/131) (merged).

Coverage: 5 file sections; exact paths, ranges and hashes in the JSON receipt.

### fix/calibrate-live-source

Tip `8c7f0dfbd3ed0dd1aaad644d8a431e0edc1ff94c`; contribution base `b831414ca11d59ab2700ab3db454320154231be2`.

Restricts station calibration to actual live GEFS/ECMWF lead-one forecast snapshots. This removes the archive/live-source mismatch while retaining the matched-pair sample gate and refusal behavior. The tests explicitly distinguish live and archive provenance. Its exact patch is in main through PR 125.

**DELETE:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

PR metadata: [#125](https://github.com/jaloo8/forecast-lab/pull/125) (merged).

Coverage: 2 file sections; exact paths, ranges and hashes in the JSON receipt.

### fix/double-exposure-nba

Tip `70dac7af088f9dc1075280766e7481811d68b913`; contribution base `c84c6c591b0e76aedc7634c8047ff6b7f3ed0d33`.

Stable ticker-based signal identity and a repository guard allowing one open position per ticker, with adversarial tests. Changing model/version metadata can no longer create duplicate positions for the same market. Two branch commits were combined by the PR 129 squash, so individual git-cherry plus signs are misleading here. The complete base-to-tip patch has the same stable patch ID and identical raw patch SHA-256 as the base-to-squash change on main.

**DELETE:** The complete reviewed two-commit contribution is byte-identical to the patch integrated by main commit 73c05ff35324c6d769970e7f6b4596ec0b5457ce; no additional merge is needed.

PR metadata: [#129](https://github.com/jaloo8/forecast-lab/pull/129) (merged).

Coverage: 4 file sections; exact paths, ranges and hashes in the JSON receipt.

### fix/p1-hardening-wave1

Tip `c2d9ef819b00ba7edc27e622e80bb961a264e49c`; contribution base `53179c348b5edfe073cf3b2323c7f38a548c3833`.

Wide correctness hardening across sizing, execution, atomic storage, NBA truth, weather provenance, cross-validation, manifests and diagnostics. Reviewed fee-aware Kelly and ticket-cost sizing, one-sided books/depth, atomic signal/trade persistence, observed/final NBA state and unresolved late voids, Elo calculations, no fabricated weather runtimes, ECMWF step/missing-data guards, honest CV/router inputs, zero-cache handling, atomic manifest writes and logging/read-only diagnostics. These are integrated safeguards, not outstanding branch work.

**DELETE:** The reviewed tip is an exact ancestor of main via 0d7197b11922dbd70898702ca14ab58df5442ada; its contribution is preserved in history and no missing branch-only work was found.

Coverage: 87 file sections; exact paths, ranges and hashes in the JSON receipt.

### fix/pr-a-kalshi-prod-payload

Tip `95752319be3b89a045604d395d1170c5b744820a`; contribution base `f4b17e4406e0e92a603e1f58260ddcfbc30ee714`.

Parses production dollar prices and fractional order books, with schema/migration changes and captured payload fixtures. The temporary greater-only guard prevents inversion of unsupported less-than contracts until the later typed-strike implementation. Production payload parsing and the tests are preserved in main through PR 101, with later extensions reviewed separately.

**DELETE:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

PR metadata: [#101](https://github.com/jaloo8/forecast-lab/pull/101) (merged).

Coverage: 11 file sections; exact paths, ranges and hashes in the JSON receipt.

### fix/pr-b-strike-aware-pricing-settlement

Tip `8849097a32c87d79931b5da1734e90e25c1db649`; contribution base `21b655b0f33217a2c138fd6e5bf6be8d45f82389`.

P0 correctness series: typed strikes and settlement, station correction, causal weather history, NBA timing/CLV, UTC storage, backup/setup safeguards and regenerated model evidence. Reviewed greater/less/between strike parsing and ticker cross-checks, half-degree pricing and complete local-standard-time settlement, KJFK-to-KNYC correction, pagination, pre-tipoff NBA and one-side-per-game rules, outcome-independent CLV, true lead-one previous-run weather and deduplication, UTC insertion, ACIS truth, atomic backup/checkpoint and sizing caps. The six generated-model diff sections are covered by eleven exact before/after images reconstructed from 805 fully read canonical objects/arrays. New station results are worse than NDFD despite synthetic profit displays; calibration pass labels can rest on few qualifying bins. The removed reforecast artifact includes depleted/negative accounts. This is preserved failure evidence, not a reason to remerge or promote the models.

**DELETE:** The reviewed tip is an exact ancestor of main via 53179c348b5edfe073cf3b2323c7f38a548c3833; its contribution is preserved in history and no missing branch-only work was found.

Coverage: 113 file sections; exact paths, ranges and hashes in the JSON receipt.

### fix/pseudo-replication

Tip `62ee84e092468ecc7c71cbf6d72826d711d401bc`; contribution base `c84c6c591b0e76aedc7634c8047ff6b7f3ed0d33`.

Independent-day sample counts for backtest reliability and calibration gates. Multiple brackets for the same station/day no longer masquerade as independent observations. The change adds n_unique_days and uses it in the reliability thresholds while preserving bracket-level results. Tests cover the correlated-sample case. The exact patch matches PR 130.

**DELETE:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

PR metadata: [#130](https://github.com/jaloo8/forecast-lab/pull/130) (merged).

Coverage: 4 file sections; exact paths, ranges and hashes in the JSON receipt.

### fix/report-minute-42

Tip `21ad7538de71d1acb26faac19e200904e957916b`; contribution base `47121a21e22c5d15ab6569c8ebf20db92b52ec37`.

Moves the status-report schedule from minute 25 to minute 42 with explanatory operational notes. The timing avoids the documented DuckDB/uv writer and settlement windows. This is a source-file schedule correction; the audit did not reschedule a live host. The exact patch is integrated through PR 135.

**DELETE:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

PR metadata: [#135](https://github.com/jaloo8/forecast-lab/pull/135) (merged).

Coverage: 3 file sections; exact paths, ranges and hashes in the JSON receipt.

### fix/report-signal-quality

Tip `00a5fc162b9f452ee937b35c9f43e430d1aaaf3b`; contribution base `0647e9da51f677758d156e614c83dae3ddea3077`.

Health-signal semantics, METAR observation-clock freshness, alert-change handling, bounded busy-read retries and report timing. The code distinguishes UNKNOWN busy reads from false critical failures, recognizes the critical marker and avoids repeatedly paging unchanged calibration failures. PR 133 integrated the first commit. PR 134 is closed and unmerged at the current tip, but the extra minute-42 timing commit matches the separately merged PR 135 exactly. Therefore the closed PR does not contain missing work.

**DELETE:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

PR metadata: [#134](https://github.com/jaloo8/forecast-lab/pull/134) (closed, unmerged); [#133](https://github.com/jaloo8/forecast-lab/pull/133) (merged).

Coverage: 6 file sections; exact paths, ranges and hashes in the JSON receipt.

### fix/vertical-bankrolls

Tip `ccc003f28f10186f5b9524146ca92bdace536a8f`; contribution base `b5054ef7549790699a633ec2d2b60a735f02c65e`.

Separate weather, NBA and NFL bankroll calculations and paper-flow filters, together with the preceding NFL scheduling commit. Weather losses cannot silently disable another vertical, and market-prefix filtering keeps each paper balance scoped correctly. This tip is identical to feat/nfl-team-lane-schedule and includes both PR 127 and PR 128 patches. Both are already present on main.

**DELETE:** Every branch-only commit has a verified matching patch on main, and the reviewed content reveals no additional work to merge.

PR metadata: [#128](https://github.com/jaloo8/forecast-lab/pull/128) (merged).

Coverage: 7 file sections; exact paths, ranges and hashes in the JSON receipt.

## Branch dependencies and limits

.github/workflows/ci.yml was fully read: push targets main and pull_request targets all branch patterns; no assigned branch name is pinned.

Read-only branch/ref/checkout searches and relevant schedule/setup/deployment docs found no operational dependency requiring retention of an assigned branch.

External machine checkouts, unpublished scripts and other users' local branch pointers were not audited. Parent is responsible for backup and remote-tip checks.

Historical schedule/host claims were not replayed or treated as current state. No strategy was retuned, no model was promoted and no paper/live trade or network diagnostic was executed. Cleanup preserves the research, including failures and incomplete options evidence, on main and in the parent's verified backup.
