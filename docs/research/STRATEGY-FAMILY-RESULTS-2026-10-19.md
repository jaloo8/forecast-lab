# Strategy-family results: October 19, 2026

**The completed batch found no strategy meeting the requested 10% minimum in every calendar year.** All **279 stock/ETF account paths** failed that test. The six recovered options accounts also lost money across their three sampled dates, but do not have enough coverage for an annual test. This is **285 newly executed account scenarios**, comprising 28 ETF policies under overlapping cost/window conventions plus six options sensitivities—not 285 algorithms or independent experiments. No live trading was activated.

**Direct evidence:** The stock run completed at **2026-10-19T22:46:42.893352+00:00**, with **279 complete, zero failed and zero blocked** cases. The full [results](evidence/2026-10-19-strategy-families/stock-results.json), [trial inventory](evidence/2026-10-19-strategy-families/stock-trial-index.json), [comparisons](evidence/2026-10-19-strategy-families/stock-comparisons.json), [selection](evidence/2026-10-19-strategy-families/stock-selection.json) and [manifest](evidence/2026-10-19-strategy-families/stock-run-manifest.json) preserve every case. Returns above 20% are retained and do not fail the screen; the failure condition is any complete year below 10%.

## What the test actually covered

The [frozen study](STRATEGY-FAMILY-STUDY-2026-10-19.md) registered five controls and 23 candidate policies before this batch ran. SPY, QQQ and nine US sector ETFs supply the fixed universe. The common signal history begins March 10, 1999; **5,031 observed sessions** from 2006–2025 support the account windows. Training is 2006–2013; later evaluation is 2014–2025; a separate full-period account covers 2006–2025. Each starts with fresh **$1,000**, without inheriting positions or wealth. The later/full paths overlap and are not independent replications.

The **252 fractional paths** use distribution-adjusted wealth units, with up to 98% initial/target risky allocation and zero-yield cash. Signals use completed observations and execute at the following observed opening proxy. Rebalancing solves for post-cost NAV; every traded dollar, entry and final liquidation incurs the registered cost. **10/25/50 basis points per side** mean 0.10%/0.25%/0.50% of traded notional; 25 bp is primary. The model excludes taxes and recurring service charges. Its lack of minimum ticket or order-size constraints matters particularly when accounts become tiny.

The **27 nominal SPY paths** separately use whole shares and raw SPY prices, subject to the verified zero-split history. Cash dividends accrue to locked receivables, count in NAV and never finance purchases. This deliberately conservative availability convention is not actual broker payment-date accounting. The broad fractional panel is not proof that a $1,000 broker account can execute every target.

## Training selection and descriptive leaders

The preregistered selector chose **T01, SPY above its ten-month moving average**, using only the primary-cost training results: greatest worst-year return, then CAGR, drawdown and policy ID. Its choice was saved at **2026-10-19T22:46:05.219770+00:00**, before evaluation/full simulations. Training CAGR was **8.99%**, worst year **−3.05%**, and five of eight years missed 10%. Even its training record failed the actual objective.

Fresh 2014–2025 T01 returned **6.85% CAGR**, ending at **$2,214.31**, with a **−22.11%** worst year, **−27.16%** event drawdown and **six of twelve years below 10%**. It had three losing years. The full-period and later-period T01 losses in 2022 are the same percentage; their first-year returns differ because the accounts start separately.

At primary cost, the highest descriptive CAGR was the **QQQ buy-and-hold control**, both full period (**15.30%**) and later period (**18.37%**). It nevertheless lost **41.07%** in its worst full-period year and had a **52.61%** event drawdown. The active growth leader was **M03**, the SPY/QQQ relative-momentum switch, at **13.62%/17.31% CAGR** across the two windows. These rankings use outcomes now visible; they are not newly selected, independently validated trading recommendations.

Among the 23 active policies, **B03 sector breakouts** had the least-bad full-period worst year (**−8.79%**) but only **0.92% CAGR**, missing 10% in **19 of 20 years**. **V04 low-volatility sectors** had the least-bad later-period worst year (**−3.89%**) but still missed 10% in **7 of 12 years**. The all-cash control has a 0% worst year and fails the growth requirement every year.

Primary 25-bp comparisons below include the selected rule, controls and descriptive leaders. Drawdowns include opening marks before/after costs and closing/terminal marks; they are not intraday maximum losses. Displayed values are rounded; all threshold tests and rankings use unrounded values.

