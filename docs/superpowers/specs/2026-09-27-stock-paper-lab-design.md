# Stock research and paper pilot

Approved in chat on 2026-09-27: news + earnings + stock metrics, multiple horizons, paper trading before any $100 live pilot. The user delegates research, coding and testing and wants updates readable in 15 seconds. This is an explicit equities research expansion; Kalshi live gates, fees and caps remain unchanged.

## First working release

A local, snapshot-driven research tool consumes read-only Robinhood MCP market data and timestamped public news/filing observations. It ranks a fixed, disclosed liquid-stock watchlist at 5, 20 and 126 trading-session horizons, saves immutable forward predictions, and tracks a separate $100 virtual medium-horizon book. No live order code, credentials, new dependencies, or paid feeds.

Prices come from completed regular-session daily bars; ignore synthetic bars. Every input records when it was retrieved. Current fundamentals/earnings and newly discovered news are usable prospectively only, never backdated into historical tests. Initial ranking uses transparent benchmark-relative momentum; earnings, fundamentals and news appear as sourced context, not an unvalidated numeric adjustment or invented probability. Missing sources are explicitly marked unavailable. No claims of calibrated probabilities, proven edge, or demonstrated benefit from news.

The first data path is an explicit snapshot export from the existing authenticated MCP tools, plus public web observations. A standalone command validates an export, creates a local readable report and records prospective forecasts. Refreshing requires fresh snapshots; this release must not pretend a persistent data feed or unattended scheduler already exists.

## Snapshot contract

JSON object: captured_at (aware ISO UTC), benchmark (SPY), bars (Robinhood data.results entries: symbol/interval/bounds/bars), fundamentals (data.results list), earnings (flattened data.results list), news (list of symbol/title/url/published_at/retrieved_at/kind), source_errors (list of strings). News kind is news or filing; publication and retrieval required; no automatic sentiment. Record raw captures in ignored data/equities. Never save account data or OAuth credentials.

## Research output

DataFrame columns: symbol, horizon_sessions (5/20/126), as_of (UTC), session_date, close, benchmark_close, momentum, benchmark_momentum, excess_momentum, volatility_20d, pe_ratio, market_cap, sector, latest_eps_actual, latest_eps_estimate, news_count, status. Only complete synchronized history produces a ranked row. All scores are historical features, not expected returns. Display source coverage and stale-data failures. Future-dated observations fail validation; all positive financial numbers must be finite. Every report includes the input digest and model label momentum_baseline_v1.

## Forward ledger and paper trades

SQLite file separate from Kalshi DuckDB. Forecast identity includes symbol/horizon/source capture, idempotent, append-only. Record source availability separately from the actual first import/forecast creation time; delayed imports cannot receive an earlier fill. Evaluation uses the first real shared stock/benchmark session whose 09:30 America/New_York opening time is strictly after forecast creation, entering at that open and exiting at the close of the Nth session including entry. Daily bar labels are midnight UTC, not market opening times. No entry using an open that preceded the forecast; no forecast can be scored until the full horizon completes. Persist input hash and original forecast score. Immutable forecasts with conflicting payloads must error.

The medium horizon virtual book has $100 cash, at most five concurrent $10 long positions, no leverage and no shorting. Select positive excess-momentum candidates deterministically, excluding benchmark. Orders are queued prospectively and fill at a later open; estimate 10 basis points adverse execution on entry and exit (paper assumption, not existing Kalshi fees). Prevent cash overdrafts, duplicate orders, reuse of committed cash, and additions after $10 marked loss from initial capital. Only information available before an open can cancel that open's queued fill; mark losses after the session. This is a pause threshold, not a guaranteed loss limit. The first release requires daily active-book refreshes and refuses catch-up across multiple new sessions rather than simulate a false path. Reject/halt on missing previously captured session coverage or history revisions that would invalidate stored share quantities or prices; record the reason. Historical price comparisons are price returns, not dividend-inclusive returns. No real account writes.

## Evidence and progression

Tests cover malformed/stale/future inputs, missing benchmark sessions, synthetic bars, repeat imports, timestamp ordering, no-lookahead entry, insufficient future sessions, cost arithmetic, and immutable ledger records. Probe actual provider payloads before implementation. After the first forward collection period, evaluate medium-horizon outcomes against SPY and compare models with/without dated news; long-horizon conclusions require matured long-horizon observations. Walk-forward calibration, broad-universe research, SEC financial-history ingestion and automated refresh are subsequent milestones, not claims made by this release.

## Delivery boundaries

Existing work is preserved in a managed worktree on codex/stock-paper-lab. Small independently reviewable commits; no push, release or main merge. All default tests, ruff and strict mypy must be run. Report pre-existing failures separately. First release completion means the tool runs and paper records are valid, not that a profitable strategy has been established.
