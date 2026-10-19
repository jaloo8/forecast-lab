# Long-history and source-vintage branch review

Reviewed main: `e1e1f4bc43e19ca862e1425ff637e7fa0d124db1`. 12 branches, 15 unique contribution commits, 3,292 net contribution patch lines fully read. Three follow-up correction diffs were also fully read.

All twelve recommend **DELETE the redundant branch pointer after backup**, with no additional merge. The original PRs #187–#198 were closed without individual merge; exact commit ancestry and merged PR #214 prove their integration. Every contribution file remains in current main.

This is a branch-content/integration review. Historical results and A8 checks are documented evidence, not newly reproduced performance or runtime verification. No branch, source, account, cache or runtime state was changed.

| Branch | Tip | Original PR | Recommendation | Contribution |
|---|---|---:|---|---|
| `codex/stock-vintage-evidence` | `64fa22a61f` | #187 | DELETE | Validates original September 28 session evidence and documents why primary daily prices can differ from supplemented official-close observations. |
| `codex/stock-vintage-review` | `df5a14bc05` | #188 | DELETE | Implements the finite September 28 compatibility view without rewriting accepted observations. |
| `codex/stock-vintage-tests` | `41b9eb857d` | #189 | DELETE | Exercises finite review, evidence integrity, source metadata and later-session inheritance with portable synthetic fixtures. |
| `codex/stock-vintage-cli` | `8d78f1af63` | #190 | DELETE | Adds capture-only primary/review/legacy CLI modes and immutable raw-input/output receipts. |
| `codex/stock-vintage-ledger-tests` | `a8e080d3eb` | #191 | DELETE | Tests reconciliation through the real paper importer and ledger chronology. |
| `codex/stock-vintage-dashboard` | `1ae4cb2eaa` | #192 | DELETE | Adds a read-only dashboard notice backed by verified immutable per-lane source-review evidence. |
| `codex/stock-vintage-operations` | `4b19f1e680` | #193 | DELETE | Records the completed manual A8 repair, immutable observations and revised operating policy. |
| `codex/stock-long-history` | `05fe6ff4c9` | #194 | DELETE | Adds a hash-verified long daily-history loader with explicit source coverage and exclusions. |
| `codex/stock-long-comparisons` | `726a7c7c92` | #195 | DELETE | Adds 189 fixed component/blend cost scenarios with explicit reset-cohort accounting and missing outcomes. |
| `codex/stock-long-publication` | `f1c2c5c258` | #196 | DELETE | Adds isolated A8-only publication of frozen long-history research with manifests and failure receipts. |
| `codex/stock-vintage-test-stability` | `f130de152e` | #197 | DELETE | Fixes a timestamp-sensitive source-review panel assertion. |
| `codex/stock-long-research-notes` | `3ceaf80597` | #198 | DELETE | Documents the long study protocol, source-access boundaries, component evidence and measured no-winner outcome. |

## codex/stock-vintage-evidence

Adds strict canonical daily OHLCV, source time, duplicate, provider-error and historical-fingerprint validation; verifies original supplement hashes and reconstructed bars. Documents 7 baseline and 56 research revisions, including 49 supplements and 7 volume increases, with overlapping books.

Keep the source policy and evidence module in main; the finite review prerequisite is already retained by exact commit ancestry. Source equivalence or accurate executable fills is not claimed.

Read `root-patches\stock-vintage-evidence.patch` lines 1–232 in full. SHA-256 `6398d1137f570270f5a85d19e84dcedf3a354ef16bbeae3f624c3babca2b0c7d`. Original base `12b260ed726ce91c24fa2ca89ec5fb3833c1322a`; own commits: `64fa22a61ffec9a0352f10c7a86069ed1e098a00`.

Integration: exact tip and all own commits are ancestors of main; tip is an ancestor of PR #214 head `c3687485ccbb7a6b66ef0957943fa4b60a302b20`, whose merge `31abd9aa569cf06a1a21f523a84256e069d0f7bc` is retained in main. No unique graph commits remain. Original PR metadata, exact per-file patch ranges, later-main changes and deduplicated inherited commit IDs are in the JSON receipt.

## codex/stock-vintage-review

Binds exact prior/primary snapshots and accepted-history fingerprints; allows only evidenced supplements and seven named volume-only increases on the fixed date. Inherited bindings cannot reanchor; unknown revisions fail. Primary captures require fresh genuine completed bars and exclude synthetic/current-day observations.

Keep the pure reconciliation behavior in main. Its parent evidence dependency and successor tests are integrated; no separate merge or ongoing feature work remains at this pointer.

