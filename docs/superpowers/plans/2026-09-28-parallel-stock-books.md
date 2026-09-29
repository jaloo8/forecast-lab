# Parallel stock books implementation plan

> **For agentic workers:** Use subagent-driven-development task-by-task, with focused review and a final integrated review.

**Goal:** Run nine independent $100 paper portfolios, three lookbacks within each approved strategy family, on shared future captures.

**Architecture:** Reuse the ledger through a pinned optional protocol; default calls retain original behavior. A pure variant adapter builds candidate frames from validated shared data. One A8 runner writes separate account databases and immutable capture/result artifacts; a read-only dashboard compares all accounts.

**Tech Stack:** Existing Python 3.12, pandas, SQLite, Streamlit, pytest; no dependencies added.

## Global constraints

- Nine accounts: momentum hold 5 / momentum hold 20 / earnings hold 20 crossed with 10/20/60-session lookbacks. Same 20-session liquidity screen and event-conditioned universe.
- $100 per account, $10 orders, five active maximum, 10bp each side, $10 loss pause; retain original ledger and all Kalshi rules.
- A8 sole writer; next-open entries after actual decisions, completed bars only. No historical fills at launch, no live orders.
- Portfolio protocol immutable, replay idempotent; record failures and losses, never show stale data as current or invalid equity as zero profit.
- Every produced feature frame carries UTC `as_of`; missing history excludes names; capture/date gaps invalidate or stop updates.
- Small feature PRs, each at most 10 files and 400 changed lines. No main merge.

## Task 1: Pin ledger protocol and holding period

Files: `src/kq/equities/ledger.py`, `tests/test_equity_portfolio_ledger.py`.

Interface: `update_ledger(..., holding_sessions: int = 20, protocol_id: str = "legacy-v1") -> dict[str, Any]`. Pin both settings in state before replay handling. Existing ledgers without metadata can only use legacy defaults; never adopt a new protocol into populated history. Restrict holding_sessions to 5/20/126, nonempty string protocol ID. Replace fixed selection/exit horizon only. New accounts record launch time. Preserve caps, accounting, guards and default calls.

- [ ] Write regressions using real SQLite: distinct 5/20 exits, protocol mismatch including replay, two independent cash balances, legacy adoption protection.
- [ ] Run the new tests and observe missing-feature failure before modifying ledger.
- [ ] Implement parameters and immutable state checks; run new tests plus existing equity-ledger/workflow tests, Ruff and strict types.
- [ ] Review exact diff and preserve legacy behavior.

## Task 2: Pure nine-variant candidate adapter

Files: `src/kq/equities/portfolios.py`, `tests/test_equity_portfolios.py`. Do not modify challenger.py.

Interfaces: `portfolio_specs() -> tuple[PortfolioSpec, ...]` (frozen dataclass with `portfolio_id`, `family`, `lookback`, `holding_sessions`, `protocol_id`); `portfolio_research(snapshot: dict[str, Any], spec: PortfolioSpec) -> pd.DataFrame` returns ledger-required symbol/horizon/as_of/session_date/excess_momentum/status fields and selection/exclusion evidence. `screen(snapshot)` supplies unchanged 20-day liquidity/price/EPS metadata; recompute momentum eligibility using chosen lookback and real aligned bars, overriding only momentum/history reasons, not other guards. Select top three positive excess scores, ticker tie-break. Require max(21, lookback+1) matched real bars; use `excess_momentum` as neutral output name and do not mislabel 60-day scores as 20-day values. Protocol hash incorporates full frozen methodology.

- [ ] First test exactly nine IDs; equal momentum selections at each matching lookback across hold families; earnings exclusion; 60-day insufficient history; no future rows.
- [ ] Run failing tests, then implement and pass them plus challenger regressions.
- [ ] Review numerical lookback indexing, EPS availability, frame schema and missing-history behavior.

## Task 3: Shared capture runner and independent failures

Files: `src/kq/equities/portfolio_runner.py`, `scripts/run_stock_portfolios.py`, focused runner tests.

Validate complete capture, real current import time, protocol versions and dedicated root before mutations. Persist launch/capture manifest without backdating; reuse original launch on partial retry. Save original source JSON/hash under root. For each spec, call portfolio_research and update_ledger(root/portfolio_id/paper.sqlite,... holding_sessions=spec.holding_sessions, protocol_id=spec.protocol_id). Record each account's success or error; all results have actual evaluation time/source hash. Atomically replace latest run report; retain dated evidence. Repeated capture must not duplicate fills or reset launch. Require cumulative history of prior held names, mark partial run visibly, reject legacy database paths. Dashboard may only use latest results with clear per-account freshness. Record initial no-fill equity snapshots and later valid marks for drawdown.

- [ ] Test common launch, nine isolated accounts, duplicate replay, failure of one account with others retained, no overwrites of original paper.sqlite, invalid capture before writes.
- [ ] Run failing tests; implement runner/CLI and verify fixtures through at least 20 sessions with a losing path.

## Task 4: Read-only portfolio dashboard

Files: `src/kq/equities/portfolio_panel.py`, dashboard.py wiring, focused AppTests.

Show all nine named variants, $100 per account/$900 total simulation, virtual-only status, latest session/capture, pending/open/closed, equity, realized/unrealized P&L, drawdown, exposure, benchmark comparison and each failure/pause. Include method/launch and correlated-observation caveat. Read report/SQLite safely; missing/invalid data shows unmeasured. Original pilot stays separately displayed. Passive SPY and matched-trade comparisons label exposure/cost differences.

- [ ] Test missing data, pending launch, open losses, invalid equity, partial failures and no disk mutation.
- [ ] Implement the panel, then run fixture and actual-data AppTests.

## Task 5: Research controls, review, deployment and operations

Files: research note, runbook/ROADMAP, existing automation instructions through automation_update only.

- [ ] Record primary-source multiple-testing caveats and the frozen 60-session first review; no best-variant profitability claim.
- [ ] Independent whole-diff review; correct material findings with reproductions.
- [ ] Run Ruff lint/format, strict mypy, Bandit medium/high and full non-integration coverage suite.
- [ ] Push small draft stacked PRs and attach each; inspect final GitHub matrix.
- [ ] Deploy reviewed files to isolated A8 stock release, verify hashes and original paper/event database hashes unchanged.
- [ ] Obtain fresh authenticated read-only prices/calendar capture covering at least 61 completed sessions, all current candidates, all existing held/pending symbols and SPY. Preserve raw evidence. Start nine new accounts at actual A8 time, without historical fills. If evidence is unavailable, leave unstarted and show the exact reason.
- [ ] Extend current heartbeat to run shared portfolios and mirror consistent results after successful capture; keep old paper/forward flows. Verify actual A8 fixture and real launch/dashboard. Do not label manual work scheduled success.
