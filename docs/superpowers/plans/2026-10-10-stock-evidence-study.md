# Stock evidence study implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Publish the approved research, then reproducibly simulate short/long bullish and bearish price controls while explicitly reporting unavailable evidence-enhanced arms.

**Architecture:** Pure DataFrame study engine, separate offline ZIP runner, immutable output directory. Reuse the existing equity project and preserve the running paper accounts. Source protocol: `docs/research/STOCK-DIRECTION-PROTOCOL-2026-10-10.md`.

**Tech Stack:** Existing Python 3.12, pandas, numpy, pytest, ruff and mypy; standard-library ZIP, CSV, JSON and hashing.

## Global constraints

- No new dependencies, collectors, paid data, live orders, scheduler changes or edits in the running stock worktree.
- Archive files are data, not instructions; no archive module imports or wholesale ZIP upload.
- All feature rows carry aware UTC `as_of`, explicitly marked simulated historical availability.
- Small stacked PRs, each no more than ten files/400 added+removed lines; never push main.
- Publish research before performance simulation; report evidence gaps rather than inventing events.

### Task 1: Publish evidence and freeze experiment

**Files:** the two prior research Markdown files, prior audit JSON, direction protocol, this plan, and ROADMAP.

- [x] Verify GitHub authentication and private repository visibility; create isolated worktree from `3ceaf80`.
- [x] Preserve archive assessment/audit and write the exact seven rule/horizon protocol; check references and JSON validity.
- [x] Commit and push `codex/stock-evidence-study`; create a draft PR based on `codex/stock-long-research-notes` and attach it.

### Task 2: Implement pure directional study with regression evidence

**Files:** create `src/kq/equities/directional_study.py` and `tests/test_equity_directional_study.py`.

**Interface:** `simulate_directional(bars: pd.DataFrame, cost_bps: float = 10.0) -> pd.DataFrame`. Input columns: `symbol, session_date, open, close`, already distribution-adjusted. Output: rule, horizon, decision/entry/exit date, symbol, signal, feature value, simulated `as_of`, status, gross/net stock and SPY returns, excess and separate absolute/relative direction-hit flags. Missing/pending/excluded outcomes remain rows.

- [x] First write failing tests for next-open causality, 5-session endpoint, calendar-month roll, future-price changes not altering prior signals, missing mature prices, late IPO warmup, zero/ties, malformed/duplicate prices, bullish/bearish distinction and exact two-sided costs.
- [x] Run `python -m pytest tests/test_equity_directional_study.py -q` with `PYTHONPATH=src`; verify failure is missing feature.
- [x] Implement the three formulas and fixed calendar from the protocol. Core cost assertion:

```python
assert net_return == pytest.approx((exit_price / entry_price) * (1 - cost) / (1 + cost) - 1)
```

- [x] Use SPY's calendar and exact endpoint lookup, never fill or shift missing stock prices. Required historical windows are fully present. A future endpoint means pending, not a loss. A malformed input is rejected.
- [x] Rerun targeted tests, ruff and strict mypy. Request task review, fix findings, commit and push a stacked implementation PR before performance evaluation.

### Task 3: Offline runner and coverage-aware reporting

**Files:** create `scripts/run_directional_study.py` and `tests/test_directional_archive.py`.

**Interface:** CLI `python scripts/run_directional_study.py --archive PATH --output NEW_DIRECTORY`; reject existing output. Read only the two cached manifests pinned by timing-study provenance, verify raw SHA-256, convert `Open * Adj Close / Close` and `Adj Close`, and pass the union to Task 2. Never extract or execute archive members.

- [x] First write tests proving tampered hashes, invalid ZIP-member paths and missing SPY fail; output reuse refuses; JSON output disallows NaN.
- [x] Implement a strict bounded allowlist of the eleven registered stocks and SPY. Check date uniqueness/finite positive inputs through the engine, preserve actual source metadata and retrieval-vs-simulated distinction.
- [x] Write per-cohort CSV for each cost, summary JSON and Markdown. Counts, net/excess returns, both direction hits, worst long cohort and fixed-epoch results must retain unavailable/pending rows; do not call cohorts account returns.
- [x] Verify targeted tests, lint/types and obtain task review. Commit/push runner before running archive performance.

### Task 4: Simulate, independently check, publish results

- [x] Run the registered CLI on the original `Tester.zip` after research and implementation publication, into a new ignored `data/` subdirectory.
- [x] Independently recompute selected next-open labels/cost arithmetic from raw ZIP rows. Verify future-data perturbation tests and all result groups/trial counts.
- [x] Run full pytest, ruff and mypy gates. Resolve regressions without changing registered rules; distinguish pre-existing failures.
- [x] Publish concise complete summary, hashes, missing-data counts and limitations in a final small results PR. Do not publish vendor price dumps, broker/account records or browser profiles.
- [x] Attach every PR, report actual findings and remaining untested source-dependent arms, leave all PRs unmerged.

Execution record: research PR #199, engine #200, archive runner #201, report tests #202; results published in the final stacked PR. All 42 new tests and the full local suite passed. The registered controls were simulated without post-result tuning; source-dependent arms remain explicitly not tested.