Read `root-patches\stock-vintage-review.patch` lines 1–265 in full. SHA-256 `b3fbfbb5f4b1cfdce11663e85ce9f343956ae2bb3fb7bd8d50f0bc0b98fa99c9`. Original base `64fa22a61ffec9a0352f10c7a86069ed1e098a00`; own commits: `df5a14bc05e4b32d90fde4a83cec54a4450fb411`.

Integration: exact tip and all own commits are ancestors of main; tip is an ancestor of PR #214 head `c3687485ccbb7a6b66ef0957943fa4b60a302b20`, whose merge `31abd9aa569cf06a1a21f523a84256e069d0f7bc` is retained in main. No unique graph commits remain. Original PR metadata, exact per-file patch ranges, later-main changes and deduplicated inherited commit IDs are in the JSON receipt.

## codex/stock-vintage-tests

Tests accepted-bar preservation, hash/pair tampering, unlisted/older revisions, missing history, stale required bars, duplicates, weekends, future times and provider errors. The second commit replaces dependencies on ignored real capture files with explicit small fixtures and adjusted expected counts.

Retain the portable tests, including the correction commit. The old ignored-capture dependence is superseded within this branch before integration.

Read `root-patches\stock-vintage-tests.patch` lines 1–360 in full. SHA-256 `9689c983c5cce746f6afc311be386ab62a3af53178c290f2f1875a4654edb6f4`. Original base `df5a14bc05e4b32d90fde4a83cec54a4450fb411`; own commits: `96046e139cd9b1fa185b7e6dc404933c33b5e601`, `41b9eb857da35785b7c054ba2dcc459010132917`.

Integration: exact tip and all own commits are ancestors of main; tip is an ancestor of PR #214 head `c3687485ccbb7a6b66ef0957943fa4b60a302b20`, whose merge `31abd9aa569cf06a1a21f523a84256e069d0f7bc` is retained in main. No unique graph commits remain. Original PR metadata, exact per-file patch ranges, later-main changes and deduplicated inherited commit IDs are in the JSON receipt.

## codex/stock-vintage-cli

Validates mode arguments, path aliasing and required symbols; uses flushed temporary bytes plus hard-link publication to refuse overwrite. Tests repeat-write refusal, malformed review, required-symbol validation, exact raw input hashes and accepted-volume preservation.

Retain CLI and tests in main. This branch does not execute ledger orders; deletion removes only a completed integration pointer. Historical native-path handling is not a claim of universal filesystem portability.

Read `root-patches\stock-vintage-cli.patch` lines 1–342 in full. SHA-256 `08c56952752671025c415aa19a7c23f0df87a399646e5de3b0cd200628fce23a`. Original base `41b9eb857da35785b7c054ba2dcc459010132917`; own commits: `8d78f1af635cda29f50e1539b9577bc133ed6445`.

Integration: exact tip and all own commits are ancestors of main; tip is an ancestor of PR #214 head `c3687485ccbb7a6b66ef0957943fa4b60a302b20`, whose merge `31abd9aa569cf06a1a21f523a84256e069d0f7bc` is retained in main. No unique graph commits remain. Original PR metadata, exact per-file patch ranges, later-main changes and deduplicated inherited commit IDs are in the JSON receipt.

## codex/stock-vintage-ledger-tests

Synthetic full lifecycle keeps the original September 28 AAA fill at 120 despite a revised primary open at 121; same-session reconciliation creates no duplicate trade, the next session opens BBB at 152, retry stays idempotent, and the original holding-period exit occurs only after its required later sessions.

Keep chronology regression in main. Fixture execution evidence is not a broker-confirmed fill; the completed test contribution needs no additional branch.

Read `root-patches\stock-vintage-ledger-tests.patch` lines 1–255 in full. SHA-256 `7da74876ecfbb21f5f099ff225caae6b18bd62275ca3e892091c6c06cd0817ba`. Original base `8d78f1af635cda29f50e1539b9577bc133ed6445`; own commits: `a8e080d3ebb0e859833e9e8ea5ba61c9ea545691`.

Integration: exact tip and all own commits are ancestors of main; tip is an ancestor of PR #214 head `c3687485ccbb7a6b66ef0957943fa4b60a302b20`, whose merge `31abd9aa569cf06a1a21f523a84256e069d0f7bc` is retained in main. No unique graph commits remain. Original PR metadata, exact per-file patch ranges, later-main changes and deduplicated inherited commit IDs are in the JSON receipt.

## codex/stock-vintage-dashboard

