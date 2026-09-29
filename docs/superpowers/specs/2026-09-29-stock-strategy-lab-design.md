# Broader stock discovery and a strategy comparison lab

Status: concrete proposal for owner review; implementation has not started.

## User outcome

Use the forward observation period productively: discover stocks beyond the recent-earnings list, compare genuinely different selection rules and portfolio sizes, and make the evidence visible. The existing pilot, nine books and adaptive advisory journal continue unchanged. A working data pipeline is not a demonstrated profitable strategy.

## What inspection established

- The broad archive contains 501 capture files covering requests for 4,999 current-listing candidates plus SPY. The existing study accepted 4,447 stocks on a shared March 2–September 25, 2026 grid. These are current survivors, not historical index constituents or all global stocks.
- `historical_study.py` and `run_broad_stock_study.py` implement a fixed top-three momentum experiment. They do not compare portfolio breadth or other signal families. Keep this failed experiment reproducible.
- `broad_scan.py` validates dated directory/history captures. It is reusable for coverage reporting. The scheduled capture currently follows the earnings-calendar subset; it is not a daily all-market scanner.
- The six-stock 2010–2026 archive is a separate, narrow long-history stress sample. Do not combine its results with the broad short-history sample or call it diversified historical evidence.
- Reliable historical news, filing-vintage fundamentals, delisted-inclusive returns and options bid/ask chains are missing. Current snapshots cannot supply these retrospectively.

## Approaches considered

1. **Comparison engine first, then broader collection (recommended).** Uses existing prices immediately, answers whether selection breadth and different price rules matter, and exposes data gaps. Findings remain exploratory until later observations exist.
2. Scanner first. Improves daily discovery, but adds roughly 500 price calls per full sweep at the current ten-symbol provider limit before expanding our ability to evaluate selections. Useful second delivery, not a substitute for comparative tests.
3. Large external platform or options engine first. Could add capabilities, but requires new dependency/feed decisions and does not repair missing historical evidence. Defer integration; audit existing connector capabilities without purchases.

## Delivery 1: reproducible comparison engine and visible results

### Fixed experiment registry

Register rules and source hashes before evaluating their outputs. Five deliberately simple price-based hypotheses are the first comparison, not a claim that the published literature validates our settings:

| Family | Score and eligibility beyond common filters |
| --- | --- |
| Relative momentum | Stock L-session simple return minus SPY L-session return; positive only, descending. |
| Volatility-adjusted relative momentum | Relative L-session log return divided by stock sample daily log-return volatility over L sessions times square root of L; positive only, descending. Zero volatility is unavailable. |
| Reversal | Negative of the stock L-session return; require that stock return to be negative; descending. This tests rebound behavior and can lose in persistent declines. |
| Low volatility | Negative sample standard deviation of L daily stock log returns; rank descending, without a positive-momentum gate. |
| Closing-price breakout | Current close divided by the highest close in the preceding L sessions, excluding the current close, minus one; strictly positive only, descending. |

Cross each family with lookbacks **10, 20, 40, 60 sessions** and maximum selection sizes **1, 3, 5, 10, 20**: **100 selection configurations**. Evaluate fixed **5- and 20-session holding periods**: **200 strategy variants**. Apply **10, 25 and 50 basis points per side** as cost assumptions: **600 result rows**, not 600 independent experiments. These numbers count every attempted configuration, including failed, empty and losing ones.

All settings are hypotheses, not optimized values. A changed rule gets a new version. Keep deterministic symbol tie-breaking and a complete experiment manifest. Do not automatically choose or deploy the highest backtest return.

### Fair comparison and execution convention

