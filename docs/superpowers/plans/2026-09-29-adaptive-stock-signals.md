# Adaptive stock signals implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task by task. Track steps below.

**Goal:** Deliver the approved research signal, immutable prospective journal and read-only dashboard, verified against fixtures and current A8 evidence.

**Architecture:** A pure DataFrame scorer consumes captured prices and explicit reference position states. A separate journal records advisory decisions with actual wall time and a read-only snapshot of the original pilot's positions. No execution is connected; dynamic account activation remains a separately reviewed phase of the approved design.

**Tech Stack:** Existing Python 3.12, pandas, SQLite, Streamlit, pytest, Ruff and mypy; no new dependencies.

## Global constraints

- A8 is the sole prospective journal writer. Local files are read-only mirrors or engineering previews; no local paper import.
- Existing pilot and nine books, costs, caps, frozen strategies and schedules remain unchanged.
- Formula: S = 0.5*(E20/(v20*sqrt(20))+E60/(v20*sqrt(60))), E = stock minus SPY log return, v20 = stock log-return sample standard deviation. BUY >= 0.5; held SELL <= 0; held positive HOLD; unheld below threshold WATCH. Invalid data WAIT_DATA; existing intent PENDING.
- Require 61 real aligned sessions, original observation times, 24-hour capture freshness, price >= $5 and median20 dollar volume >= $20m for new candidates only. Missing metrics are null.
- Use only verified 2026 NYSE scheduled closures in the new scorer, from the December 23, 2025 ICE announcement, checked September 29, 2026. Unknown-year or unexpected missing weekdays remain invalid. Do not alter existing lanes' holiday behavior.
- Actual prototype state is the original pilot's read-only held/pending positions, explicitly labelled. BUY/SELL rows are advisory signals, never new orders, fills or funded-account returns.
- News is source-linked context only. No invented probabilities, sentiment, backdating, threshold tuning or historical prospective decisions.

### Task 1: Pure scoring and boundary tests

Files: create `src/kq/equities/adaptive.py`, `tests/test_equity_adaptive.py`. If calendar isolation is useful, add `src/kq/equities/session_calendar.py` and its tests in its own small commit.

Interface: `signals(snapshot: dict[str, Any], states: dict[str, str], *, now: datetime) -> pd.DataFrame`; exported frozen `PROTOCOL` and `METHOD_HASH`. States are `flat`, `held`, `pending_entry`, `pending_exit`. Output includes symbol, as_of, session_date, source_hash, method_hash, price_as_of, excess20, excess60, volatility20, score, state, action, reason and candidate_eligible.

- [ ] Write red tests for known arithmetic, state transitions, equality boundaries, volatility changes, held candidates leaving universe, invalid zero-volatility and synthetic bars, missing stock/SPY weekdays and future/stale capture times.
- [ ] Implement normalization with existing `daily_bars`; validate boolean flags explicitly. Exact official calendar dates: 2026-01-01,01-19,02-16,04-03,05-25,06-19,07-03,09-07,11-26,12-25. Require known year and all expected sessions through the prior completed UTC day; early-close sessions remain valid sessions.
- [ ] Run focused pytest red then green, Ruff and strict types. Review and commit only this task's files.

### Task 2: Immutable advisory journal

Files: `src/kq/equities/adaptive_journal.py`, `tests/test_equity_adaptive_journal.py`, then `scripts/run_adaptive_research.py` in a separate small CLI commit if needed.

Interfaces: `reference_state(database: Path) -> dict[str, Any]`, `record(snapshot: dict[str, Any], reference: dict[str, Any], root: Path) -> dict[str, Any]`, `load_latest(root: Path) -> dict[str, Any]`. Reference contains actual read timestamp, states, reference source/session and source kind. Read SQLite via `mode=ro` in a consistent transaction. The runner takes required `--snapshot`, `--reference-ledger`, `--root`; writes only the new journal root.

- [ ] Write red tests for same-input retry preserving decision time, changed same-session capture/state archived as revision and refused, older input refusal, previously anchored price revision/missing sessions refusal, real clock chronology and corrupt artifacts.
- [ ] Use a dedicated SQLite transaction journal with application ID and foreign-database refusal. Store canonical full input/reference and artifact hashes, one decision per method/session; revisions retain original evidence without replacing a decision. Store failure evidence separately from accepted latest so dashboard can flag a current failure. Never write a caller-supplied paper.sqlite or events.sqlite. Atomic SQLite transactions avoid half-written latest pointers.
- [ ] Bind states to read-only pilot trades/orders. Preserve original reference observation timestamps on retries. Output JSON report with created_at, input_captured_at, source_hash, method_hash, session_date, reference_kind, rows, source_errors, news and data limitations. Verify reference freshness/session alignment before new decisions.
- [ ] Run focused tests including read-only database byte equality; verify no ledger writes. Review and commit in <=400-line PR slices.

### Task 3: Dashboard and deployment

Files: `src/kq/equities/adaptive_panel.py`, minimal `dashboard.py` import/call, `tests/test_equity_adaptive_panel.py`, runbook and design status update.

- [ ] Write AppTests for unavailable journal, recorded advisory BUY/HOLD/SELL/WATCH/WAIT_DATA, pending intent, corrupt data, stale capture, failed latest attempt and source context.
- [ ] Render score/components and evidence times, separate data/position states, news count/timestamps, reference pilot label, and clear absence of trading/profit validation. Read only; never create a database on dashboard load.
- [ ] Run equity regression suite, full lint/format, strict mypy, security and repository coverage gate; get independent review, resolve findings and push small draft PRs.
- [ ] Hash/deploy reviewed source to isolated A8, validate focused tests there, create first journal entry from already verified fresh snapshot at actual current time and current read-only pilot state. No source timestamps are refreshed by this operation.
- [ ] Mirror through a consistent A8 SQLite backup and verified temporary-file replacement. Verify all existing ledger hashes unchanged. Run actual-data dashboard AppTests locally and on A8; respect existing browser policy rejection.

## Validation limits

This first implementation is a functioning daily advisory research journal with reference holdings, not a new dynamic-exit account. Numerical fixture tests and today's preview cannot establish profit. The next execution slice needs a separate fresh $100 account/control protocol, next-open fills, costs/caps, losing-path and recovery tests before activation. No automatic refresh extension is claimed until its scheduler instructions are updated and an actual scheduled run succeeds.
