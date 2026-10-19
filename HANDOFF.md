# Resume forecast-lab on another computer or account

Checkpoint: October 19, 2026. Active handoff branch: `research/annual-profit-audit-20261019`. Base main commit: `e1e1f4bc43e19ca862e1425ff637e7fa0d124db1`. The current checkout commit is obtained with `git rev-parse HEAD`; it is not embedded inside a file that would change its own commit hash.

## Current objective and result

The owner wants 10–20% profit in **every calendar year**, with **$1,000** as the practical reference. No result demonstrates that future annual floor. Keep CAGR, downside, costs and feasibility visible; do not silently replace the objective with benchmark outperformance or average annual growth.

Completed work:

- Reviewed the base checkout: 631 nonempty files / 120,658 lines and five empty files. The lockfile was structurally inspected; encrypted secrets were not decrypted. The [coverage receipt](docs/research/evidence/2026-10-19/review-coverage.json) records scope and hashes.
- Reproduced 24 fixed stock/cost paths on common 2006–2025 dates. None passes 10% every year. All four published option indices also fail in their common 2009–2025 window. These index histories are not retail net backtests, and the stock study's original $10,000 fractional-unit model is not evidence of $1,000 execution. See the [annual audit](docs/research/ANNUAL-PROFIT-AUDIT-2026-10-19.md).
- Corrected independent percentage/dollar drawdown maxima, Windows long raw-cache paths, and overstated hypothetical-return dashboard wording. Existing full-suite evidence is 2,563 passes / 25 skips; the later audit guard and current 13-test focused verification are recorded separately in [validation](docs/research/evidence/2026-10-19/validation.json).
- Reviewed and deleted 120 redundant GitHub branch pointers: 106 exact ancestor tips plus 14 byte-equivalent integrated contributions. No new merge was needed. The [cleanup record](docs/research/evidence/2026-10-19/branch-cleanup/branch-cleanup-report.json) and reviewer receipts preserve the decisions. Main was unchanged. This active handoff branch is new work, not another stale branch.
- Investigated agent trading frameworks and the owner-provided trading-skills repository. Read the [source review](docs/research/AGENT-TRADING-SOURCE-REVIEW-2026-10-19.md), [pinned skill/code review](docs/research/TRADERMONTY-REVIEW-2026-10-19.md), and [proposed architecture](docs/research/AGENT-RESEARCH-FLOOR-2026-10-19.md). The [read receipt](docs/research/evidence/2026-10-19/tradermonty-review-receipt.json) records 43 targeted third-party files and exact ranges; it does not claim all 2,150 files were reviewed. No third-party skill, agent daemon or provider budget gateway was installed or activated.

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

1. **Databento cache:** the owner confirmed it needs transfer from the other PC. Transfer the complete owner-controlled `Documents/MarketData/databento` folder privately: `catalog.sqlite`, raw payloads, `runs/`, derived selections/census and manifests. The original handoff reports about 15.09 GiB of raw inputs plus derived files. Preserve original files and hashes; do not acquire them again. Use [the frozen options handoff](docs/research/OPTIONS-RESULTS-2026-10-18.md#device-handoff) for the strict and conditional replay commands, after checking that the copied inputs exist. Offline replay requires no API key. The original negative strict/conditional results were not independently reproduced on this PC.
2. **Stock replay wrapper:** privately transfer the previously generated `frozen-data-wrapper.zip` (3,933,510 bytes, SHA256 `4df237cec1ddc6049c628887108cf247f9d2e1041abbf36bc4fa7406d70b2f70`) into an owner-chosen local path. It embeds raw price histories and is not published here. The audit's `prepare --source ..` command assumes a separate QuantLab workspace; it is not a valid assumption for a standalone clone.
3. **Related QuantLab workspace:** older 2000-start, high-return and combination studies plus broker state remain in the owner's private portable workspace. This repository does not contain that entire workspace or transfer authority to run its broker. The latest local handoff ZIP is `QuantLab-branch-cleanup-checkpoint-20261019.zip`, SHA256 `d7e3117a8e4c758c2724ec49cbcfb13c4a61040bd789c4d017809a79a0f414f4`. It is a snapshot, not a distributed lock or live sync.

With the verified stock wrapper at `data/private-transfer/frozen-data-wrapper.zip`, choose a **new** output directory and run the frozen code:

```powershell
uv run --frozen python -m scripts.run_sector_study --archive data/private-transfer/frozen-data-wrapper.zip --output data/replay-new/sector
uv run --frozen python -m scripts.run_inverse_vol_study --archive data/private-transfer/frozen-data-wrapper.zip --baseline data/replay-new/sector --output data/replay-new/inverse-vol
uv run --frozen python -m scripts.audit_annual_target screen --run data/replay-new/inverse-vol --output data/replay-new/annual-screen
```

Do not overwrite original outputs. Hash verification and a successful replay are separate from statistical validity or real execution. Published evidence is historical; no market refresh was performed for this handoff.

## Exact next actions

1. Restore and validate the complete private Databento cache; reproduce the frozen strict and conditional options runs offline into new directories. Preserve missing exits and negative outcomes. This is an integrity check, not a new profitable strategy search.
2. Identify the API-credit provider, available balance, expiry and an explicit numerical spend/call cap without sharing the key. Current agent-floor external-model allowance is zero, and the proposal is not an implemented billing control.
3. Choose one data-qualified research task, then finalize the bounded process-pilot registration. Agents should improve specifications, data review and independent criticism; deterministic engines compute P&L. The proposal is not a promise to find a perfect algorithm.
4. Before any new options annual-return claim, implement and independently validate funded-account NAV, integer contracts, cash/collateral, overlapping positions, fees, marks and lifecycle handling. Before broad stock-selection claims, address historical membership, delistings and as-filed fundamentals.

No live order, new acquisition, subscription, deployment or paper-account migration is authorized by this handoff. No API key is committed. Read-only research can proceed without another account's conversation history.