- Reuse the verified dated stock catalogue; no S&P membership requirement. Keep the prior failed baseline separate and unchanged.
- At each decision, require price at least $5, trailing 20-session median dollar volume at least $20 million, and real positive-volume regular bars sufficient for that rule. Price and liquidity use only information through the decision close. These gates match existing research assumptions; their adequacy is not established.
- Use common decision dates beginning only after all configurations can have 60 return observations. Compare holding periods separately. Within a holding period, use nonoverlapping cohorts on the same dates. Report excluded and unavailable symbols per decision.
- Enter at the next observed verified regular session's open. Exit at the fixed horizon's close, counting the entry session as session one. Do not execute at the close used to generate a signal.
- Each cohort has K equal slots of a normalized budget. With fewer than K qualifying names, unused slots remain cash; do not silently concentrate the budget in fewer stocks. Fractional-stock exposure is an assumption. Report exposure so larger K is not credited merely for investing more cash.
- Report price gain separately from simulated entry and exit costs. Cost scenarios are sensitivity tests, not assertions of executable spreads. Zero spread and perfect fills are never the default.
- Historical results are cohort returns and normalized budget equivalents, not writes into $100 forward accounts. Portfolio sizes and hypothetical weights here do not modify any live paper ledger's caps.
- Cash, same-date SPY, and equal-weight eligible-universe cohorts are controls under the same dates/cost convention. Show SPY's different invested exposure. Missing outcomes are unavailable, never zero returns or dropped losing trades.

### Evidence boundary

The archived period has already been inspected. Every run on it is **exploratory**, including any retrospective chronological split. Preserve catalogue retrieval dates and actual price retrieval dates; historical simulated decision timestamps are explicitly simulation timestamps, not claimed collection times.

Current-listing bias, missing delisted names, omitted dividends, short history and hypothetical fills remain visible on every report. A complete-history sample also conditions on future availability; disclose that selection. Never label this dataset an untouched validation set.

Freeze a prospective validation manifest before its first future decision. Later completed-session captures can evaluate frozen selections with actual creation times and next-open entries. No historical cohort enters a forward ledger. A longer historical dataset can be added later as separately labelled research, with its own coverage audit.

The first release publishes all outcomes and the entire search count, without an automatic winner, annualized-return promise or precise significance claim. Short, overlapping and correlated samples do not justify a confidence number. Formal multiple-testing statistics require an adequate return matrix and a separately reviewed inference design.

### Interfaces and storage

- A pure registry returns immutable, typed configurations with method hashes.
- A feature/scoring function consumes validated bars and a simulated decision session and returns a documented DataFrame with `as_of`, symbol, score, eligibility and reasons. Preserve actual source retrieval timestamps separately.
- A pure cohort engine applies fixed allocation, next-open entry, horizons and costs. Emit selection, entry, exit and cost audit rows, alongside summary metrics.
- A command validates a manifest and public captures, executes on A8, and writes a new immutable research directory with configuration, source hashes, coverage, per-cohort returns and all result rows. No ledger writer is imported.
- A8 remains authoritative for durable research. Tests use temporary fixtures; local captures and mirrors are not a fallback account writer. Transfer public input artifacts with verified hashes, then mirror research outputs after digest checks.
- New files should be bounded modules under `src/kq/equities/strategy_lab/`, a dedicated CLI under `scripts/`, and a read-only dashboard panel. Do not broaden the old baseline's fixed behavior.

### Dashboard

Add obvious top-level navigation for **Paper accounts**, **Strategy comparisons**, **Scanner**, and **Data health** in staged UI work. Label the original pilot separately from the nine portfolios. Show existing accounts near the top rather than beneath research detail.

The strategy table shows family, lookback, breadth, hold, cost case, cohort count, exposure, mean/median net return, same-date SPY difference and worst cohort. Include all negative, empty and invalid runs. Do not call worst cohort loss an account maximum drawdown; an equity-path drawdown requires an actual defined path. Provide filters and downloadable rows. Explain each buy/sell rule in plain language. Historical research, forward research and paper-account balances never share an unlabeled profit total.

### Acceptance tests