| Policy | Fresh account window | CAGR | Worst year | Event drawdown | Years below 10% | Ending NAV |
|---|---|---|---|---|---|---|
| C02 SPY buy/hold | 2006–2025 | 10.76% | -36.19% | -54.56% | 6/20 | $7,714.64 |
| C02 SPY buy/hold | 2014–2025 | 13.26% | -18.05% | -33.39% | 3/12 | $4,457.62 |
| C03 QQQ buy/hold | 2006–2025 | 15.30% | -41.07% | -52.61% | 7/20 | $17,237.94 |
| C03 QQQ buy/hold | 2014–2025 | 18.37% | -32.44% | -36.54% | 4/12 | $7,564.94 |
| T01 SPY 10-month trend | 2006–2025 | 7.71% | -22.11% | -27.16% | 11/20 | $4,415.06 |
| T01 SPY 10-month trend | 2014–2025 | 6.85% | -22.11% | -27.16% | 6/12 | $2,214.31 |
| T02 QQQ 10-month trend | 2006–2025 | 11.48% | -20.41% | -28.57% | 10/20 | $8,794.49 |
| T02 QQQ 10-month trend | 2014–2025 | 14.29% | -8.46% | -28.05% | 5/12 | $4,969.49 |
| T05 QQQ 12-month gate | 2006–2025 | 13.41% | -21.06% | -28.05% | 8/20 | $12,399.39 |
| T05 QQQ 12-month gate | 2014–2025 | 15.81% | -21.06% | -28.05% | 4/12 | $5,817.85 |
| M03 SPY/QQQ relative momentum | 2006–2025 | 13.62% | -39.27% | -56.75% | 7/20 | $12,862.14 |
| M03 SPY/QQQ relative momentum | 2014–2025 | 17.31% | -20.98% | -29.30% | 4/12 | $6,793.27 |
| B03 Sector breakouts | 2006–2025 | 0.92% | -8.79% | -17.56% | 19/20 | $1,200.05 |
| B03 Sector breakouts | 2014–2025 | -0.55% | -8.79% | -17.56% | 12/12 | $936.21 |
| V04 Three lowest-volatility sectors | 2006–2025 | 8.26% | -23.08% | -42.44% | 10/20 | $4,895.05 |
| V04 Three lowest-volatility sectors | 2014–2025 | 8.02% | -3.89% | -29.25% | 7/12 | $2,523.65 |

## Costs and blends

At **each** cost, all **31 accounts per window** failed the annual minimum: 28 fractional policies plus three whole-SPY diagnostics, repeated over three windows. That is **0/93 passing accounts at 10 bp, 0/93 at 25 bp and 0/93 at 50 bp**. All 28 fractional policies' full/later CAGRs are retained below; training and complete annual vectors remain in the linked JSON.

| Policy | Full 10 bp | Full 25 bp | Full 50 bp | Later 10 bp | Later 25 bp | Later 50 bp |
|---|---|---|---|---|---|---|
| C01 Cash | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| C02 SPY buy/hold | 10.77% | 10.76% | 10.73% | 13.29% | 13.26% | 13.22% |
| C03 QQQ buy/hold | 15.32% | 15.30% | 15.27% | 18.40% | 18.37% | 18.32% |
| C04 Equal sectors | 10.00% | 9.93% | 9.83% | 11.28% | 11.21% | 11.08% |
| C05 50/50 SPY/QQQ | 12.95% | 12.92% | 12.86% | 15.73% | 15.68% | 15.61% |
| T01 SPY 10-month trend | 7.96% | 7.71% | 7.29% | 7.16% | 6.85% | 6.33% |
| T02 QQQ 10-month trend | 11.78% | 11.48% | 10.99% | 14.55% | 14.29% | 13.87% |
| T03 Sector 10-month trend | 7.43% | 7.12% | 6.59% | 6.80% | 6.46% | 5.89% |
| T04 SPY 12-month gate | 9.22% | 9.09% | 8.87% | 9.14% | 8.98% | 8.71% |
| T05 QQQ 12-month gate | 13.55% | 13.41% | 13.19% | 15.95% | 15.81% | 15.57% |
| T06 Sector 12-month gate | 7.12% | 6.91% | 6.57% | 6.07% | 5.82% | 5.39% |
| B01 SPY breakout | 4.13% | 3.26% | 1.83% | 3.25% | 2.32% | 0.79% |
| B02 QQQ breakout | 5.90% | 5.05% | 3.64% | 6.07% | 5.24% | 3.87% |
| B03 Sector breakouts | 1.79% | 0.92% | -0.52% | 0.34% | -0.55% | -2.02% |
| M01 Sector 12-minus-1 momentum | 8.64% | 7.78% | 6.36% | 10.63% | 9.80% | 8.43% |
| M02 Sector multi-horizon momentum | 8.35% | 7.20% | 5.31% | 9.91% | 8.74% | 6.84% |
| M03 SPY/QQQ relative momentum | 14.13% | 13.62% | 12.79% | 17.98% | 17.31% | 16.21% |
| M04 Gated sector momentum | 8.37% | 7.53% | 6.14% | 9.61% | 8.77% | 7.38% |
| V01 SPY volatility cap | 7.35% | 7.18% | 6.90% | 8.09% | 7.91% | 7.60% |
| V02 QQQ volatility cap | 8.54% | 8.39% | 8.13% | 9.60% | 9.42% | 9.13% |
| V03 Sector volatility cap | 6.87% | 6.70% | 6.42% | 6.89% | 6.70% | 6.40% |
| V04 Three lowest-volatility sectors | 8.86% | 8.26% | 7.28% | 8.78% | 8.02% | 6.77% |
| R01 Weekly sector reversal | 3.46% | -6.33% | -20.63% | 3.94% | -5.83% | -20.12% |
| R02 Monthly sector reversal | 5.85% | 3.40% | -0.56% | 8.97% | 6.37% | 2.17% |
| R03 Trend-gated weekly reversal | 0.80% | -6.93% | -18.52% | 1.07% | -7.06% | -19.18% |
| E01 Half T01/M01 | 8.47% | 7.91% | 6.98% | 9.03% | 8.46% | 7.50% |
| E02 Half M01/R02 | 7.46% | 5.90% | 3.34% | 10.04% | 8.40% | 5.74% |
| E03 Thirds T01/M01/V04 | 8.69% | 8.13% | 7.20% | 9.03% | 8.41% | 7.38% |

