# Long-history interpretation, 20 October 2026

The completed run found historical growth candidates and several ways to reduce measured market drawdown. It did not establish reliable annual income or a strategy ready for a $1,000 broker account. Of 200 related configurations, 87 passed the relative-stability screen, 94 earned at least 10% CAGR in both primary periods, and none earned at least 25% in both. The overlap between the first two groups is 25 configurations; their union contains 156. These groups overlap and cannot be counted as separate discoveries. None of the 3,672 account scenarios earned at least 10% in every calendar year.

This interpretation was written after performance. The rules were frozen in the [registration](long-history-registration-2026-10-20.json) at 15:47:05 UTC, with [clarifications](evidence/2026-10-20-long-history/pre-performance-clarifications.json) at 15:55:20 UTC. The run started at 16:01:17 UTC and finished at 16:08:28 UTC. Training choices were saved at 16:03:37 UTC before evaluation/full accounts. This order controls this experiment's selection process; it does not make familiar, revised historical data an untouched holdout.

The run comprises 200 candidate configurations in 20 mechanism families, four controls, three transaction costs, two information lags and three account windows: 3,672 successful accounts, with no scenario errors recorded. The exact primary-full monthly-return comparison found 198 machine-distinct candidate paths; CPPIFIXED_04, CPPIFIXED_05 and CPPIFIXED_10 shared a path. Distinct paths are not independent hypotheses. The summaries show 194 candidates with positive CAGR across all 12 full/later cost-and-lag cases and 199 positive in both primary periods.

All tables below use 25 basis points per risky-dollar side and information lag two months. A target for month t uses information through t-2, leaving one whole month between cutoff and the return month. Each training, later and full account begins with $1,000; training covers 1976–2010, later evaluation covers 2011–2025, and full covers 1976–2025. Residual cash earns the supplied RF return. Fees and final risky liquidation are included. The inputs are current-vintage monthly research portfolios, with 49 industries and a broad market proxy. This is not an options backtest, a 1976-start ETF record, or broker execution evidence.

| Policy and selection status | Training CAGR | Later CAGR | Full CAGR | Later drawdown | Full drawdown |
| --- | ---: | ---: | ---: | ---: | ---: |
| MOM_05: Training-selected growth leader | 17.06% | 11.34% | 15.32% | -29.80% | -59.51% |
| CPPIRATCHET_06: Training-selected stability leader | 6.76% | 3.82% | 5.87% | -4.35% | -9.28% |
| VOLMOM_07: Best later CAGR, identified retrospectively | 13.76% | 14.07% | 13.86% | -21.04% | -60.19% |
| CMKT: Market control | 11.50% | 13.67% | 12.19% | -24.73% | -50.18% |
| CRF: Cash-return control | 5.50% | 1.41% | 4.25% | 0.00% | 0.00% |

MOM_05 is the first growth candidate selected using training data: it ranks the preceding 12 months' compounded industry return and holds the best five equally, with 98% total risky allocation. Its later 11.34% CAGR is positive but below the matched market's 13.67%. Its full 15.32% CAGR incorporates stronger early decades. Its full drawdown was 59.51%, worse than the market's 50.18%; its later worst calendar year lost 11.94%. High historical compound growth and dependable yearly income are separate outcomes.

CPPIRATCHET_06 is the first stability candidate selected from training. It uses the account's own delayed, already-funded NAV and a floor equal to 80% of its previous closing peak, with multiplier one. The risky target is 0.98 times the nonnegative cushion divided by reference NAV. At a new high it allocates 19.6% to the market; below that high it allocates less. Its observed full-account risky allocation averaged 19.13% and ranged from 11.58% to 19.60%. Low exposure is a direct mechanism behind its smaller market sensitivity. The associated growth tradeoff is visible: 5.87% full CAGR and 3.82% later CAGR, with 9.28% and 4.35% drawdowns. A formula called a floor is not a guaranteed loss limit between monthly observations or in live trading.

