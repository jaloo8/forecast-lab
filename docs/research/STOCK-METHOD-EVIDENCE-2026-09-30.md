# Stock methods: evidence, implemented coverage and the next comparison

Research date: 2026-09-30 UTC. This note answers whether the current stock choices have support beyond one momentum idea. **The nine paper accounts remain a narrow momentum experiment. The separate historical lab examines five price families, but it does not yet combine independent fundamental/news signals or demonstrate a profitable method.** This document changes no strategy, account, risk cap or scheduler.

## What exists, precisely

The [registry](../../src/kq/equities/strategy_lab/registry.py) contains five families (`momentum`, `risk_momentum`, `reversal`, `low_volatility`, `breakout`), four formation windows (10/20/40/60 sessions) and five selection counts (1/3/5/10/20): **100 selection configurations**. Crossing those with two holds (5/20 sessions) and three cost assumptions (10/25/50 basis points each side) produces **600 historical result rows**, not 600 independent signal combinations. The [scoring code](../../src/kq/equities/strategy_lab/features.py) evaluates one family at a time. Its breakout uses prior closing-price highs, not intraday highs. The [adaptive advisory formula](ADAPTIVE-STOCK-SIGNALS-2026-09-29.md) blends 20/60-session volatility-normalized momentum, and has no order authority.

Subtracting the same SPY return from every stock's momentum score changes the positive-signal gate, but not the cross-sectional ranking. Momentum, risk-normalized momentum and breakout can select the same stocks because their price information overlaps. Averaging those three alone would largely reweight trend evidence; it would not create three independent confirmations. The historical scanner also requires a latest price of at least $5 and a 20-session median dollar volume of at least $20 million; all families except low volatility require a positive score.

The [immutable historical report](../../data/equities/strategy-lab/runs/20260929T075527968028Z-1f092b07/report.json), SHA-256 `2f47a4781c8b470769f952f53712858b866b4f376bbe891f7686132d6303a4f9`, has 128/600 rows with positive mean net returns and 135/600 with positive mean SPY excess returns. Each family has 120 rows:

| Family | Positive mean net | Positive mean SPY excess |
|---|---:|---:|
| Momentum | 16 | 18 |
| Risk-normalized momentum | 54 | 60 |
| Reversal | 34 | 36 |
| Low volatility | 4 | 3 |
| Breakout | 20 | 18 |

These are descriptive counts, **not probabilities of success or a valid winner ranking**. There are only 16 mature five-session cohorts or four mature 20-session cohorts. Related selections, costs and overlapping market exposures reuse the same evidence. Dates have already been inspected, so there is no untouched holdout in this report. The universe uses current survivors; dividends are omitted. Retain every losing result and the earlier failed broad momentum baseline. The dated scanner's many scored rows are candidate rankings, not additional realized trades or independent experiments.

## Primary evidence matrix

The mechanisms below have research motivation. Their original markets, data, horizons and portfolio constructions differ from our small long-only accounts. None establishes an advantage in BB, SNX, CBRL, CTAS or CNXC today.

