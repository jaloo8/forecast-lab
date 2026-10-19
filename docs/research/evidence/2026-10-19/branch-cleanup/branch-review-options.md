# Options and Databento branch review

Main reviewed: `e1e1f4bc43e19ca862e1425ff637e7fa0d124db1`. **19 branches;22 unique contribution commits;6,540 patch lines read in full.** Each branch contribution exactly matches its integration delta. No branch was changed.

All 19 recommendations are **DELETE the completed branch pointer**, retaining the integrated code, tests, documents and commit history. No remaining change needs merging. Root reports backup-bundle verification and no open/protected branches; confirm current tip again when applying cleanup. The dirty annual-audit changes and private raw cache are separate and remain untouched.

The apparent exception is `codex/options-data-source-study`: its tip is not an ancestor of main because PR215 was squash-merged, but its full contribution patch exactly matches `b3212454761301582adf95149aafe91e6bd542c6`. Re-merging it would duplicate integrated work.

## Branch-specific review

### codex/options-data-source-study — DELETE

Tip `e830238ee16a6278dbf8483ba72a8a3e6550e4b0`. [PR#215](https://github.com/jaloo8/forecast-lab/pull/215) merged 2026-10-18T22:13:59Z as `b3212454761301582adf95149aafe91e6bd542c6` (squash).

Documents why the OptionsDX sample cannot score the fixed rule; compares historical sources, timestamp/expiry limitations and bounded acquisition protocol; corrects the roadmap to acknowledge PR214 integration.

The exact contribution was squash-merged in PR215. The one graph-unique commit is not unique content; do not merge it again. Preserve the historical source audit in main.

Reviewed commits: `e830238ee16a6278dbf8483ba72a8a3e6550e4b0`. Files: `ROADMAP.md`, `docs/research/OPTIONS-CANDIDATE-2026-10-18.md`, `docs/research/OPTIONS-DATA-SOURCES-2026-10-18.md`.

Integration proof: exact contribution-patch SHA256 `04dcc680f02f3e0fe99757724c9cfcdeb8b40a1f50b327ace79a4d769a5e2e34` equals the integration-delta SHA256; integration commit is an ancestor of reviewed main. Unmatched content: none.

### codex/options-cache-plan — DELETE

Tip `c62a24704e43f71982c7cd55795acd3b1cf724f3`. [PR#216](https://github.com/jaloo8/forecast-lab/pull/216) merged 2026-10-18T22:45:36Z as `d70d7208d3e7dcd680601a66b9199b7e064ee739` (merge).

Registers separate acquisition versus offline replay, narrow-window/session cost comparison, durable raw/catalog/derived/runs layout, staged credit budget, unresolved submission recovery and verified backups.

Preserve the historical design and its limitations in main. Its early suggested ceiling is historical context, not a reason to keep a development branch active.

Reviewed commits: `c62a24704e43f71982c7cd55795acd3b1cf724f3`. Files: `ROADMAP.md`, `docs/superpowers/specs/2026-10-18-options-cache-design.md`.

Integration proof: exact contribution-patch SHA256 `cf128fb45d8cdd645b36726a3f9327d30314f4011b4e69ac72f08c12d86fd0f2` equals the integration-delta SHA256; integration commit is an ancestor of reviewed main. Unmatched content: none.

### codex/options-cache-implementation — DELETE

Tip `3c31e9969b8d9405a7949547e08ed7702fbc9bc4`. [PR#217](https://github.com/jaloo8/forecast-lab/pull/217) merged 2026-10-18T22:45:43Z as `cc179b07f7ef3af90008869a5f8827025571b812` (merge).

Adds a free-only metadata GET allowlist, private-key loading, sanitized errors, explicit bounded symbols/time, outward-rounded Decimal estimates and canonical request hashes, with mocked transport tests.

Free discovery remains useful and is integrated, with later record-count support; there is no unmerged implementation to recover.

Reviewed commits: `3c31e9969b8d9405a7949547e08ed7702fbc9bc4`. Files: `ROADMAP.md`, `docs/TESTING.md`, `src/kq/clients/databento_metadata.py`, `tests/test_databento_metadata.py`.

Integration proof: exact contribution-patch SHA256 `8bfd1dbf92f411f72c439b8eb4f0e8534c53633a81024514f3b1e1e17d973499` equals the integration-delta SHA256; integration commit is an ancestor of reviewed main. Unmatched content: none.

### codex/options-estimate-command — DELETE

Tip `b4c3ea831b92d35f91b0a4191386a47cf2c21f6d`. [PR#218](https://github.com/jaloo8/forecast-lab/pull/218) merged 2026-10-18T22:45:48Z as `67be1370e193a2592aa4a3ab2719e2a17c3c1ea3` (merge).

Adds metadata-only CLI receipts, refusal of reused outputs/malformed plans, and implementation plan; also records owner-supplied trading-repository and optional dashboard relevance/license assessment.

Both the estimator and the additional research notes are integrated. Review includes these non-title side contributions; no outstanding change requires merge.

Reviewed commits: `b4c3ea831b92d35f91b0a4191386a47cf2c21f6d`. Files: `ROADMAP.md`, `docs/TESTING.md`, `docs/research/TRADING-REPOSITORIES-2026-10-18.md`, `docs/superpowers/plans/2026-10-18-options-cache-implementation.md`, `scripts/estimate_options_data.py`, `tests/test_estimate_options_data.py`.

Integration proof: exact contribution-patch SHA256 `9be88c243b66a40c50711df7712bcb9e542e09f32c87b3a33a5f5715010beaa2` equals the integration-delta SHA256; integration commit is an ancestor of reviewed main. Unmatched content: none.

### codex/options-cache-storage — DELETE

Tip `b0d2b2932d956dba91ffc55c374f56604707b48c`. [PR#219](https://github.com/jaloo8/forecast-lab/pull/219) merged 2026-10-18T22:45:54Z as `59db28559f571b959480881d47b2c4f95ace1185` (merge).

Adds canonical Request/CreditSnapshot/RawFile/Job objects, atomic verified file publication with corruption quarantine, manifest path checks, consistent SQLite backup and validated restore; adds value-object tests.

The storage primitives remain in main. Current dirty Windows portability fixes are separate local work and must be preserved; deleting the remote branch does not replace them.

Reviewed commits: `b0d2b2932d956dba91ffc55c374f56604707b48c`. Files: `ROADMAP.md`, `docs/TESTING.md`, `src/kq/equities/_options_cache_io.py`, `tests/test_options_cache_values.py`.

Integration proof: exact contribution-patch SHA256 `9d936da79d6a11d1cc9a58b17843d5056dfbdc81e8c2b3db78634d7ab5659b25` equals the integration-delta SHA256; integration commit is an ancestor of reviewed main. Unmatched content: none.

### codex/options-cache-ledger — DELETE

Tip `a2fbdb59037ab04c6c6e1ed6ce76fe9180c2b386`. [PR#220](https://github.com/jaloo8/forecast-lab/pull/220) merged 2026-10-18T22:46:00Z as `27c0a7b677b2ab52f9cf569428f9389be7a357e0` (merge).

Adds the SQLite acquisition ledger: immutable budget, per-symbol interval coverage verified against bytes, serial reservations, durable unknown/submitted states, immutable completed imports and local-only replay/backup/restore.

The core offline state and spending controls are retained in main; later extension changes build on this exact implementation.

Reviewed commits: `a2fbdb59037ab04c6c6e1ed6ce76fe9180c2b386`. Files: `ROADMAP.md`, `docs/TESTING.md`, `src/kq/equities/options_cache.py`, `tests/test_options_cache_smoke.py`.

Integration proof: exact contribution-patch SHA256 `9d8d96ee5aa9da9404efc906521d4c3adbaa32b78dd82c2fa4c65cab8eb40ec6` equals the integration-delta SHA256; integration commit is an ancestor of reviewed main. Unmatched content: none.

### codex/options-cache-regressions — DELETE

Tip `c2530c0178b0e1016226a6d5620d497f66747400`. [PR#221](https://github.com/jaloo8/forecast-lab/pull/221) merged 2026-10-18T22:46:06Z as `1d8063f74f247b059e410e7d213b3478d0b253a9` (merge).

Adds full cache regressions for subset/adjacent interval reuse, per-symbol/schema/version isolation, corrupted data refusal, durable uncertainty, stale/unknown credits, exact cumulative ceiling, immutable corrections, backups and competing reservations.

These useful regression contracts are integrated; delete only the pointer, retaining tests and commit history.

Reviewed commits: `c2530c0178b0e1016226a6d5620d497f66747400`. Files: `ROADMAP.md`, `docs/TESTING.md`, `tests/test_options_cache.py`.

Integration proof: exact contribution-patch SHA256 `b4c0289410638704ef1d2c8209333465478432963ffde6d0d605ea35da9c06b3` equals the integration-delta SHA256; integration commit is an ancestor of reviewed main. Unmatched content: none.

### codex/options-cache-evidence — DELETE

Tip `e47783a5f6a31fb0881c2902502804d9d2369fdb`. [PR#222](https://github.com/jaloo8/forecast-lab/pull/222) merged 2026-10-18T22:46:12Z as `c661d595d924d805b7238c04a21dcfce2160582e` (merge).

Publishes authenticated metadata/cost evidence and the limits of the then-empty cache. Adds interruption-after-publish/catalog, low-precision budgeting, cost-overrun, stale credits, unknown-job restore, corruption repair and SQLite-sidecar regressions.

Keep the audit evidence and adversarial tests in main, including the historical no-download checkpoint; the branch pointer is redundant.

Reviewed commits: `e47783a5f6a31fb0881c2902502804d9d2369fdb`. Files: `ROADMAP.md`, `docs/TESTING.md`, `docs/research/OPTIONS-CACHE-2026-10-18.md`, `docs/research/OPTIONS-DATA-SOURCES-2026-10-18.md`, `docs/superpowers/specs/2026-10-18-options-cache-design.md`, `tests/test_options_cache.py`.

Integration proof: exact contribution-patch SHA256 `dfd47cc8fb03831d8684d6ce76a66a26a689765c0b48f0292216df154327ed05` equals the integration-delta SHA256; integration commit is an ancestor of reviewed main. Unmatched content: none.

### codex/databento-pilot — DELETE

Tip `e67c715bd386fb84c074b46e19bcacab80e2c3e5`. [PR#223](https://github.com/jaloo8/forecast-lab/pull/223) merged 2026-10-19T01:25:14Z as `a1bc2ac745c49b5b1bbc7ffcfaa2661d07fbff50` (merge).

Adds bounded CSV batch transport, durable uncertainty before submission, a transactional $9.99 run ceiling, verified vendor job/file identities, host validation, SHA256/size checks, and reusable downloads.

Preserve the transport and no-duplicate-spend safeguards in main; this completed branch adds no remaining work.

Reviewed commits: `e67c715bd386fb84c074b46e19bcacab80e2c3e5`. Files: `ROADMAP.md`, `src/kq/clients/databento_batch.py`, `src/kq/equities/options_cache.py`, `tests/test_databento_batch.py`.

Integration proof: exact contribution-patch SHA256 `ddcc0e8f97ed1788336617fcdb3a1f96b240d8cffd57c87688dfa3e58c2da206` equals the integration-delta SHA256; integration commit is an ancestor of reviewed main. Unmatched content: none.

### codex/databento-pilot-cli — DELETE

Tip `679fe3b74ac6308b4c983d6f685fc1ba572e6552`. [PR#224](https://github.com/jaloo8/forecast-lab/pull/224) merged 2026-10-19T01:28:51Z as `89e0a778a7acc95df0b10e2380a27c78d7ea083c` (merge).

Adds the seven-request pilot operator and approved plan. Exact unrounded request bounds and unlimited-record job parameters are checked; estimates, submissions and deliveries receive separate receipts; known jobs resume without resubmission.

The working acquisition entry point and plan are integrated; retaining an extra old branch would not preserve additional functionality.

Reviewed commits: `679fe3b74ac6308b4c983d6f685fc1ba572e6552`. Files: `ROADMAP.md`, `docs/superpowers/plans/2026-10-18-databento-pilot.md`, `scripts/acquire_options_pilot.py`, `tests/test_acquire_options_pilot.py`.

Integration proof: exact contribution-patch SHA256 `8f0c2444be182cc1c05376dd9b923ab4f80bcde9f839606c6200f9e7948f8ce5` equals the integration-delta SHA256; integration commit is an ancestor of reviewed main. Unmatched content: none.

### codex/options-pilot-replay — DELETE

Tip `d6b1a1485d237da193b502d30d2be170e0b2aee4`. [PR#226](https://github.com/jaloo8/forecast-lab/pull/226) merged 2026-10-19T01:29:07Z as `7525c36b90d2b82f3ec198d6b93b02a02640cb63` (merge).

Adds chunked causal receive-time CMBP quote/definition adapter, same-local-day chain checks, standard multiplier confirmation, nanosecond freshness/synchronization, invalid-latest refusal and explicit unresolved exits.

These causal and missing-exit safeguards are integrated. The source parent also contains the separate inverse-volatility contribution, already in main via PR225; it is not duplicated as this branch work.

Reviewed commits: `d6b1a1485d237da193b502d30d2be170e0b2aee4`. Files: `ROADMAP.md`, `src/kq/equities/options_replay.py`, `tests/test_options_replay.py`.

Integration proof: exact contribution-patch SHA256 `47a8dfff84c468b28095d9b6a089d5c745df970b9899c8dda6d65ae0dc33842a` equals the integration-delta SHA256; integration commit is an ancestor of reviewed main. Unmatched content: none.

### codex/options-pilot-results — DELETE

Tip `42b5ff0099ec4aeee9ef931f352440a4d6154c92`. [PR#227](https://github.com/jaloo8/forecast-lab/pull/227) merged 2026-10-19T01:35:57Z as `88ebebf8dd283a1a5f0f73e2de902d1929a65875` (merge).

Beyond its report title, adds the actual offline pilot runner: hash-verified Yahoo input, causal standard-call selection, original contract reproduction, local cached payload use, underlying overlap diagnostics and null unresolved-only totals; publishes the three-trade negative result.

Keep runner, selection regressions and evidence in main. The branch carries no remaining data or code; private licensed quotes were never stored in it.

Reviewed commits: `42b5ff0099ec4aeee9ef931f352440a4d6154c92`. Files: `ROADMAP.md`, `docs/TESTING.md`, `docs/research/OPTIONS-CACHE-2026-10-18.md`, `docs/research/OPTIONS-CANDIDATE-2026-10-18.md`, `docs/research/OPTIONS-PILOT-2026-10-18.md`, `scripts/run_options_pilot.py`, `tests/test_options_pilot_runner.py`.

Integration proof: exact contribution-patch SHA256 `f3468c290453b1f6895cd7cfb107a09928947e85260126a63515ea06e7194e6c` equals the integration-delta SHA256; integration commit is an ancestor of reviewed main. Unmatched content: none.

### codex/options-extended-plan — DELETE

Tip `d20832b5010a28218f6bcbb0079e035576d47508`. [PR#228](https://github.com/jaloo8/forecast-lab/pull/228) merged 2026-10-19T02:15:45Z as `233ef0b4719bc6f8dab1f57416cac1a644576075` (merge).

Adds cached session census, strictly lagged volatility/trend labels, outcome-independent first/last cost samples, next-calendar-day provisional symbols and contiguous-only definition plans. Follow-up subtracts all verified definition coverage before replanning.

The planning code and protocol are retained with the cache-reuse correction; completed downstream study supersedes its pending-status text without losing the original record.

Reviewed commits: `6d40d24a4e3e71214f5fcb25b79055a8cf97c049`, `d20832b5010a28218f6bcbb0079e035576d47508`. Files: `ROADMAP.md`, `docs/research/OPTIONS-EXTENSION-2026-10-18.md`, `scripts/plan_options_extension.py`, `tests/test_options_extension.py`.

Integration proof: exact contribution-patch SHA256 `83e302df1953c7608d9a81bea9c4be20ba0f6db0e03f960865adb6ca9669f98e` equals the integration-delta SHA256; integration commit is an ancestor of reviewed main. Unmatched content: none.

### codex/options-credit-extension — DELETE

Tip `e17d6cfdf847b0badac90ae0378f215ee94c6aa6`. [PR#229](https://github.com/jaloo8/forecast-lab/pull/229) merged 2026-10-19T02:52:59Z as `fe26515eeaf6b95dcfb4c9493a6854652d973f3b` (merge).

Adds explicit approved extension scope, $17 cumulative reservation ceiling from $7 prior reservations plus $10 extension, fresh five-minute credit evidence with subsequent imports deducted, bounded serial repricing/resume operator and refusal tests.

The approved historical acquisition workflow is integrated. No new spending permission follows from retaining or deleting this branch.

Reviewed commits: `e17d6cfdf847b0badac90ae0378f215ee94c6aa6`. Files: `ROADMAP.md`, `docs/research/OPTIONS-EXTENSION-2026-10-18.md`, `scripts/acquire_options_extension.py`, `src/kq/clients/databento_batch.py`, `src/kq/equities/_options_cache_io.py`, `src/kq/equities/options_cache.py`, `tests/test_databento_batch.py`, `tests/test_options_acquisition_extension.py`, `tests/test_options_cache.py`.

Integration proof: exact contribution-patch SHA256 `8f7e4b64a188c317e795d2c01ffd328f68522745567d57911f2f131f8214680a` equals the integration-delta SHA256; integration commit is an ancestor of reviewed main. Unmatched content: none.

### codex/options-stream-extension — DELETE

Tip `52a76d4a25e442476550a73ed0b9f02409b22c65`. [PR#230](https://github.com/jaloo8/forecast-lab/pull/230) merged 2026-10-19T02:55:32Z as `d1d6dc1c756bd0de9a7a6f7006ad9eb433d915db` (merge).

Adds explicit bounded stream acquisition using aligned intervals and independent metadata record counts, local hashes, no automatic retry, conservative reservation accounting and abandoned-attempt charges without coverage; supports HTTP200/206 with tests.

The streaming path and uncertainty evidence are integrated; PR231 subsequently preserves X-Warning and extends coalesced windows. No unfinished stream work remains on this pointer.

Reviewed commits: `52a76d4a25e442476550a73ed0b9f02409b22c65`. Files: `ROADMAP.md`, `docs/research/OPTIONS-EXTENSION-2026-10-18.md`, `scripts/stream_options_extension.py`, `src/kq/clients/databento_metadata.py`, `src/kq/clients/databento_stream.py`, `src/kq/equities/options_cache.py`, `tests/test_options_cache.py`, `tests/test_options_stream.py`.

Integration proof: exact contribution-patch SHA256 `2c5966696fa3f81bcb4894cd87957fb4f96e9f708f374a2b71c01853c439ab43` equals the integration-delta SHA256; integration commit is an ancestor of reviewed main. Unmatched content: none.

### codex/options-extension-replay — DELETE

Tip `a62ed42bf322384a93b40b501dc69d16916be1e8`. [PR#231](https://github.com/jaloo8/forecast-lab/pull/231) merged 2026-10-19T03:09:23Z as `f086798d5307f77ac93955a3403f90fd4ffac02d` (merge).

Adds causal dated-chain selection, overlapping quote-window coalescence, offline all-session report, year/regime grouping, cost affordability rechecks, unresolved debits and five-session exploratory intervals. Raises coalesced stream limit to40 minutes. Follow-up preserves X-Warning headers instead of reading the wrong header.

Both replay and receipt correction are integrated; no remaining branch-only fix exists. This is independent one-spread research, not a funded annual portfolio.

Reviewed commits: `519cff0695e2ae9ef53ad4ee40759e2d6ccf4437`, `a62ed42bf322384a93b40b501dc69d16916be1e8`. Files: `ROADMAP.md`, `docs/research/OPTIONS-EXTENSION-2026-10-18.md`, `scripts/prepare_options_extension.py`, `scripts/report_options_extension.py`, `src/kq/clients/databento_stream.py`, `tests/test_options_extended_replay.py`, `tests/test_options_stream.py`.

Integration proof: exact contribution-patch SHA256 `7c1678d733e229fa7d9cccd27188c45032c3e7aa0c5e6030c5addce8ab2e8e2d` equals the integration-delta SHA256; integration commit is an ancestor of reviewed main. Unmatched content: none.

### codex/options-publisher-flag-study — DELETE

Tip `607bd056c136802fc3ead1d5eebf6fd2cebb2351`. [PR#232](https://github.com/jaloo8/forecast-lab/pull/232) merged 2026-10-19T04:07:59Z as `08821bf27afed7eb8bf4072c47eb62eaa51ec451` (merge).

Keeps strict bit2 refusal by default, introduces explicit separately labeled sensitivity only for OPRA publisher30/rtype177, preserves all other flag/quote guards, and records the selected quote policy in each report with tests.

Both policies and the unresolved publisher meaning are preserved in main. Branch deletion neither endorses the sensitivity nor resolves vendor semantics.

Reviewed commits: `607bd056c136802fc3ead1d5eebf6fd2cebb2351`. Files: `ROADMAP.md`, `docs/research/OPTIONS-EXTENSION-2026-10-18.md`, `scripts/report_options_extension.py`, `src/kq/equities/options_replay.py`, `tests/test_options_extended_replay.py`, `tests/test_options_replay.py`.

Integration proof: exact contribution-patch SHA256 `b534ab313c5bb81dd1f9f457c61545cfd78f80d81c17254592b85e422b0cbd03` equals the integration-delta SHA256; integration commit is an ancestor of reviewed main. Unmatched content: none.

### codex/options-extended-results-final — DELETE

Tip `81aa486f0315d3fa9cc8452eccc4154792d61765`. [PR#233](https://github.com/jaloo8/forecast-lab/pull/233) merged 2026-10-19T07:15:58Z as `38664f188db590cd973d3599cc1c5f2ce86633a0` (merge).

Publishes the negative extended study, strict versus publisher-flag sensitivity, all coverage/refusal/unresolved counts, cost stress and verification evidence; replaces obsolete roadmap notices while preserving protocol history.

Preserve rejected-strategy results and caveats in main. Negative performance is not a reason to erase evidence; only the merged development pointer is redundant.

Reviewed commits: `81aa486f0315d3fa9cc8452eccc4154792d61765`. Files: `ROADMAP.md`, `docs/research/OPTIONS-CANDIDATE-2026-10-18.md`, `docs/research/OPTIONS-EXTENSION-2026-10-18.md`, `docs/research/OPTIONS-RESULTS-2026-10-18.md`.

Integration proof: exact contribution-patch SHA256 `a6c5fe626152aacb142bb4b8592ac49dc47713e290042b4a56291e258cf6e45c` equals the integration-delta SHA256; integration commit is an ancestor of reviewed main. Unmatched content: none.

### codex/options-device-handoff — DELETE

Tip `ed74fb14dceb8c79dec5c020f07e6afd824e3712`. [PR#234](https://github.com/jaloo8/forecast-lab/pull/234) merged 2026-10-19T08:20:10Z as `e1e1f4bc43e19ca862e1425ff637e7fa0d124db1` (merge).

Adds full closed-trade cost attribution, private raw-cache transfer and strict/conditional replay handoff. The second commit changes direct script invocation to python -m so imports work portably.

The handoff is still useful and is at current main via PR234; deleting the branch pointer retains these latest instructions. Git is not a backup of the private raw cache.

Reviewed commits: `0cba7108f0e9ffe6a5a0fb329f818b506262acca`, `ed74fb14dceb8c79dec5c020f07e6afd824e3712`. Files: `ROADMAP.md`, `docs/research/OPTIONS-RESULTS-2026-10-18.md`.

Integration proof: exact contribution-patch SHA256 `ad1ddabce8a8a0a42e148de2b5cc11a4b6ff1215625702fe96253be6b175e2ab` equals the integration-delta SHA256; integration commit is an ancestor of reviewed main. Unmatched content: none.

## Read receipt and limits

`branch-review-options.json` contains exact commit/patch SHA256 and stable patch IDs, full read ranges, file patch ranges, PR/base/merge SHAs and explicitly deduplicated inherited stack commits. Raw review patches are preserved in `options-patches/`. All 22 patches were actually read; earlier full-main review was not substituted for this work.

Historical validations and results are attributed to their original commits, not claimed as newly run here. No vendor calls, downloads, installations, strategy changes, branch mutation or private-data access occurred. Repository integration does not establish deployment, future profit, or presence of private cache data.