Weekly reversal is particularly cost-sensitive. Full-period **R01** declines from **3.46% CAGR at 10 bp** to **−6.33% at 25 bp** and **−20.63% at 50 bp**. The 50-bp fractional account ends at **$9.86**. **R03** ends at **$16.63** under that stress. Such dust-sized modeled trades are not evidence of executable broker orders; the losses are retained rather than repaired or omitted.

Blending did not produce an annual-target success. **E01 has one narrow positive exception against its best component:** full-period primary CAGR **7.910% versus 7.778%**, a **+0.132 percentage-point** difference. Its event drawdown was **−26.84%**, versus **−46.21%** for the higher-CAGR component M01, although its worst year **−15.65%** remained below the target. Every other full-period blend/cost comparison, and every later-period blend/cost comparison, trailed its best component. This preserves the actual exception instead of importing the conclusion of a different earlier combination study.

Values below are blend CAGR **minus its strongest component's CAGR**, in percentage points, at identical dates/costs. Positive means higher historical compound growth; it does not mean annual-target success.

| Blend | Full 10 bp | Full 25 bp | Full 50 bp | Later 10 bp | Later 25 bp | Later 50 bp |
|---|---|---|---|---|---|---|
| E01 | -0.164 | +0.132 | -0.310 | -1.601 | -1.348 | -0.933 |
| E02 | -1.176 | -1.882 | -3.024 | -0.597 | -1.399 | -2.695 |
| E03 | -0.171 | -0.139 | -0.089 | -1.604 | -1.395 | -1.052 |

## Which calendar years failed

These counts use the **continuous full 2006–2025 paths**, not a new account reset every January. Fractional columns count failures among all 28 policies, including five controls; the separate active column excludes those controls. The nominal column counts the three whole-SPY rules at primary cost. Counts across policies/costs share market history and must not be treated as independent probabilities.

| Year | Fractional fails /28, 10 bp | 25 bp | 50 bp | Active fails, 25 bp | Whole-SPY fails, 25 bp | Selected T01 full-path return, 25 bp |
|---|---|---|---|---|---|---|
| 2006 | 16 | 16 | 18 | 14/23 | 1/3 | 14.61% |
| 2007 | 16 | 19 | 19 | 16/23 | 3/3 | 5.05% |
| 2008 | 28 | 28 | 28 | 23/23 | 3/3 | -0.03% |
| 2009 | 4 | 5 | 8 | 4/23 | 0/3 | 21.14% |
| 2010 | 13 | 14 | 14 | 13/23 | 1/3 | -3.05% |
| 2011 | 27 | 27 | 27 | 22/23 | 3/3 | -2.04% |
| 2012 | 17 | 19 | 20 | 18/23 | 2/3 | 9.57% |
| 2013 | 4 | 6 | 6 | 5/23 | 1/3 | 31.58% |
| 2014 | 6 | 9 | 11 | 8/23 | 1/3 | 13.18% |
| 2015 | 28 | 28 | 28 | 23/23 | 3/3 | -6.95% |
| 2016 | 23 | 25 | 26 | 22/23 | 3/3 | 4.37% |
| 2017 | 1 | 4 | 4 | 3/23 | 0/3 | 21.23% |
| 2018 | 28 | 28 | 28 | 23/23 | 3/3 | -7.81% |
| 2019 | 6 | 7 | 9 | 6/23 | 2/3 | 5.14% |
| 2020 | 12 | 14 | 15 | 12/23 | 1/3 | 14.68% |
| 2021 | 3 | 5 | 6 | 4/23 | 1/3 | 28.10% |
| 2022 | 28 | 28 | 28 | 23/23 | 3/3 | -22.11% |
| 2023 | 12 | 13 | 16 | 12/23 | 2/3 | 8.81% |
| 2024 | 5 | 6 | 10 | 5/23 | 1/3 | 24.35% |
| 2025 | 14 | 16 | 18 | 15/23 | 2/3 | 10.60% |