Verifies report/review hashes, contained paths, policy, timestamps, unique September 28 pairs and exact baseline/parallel/forward counts. Discloses overlapping lane counts and that manual review proves neither scheduled success, fill accuracy nor profit. Tests absence, tampering, traversal, counts, dates and missing primary bars.

Keep verified disclosure and tests in main; the successor stability fix is integrated too. Private runtime reports remain separately required for displaying a real notice.

Read `root-patches\stock-vintage-dashboard.patch` lines 1–395 in full. SHA-256 `a7c56cfe2c8ed505b148c2cc9c74568f140ba870ae64dbfa776b7dd505caf854`. Original base `a8e080d3ebb0e859833e9e8ea5ba61c9ea545691`; own commits: `1ae4cb2eaa5a3c2434e22f45879db04814d5ffed`.

Integration: exact tip and all own commits are ancestors of main; tip is an ancestor of PR #214 head `c3687485ccbb7a6b66ef0957943fa4b60a302b20`, whose merge `31abd9aa569cf06a1a21f523a84256e069d0f7bc` is retained in main. No unique graph commits remain. Original PR metadata, exact per-file patch ranges, later-main changes and deduplicated inherited commit IDs are in the JSON receipt.

## codex/stock-vintage-operations

Documents exact review bootstrapping and inherited prior selection, primary-only fresh scanning, same-session skip behavior, independent book writers, preserved failed scheduler audit, unchanged 12 SQLite hashes and first repaired scheduled execution still unverified. Follow-up marks completed plan items.

Retain these dated operational records in main. Their September statements that draft PRs were unmerged are historical; current ancestry proves later integration via #214. This review does not revalidate live A8 health.

Read `root-patches\stock-vintage-operations.patch` lines 1–85 in full. SHA-256 `ac158247143a9b41750802554fe1345dafbdda2c79b69c5194da7032ee477e45`. Original base `1ae4cb2eaa5a3c2434e22f45879db04814d5ffed`; own commits: `349c24b7c62b1b812bdd65ca23feab79f90d0383`, `4b19f1e6804c33671f6a3a3d01bc52be2db0e7be`.

Integration: exact tip and all own commits are ancestors of main; tip is an ancestor of PR #214 head `c3687485ccbb7a6b66ef0957943fa4b60a302b20`, whose merge `31abd9aa569cf06a1a21f523a84256e069d0f7bc` is retained in main. No unique graph commits remain. Original PR metadata, exact per-file patch ranges, later-main changes and deduplicated inherited commit IDs are in the JSON receipt.

## codex/stock-long-history

Binds manifest/receipts/request wrappers, actual retrieval versus simulated session-close time, complete contiguous request windows and exact returned/not-found identities. Rejects malformed benchmark/transport identity, excludes invalid optional/synthetic/prelisting rows with counts, caps at genuine SPY history. Tests hashes, time/metadata, optional gaps and boolean values.

Keep loader/tests in main. It is an exploratory current-survivor, split-only, observed-SPY-calendar dataset adapter; branch retention cannot supply missing delisted/dividend data.

Read `root-patches\stock-long-history.patch` lines 1–405 in full. SHA-256 `0a15e7fdbf09a8127ba82ffd58d2cedd3c6c756ebcbedd824c80e66cdcff3f60`. Original base `4b19f1e6804c33671f6a3a3d01bc52be2db0e7be`; own commits: `05fe6ff4c92d1a654e699e762ab4a3ddb81070e0`.

Integration: exact tip and all own commits are ancestors of main; tip is an ancestor of PR #214 head `c3687485ccbb7a6b66ef0957943fa4b60a302b20`, whose merge `31abd9aa569cf06a1a21f523a84256e069d0f7bc` is retained in main. No unique graph commits remain. Original PR metadata, exact per-file patch ranges, later-main changes and deduplicated inherited commit IDs are in the JSON receipt.

## codex/stock-long-comparisons

Uses M/R/V and equal-percentile blends, shared 61-observation eligibility, price/liquidity gates, 1/3/5 names, 21/63/105-session holds and 10/25/50bp each-side costs. Each cohort resets to $100 with $10 slots and cash-matched SPY; mature missing outcomes withhold aggregates, epochs exclude cross-boundary intervals. Tests next-open costs, future-invariant selections, IPO warmup, cash, ties and missing held bars.

Retain engine/tests in main. These are hypothetical reset cohorts, not annual compounded account returns; no winner promotion is lost by deleting the completed pointer.

