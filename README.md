# forecast-lab

Personal research lab for testing stock signals over short and long horizons, with a separate Kalshi forecasting and paper-trading system.

**Current focus: equities research and paper trading. No reliable stock-picking edge has been established.** The owner approved the stock experiment in September 2026 and separate short/long direction studies in October. Real-money stock execution is not enabled; the existing Kalshi live gate remains unchanged.

## Start here

- [Research register](docs/research/RESEARCH-REGISTER.md): completed tests, preserved failures, finite new studies, data gaps and the distinction between policies and repeated scenarios. Start here for the century CAGR/relative-drawdown research and the separate every-year diagnostic.
- [Cross-computer handoff](HANDOFF.md) and [machine-readable state](PROJECT_STATE.json): October20 century/options results, paper preparation, private-data restoration and exact continuation steps. `main` is the authorized integration and next-machine handoff destination.
- [Century results](docs/research/CENTURY-RESULTS-2026-10-20.md): 4,896 accounts, 200 related configurations, exact-century cash warmup and fully active comparison; every result preserved.
- [Options execution study](docs/research/OPTIONS-NEXT-STUDY-2026-10-20.md): 18 funded scenarios on three dates, costs, unknown marks and limits; no annualization.
- [Paper preparation](docs/research/A8-PAPER-PREPARATION-2026-10-20.md): offline evidence/task coordinator and four disabled $1,000 lanes. [A8 connection attempt](docs/research/A8-READONLY-CHECK-2026-10-20.md) timed out.
- [Agent research workflow](docs/research/AGENT-RESEARCH-FLOOR-2026-10-19.md): original-source review, pinned trading-skills inspection, and a proposed bounded process pilot. No agent runtime or API spending is activated.
- [Roadmap](ROADMAP.md): current priorities, dated evidence and historical milestones.
- [Stock Paper Lab](docs/STOCK-PAPER-LAB.md): dashboard, authoritative A8 ledger, refresh procedure and dated operational observations.
- [Latest direction study](docs/research/STOCK-DIRECTION-RESULTS-2026-10-10.md): complete October 10 results, limitations and next steps.
- [Twenty-year portfolio comparison](docs/research/SECTOR-STRATEGY-RESULTS-2026-10-10.md): five sector/trend controls, annual returns and costs; none achieved 10% every year.
- [Free stock-selection evidence](docs/research/FREE-STOCK-FACTOR-SCREEN-2026-10-10.md): published profitability portfolios provide a lead for annual stock selection; 13.27% gross CAGR with three losing years, not a validated trading implementation.
- [Eight-company research pilot](docs/research/COMPANY-PILOT-WATCHLIST-2026-10-10.md): financials, moats, dated valuations, calculated price controls and separate forward-test rules; no mature forward returns yet.
- [Private Reel drafts](docs/research/COMPANY-PILOT-REELS-2026-10-10.md): three evidence-based scripts/storyboards and creator-tool feasibility; no videos rendered or published.
- [Technology education and bottleneck investing](docs/research/TECH-BOTTLENECK-CONTENT-2026-10-10.md): existing publishers, a proposed teaching approach, and the evidence needed to connect technical constraints to stock returns.
- [Operating playbook](CLAUDE.md): scope, development rules and safeguards.

The earlier stacked stock work, including PRs #199–#204, was integrated through [PR #214](https://github.com/jaloo8/forecast-lab/pull/214). The October 19 cleanup removed 120 redundant remote branch pointers after content review; their integrated code and history remain. Published code, merged code, deployed code and proven performance are separate milestones. The owner authorized consolidation of the reviewed research branch into main. No current A8 deployment is implied; see the handoff and integration receipts for actual publication state.

## What we are trying to learn

Can information available at a decision time help distinguish stocks likely to rise, fall or outperform a benchmark, after realistic costs? We compare two studies separately:

| Study | Current price controls | Outcome horizons |
| --- | --- | --- |
| Short term | 20-session relative momentum; 5-session relative reversal | 5 and 20 trading sessions |
| Long term | Prior 12-month relative momentum, excluding the latest month | 6, 12 and 18 calendar months |

Earnings, SEC filings, dated news, customer/supplier connections and public social posts are candidate enhancements. Reddit, YouTube, Instagram, forums and creator recommendations require permitted access, original timestamps and complete records of misses as well as wins. **These enhancements have not been validated.** We do not have a verified complete callsbyjmo recommendation history or a demonstrated 20-year social archive. LLMs can extract and organize evidence; their opinions are not calibrated probabilities.

The [registered protocol](docs/research/STOCK-DIRECTION-PROTOCOL-2026-10-10.md) defines rules before comparisons. The [data feasibility review](docs/research/EQUITY-SIGNAL-DATA-FEASIBILITY-2026-10-10.md) separates usable inputs from missing evidence.

## What the evidence says so far

