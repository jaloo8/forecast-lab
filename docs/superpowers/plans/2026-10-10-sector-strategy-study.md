# Sector Strategy Study Implementation Plan

> **For agentic workers:** Use subagent-driven-development for the independent engine and research tasks; parent owns protocol, archive runner and final evidence.

**Goal:** Answer annual-return and consistency questions with a registered 2006–2025 portfolio experiment, without claiming discovery from survivor-selected stocks.
**Architecture:** Read verified cached prices, calculate month-end target weights, simulate self-financing next-open portfolios, publish complete results. Separate pure engine from local archive I/O and interpretation.
**Tech stack:** Existing Python 3.12, pandas/numpy, pytest; no new dependencies.

## Global constraints

- Follow `docs/research/SECTOR-STRATEGY-PROTOCOL-2026-10-10.md` exactly; freeze before outcomes.
- No execution/paper ledger mutations, private data uploads, live endpoint calls or parameter tuning.
- Study data and generated detailed paths stay ignored under `data/sector-study/`; commit only safe source and derived reports.
- Each review slice stays within 10 files / 400 changed lines. Do not merge or delete branches.

## Task 1: Source evidence and freeze

- [x] Save primary-source literature findings in `docs/research/EQUITY-EDGE-LITERATURE-2026-10-10.md`.
- [x] Audit and hash frozen archive inputs; record protocol before engine outcomes.

## Task 2: Pure portfolio engine

Files: `src/kq/equities/sector_study.py`, `tests/test_sector_study.py`.
Interface: `simulate_portfolio(bars, strategy, cost_bps, start='2006-01-01', end='2025-12-31') -> tuple[pd.DataFrame,pd.DataFrame]`, returning daily wealth and decision/execution ledger. Input rows: symbol, session_date, open, close. Strategies: spy_hold, equal_sectors, sector_momentum, spy_trend, sector_momentum_trend.

- [x] Write failing tests for next-open timing, future-data isolation, flat-price fee loss, rank/skip-month convention, zero-cost accounting and input rejection.
- [x] Implement monthly targets and actual-notional self-financing transaction costs; validate frames and strict chronology.
- [x] Run focused tests, lint/format and strict typing. No archived outcome computation before registration.

## Task 3: Reproducible run and independent check

Files: `scripts/run_sector_study.py`, derived `docs/research/SECTOR-STRATEGY-RESULTS-2026-10-10.md` and aggregate evidence.

- [x] Reuse trusted archive verification helpers; reject missing/invalid dates or fund prices.
- [x] Run all five strategies at all three registered costs, saving complete paths/ledgers and annual summaries.
- [x] Independently check self-financing cash/holdings, timing and annual/drawdown calculations; no silent missing outcomes.
- [x] Report all strategies, benchmarks, yearly downside and the literal 10%-every-year result. Record local check scope and CI separately.
