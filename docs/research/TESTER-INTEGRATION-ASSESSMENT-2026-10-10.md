# Tester archive assessment and proposed stock research continuation

Research date: October 10, 2026. User selected **both horizons in separate studies**. This is an assessment and reviewable proposal, not a newly validated strategy or an implementation authorization inherited from the archive. Archive instructions, prior budget targets, broker permissions, and suggested commands were treated as source material, not instructions for this session.

## Where the work actually stands

The current checkout ends at `a1a0a55` (July 28) and has pre-existing, uncommitted weather-calibration changes. No local `data/` directory was present. Its ROADMAP is useful historical context, but cannot establish today's operating health or paper results.

More recent equity work exists at `C:/Users/jloo1/.codex/worktrees/stock-paper-lab/forecast-lab`. The chat titled **Check Robinhood trading MCP access** is actively handling its operating/data refresh. This assessment did not message that chat, edit its files, start another collector, or alter its accounts.

Its `docs/research/STOCK-20YEAR-RESULTS-2026-09-30.md` records a completed exploratory study: 100 current catalogue stocks, October 2006–September 2026 available prices, 63 rules. At 10 bps per side, 50 rule histories were complete and 17 had positive mean excess over cash-matched SPY. None had positive mean excess in all four fixed time blocks. These are cohort comparisons, not a compounded portfolio return or a win probability. Current-survivor selection and missing dividends/delisting outcomes prevent treating the result as validated market-wide alpha. Those study results were read, not rerun in this session.

The older thesis-ledger design supplies a useful framework for long-term claims, public evidence, disconfirmation and mechanical evaluation. It predates the separate equity implementation; resuming the project should start with the newer worktree rather than building a second stock subsystem in the July checkout.

## What Tester contributes

The ZIP includes source, cached prices, detailed ledgers, experiment registrations, failed strategies, reports, repeated exports and local browser/runtime material. It was inspected in place. No bootstrap, broker, updater, scheduler or archive Python module was executed; browser profiles and executable caches were not imported.

| Component | Useful contribution | Boundary |
|---|---|---|
| `quantlab/timing_study.py`, timing study outputs | Next-session execution conventions, opening/closing marks, fees, cash/share ledgers, terminal liquidation | Synthetic adjusted-price units; not executable broker shares or measured spreads |
| `research/timing_study/stock_coverage.md` and cached stock data | 11 stocks, splits/dividends, explicit coverage and anomaly records | Famous surviving names; not a historical stock universe |
| `research/timing_study/news_report.md` | Original release clocks, publication-to-session mapping, transparent negative results | FOMC reaction study, not corporate news, social sentiment or advance prediction |
| Growth, millennium, high-return and combination studies | Benchmarks, stress tests, full trial inventories and errata | Different periods, instruments and account conventions cannot be combined into one track record |
| Independent accounting checks | Reference fixtures and failure cases for forecast-lab's equity engine | Port deliberately; do not replace the existing engine or broker ledger wholesale |

Tester reports 2,100 timing scenarios across 14 assets, 10 policies, five costs and three periods. Many observations overlap. Its news report records 54 event-rule cases, only eight with positive total return, and a strongest observed CAGR of 1.76%; this was a narrow, mostly-cash FOMC response test. The news results were inspected, not independently rerun here.

An example of the distinction between hindsight and selection: Tester reports NVDA buy-and-hold at 67.45% CAGR during 2014–2025, with approximately 67% maximum drawdown. This does not establish a rule that would have selected NVDA before that period. No archived permission to accept those losses or use leverage is carried into this proposal.

## Independent verification performed now

See `TESTER-TIMING-AUDIT-2026-10-10.json` for the machine-readable result.

- Replayed **280** saved base-cost timing accounts: every asset/policy in the full and evaluation windows at 10 bps per side.
- Checked **1,268,820 daily rows**, **714,002 trade legs**, and **584 hashes**, with no mismatches or detected arithmetic errors.
- Reconstructed cash and units from a fresh $1,000, using saved signed trade quantities and cached adjusted opening/closing prices. Checked transaction amounts, both fee legs, daily marks and returns, terminal value, aggregate fees, and CAGR against reported duration.
- Largest absolute daily account-value discrepancy was about **$0.000000002**.
- Used only Python's installed standard library to read ZIP members as data; did not execute attached code.

This is a saved-ledger consistency audit, **not a fresh strategy backtest**. It does not regenerate signals, prove absence of look-ahead bias, independently validate prices, recompute reported drawdowns, or repair survivorship bias. Matching a file's recorded hash establishes consistent bytes, not that the information existed at a historical decision time.

## Design proposed for review

