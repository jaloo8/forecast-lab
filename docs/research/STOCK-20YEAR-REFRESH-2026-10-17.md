# Twenty-year price-method rerun — October 17, 2026

The fresh A8 run tested the same seven frozen price components/blends on the original 100-name sample, using genuine daily observations from **October 2, 2006 through October 16, 2026**. The first signal is December 27, 2006 and the first entry December 28, after the 60-session warm-up. This refresh is exploratory retrospective research, not a new untouched validation set or a replay of every current paper-account rule.

The prior September 30 study already existed. The conversational suggestion that no twenty-year study had been run was incomplete; that earlier result and all its failures remain preserved. This report is a new data collection and execution, not a relabelled old result.

## Result

Seven arms (momentum M, reversal R, low volatility V, and MR/MV/RV/MRV equal-rank blends), 1/3/5 selected stocks and 21/63/105-session holds create **63 rules**. Three cost assumptions create **189 result rows**, not 189 independent strategies.

| Estimated cost per side | Complete rules | Positive mean net return | Positive mean matched-SPY excess | Positive excess in all four time blocks |
|---|---:|---:|---:|---:|
| 0.10% | 50/63 | 50 | 15 | 0 |
| 0.25% | 50/63 | 45 | 15 | 0 |
| 0.50% | 50/63 | 32 | 15 | 0 |

Thirteen rules have missing mature outcomes, withholding their full-history averages at every cost level. There are **22,830 complete, 39 unavailable and 189 pending cohort rows**, with repeated dates/selections across arms, sizes and costs. No rule is promoted.

At base costs, complete / positive-excess rule counts by family are M 9/5, R 5/1, V 5/0, MR 9/4, MV 7/2, RV 6/1 and MRV 9/2. The positive-excess count fell from 17 to 15 as new outcomes matured. `RV_n1_h21_c10` and `R_n3_h63_c10` moved below zero average excess; no historical prices were revised or removed. This change is not a reason to retune them.

Every cohort resets to $100, invests $10 all-in per selected stock, holds the balance as zero-interest cash, enters at the next open and exits at the specified close. The benchmark uses identical dates, dollar exposure and costs. Returns are per cohort, **not compounded account returns or annual growth rates**. The four fixed time blocks remain 2006–2012, 2013–2019, 2020–2025 and partial 2026; cross-boundary outcomes are excluded only from block aggregates.

## Falling-market diagnostic

The interactive report can filter to intervals when SPY's **price** fell between the hypothetical entry and exit. This condition is identified afterward for diagnosis, not used as a knowable trading signal. Fee-only losses do not classify a flat/rising price interval as falling.

For the fixed three-stock / 21-session / 0.10%-per-side view, there are 82 completed falling-market cohorts for each arm. All seven methods have negative average returns in this slice. Momentum averages **−1.42%**, matched SPY **−1.19%**, low-volatility selection **−0.79%**, and the three-component blend **−0.97%**, measured on each reset $100 budget. Low volatility loses less here but has negative average matched-SPY excess overall at this setting. Its worst cohort is −4.80%; this is not sequential account drawdown. These descriptive comparisons do not establish a profitable market-regime switch.

## Data and independent validation

- Collected all 22 primary Robinhood responses again in two bounded date windows; preserved complete wrappers, exact requests, actual retrieval times and hashes. No quotes, session-statistics supplements or synthetic fills.
- Verified the original catalogue digest and reconstructed the deterministic 100-name selection. Preserving this original sample avoids changing constituents after inspecting returns; it does not remove its original current-survivor bias.
- **289,782 usable bars**, 1,431 more than before. Zero changed overlapping real OHLCV rows and zero missing previously accepted rows. Seventeen malformed optional observations remain explicit exclusions. All requested symbols are accounted for in both request windows.
- Actual eligible choices range from 9 to 37 stocks per signal, not 100 on every date. Missing/IPO history must satisfy the formation window before eligibility.
- All **28 focused tests passed locally and on A8**, including next-open timing, future-data perturbation, missing outcomes, source hashes and writer isolation.
- An independent A8 arithmetic check recomputed all 22,830 complete cohort returns and matched-SPY comparisons directly from opens/closes, checked every held session and entry/exit indices, and agreed within **2.10e-16** in normalized return. It does not call the engine's cohort-return function. This follows the accounting-audit approach reviewed in Tester.zip; it is not strategy validation by itself.
- Twelve account/event/advisory database hashes remained unchanged. No paper rule, order, cap, scheduler or brokerage setting changed.
- Eight primary result/audit files were mirrored after archive and per-file hash verification; the two comparison files were independently hash-verified. All 54 report filter combinations render seven method rows without missing/invalid numeric output in the script checks. This is functional report verification, not a browser screenshot claim.

## Evidence and limitations

A8 run: `20261017T203518142825Z-486524ff`. Report SHA-256: `a192c9463b3a265f3b631a030a19854dce6bce3a59f22e5652133fb31bd58db6`.

- [Interactive comparison](../../data/equities/strategy-lab/long-history/runs/20261017T203518142825Z-486524ff/comparison.html)
- [All comparison summaries](../../data/equities/strategy-lab/long-history/runs/20261017T203518142825Z-486524ff/comparison-summary.json)
- [Full immutable report](../../data/equities/strategy-lab/long-history/runs/20261017T203518142825Z-486524ff/report.json)
- [Collection audit](../../data/equities/twenty-year-refresh-20261017T203120171Z/collection-audit.json) and [independent server audit](../../data/equities/twenty-year-refresh-20261017T203120171Z/run-audit.json)

Current-survivor selection, missing dividends/economic delisting outcomes, split-adjusted eligibility proxies, an observed-SPY calendar, hypothetical fractional fills and already-inspected history remain material limits. This is not a twenty-year point-in-time earnings/news/options test: the required original-vintage datasets are unavailable. The original nine accounts' earnings conditioning and 5/20-session exits are not reproduced by these 21/63/105-session price-method cohorts.

[New primary-source research](STOCK-MULTISTRATEGY-EVIDENCE-2026-10-17.md) records a bounded proposed comparison of momentum, market trend and volatility exposure controls, with component controls and matched-cash benchmarks. A value/quality/momentum comparison is conditional on original filing availability and inclusive returns. These follow-on rules are specified but **not implemented, run or activated** by this refresh. The current results do not demonstrate reliable profitability; there is no winner quota or search-until-profitable stopping rule.
