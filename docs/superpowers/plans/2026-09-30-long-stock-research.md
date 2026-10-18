# Long Stock Research Implementation Plan

> For agentic workers: use subagent-driven development task by task; preserve shared edits.

**Goal:** Run the owner-requested first twenty-year exploratory component/blend study without modifying forward accounts or selecting winners after the fact.

**Architecture:** Capture raw public data locally, validate through a pure loader, calculate fixed historical cohorts in a pure engine, and publish immutable results only through an A8-guarded CLI. See the [design](../specs/2026-09-30-long-stock-research-design.md).

**Tech Stack:** Existing Python, pandas, NumPy, SQLite read-only inspection and SSH; no dependencies.

## Tasks

- [x] Freeze the 100-name catalogue/hash selection and all method definitions before capturing returns. Preserve failed requests and explicit missing-symbol coverage.
- [x] Add `strategy_lab/long_history.py` plus `tests/test_equity_long_history.py`: hashed two-chunk wrapper loader; real bar validation; original retrieval metadata; simulated as_of; cumulative coverage; no entire-history survivor filter. Test rejection of hash changes, unexpected/missing symbols, overlap, future/synthetic bars and inconsistent adjustment.
- [x] Add `strategy_lab/long_study.py` plus `tests/test_equity_long_study.py`: seven fixed score arms, shared eligibility, 1/3/5 picks, 21/63/105 holds, 10/25/50bp costs; matched SPY with identical cash; fixed period summaries; no future-feature leakage. Test next-open fills, costs, missing outcomes, blends, tie rules, forward changes leaving earlier selections fixed.
- [x] Add `scripts/run_long_stock_study.py` plus CLI tests: positive A8 authority, read-only mirror refusal, precomputation manifest, immutable failures and separate pointer; include raw input and code hashes. Never import a paper writer.
- [x] Run focused tests, lint/format, strict mypy and required repository gates; independent review. Fix findings before publishing.
- [x] Transfer source/tests/public captures with SHA checks, run focused tests and research CLI on A8, verify all account/event/advisory database hashes remain unchanged, mirror immutable results after digest checks. Preserve failed attempts.
- [x] Record observed results, no-winner decision and data prerequisites in the runbook; publish only source/docs to feature-branch draft PRs within repository size limits, never raw market captures or databases. No merge.

Every task uses a failing test before implementation. Code ownership: engine worker owns only long_study.py and its tests; root owns loader/CLI/integration and documentation; data researcher owns its named research note. No worker reverts another's changes.
