# Bot-rule backtests — October21,2026

Executed **7,290 primary funded-account simulations** and **337,590 fresh monthly-start accounts** from preserved data. These are 15 fixed rules (12 candidates, 3 controls) across 27 instruments—not that many independent algorithms. No external bot was run or claimed reproduced.

The 27 instruments are 11 ordinary ETFs, 11 preselected surviving stocks and 5 actual leveraged ETFs. Signals are completed before the 1/2-session execution lag. Accounts begin with $1,000 and trade fractional adjusted wealth units with 10/25/50 bps per side. Actual share granularity, dividend payable dates, cash settlement and broker fills remain unqualified. No synthetic leveraged history is used.

## Complete candidate inventory

Base means 10 bps per side with a one-session execution lag. Full and later refer to each instrument's actual available full history and fresh 2014-2025, respectively.
Of 324 rule/instrument candidates, **32** are positive in all 12 full/later cost/lag scenarios; **29** also have smaller drawdowns than passive ownership of the same instrument in every scenario. This is not a comparison against SPY and does not fill the earlier stock-market-stability quota. **22** reach 10% CAGR in both base windows and **5** reach 25%. Categories overlap. **0** meet 10% in every complete calendar year in both base windows.

Full available histories differ by IPO/inception and warmup; later is fresh 2014-2025. A matched passive control uses each candidate's exact dates. These are already-known, current-vintage histories with survivor selection; the later period is chronological evaluation, not an untouched holdout.
The five cases above 25% CAGR in both base windows are NVDA/B12 and TSLA/B01, B02, B05, B12. They concentrate in two famous surviving winners, so they do not establish a broad stock-selection edge or five independent sources of profit.

## Training-selected choices, fresh 2014-2025

Each asset's candidate is selected only by its 2000-2013 available-history CAGR at 10 bps and lag 1, with ascending-ID ties. Selection on very short pre-2014 histories is weak evidence. This is an explicit per-asset comparison, not a portfolio combining all rows.

**1/27** selected choices beat that asset's passive CAGR later. All 162 later cost/lag cases for these choices are preserved in [selected_later_stresses.csv](evidence/2026-10-21-bot-study/selected_later_stresses.csv). Source code, inputs and registration are frozen; there was no retuning after this result.

| Instrument | Training choice | Later CAGR | Drawdown | Worst full year | Passive CAGR |
|---|---|---:|---:|---:|---:|
|AAPL|B12|18.40%|-24.21%|-18.08%|25.63%|
|AMZN|B04|-2.72%|-46.24%|-39.51%|22.44%|
|CSCO|B07|0.92%|-15.91%|-6.94%|14.17%|
|GOOGL|B12|4.97%|-53.39%|-34.73%|22.19%|
|IBM|B01|9.85%|-33.16%|-17.88%|8.42%|
|INTC|B11|-1.26%|-35.18%|-8.92%|5.51%|
|META|B12|8.95%|-61.56%|-41.66%|22.91%|
|MSFT|B01|0.35%|-38.28%|-34.72%|25.52%|
|NVDA|B12|36.12%|-50.58%|-27.39%|67.47%|
|ORCL|B04|-2.63%|-51.42%|-27.88%|16.18%|
|QLD|B12|15.87%|-42.66%|-23.86%|29.76%|
|QQQ|B11|-1.00%|-20.27%|-5.90%|18.40%|
|SPY|B10|1.69%|-14.35%|-4.62%|13.30%|
|SSO|B10|3.90%|-26.31%|-9.05%|20.60%|
|TECL|B12|17.18%|-56.44%|-34.82%|39.88%|
|TQQQ|B12|22.25%|-58.09%|-35.71%|36.66%|
|TSLA|B12|31.59%|-63.12%|-30.98%|37.10%|
|UPRO|B10|5.81%|-37.32%|-13.78%|25.39%|
|XLB|B04|1.31%|-37.53%|-14.49%|7.85%|
|XLE|B11|0.58%|-10.35%|-4.93%|3.94%|
|XLF|B10|-0.31%|-20.10%|-8.71%|11.76%|
|XLI|B10|0.59%|-19.89%|-8.89%|11.39%|
|XLK|B05|2.54%|-22.43%|-12.71%|20.32%|
|XLP|B04|0.53%|-23.70%|-9.86%|7.78%|
|XLU|B12|3.28%|-16.42%|-9.39%|10.39%|
|XLV|B01|2.78%|-23.89%|-19.52%|10.59%|
|XLY|B10|1.09%|-14.14%|-3.95%|12.32%|

## Short-period outcomes

Fresh $1,000 starts at the first eligible session of each month, 10 bps/side, lag 1; final close liquidation includes selling cost. Zero-trade periods remain. These overlapping starts are not independent and do not cover every possible entry date or intraday extreme. Returns below are whole-account returns, not annualized.

| Evaluation window | Candidate accounts | Losing | No trades | Best | Worst | Doubled |100x|
|---|---:|---:|---:|---:|---:|---:|---:|
|5 sessions|90,240|12,062|66,403|34.42%|-40.87%|0|0|
|21 sessions|90,240|20,361|49,846|85.33%|-61.68%|0|0|
|63 sessions|89,592|29,238|29,359|152.68%|-61.68%|17|0|

The best 63-session candidate-rule case is TSLA/B01 (MACD), March 1-May 30, 2013: +152.68%. Passive TSLA on the same dates gained 195.27%. The candidate figure is a hindsight maximum among the 12 candidate rules, not a forecast or a selected prospective trade.
A five-session test cannot verify an 18-hour social-media claim. Best/worst rows are descriptive hindsight extrema; all starts and gain/loss frequencies remain in the private ledger and public summary. No routine income or future 100x claim follows.

## What the experiment establishes

The study measures deterministic price/volume rules inspired by inspectable bots. It does not test historical Grok conversations, today's search results as past news, options Greeks inferred from stock returns, or brokerage execution. Gap rules use completed daily adjusted gaps and differ materially from a live current-movers screener.

The independent checker reconstructs signals, cash, costs, annual returns and every fresh-start result without importing the simulator. Its receipt is the authority for checked counts. Unit tests use artificial fixtures and are separate evidence. Drawdown includes observed open/close and cost marks, but not intraday lows.

No new data fees, paid model calls or orders were incurred. No strategy is automatically promoted to paper or live trading. The practical next step is an actual-instrument/whole-share execution qualification of a frozen candidate and a prospective comparison against passive exposure, with a separate trustworthy-options-data plan.

## Sources and reproduction

- [Frozen rule/data registration](bot-study-registration-2026-10-21.json) and [preperformance clarifications](BOT-STUDY-PREPERFORMANCE-AMENDMENT-2026-10-21.md).
- [Primary-source bot catalog](BOT-SOURCE-CATALOG-2026-10-21.md), [price-data/design notes](BOT-STOCK-DESIGN-NOTES-2026-10-21.md), and [separate options-index results](OPTION-BENCHMARK-RESULTS-2026-10-21.md).
- [Every primary account](evidence/2026-10-21-bot-study/primary-summary.csv), [classifications](evidence/2026-10-21-bot-study/classification.csv), [short-period findings](evidence/2026-10-21-bot-study/findings.json), [training-selected later cases](evidence/2026-10-21-bot-study/selected_later.csv).
- Commands: `python scripts/run_bot_study.py --parent <QuantLab-root> --output <new-empty-path>`; `python scripts/check_bot_study.py --help` for independent replay. Source hashes and original-input hashes are saved in started.json. Private archives preserve full inputs/signals/ledgers; no credentials belong in them.
