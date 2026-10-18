# Broad stock universe and event evidence implementation plan

User approved broad scanning and continuation of the action items in chat. This implements that design as separate research inputs; the existing six-stock paper book remains the locked baseline. No live trading, new dependencies, paid feeds or changes to risk limits.

## Design and evidence boundaries

Use Nasdaq Trader's public Nasdaq-listed and other-listed directories as a dated current US exchange-listed securities catalogue. Preserve every row and exclusion/review reason; distinguish ETFs, test symbols, known non-common securities and stock candidates. Names are classification hints, not broker tradability proof. Current membership must never be backdated into historical tests; delisted history and OTC/global coverage are absent. Preserve source URLs, original creation-time text, capture timestamp and SHA-256. Price/news/history coverage is a separate status, never implied by catalogue membership. Robinhood's read-only scanner is capped at 200 rows and its observed partition totals disagree, so it cannot establish complete market coverage.

Broader captures exposed synthetic IPO padding and impossible OHLC bars. Preserve raw captures; exclude synthetic bars using the existing validator and quarantine an entire symbol with invalid prices under an explicit `invalid_bar` coverage reason. Continue validating unrelated symbols. Malformed capture envelopes, conflicting responses and source-identity errors still fail the whole analysis. Do not repair prices or infer missing sessions.

Archive news/filing versions in a separate SQLite event store with first-observed timestamps and content hashes. Evidence becomes usable no earlier than both publication and actual archive observation. Repeated identical observations remain idempotent; revised text adds a version without overwriting history. Date-only filings become available no earlier than the next UTC day. Strictly reject future, naive and inconsistent timestamps, unsupported URLs and missing identifiers. Return documented DataFrames with `as_of`; queries before first observation return no event. This release records evidence, not sentiment or a learned forecast probability.

## Tasks and file ownership

- [ ] `src/kq/equities/universe.py`, `tests/test_equity_universe.py`: offline parser/CLI for the two captured directories and their manifest; produce full CSV plus coverage summary. Validate headers, flags, duplicate symbols, footer integrity, capture provenance and classification/exclusion reasons. No downloads from production code.
- [ ] `src/kq/equities/events.py`, `tests/test_equity_events.py`: separate event-store API/CLI and time-filtered read API; test idempotency, revisions, first-seen timing and atomic validation failure. No paper DB writes.
- [ ] `src/kq/equities/coverage_panel.py`, dashboard integration and tests: show catalogue size, candidate count, explicit history/news coverage limits and recent archived events. No trade buttons or automatic imports.
- [ ] Run parsers on real captures, archive verified existing public sources and SEC metadata with actual observation time, inspect a deterministic broader-stock data sample, and transfer only reviewed code/new research artifacts to A8. Preserve authoritative paper.sqlite.
- [ ] Run focused tests, lint, strict types and full required suite; independent review; update runbook/ROADMAP. Push small stacked PRs (each at most 10 files / 400 lines), with no main merge.

## Acceptance

Before observing broad strategy outcomes, reuse the existing historical-study protocol unchanged on captured March–September 2026 prices: 5/5, 20/20 and 126/126 lookback/hold, strongest three positive excess-momentum names, next-open entry, 10 basis points per side for stocks and matched SPY. Include only catalogue stock candidates with a complete identical benchmark session grid; record exclusions before running. Save separately from both the old six-stock study and prospective paper ledger. Report every outcome including losses and empty long-horizon groups, without selecting a winning horizon, annualizing or claiming independent validation. This short, current-survivor experiment cannot establish deployable alpha.

The catalogue enumerates the captured listings with no silent truncation, exposes missing history, and cannot masquerade as a historical universe. Event history cannot leak later-observed or revised text into earlier decisions. Dashboard evidence is read-only. Actual simulation results remain distinct: software accounting tests pass, prior six-stock historical returns are mixed, and no prospective profits are established. A news-aware model and realistic options execution remain subsequent experiments requiring adequate data.