1. Hand-calculated small fixtures verify all five scores, tie breaks, filters, zero volatility and K-slot cash behavior.
2. Changing future prices cannot change an earlier selection. Today's close cannot supply today's opening fill.
3. Missing held outcomes, synthetic bars, revisions and invalid OHLCV remain explicit; no fabricated fills or zero-loss substitutions.
4. Flat prices lose exactly modeled costs; rising and falling fixtures verify both sides and horizon counting.
5. Registry cardinality is 100 selections, 200 hold variants and 600 cost scenarios with unique protocol IDs; every attempted variant appears in the report.
6. Identical source/configuration hashes reproduce identical numerical results. A8 and local fixture execution agree. The failed original study reproduces unchanged.
7. Source modules, CLI and actual-data dashboard pass repository checks. Verify existing paper databases, strategy definitions and scheduler configuration remain untouched.
8. Publish the complete exploratory result set, exclusions and source hashes on the read-only dashboard. Success means reproducible comparisons, not a favorable profit number.

## Delivery 2: recurring broad discovery

Extend the existing scheduled workflow, not a second scheduler, after validating provider capacity. Refresh the dated stock catalogue and scan all supported candidates in explicit batches. Archive raw responses, request ranges, retrieval times and per-symbol errors. Resume interrupted collection through a manifest; never pass an incomplete snapshot as a full-universe success.

Score all eligible names using the frozen registry and display why each name matched. A catalogue is not proof of broker eligibility or global coverage. Retain symbols needed by existing accounts and research journals even when they leave today's scanner. Do not silently fill missing history or reinterpret same-session updates as fresh decisions.

Keep current earnings and limited official sources as labelled context. A scanner alert is a candidate for research, not an order. A8 receives verified capture artifacts; authenticated collection still depends on the Codex host and session until an independent feed is explicitly established.

## Delivery 3: fundamentals/news and options evidence

Audit public-data connector capabilities for filing-time financials, immutable news and historical option chains. Produce a coverage table: available fields, earliest dates, retrieval/vintage limitations and any cost/dependency requirement. No purchases or installations.

Add value, quality and earnings/news experiments only when decision-time inputs exist. Prospective capture may start before historical testing is possible. LLM-generated sentiment does not become a probability. Options remains a separate contract-aware study requiring observed bid/ask data, strike/expiry/multiplier, fees, liquidity and lifecycle outcomes; stock bars cannot stand in for option prices. Whole-contract affordability must be checked against any eventual $100 account protocol.

## Research basis and limits

- [AQR, Fact, Fiction and Momentum Investing](https://www.aqr.com/Insights/Research/Journal-Article/Fact-Fiction-and-Momentum-Investing), rechecked September 29, 2026: motivation for a price-strength hypothesis, not validation of these lookbacks, universe, allocations or exits.
- [Bailey et al., The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf), rechecked September 29, 2026: searching many configurations can select noise; retaining the whole search and future evidence is necessary. No PBO estimate is claimed for this short sample.
- Existing [institutional/data review](../../research/INSTITUTIONAL-STOCK-NEWS-OPTIONS-2026-09-28.md) and [adaptive-signal evidence review](../../research/ADAPTIVE-STOCK-SIGNALS-2026-09-29.md) record the options, historical-data and inference limitations. Reversal, breakout and low-volatility formulas above are explicit comparison hypotheses, not claimed replications of a cited paper.

## Implementation sequence after review

Use small reviewed branches: (1) registry/features and focused tests; (2) cohort engine and execution tests; (3) capture adapter/CLI, provenance and A8 exploratory run; (4) dashboard comparisons/account navigation; (5) resumable broad collection; (6) point-in-time and options capability report. Keep each implementation PR within the repository's size guidance. Run required checks and present measured results, including failures, before proposing any changes to the nine ongoing experiments.

Review decision requested: approve this staged scope, starting with the price-based comparison engine and dashboard, followed by broader recurring collection. No new capital, brokerage execution, existing method changes, paid data or dependencies are included.