**Every tested fractional policy missed 10% in 2008, 2015, 2018 and 2022 at every cost.** All three whole-SPY rules also failed in those years. Even combining the best-performing policy after seeing each year's result could not overcome these particular annual shortfalls within this registered menu; that observation does not justify such an unregistered selector.

## The $1,000 whole-share check

All 27 whole-SPY cases completed and failed the annual target. At primary cost, the fresh later-period T01 account earned **5.28% CAGR**, versus the fractional convention's **6.85%**. This reflects the combined effects of integer shares, cash left unused and locked dividends; it is not a clean estimate of any one effect. For example, the initial later-period SPY buy/hold account held five shares with **$77.80** cash remaining. Historical affordability is not present-day broker eligibility.

| Rule | Fresh account window | CAGR | Worst year | Event drawdown | Years below 10% | Terminal spendable cash | Locked dividends in NAV |
|---|---|---|---|---|---|---|---|
| C02 | 2006–2025 | 8.90% | -31.56% | -47.85% | 7/20 | $4,882.99 | $617.05 |
| C02 | 2014–2025 | 11.80% | -16.27% | -29.84% | 3/12 | $3,478.88 | $334.04 |
| T01 | 2006–2025 | 6.81% | -17.90% | -22.05% | 12/20 | $3,242.95 | $491.39 |
| T01 | 2014–2025 | 5.28% | -19.21% | -23.87% | 7/12 | $1,671.58 | $181.99 |
| B01 | 2006–2025 | 2.62% | -9.66% | -21.12% | 17/20 | $1,488.24 | $190.06 |
| B01 | 2014–2025 | 1.49% | -10.93% | -19.53% | 10/12 | $1,110.12 | $84.19 |

Terminal NAV equals the last two columns after costed liquidation. Locked dividends are still owned economic value, not a trading loss; they simply never become buying power in this sensitivity. This is not an assignment, settlement or brokerage reconciliation test.

## Six recovered options accounts

The separate [options protocol](RECOVERED-OPTIONS-PROTOCOL-2026-10-19.md) covers **October 8, 14 and 15, 2026** only. It reuses recovered vendor deliveries and substitutes EQUS.MINI underlying bars for the unavailable original Yahoo capture. It is a retrospective reconstruction, not a byte-identical reproduction or new holdout.

Each account starts at $1,000 and uses at most one $1-wide SPY call spread on each sampled date. Entry debit including entry commissions plus an exit-commission reserve is limited to the lesser of $100 and available cash. Baseline already crosses the observed bid/ask and adds **$0.65 commission per contract per side plus one cent adverse slippage per leg per side**. Labels “extra-1c” and “extra-2c” add to that baseline: total modeled adverse slippage is respectively two and three cents per leg per side, not one and two cents all-in.

| Scenario | Closed trades | Ending cash | Net cash P&L | Sample-period return | Annual return |
|---|---|---|---|---|---|
| strict-extra-0c | 3 | $983.20 | -$16.80 | -1.68% | Not measurable |
| strict-extra-1c | 3 | $971.20 | -$28.80 | -2.88% | Not measurable |
| strict-extra-2c | 3 | $959.20 | -$40.80 | -4.08% | Not measurable |
| publisher_flag_sensitivity-extra-0c | 3 | $983.20 | -$16.80 | -1.68% | Not measurable |
| publisher_flag_sensitivity-extra-1c | 3 | $971.20 | -$28.80 | -2.88% | Not measurable |
| publisher_flag_sensitivity-extra-2c | 3 | $959.20 | -$40.80 | -4.08% | Not measurable |