The supplied cash-return environment matters to that comparison. CRF earned 4.25% CAGR over the full history and 1.41% later. In the continuous CPPIRATCHET_06 account, the saved monthly ledger attributes $8,238.93 to cash returns and $8,132.71 to risky returns, less $78.75 in fees, producing $16,292.89 net growth. These are additive ledger dollars on a changing account balance, not separable CAGR estimates or a causal comparison with an otherwise identical policy.

VOLMOM_07 had the best later primary CAGR among the 200 candidates, 14.07%, roughly 0.40 percentage points above the market. That is a descriptive winner identified after observing later results, not the frozen training-selected growth leader. It ranks 18-month compounded industry return divided by monthly volatility and holds the best five. Its full drawdown was 60.19%; its favorable later drawdown cannot be generalized to earlier conditions.

“Stable” here means positive growth and a strictly smaller drawdown than the matching market control in both full and later windows at every cost/lag combination: 12 comparisons. It does not mean low absolute risk. Among the 25 configurations that also passed the primary 10% growth screen, INVERSEDOWN_04 had the highest full CAGR, 12.47%, but still lost 49.26% peak to trough, versus 50.18% for the market. Across all 87 stability qualifiers, the worst primary-full drawdown was 49.98%. CMKT is the registered broad market research control, not SPY, and its initial 98% allocation drifts as buy-and-hold positions grow; its full average risky allocation was 99.39%.

The decade slices show where full-history averages conceal changes. These are net CAGR slices of each continuous full account, not newly funded decade simulations. A stateful floor therefore carries its actual prior peak into each slice; the final slice includes the account's terminal liquidation.

| Years | MOM_05 | CPPIRATCHET_06 | CMKT | VOLMOM_07 | CRF |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1976-1985 | 20.70% | 10.48% | 15.69% | 21.83% | 9.03% |
| 1986-1995 | 19.18% | 7.33% | 14.22% | 15.51% | 5.56% |
| 1996-2005 | 17.82% | 4.81% | 9.11% | 11.62% | 3.64% |
| 2006-2015 | 7.51% | 2.31% | 7.51% | 7.21% | 1.12% |
| 2016-2025 | 11.92% | 4.58% | 14.67% | 13.63% | 2.11% |

MOM_05 exceeded the market in the first three displayed decades, was nearly equal in 2006–2015, and lagged it in 2016–2025. That is evidence of an uneven relative result across periods, not evidence of a permanent momentum premium. The defensive account's cash-heavy structure accompanies much stronger early cash returns and weaker cash returns in 2006–2015. The table alone does not isolate the effect of interest rates from market returns, exposure changes, or path dependence.

The registered stress intervals expose different weaknesses. Every cell below is cumulative net return over the named interval in the full account. These are not maximum drawdowns and the intervals are not interchangeable lengths.

| Inclusive interval | MOM_05 | CPPIRATCHET_06 | CMKT | VOLMOM_07 | CRF |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1987-10 to 1987-10 | -29.34% | -3.95% | -22.41% | -25.43% | 0.60% |
| 2000-03 to 2002-10 | -0.73% | -0.17% | -37.04% | -30.19% | 10.54% |
| 2007-10 to 2009-03 | -47.19% | -7.60% | -44.56% | -51.36% | 2.57% |
| 2020-02 to 2020-04 | -8.34% | -1.54% | -9.36% | -10.10% | 0.24% |
| 2022-01 to 2022-12 | 9.53% | -2.60% | -19.90% | -6.18% | 1.41% |

MOM_05 was nearly flat in the 2000–2002 interval while the market lost 37.04%, and gained 9.53% during 2022 while the market lost 19.90%. But it lost 29.34% in October 1987 and 47.19% in the 2007–2009 interval. VOLMOM_07 lost 51.36% over that latter interval. Holding recent industry leaders with 98% exposure did not provide consistent crash protection. Those statements describe the registered portfolios and observed intervals. No historical headline model, recession announcement rule or causal news attribution was tested.

The four regime labels describe information available at each synthetic cutoff. “Up” means trailing 12-month market wealth exceeded trailing 12-month RF wealth; “high volatility” means trailing market volatility exceeded the expanding median available by that cutoff, starting with the supplied 1969 history. Regime labels are delayed state descriptions, not contemporaneous crash labels. The entries below are arithmetic mean monthly net returns, not annualized growth or contiguous-period returns.