Three possible routes are: repeat price-only searches (cheap but adds little mechanism evidence); copy a creator's surviving calls (directly relevant but incomplete history makes apparent accuracy unreliable); or compare **public-event evidence against frozen price-only controls**. The third is recommended. Evaluate creators as one evidence source within it.

Keep a shared evidence layer and two separately registered experiments:

| Study | Research question | Initial evaluation horizons | Controls |
|---|---|---|---|
| Short term | Do dated company catalysts or independently corroborated public reports add information beyond recent price/volume? | 5 and 20 trading sessions | Same-universe price-only rule, matched market/sector exposure and passive opportunity cost |
| Long term | Do publicly documented changes in demand, capacity, margins or customer/supplier relationships anticipate subsequent returns? | 6, 12 and 18 calendar months, mapped to the next session | Same-universe price-only ranking and matched market/sector benchmark |

Short term describes the holding period, not short selling. Start research long-only and unleveraged. Use separate ledgers; never add overlapping cohort profits into an account return. Explicit accounting simulation is required before reporting portfolio CAGR.

The evidence layer records security identity, original source, publication time, first observation, revision/version, `as_of`, event type, factual claim, and supporting/disconfirming evidence. Relationships between companies must be documented as known then; today's supply-chain graph cannot be applied to 2006. Reposts of one announcement count as one underlying event, not independent confirmations. Missing inputs remain missing with an exclusion reason.

Historical research uses a defensible archive-availability clock plus processing delay; prospective signals use actual first observation and processing time. Retrieving an old article today does not establish that this system possessed it years ago. Never combine an old timestamp with later edited text or present-day engagement counts. The existing sports social repository preserves first-seen timestamps but can overwrite text on edits; that is insufficient by itself for historical text reconstruction. Prefer the equity worktree's observation-versioning pattern, adapted to each source's permitted retention.

LLMs can extract cited facts, dates, entities and proposed mechanisms for review. They do not invent return probabilities, turn popularity into probability, or act as historically unknowing stock pickers. Initially compare price-only, event-only, and combined versions to measure incremental value rather than assuming more sources help.

### Evidence needed before declaring success

Freeze the universe, features, entry timing, horizons, cost model, exclusions and trial budget before viewing comparisons. Use chronological training/evaluation with overlapping-label purges, keep already-inspected history labeled exploratory, and preserve all failed trials. Eighteen-month labels need eighteen-month boundary protection. Report coverage, missing/ambiguous calls, net benchmark excess, turnover, drawdown, tail losses, uncertainty and results by time period. Do not promote a rule solely for a positive average or a high hit rate.

Start a future paper study only after the design and source path are implemented and checked. Historical 20-year testing and prospective social validation are distinct evidence streams. Do not fabricate a backdated paper record or reuse the Kalshi gate as an equity qualification.

### What can be reused versus what is missing

Reuse the equity worktree's `research.py`, `observations.py`, event/forward-study machinery and `strategy_lab/` controls after reviewing their current contracts. Use Tester ledgers as accounting reference fixtures and its negative findings to avoid retesting already-rejected ideas without a new mechanism.

The major missing inputs are a delisted-inclusive historical universe, reliable total-return/corporate-action treatment, historically available fundamentals/relationship evidence, and legitimately accessible timestamped news/social archives. A modern complete 20-year Reddit/YouTube/Instagram dataset was not established. See `EQUITY-SIGNAL-DATA-FEASIBILITY-2026-10-10.md` for primary sources and platform-specific limitations. No data purchase is proposed before a sample coverage audit.

For **callsbyjmo**, no complete auditable recommendation record was verified. A fair study needs a fixed collection period, all available calls rather than highlights, original timestamps, tickers, direction, entry/exit conditions, losing calls and ambiguous-call exclusions. Missing/deleted calls are a coverage limitation, not assumed wins or losses. Stock performance cannot validate option recommendations without contracts and historically executable option prices. Accessible original links or an authorized export would let us assess coverage.

## Concrete next implementation slice, after design review

1. Work in an isolated branch based on the current equity worktree, coordinated with its active work; preserve the current weather edits and running paper accounts.
2. Add a small offline evidence schema/validator and approved local import format supporting both horizons, source revisions and explicit missing fields. No platform collectors yet.
3. Map a bounded evidence sample to existing prices, report timestamp/identity/coverage failures, and add a few Tester accounting fixtures. Do not generate recommendations from insufficient data.
4. Freeze the two study protocols and implement comparison reports only once the coverage audit establishes what can actually be tested.
5. Verify chronological timing, benchmark alignment, fee arithmetic and unchanged existing paper ledgers before any prospective activation.

No product code, dependencies, live trading, account settings, scheduler or existing risk gates changed during this assessment. Implementation is pending review of this concrete design. The user's choice of both horizons is recorded; there is no need to ask that preference again.