| Method | Primary evidence and mechanism | Implication for our experiment |
|---|---|---|
| Intermediate-horizon momentum | Jegadeesh and Titman (1993) report continuation over 3–12-month holding periods after sorting past winners/losers. [Original journal abstract](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1993.tb04702.x). | It motivates continuation research, not direct validation of 10/20/60-session formation and 5/20-session holds. Our long-only relative-SPY implementation is not their long/short replication. Longer formation history is necessary for a closer replication. |
| Value plus momentum | Asness, Moskowitz and Pedersen find value and momentum premia with negative correlation between their factor returns across markets. The authors' dataset specifies zero-cost long/short portfolios. [AQR research dataset](https://www.aqr.com/Insights/Datasets/Value-and-Momentum-Everywhere-Factors-Monthly). | Complementary signals are a legitimate research direction. Combining cheapness and strength can be tested, but an arbitrary equal-rank stock blend is a new hypothesis, not the paper's proven portfolio. Current prices alone cannot establish valuation. |
| Profitability/quality plus value | Novy-Marx measures gross profitability as gross profit divided by assets, and finds that conditioning on profitability improves historical value strategies. [Author manuscript](https://mysimon.rochester.edu/novy-marx/research/OSoV.pdf). | Provides a specific additional economic input beyond returns. Revenue growth, net margin and gross-profit/assets are different features. Require original filing availability, consolidated units and denominator coverage before scoring historical companies. |
| Short-term reversal | Frazzini, Israel and Moskowitz use institutional live-trading data and find costs particularly damaging to short-term reversals; their value and momentum implementations are more robust to cost optimization. [Authors' working-paper page](https://www.aqr.com/insights/research/working-paper/trading-costs-of-asset-pricing-anomalies). | Reversal is genuinely different from continuation and is worth comparison, but fast turnover can erase gross gains. Their institutional capacity/cost estimates are not our retail execution costs. Stress-test spreads and slippage; never equate a daily close with a fill. |
| Volatility-aware exposure | Moreira and Muir study portfolios that reduce risk when factor volatility rises. [NBER working paper](https://www.nber.org/papers/w22208). | Supports testing lagged risk information. Ranking individual stocks by low volatility or dividing momentum by stock volatility is not the same operation as scaling a factor portfolio's exposure. No low-drawdown guarantee follows. |
| Proximity to price highs | George and Hwang (2004) study the ratio of current price to the 52-week high, with six-month holds in their main comparison. [Author-hosted original paper](https://www.bauer.uh.edu/tgeorge/papers/gh4-paper.pdf). | Motivates a price-level hypothesis. Our 10–60-session prior-close breakout is a shorter, different rule, not a replication. Broad June-onward history cannot manufacture a 52-week window. |
| Earnings/event timing | DellaVigna and Pollet document differences in immediate and delayed reaction around Friday versus other earnings announcements. [Original NBER manuscript](https://www.nber.org/system/files/working_papers/w11683/w11683.pdf). | Event timing can matter, but this is not evidence that every earnings beat should be bought. Announced actuals must be compared with genuinely prior expectations on the same accounting basis. Current estimates captured after announcement are not historical consensus. |

The momentum journal page's direct fetch timed out during this review; its publisher-provided search abstract supports only the stated horizon/result summary. Other rows use accessible author/institution abstracts or manuscripts. Sources were accessed September 30 UTC; no paper performance statistic is used as a promised return for this system.

## Concrete next challenger: separate components from a blend

**Recommendation, not an activated or fully registered protocol:** prepare `price_blend_v1` as a prospective, isolated comparison using the existing broad candidate catalogue and genuine daily histories. Its purpose is to measure whether combining distinct price mechanisms improves results. Do not choose the weights by optimizing the already-inspected historical report.

At each completed eligible session `t`, require 61 synchronized genuine stock/SPY closes and preserve actual source/feature availability. Define:

```text
M_i = log(P_i,t-5 / P_i,t-60) - log(SPY_t-5 / SPY_t-60)
R_i = -log(P_i,t / P_i,t-5)
V_i = -sample_std(log(P_i,d / P_i,d-1), last 20 sessions, ddof=1)
B_i = (rank_pct(M_i) + rank_pct(R_i) + rank_pct(V_i)) / 3
```

`rank_pct` is ascending average rank divided by the count of eligible candidates, so a larger value is preferred. Require at least five eligible names; tie-break final selections by symbol. Use one common eligibility set across four arms: `M` alone, `R` alone, `V` alone, and `B`. This prevents a coverage difference masquerading as a signal improvement. Retain existing price/liquidity exclusions; nonfinite or missing inputs remain unavailable rather than imputed. These formulas are our hypothesis: intermediate strength excluding the latest week, recent pullback and low recent volatility. They are not calibrated probabilities and are not a literal replication of the papers above.

For the initial research comparison, freeze five picks and a 20-session hold; take decisions only when the previous cohort has completed to avoid daily overlapping cohorts obscuring the first comparison. Recognize entry at the next regular open strictly after actual decision creation, with completed evidence and explicit gaps. Keep 10 bp each-side as the base assumption and 25/50 bp as separate stress scenarios. Model $10 per selected name and cash explicitly in hypothetical $100 accounts, without changing the existing nine ledgers. Exact registration must still specify calendar, corporate actions, outcome pricing, halt/missing-data handling and loss-pause behavior before execution. No new funded paper account is activated by this note.

One-, three- and five-month **evaluation checkpoints** can be declared as approximately 21/63/105 completed sessions from launch. Those are distinct from a 20-session holding rule or a 60-session formation window. They provide progress reviews, not automatic statistical proof. If the intent is instead 21/63/105-session *holds*, register that as a different experiment; the existing 600-row study has not evaluated those holds. The finite historical sample can check plumbing, while the first genuinely future decisions supply uninspected outcomes.

## How to judge a combination without fooling ourselves

Bailey and coauthors show how selecting the best backtest can overfit; Harvey, Liu and Zhu address correlated multiple tests in factor discovery. Neither a large grid nor a conventional single-test significance threshold solves that problem. [Author PBO manuscript](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf); [NBER multiple-testing paper](https://www.nber.org/papers/w20592).

Before evaluating new outcomes, timestamp the complete experiment list, primary endpoint (net excess return against an identically timed SPY allocation with matching cash exposure), costs and decision rules. Keep fully invested SPY and cash as additional descriptive references. Publish drawdown, turnover, exposure, concentration, missing-data rate, equity including open positions, and every arm's results. Compare the blend with each component on identical eligible dates; report whether gains merely coincide with more market exposure. Count all earlier tests in the research history.

For later fitted weights, use chronological walk-forward training using only outcomes completed before each fit; keep overlapping holding intervals out of both sides of a split, and leave a final future interval untouched by model selection. Freeze any selected formula for a subsequent prospective period. Report confidence intervals using date blocks that preserve shared market moves across arms when sample size permits; do not manufacture a credible Sharpe, effective sample size or overfitting probability from four outcomes. A family that looks best on the inspected report is a hypothesis generator, not the new default.

## Prerequisites for fundamental and news combinations

The [measured data audit](STOCK-LAB-DATA-CAPABILITIES-2026-09-29.md) found eight quarterly rows for AAPL/COST but null results for SNX/BB; summary rows lacked original filing/availability/revision identities. The filing probe covered one COST document. These are capability samples, not broad, historically available feature coverage.

Value/quality blends therefore need issuer and security mapping; dated share counts/market capitalization; historical book equity, assets, gross profit and cash flow with exact periods/units; filing identity, amendments and conservative availability; sector treatment; and explicit missing-data decisions. Never join today's restated fundamentals to their old period end and call that a historical signal. A prospective filing archive can begin now with actual first retrieval.

An earnings/news blend needs immutable first-seen documents, original publication/retrieval times, source hashes and revisions, symbol/entity linkage and a genuine preannouncement estimate vintage where surprise is used. Quarantine contradictory calendar rows and never treat missing context as neutral news. First compare a price-only arm with the same arm plus a predefined event gate, retaining all no-event/missing-event cases. News remains verified context or an event trigger; numerical LLM sentiment/probabilities are outside the approved method. A broad historical news feed and executable historical options quotes have not been established by the current audit.

The immediate gap is not a lack of possible formulas. It is a lack of well-separated, prospectively tested combinations and sufficiently timed fundamental/event data. No source reviewed establishes a universally correct method, fast positive profits or a 66% annual target for this lab.