Read `root-patches\stock-long-comparisons.patch` lines 1–404 in full. SHA-256 `da1eb9f324859957a44c561c9f1090fab184fe6be423b96a5417710c243685e8`. Original base `05fe6ff4c92d1a654e699e762ab4a3ddb81070e0`; own commits: `726a7c7c929a434a25150dd2f796bfe5ed3dbbb9`.

Integration: exact tip and all own commits are ancestors of main; tip is an ancestor of PR #214 head `c3687485ccbb7a6b66ef0957943fa4b60a302b20`, whose merge `31abd9aa569cf06a1a21f523a84256e069d0f7bc` is retained in main. No unique graph commits remain. Original PR metadata, exact per-file patch ranges, later-main changes and deduplicated inherited commit IDs are in the JSON receipt.

## codex/stock-long-publication

Positive authority and exact output-root checks reject local mirrors and short-study destinations; exclusive writer lock, source/code identity manifest before calculation, immutable success/failure run directories, latest-success versus latest-attempt pointers. Tests refusal before writes, precomputation manifest, failure preservation and output isolation.

Retain CLI/module/tests in main. Required raw capture, authority and ignored output artifacts are separate runtime prerequisites, not unmerged branch work.

Read `root-patches\stock-long-publication.patch` lines 1–229 in full. SHA-256 `a1b8886543990bb251aa7b19f3fe6987d411b4f5fc1ab3312477674c36eeaf4e`. Original base `726a7c7c929a434a25150dd2f796bfe5ed3dbbb9`; own commits: `f1c2c5c258a4c61bd5197e15cf2fef6158c30ee7`.

Integration: exact tip and all own commits are ancestors of main; tip is an ancestor of PR #214 head `c3687485ccbb7a6b66ef0957943fa4b60a302b20`, whose merge `31abd9aa569cf06a1a21f523a84256e069d0f7bc` is retained in main. No unique graph commits remain. Original PR metadata, exact per-file patch ranges, later-main changes and deduplicated inherited commit IDs are in the JSON receipt.

## codex/stock-vintage-test-stability

Forces fixture microseconds to contain 119000, then checks that overlapping counts are not summed to 119 only in the actual count caption rather than every caption including timestamps. Product behavior is unchanged.

Keep the deterministic regression correction in main; no independent feature or outstanding work requires this pointer.

Read `root-patches\stock-vintage-test-stability.patch` lines 1–25 in full. SHA-256 `f4b72a251d588c4ef49708b62f8c98f87a2b28649f10986c9b993f28a79c7329`. Original base `f1c2c5c258a4c61bd5197e15cf2fef6158c30ee7`; own commits: `f130de152e2bb9b24b8a940edd336be1601a43a3`.

Integration: exact tip and all own commits are ancestors of main; tip is an ancestor of PR #214 head `c3687485ccbb7a6b66ef0957943fa4b60a302b20`, whose merge `31abd9aa569cf06a1a21f523a84256e069d0f7bc` is retained in main. No unique graph commits remain. Original PR metadata, exact per-file patch ranges, later-main changes and deduplicated inherited commit IDs are in the JSON receipt.

## codex/stock-long-research-notes

Records 100 current hash-selected candidates, 189 comparisons, 150 complete/39 incomplete scenario histories, positive mean counts at each cost, and no method with positive matched-SPY excess in all four blocks. Preserves failure/coverage hashes and explicitly separates reset-cohort means from annual growth; identifies missing delist/dividend/filing/news data and holds prospective promotion. Follow-up marks publication complete.

Preserve all dated results and negative evidence in main. The described future data/validation needs are roadmap work, not an unmerged implementation at this branch tip; no merge is needed.

Read `root-patches\stock-long-research-notes.patch` lines 1–295 in full. SHA-256 `e89f4fdf4f3674b952092515062296ef2039645d15f81552fb241fd5333fd8ea`. Original base `f130de152e2bb9b24b8a940edd336be1601a43a3`; own commits: `51f85e722e4b7adf8ad43c1239e711b81b070a14`, `3ceaf805979e4591928bdb23c16851a4dc8855f7`.

Integration: exact tip and all own commits are ancestors of main; tip is an ancestor of PR #214 head `c3687485ccbb7a6b66ef0957943fa4b60a302b20`, whose merge `31abd9aa569cf06a1a21f523a84256e069d0f7bc` is retained in main. No unique graph commits remain. Original PR metadata, exact per-file patch ranges, later-main changes and deduplicated inherited commit IDs are in the JSON receipt.

Parent reported live admin/protection/open-PR checks and a verified backup bundle. Recheck each recorded tip before mutation. Preserve all main history and ignored raw captures/results; branch cleanup is not dataset transfer or a profitability finding.