All cases ended flat, with no unresolved debit/reserve or cash deficit. Strict and publisher-flag sensitivity cases happen to agree on these dates; that agreement does not resolve the flag's meaning. The [published cash summary](evidence/2026-10-19-strategy-families/recovered-options-summary.json) and [independent Decimal cash check](evidence/2026-10-19-strategy-families/options-independent-cash-check.json) support these numbers. The check recomputed saved quote-evidence cashflows; it did not independently reparse raw quote selection. Separate-leg quotes do not prove an atomic executable spread. Missing interim/lifecycle marks prevent valid daily drawdown, assignment/exercise accounting, CAGR or annual-profit conclusions.

## Earlier experiments were retained

The [prior-target rescreen](evidence/2026-10-19-strategy-families/prior-target-rescreen.json) applied the annual minimum to existing saved results; it did **not** run 3,368 new algorithms. The [independent review](evidence/2026-10-19-strategy-families/prior-target-independent-review.json) checked **58,112 saved annual rows** across those **3,368 scenario records**. Of **3,218 records with at least ten complete years, zero passed**. This total includes overlapping costs/windows and 189 derived training prefixes.

| Earlier study | Scenario records | At least ten complete years | Long-window passes | Short-window passes |
|---|---|---|---|---|
| High-return | 980 | 980 | 0 | 0 |
| Timing | 2100 | 1950 | 0 | 54 |
| Combination | 288 | 288 | 0 | 0 |

The 54 short successes are preserved: **40 META records with one complete year** and **14 TSLA records with three complete years**. These surviving-stock examples do not establish reliable annual income. Existing synthetic-leverage, survivor-universe, accounting and cost limitations carry forward; this screen does not repair their underlying histories.

## Evidence strength and next decision

**Direct:** Both the registration and warm-up amendment hashes matched the run. A [pre-performance static review](evidence/2026-10-19-strategy-families/static-review-before-performance.json) read all new engine, runner and test lines and resolved timing/cost-mapping findings before execution. Artificial fixture tests exercise causality, fees and integer accounting; passing them is not performance evidence. This results review inspected summary metrics for every one of the 279 paths, checked all **3,720 annual-return/count/expense-gap records**, all 279 same-SPY comparisons, all 27 blend comparisons and the saved 23-candidate training ranking. These arithmetic checks use saved results and are distinct from reconstructing daily ledgers.

An [independent accounting checker](evidence/2026-10-19-strategy-families/stock-accounting-independent-review.json), importing no study engine, reconciled **all 279 paths, 935,766 daily rows, 49,881 ledger rows and 195,707 traded asset legs** against the frozen source CSVs. The largest absolute NAV residual was **$2.19 × 10⁻¹¹**. It checked prices, cash, units, costs, dividend entitlement/locks, calendar returns, drawdowns and selection. [Eight deliberate corruptions](evidence/2026-10-19-strategy-families/stock-accounting-checker-mutations.json) were rejected. Recorded target weights remain inputs to that checker: it does **not** independently reconstruct the policy formulas, breakout state or warm-up counts. Static mapping review and causality fixtures supply separate, narrower evidence for those parts.

**Limits:** The eleven surviving ETFs, current-vintage adjusted histories and known market periods are not a point-in-time all-stock universe or untouched holdout. Warm-up from 1999 does not mean the new accounts ran from 2000; the new study starts in 2006, while the earlier rescreen supplies the separate 2000-era context. The observed calendar was not independently audited against every historical exchange session. Opening proxies are not actual fills; event drawdowns omit within-session extremes. Multiple prior studies and these correlated trials preclude treating the best retrospective result as a statistically established discovery.

**Economic limit:** The stock runner made no external API calls and reports **$0 new API spend**; options recovery reports **$0 new data charges**. Those facts do not price future subscriptions, recurring LLM usage or the replacement value of credits. For selected T01's fresh later account, the additional year-end expense capacity while retaining 10% was zero in six years; in 2025 it was only **$11.95**. That is a year-specific calculation from that year's starting NAV, not a compound simulation with recurring expenses deducted. Its 2022 result was already **$610.11 below** the year's 10% target before such expenses.

**Inference / recommendation:** Treat the requirement as unproven and all registered candidates as rejected for a 10% annual floor. The growth leaders show a different, risky long-run-growth objective and would require an explicit objective change before being promoted. Do not retune these rules against the now-seen later results, increase leverage to force the target, or spend scarce credits on daily agent debate. Preserve this complete trial record; any materially new family needs a new registration, suitable data and a bounded budget. A fixed prospective paper observation can evaluate implementation behavior, but cannot promise future profits. No strategy migration or live order follows from this report.
