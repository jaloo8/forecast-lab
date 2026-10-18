# Stock Paper Lab Implementation Plan

> **For agentic workers:** Use subagent-driven-development to implement and review the scoped tasks. User approved continuous execution; do not ask again between tasks.

**Goal:** Deliver a snapshot-driven stock scanner, forward forecast ledger, and $100 paper-only pilot with an actual first data capture.

**Architecture:** Isolated kq.equities package; read-only provider exports feed a validated pandas research table, SQLite forward ledger and local HTML report. No changes to existing weather/NBA flows or broker execution.

**Tech Stack:** Existing Python 3.12, pandas, numpy, pydantic, pytest; standard-library SQLite/HTML/JSON. Existing authenticated Robinhood MCP tools provide raw exports.

## Global Constraints

- No live order code, credentials, new dependencies, or paid feeds.
- Every feature row has an aware UTC as_of; no future or same-bar information.
- Current news and fundamentals are prospective context, never invented historic features or prediction probabilities.
- Separate paper data from Kalshi DuckDB; preserve unrelated edits.
- Report benchmark-relative historical momentum as a baseline, not proven forecasting skill.
- Account information and credentials must never enter captures.

## Steps and ownership

- [x] 1. Read scope and actual tool contracts; isolate from unfinished edits; capture real daily-bar response for MSFT/SPY before mocking fixtures.
- [x] 2. Source/feature worker: create src/kq/equities/__init__.py and research.py plus tests/test_equity_research.py. Interface scan(snapshot: dict[str, Any]) -> pd.DataFrame and daily_bars(snapshot: dict[str, Any]) -> pd.DataFrame. Daily columns symbol/session_date/open/close/volume/as_of; research columns in design. Tests fail first for incomplete sessions, synthetic data, impossible numbers, timestamp leaks, missing benchmark, and reproducible ranking. Run targeted tests, ruff, strict mypy.
- [x] 3. Ledger worker: create src/kq/equities/ledger.py and tests/test_equity_ledger.py. Interface update_ledger(path: Path, research: pd.DataFrame, bars: pd.DataFrame, *, snapshot_hash: str, as_of: datetime) -> dict[str, Any]. Create immutable forecasts, forward evaluation and medium-only virtual book as designed. Verify idempotence, next-session execution, horizon counting, no overdrafts, cash reservations, cost arithmetic and paused state with unit tests before implementation.
- [x] 4. Parent: create src/kq/equities/__main__.py and report.py with tests/test_equity_cli.py. Command python -m kq.equities --snapshot FILE --ledger FILE --report FILE; reject invalid input before ledger updates; escape all external text in HTML; show rankings by horizon, fundamentals/earnings/news context, coverage, warnings and paper performance. No actionable probability claims. Test real CLI on sample data and prove malformed imports cannot create a ledger.
- [x] 5. Record first actual multi-stock MCP export under ignored data/equities; obtain dated public news observations if supported. Run command and inspect local report. Paper orders created now must remain pending until later real sessions arrive. Add docs/STOCK-PAPER-LAB.md with exact refresh instructions and limits; update ROADMAP.md with experiment and unshipped milestones.
- [x] 6. Independent review for leakage and paper arithmetic; fix meaningful findings; run full pytest, ruff and strict mypy; review diff and working-tree cleanliness; open report and summarize only verified outcome.

## Test commands

Use existing C:/Users/jloo1/Documents/Github/forecast-lab/.venv/Scripts/python.exe with PYTHONPATH=<worktree>/src to avoid installing dependencies. From worktree run -m pytest tests/test_equity_research.py tests/test_equity_ledger.py tests/test_equity_cli.py, then full -m pytest, -m ruff check ., -m mypy src/kq. Focused tests must fail because the feature is absent before implementation. Never relax checks merely to obtain green output.

## Progress / review ledger

Design self-review: the initial release deliberately separates historical ranking from unproven probabilistic forecasts; source freshness, no synthetic same-bar fills, capital reservation and history revisions are explicit. A persistent scanner/news feed is not implied by one MCP export. Multi-horizon quality remains an empirical follow-up.

Final validation (2026-09-28): 1,757 tests passed, 24 platform skips, 1 deselected; all 40 equity tests passed. Repository-wide ruff and strict mypy passed. The actual captured snapshot imported successfully and replayed idempotently. The local HTML report was inspected in the browser.

Independent review found and verified fixes for delayed-capture timing, shifted entry dates, replay validity, history revisions, and daily fill/loss-pause chronology. Active books refuse multi-session catch-up atomically. Cumulative history from the fixed 2025-03-01 start is required; rolling-window exports or provider coverage limits require review.

The first real-data import contains 18 prospective forecasts and three pending virtual orders, with $100 cash and $30 reserved. There are no settled outcomes and no demonstrated prediction accuracy. News and financial reports remain context for the unchanged momentum baseline.

Weekday 6 PM America/Los_Angeles checks are registered through the Stock paper pilot heartbeat. Its first scheduled run and unattended uptime remain unverified. Keep this worktree and its ignored operational data available. Code is committed locally on codex/stock-paper-lab, not merged into main; subsequent news-model research and forward evaluation remain open milestones.