| Lagged state | Months | MOM_05 | CPPIRATCHET_06 | CMKT | VOLMOM_07 | CRF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| down high vol | 95 | 1.49% | 0.47% | 1.46% | 1.46% | 0.27% |
| down low vol | 54 | 0.93% | 0.53% | 0.42% | 0.38% | 0.55% |
| up high vol | 181 | 1.94% | 0.57% | 1.45% | 1.66% | 0.37% |
| up low vol | 270 | 1.04% | 0.41% | 0.79% | 1.04% | 0.32% |

For example, 63 of the 95 months carrying the delayed “down, high volatility” label had positive market-control returns. Their average market monthly return was 1.46%. Recovery months can retain a label based on earlier weakness. Reading these labels as a perfect crisis detector would misrepresent the test. CPPIRATCHET_06 averaged 17.71% risky exposure in that state, versus 19.49% in “up, low volatility”; both momentum examples remained at 98%. Exposure and cash allocation explain the implemented response, but do not prove why economic events moved the underlying returns.

The multiplicity diagnostic provides no statistically significant evidence of superior mean monthly net return versus the market among these candidates. It used 180 later-period observations per candidate, centered each excess-return series, resampled shared calendar indices with a circular stationary bootstrap of mean block length six months, and compared observed means with the maximum across all 200 candidates in each of 2,000 resamples. The smallest familywise adjusted p-value was 0.994003 for SKIPMOM_03; even the smallest unadjusted p-value was 0.351324. VOLMOM_07's adjusted value was 0.997001. No candidate passes a 5% threshold under this registered diagnostic.

A p-value of 0.994 is not a 99.4% probability that a strategy will fail. This test concerns mean monthly excess return under its bootstrap assumptions; it does not test whether a portfolio can earn positive absolute returns, guarantee a drawdown ceiling, or satisfy an annual income target. It is not studentized, uses one registered block-length choice, and adjusts only this set of 200 configurations. It does not remove prior project search, revised data, imperfect execution assumptions or model risk. A visually attractive CAGR is insufficient evidence of an exploitable edge here.

The practical next research task is an implementation study of a small, frozen shortlist using actual tradable instruments and observable timestamps. Mapping French industries to ETFs or individual stocks changes the tested universe and must be registered as a new experiment. The 49 industry portfolios are research indexes whose internal constituent trading costs and timing are not simulated by these account fees. The broad market and RF series are also proxies. A $1,000 account cannot be assumed to replicate those holdings or earn RF frictionlessly; fractional eligibility, minimum tickets, actual cash yield, spread, turnover, settlement and taxes remain unproven. For scale, the later MOM_05 path made 1,162 risky trade legs, including 40 below $1, versus two risky legs for CMKT. These are synthetic risky-dollar changes, not broker orders or fills.

The recorded 10/25/50-basis-point costs and one-/two-month information lags are sensitivity cases, not a certificate of realistic executable costs or historical publication availability. Drawdown marks are monthly before/after-cost and month-end/terminal observations; losses inside a month are unknown. The [source review](evidence/2026-10-20-long-history/data-sources.json) documents the current-vintage/revision and instrument limitations. Existing known history and comparisons across this repository remain part of the research search, even though this run's own rules were frozen before its results.

Numerical provenance is recorded in the [interpretation review receipt](evidence/2026-10-20-long-history/interpretation-review.json). This report's checks re-derived all candidate classification flags from the 3,672 saved summaries, verified 15 primary account CSVs for the five displayed policies, and independently recomputed the five full-account decade, stress and regime diagnostics. They used a separate parser for the factor inputs and no simulation-engine imports. They did not rerun strategy performance, reconstruct every asset holding in all accounts, or rerun the bootstrap. The separate complete accounting audit is the authority for that broader reconciliation. Raw inputs and full account files remain in the private run snapshot; the public evidence preserves hashes and bounded derived results.