The October 10 experiment replayed 2006–2025 decisions for eleven selected surviving stocks plus SPY, with next-session entries and three cost assumptions. All seven rule/horizon pairs had lower direction accuracy than an always-up diagnostic on the same completed observations. That diagnostic was computed after the run; it is not a newly validated strategy.

The archive's arithmetic was reproducible, but this does **not** establish forecasting skill. Current-vintage adjusted prices, selected survivors and overlapping observations limit the conclusions. Returns represent adjusted wealth, including distributions, rather than raw share-price direction. Bearish labels are research flags, not simulated short-sale profits. All [504 aggregate groups and the audit](docs/research/STOCK-DIRECTION-RESULTS-2026-10-10.md) are retained, including unfavorable outcomes.

A separate [100-stock long-history study](docs/research/STOCK-20YEAR-RESULTS-2026-09-30.md) also did not establish a robust winner across time blocks. Historical cohorts are not the forward paper account's performance. No strategy was promoted after either study.

The subsequent [free research-portfolio screen](docs/research/FREE-STOCK-FACTOR-SCREEN-2026-10-10.md) compared profitability, momentum, value and monthly reversal over 2006–2025. Larger high-profitability companies earned 13.27% gross CAGR versus 11.06% for the broad-market research benchmark. Reconstructing this annually refreshed rule using individual-company histories, original filing availability and actual turnover costs is a concrete next experiment. These published portfolio returns do not identify today's stock picks or establish short-term skill.

## Next research steps

1. Improve historical coverage: delisted names, historical universe membership, corporate actions and data availability at each decision time.
2. Add dated earnings/filing events first; retain the frozen price controls for comparison.
3. Test news, economic relationships and social events one at a time against the same controls, including collection delays and missing records.
4. Use time-ordered evaluation, separate tuning from held-out periods, account for dependent observations and multiple trials, and stress transaction costs.
5. Require reproducible improvement over simple benchmarks, followed by prospective paper evidence, before proposing a strategy change.

No historical result promises that we can identify the next stock that will surge. The goal is to measure whether any signal adds useful information and retain negative findings when it does not.

## Two separate operating paths

**Stocks:** the [Stock Paper Lab runbook](docs/STOCK-PAPER-LAB.md) is the operational entry point. A8 is the authoritative paper writer; local ledgers are read-only mirrors. Its dashboard is separate from Kalshi. Collection depends on the authenticated provider/app workflow; the runbook's observations are dated evidence, not a current health check. Offline direction studies do not import trades into the paper ledger.

**Kalshi:** weather and sports forecasting remain in the repository. Use the [Kalshi setup guide](docs/GETTING-STARTED.md), [machine setup](docs/SETUP.md) and [scheduled-run reference](docs/SCHEDULED-RUNS.md) for that path. The installers and `kq setup` configure Kalshi, not the stock data workflow. Recheck actual host/data health before asserting uptime. The ten Phase 5 criteria in [the playbook](CLAUDE.md#phase-5--real-money-decision-gate-day-38) apply to Kalshi; they do not authorize stock execution.

## Repository map

| Location | Purpose |
| --- | --- |
| `src/kq/equities/` | Stock data handling, research, paper ledger and dashboard |
| `scripts/run_directional_study.py` | Offline replay of the registered direction study from the local Tester archive |
| `src/kq/clients/`, `features/`, `models/` | Provider clients and Kalshi forecasting |
| `src/kq/execution/`, `backtest/`, `dashboard/` | Kalshi execution controls, evaluation and dashboard |
| `tests/` | Automated checks and fixtures |
| `docs/research/` | Dated protocols, source reviews, results and audit records |
| `data/` | Local captures and ledgers; not published research evidence by default |

Python 3.12, `uv`, DuckDB/SQLite, Streamlit, `ruff`, strict `mypy`, `pytest` and `hypothesis` underpin the existing tooling. Host-specific operating instructions belong in the relevant runbook. Do not install dependencies or initialize a second paper writer merely to read research results.

## Review and safeguards

Changes go through feature branches and pull requests. [Branch protection](docs/BRANCH-PROTECTION.md) records the actual GitHub setting and recommended checks. Local passing tests do not replace CI or human review. Keep raw archives, credentials, browser profiles and private ledgers out of commits.

Use public information with source URLs and availability timestamps. Follow the [compliance addendum](docs/COMPLIANCE-ADDENDUM.md) and [security policy](SECURITY.md). Neither a backtest nor this research pivot authorizes a real-money order. Commercial products and autonomous live trading remain outside the current work.

The older [Kalshi feasibility study](docs/research/PASS-1-FEASIBILITY.md) and [equities architecture notes](docs/research/PASS-2-EQUITIES-AGENT.md) are background, not current evidence of returns or vendor capabilities.

## License

All rights reserved. Source-available for personal reference only; no license to use, copy, modify, or redistribute.
