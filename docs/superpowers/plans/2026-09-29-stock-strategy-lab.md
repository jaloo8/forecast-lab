# Stock Strategy Lab Implementation Plan

> **For agentic workers:** Use subagent-driven-development for bounded tasks and independent reviews. Owner approved the design September 29, 2026; execute without another approval checkpoint.

**Goal:** Deliver the approved staged stock strategy comparison, broad discovery and data-capability work.

**Architecture:** Pure registry/scoring and cohort accounting consume validated captured prices. A separate A8-only research runner persists immutable artifacts; the dashboard reads verified mirrors. Existing ledger writers and trading protocols are untouched.

**Tech Stack:** Existing Python, pandas, SQLite and Streamlit; no new dependencies.

## Global constraints

Paper/research only. A8 is the sole durable research/account writer. No new accounts, risk-cap edits, live orders, paid feeds or new scheduler. Existing historical archive is exploratory and survivor-biased; do not label retrospective splits untouched. Preserve all failures and experiments. Use next-session open, fixed exit session and full costs; unavailable outcomes remain unavailable.

## 1. Registry and scores

Files: `src/kq/equities/strategy_lab/{__init__,registry,features}.py`, `tests/test_strategy_lab_features.py`.

Interfaces: frozen `SelectionSpec(family: str, lookback: int, size: int)` with stable `selection_id`; `selection_specs() -> tuple[SelectionSpec, ...]` (100). `score_candidates(bars: pd.DataFrame, decision_date: date, family: str, lookback: int) -> pd.DataFrame` returns symbol, score, eligible, reason, as_of. Input bars contain symbol/session_date/open/high/low/close/volume/as_of. Features use only rows through decision_date. Common gates: price >=5, median trailing20 dollar volume >=20m, real aligned sessions, full lookback. Five formulas exactly as approved design; deterministic ties.

- [ ] Write hand-computed score, missing history, future-invariance, tie and registry tests; run and record failure before implementation.
- [ ] Implement typed registry and pure features. Example assertion: `assert len(selection_specs()) == 100`; test reversal of a declining price path gives positive score, breakout excludes current close from reference maximum.
- [ ] Run focused pytest, Ruff and strict mypy. Review diff, then commit bounded pieces.

## 2. Cohort engine

Files: `src/kq/equities/strategy_lab/engine.py`, `tests/test_strategy_lab_engine.py` (split helpers if needed).

Interface: `compare(bars: pd.DataFrame, specs: tuple[SelectionSpec, ...] | None = None) -> dict[str, Any]`; returns `results` (600 summary rows), `cohorts` (all attempts, selections/entries/exits/costs), `controls`, `limitations`. Summary fields: selection_id, family, lookback, size, hold_sessions, cost_bps, cohort_count, unavailable_count, mean_exposure, mean_net_return, median_net_return, mean_excess_vs_spy, worst_cohort_return, status. Cache scores per decision/family/lookback.

- [ ] Write failing next-open, flat-cost, horizon, missing-outcome and fewer-than-K tests.
- [ ] Implement decision grid starting after60 returns; entry following decision; 5/20-session hold; 10/25/50bp each side; each selected slot weighs1/K; cash for missing slots. Missing held prices invalidate the cohort and aggregate performance is withheld for incomplete variants. No silent omissions.
- [ ] Controls are cash, same-period SPY and equal-weight eligible universe at each cost/hold. Keep all 600 rows and explicit no-history/unavailable states.
- [ ] Verify exact accounting on small fixtures; run targeted gates; review and commit bounded pieces.

## 3. Validated input, immutable runner and A8 results

Files: `src/kq/equities/strategy_lab/artifacts.py`, `scripts/run_stock_strategy_lab.py`, `tests/test_strategy_lab_artifacts.py`.

- [ ] Test artifact path/source hash validation, interrupted attempts, read-only mirror refusal and exclusive creation.
- [ ] Reuse validated broad scan and dated raw archive, preserving source/catalogue hashes and exclusion counts. Validate every accepted OHLCV row, session grid and adjustment type. Use a distinct source adapter; never modify the frozen broad-study runner.
- [ ] Before evaluation, persist a manifest of every setting and input hash. Write results to a new A8-only dated directory; failure record remains explicit. Publish latest only after complete success and artifact digest verification.
- [ ] Transfer only scoped source/test files and public captures to isolated A8 release with SHA256 checks. Run focused tests and actual comparison there. Preserve database/source hashes. Mirror output with hash checks; never run local account imports.

## 4. Visible comparisons and account navigation

Files: `src/kq/equities/strategy_lab_panel.py`, `src/kq/equities/dashboard.py`, `tests/test_strategy_lab_panel.py`.

- [ ] Write AppTests for all result rows, invalid/missing reports, filters and unchanged paper sections.
- [ ] Add obvious top-level Paper accounts, Strategy comparisons, Scanner and Data health navigation. Keep original pilot and nine accounts visible in Paper accounts. Place historical and forward/adaptive research with appropriate labels.
- [ ] Panel reads `data/equities/strategy-lab/latest.json` pointing to an immutable report with hash verification; results table uses the engine fields above. Show all outcomes, cost/cash conventions, coverage and exploratory limitations. Downloads retain complete results; no automatic winner.
- [ ] Run actual-data AppTest and health check; restart only the isolated stock dashboard if required.

## 5. Broad discovery collection

Files: `src/kq/equities/strategy_lab/collection.py`, `tests/test_strategy_lab_collection.py`, `docs/STOCK-PAPER-LAB.md`.

- [ ] Test deterministic <=10-symbol batch plan, missing/duplicate response coverage, malformed/error wrappers, range identity, exact retry and immutable accepted batches.
- [ ] Build resumable public-capture manifest for dated catalogue candidates plus retained names. Preserve actual times and errors, and don't present partial collection as complete. Source connector remains host/app authenticated.
- [ ] Exercise provider capacity read-only, run broad collection if supported, transfer verified capture, score on A8 and mirror scanner results. Extend existing heartbeat only when this path works; preserve schedule and all existing lane instructions.

## 6. Data-capability audit and release

Files: `docs/research/STOCK-LAB-DATA-CAPABILITIES-2026-09-29.md`, runbook and ROADMAP status notes.

- [ ] Inspect read-only connector metadata and captured responses for filing-vintage fundamentals, news, option history/quotes; write available/unavailable coverage and prerequisites, with no purchases or invented fields.
- [ ] Run independent spec/correctness review. Reproduce defects with tests and repair. Run full repository Ruff, strict mypy, pytest/coverage and security checks once changes settle.
- [ ] Create small stacked draft PRs (<=10 files and approximately<=400 changed lines each), push and attach every PR. Do not merge. Document A8 execution and exact exploratory results; report incomplete data capabilities candidly.

## Verification commands

Use `C:/Users/jloo1/Documents/Github/forecast-lab/.venv/Scripts/python.exe` with `PYTHONPATH=src` from the isolated stock worktree. Focused: `-m pytest tests/test_strategy_lab_*.py`. Full: `-m ruff check .`, `-m ruff format --check .`, `-m mypy src/kq`, `-m pytest --cov=kq --cov-report=term-missing`. A8 uses its existing forecast-lab Python but only the isolated stock release source and outputs.
