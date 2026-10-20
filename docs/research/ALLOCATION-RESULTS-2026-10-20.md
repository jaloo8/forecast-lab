# Executed allocation research: 108 additional accounts

The separately registered allocation study executed **12 policies: eight candidates and four controls**, across three cost assumptions and three fresh-capital windows. **All 108 accounts completed; zero achieved at least 10% in every calendar year.** This is a new historical simulation batch, separate from the previous 279-path stock study. Repeated controls, related insurance sleeves and cost/window variants are not independent discoveries.

The [machine registration](allocation-study-registration-2026-10-20.json) was saved at **2026-10-20T06:18:46.810626+00:00**, before new performance. Read the [protocol](ALLOCATION-STUDY-2026-10-20.md), [pre-performance review](evidence/2026-10-20-allocation/pre-performance-review.json), [all results](evidence/2026-10-20-allocation/results.json) and [independent accounting report](evidence/2026-10-20-allocation/independent-accounting.json). Prior failures remain preserved; this batch did not retune their thresholds.

## What was actually tested

The existing private six-ETF snapshot adds EFA international equities, IEF Treasuries, VNQ real estate, GLD gold and BIL Treasury bills alongside SPY. Its complete common history starts May 30, 2007; all rows after December 31, 2025 were excluded. Training accounts cover **2008–2015**, evaluation **2016–2025**, and continuous full accounts **2008–2025**, including the financial crisis. Each starts with **$1,000 cash**, targets at most 98% invested, uses the next observed opening proxy and pays modeled costs at **10/25/50 basis points per traded side**, including final liquidation. Twenty-five basis points is primary.

The candidates test covariance allocation, fixed/ratcheting portfolio-insurance exposure, and two online weighting rules. Minimum variance is a previous mechanism applied to a broader basket. The online wealth mixture's 126 virtual experts are gross signal components, not 126 separately funded backtests. Actual accounts pay costs. No borrowing, shorting, leverage or additional capital is used.

## Training choice and full results

The registered training selector chose **A02, Equal risk contribution**, by worst training year, then CAGR, drawdown and ID. Its choice was saved before evaluation/full accounts were computed. Fresh 2016–2025 performance was **6.24% CAGR**, **-13.59% worst year**, **-20.60% event drawdown**, ending at **$1,832.28**. It missed 10% in **5 of ten years**. This selection failed the user's annual target.

Primary-cost comparisons follow. Event drawdown includes opening marks before/after costs and closing/terminal marks; it does not observe intraday extremes. These columns compare identical dates within each window.

| Policy | Full CAGR | Full worst year | Full drawdown | Later CAGR | Later worst year | Later drawdown | Later years below 10% |
|---|---:|---:|---:|---:|---:|---:|---:|
| C01 Zero-yield cash | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 10/10 |
| C02 BIL buy and hold | 1.15% | -0.13% | -1.32% | 1.95% | -0.16% | -0.29% | 10/10 |
| C03 SPY buy and hold | 10.82% | -36.35% | -51.58% | 14.68% | -18.04% | -33.34% | 2/10 |
| C04 Monthly equal five assets | 7.29% | -19.69% | -38.10% | 8.98% | -14.55% | -22.83% | 3/10 |
| A01 Capped minimum variance | 5.86% | -13.24% | -19.49% | 6.15% | -13.24% | -19.49% | 5/10 |
| A02 Equal risk contribution | 5.90% | -13.59% | -20.60% | 6.24% | -13.59% | -20.60% | 5/10 |
| I01 CPPI SPY | 6.68% | -17.81% | -31.14% | 13.38% | -17.81% | -32.78% | 3/10 |
| I02 CPPI equal five | 5.17% | -14.65% | -22.88% | 7.70% | -14.65% | -22.88% | 5/10 |
| I03 Ratcheting floor SPY | 3.59% | -17.14% | -18.75% | 6.94% | -10.51% | -14.40% | 5/10 |
| I04 Ratcheting floor equal five | 3.22% | -10.85% | -16.29% | 5.07% | -8.16% | -11.35% | 8/10 |
| O01 Finite-grid wealth mixture | 6.45% | -15.10% | -29.42% | 8.28% | -12.71% | -19.96% | 3/10 |
| O02 Exponentiated gradient | 6.35% | -16.08% | -32.07% | 7.91% | -12.07% | -19.35% | 3/10 |

Among the eight candidates, **I01 CPPI-SPY** has the highest descriptive later CAGR, **13.38%**, but its worst year is **−17.81%**, and its full-period CAGR is only **6.68%**. It was not the training-selected rule. The continuous crisis-start account and fresh 2016 account have different funded cushion histories; do not splice the fresh-account results into a continuous path. All eight candidates' primary full/later CAGRs trail the same-date SPY control. Several reduce drawdown, which is a different outcome from meeting the annual minimum.

## Costs and every failed year

All 36 accounts at each cost fail the annual screen. Complete annual vectors, fees, dollar expense gaps, holdings-event counts and same-date SPY differences are in the linked JSON. The table below retains each candidate's CAGR at each cost; these are sensitivity cases, not different algorithms.

| Candidate | Full 10 bp | Full 25 bp | Full 50 bp | Later 10 bp | Later 25 bp | Later 50 bp |
|---|---:|---:|---:|---:|---:|---:|
| A01 | 6.00% | 5.86% | 5.61% | 6.32% | 6.15% | 5.88% |
| A02 | 6.00% | 5.90% | 5.72% | 6.37% | 6.24% | 6.04% |
| I01 | 7.82% | 6.68% | 3.59% | 13.62% | 13.38% | 12.82% |
| I02 | 5.99% | 5.17% | 3.31% | 8.20% | 7.70% | 6.66% |
| I03 | 4.41% | 3.59% | 2.20% | 7.66% | 6.94% | 5.74% |
| I04 | 3.81% | 3.22% | 2.23% | 5.56% | 5.07% | 4.25% |
| O01 | 6.50% | 6.45% | 6.36% | 8.35% | 8.28% | 8.18% |
| O02 | 6.41% | 6.35% | 6.24% | 7.98% | 7.91% | 7.79% |

Counts below show candidate accounts below 10% in each full-path calendar year. The same eight policies share market history; these counts are not independent probabilities.

| Year | Fails at 10 bp | Fails at 25 bp | Fails at 50 bp |
|---|---:|---:|---:|
| 2008 | 8/8 | 8/8 | 8/8 |
| 2009 | 6/8 | 6/8 | 6/8 |
| 2010 | 4/8 | 4/8 | 4/8 |
| 2011 | 8/8 | 8/8 | 8/8 |
| 2012 | 7/8 | 7/8 | 7/8 |
| 2013 | 6/8 | 8/8 | 8/8 |
| 2014 | 8/8 | 8/8 | 8/8 |
| 2015 | 8/8 | 8/8 | 8/8 |
| 2016 | 8/8 | 8/8 | 8/8 |
| 2017 | 1/8 | 1/8 | 4/8 |
| 2018 | 8/8 | 8/8 | 8/8 |
| 2019 | 0/8 | 0/8 | 0/8 |
| 2020 | 3/8 | 3/8 | 6/8 |
| 2021 | 3/8 | 3/8 | 3/8 |
| 2022 | 8/8 | 8/8 | 8/8 |
| 2023 | 1/8 | 1/8 | 2/8 |
| 2024 | 2/8 | 2/8 | 2/8 |
| 2025 | 1/8 | 1/8 | 1/8 |

Every candidate lost money in 2018 and 2022 at primary costs. The online allocation machinery and changing risk exposures did not avoid those shared losses. No historical annual-floor winner was found or promoted.

## Practical account limitations

The model uses fractional distribution-adjusted wealth units. It does not validate literal historical share quantities, broker fractional-order eligibility, dividend-payment dates, settlement, auction fills, taxes or recurring software fees. No minimum trade ticket is imposed in this research model; small modeled orders remain visible.

In the later primary I01 account, **2,076 of 2,993 traded legs were below $1**. For I04, **6,712 of 15,090 were below $1**, with a smallest traded leg of about **$0.000165**. Such figures are an implementation warning, not proof that these orders can be placed. The published result retains their full economic calculation rather than silently suppressing trades and changing the rule.

The 36 insurance paths show no recorded floor breach under the sampled marks. The floor is still only an input to the exposure rule: gaps, costs, BIL losses and unobserved intraday movement can breach it. No guaranteed capital protection or annual income follows. No two-session delay stress, cash-payment-date account, live broker execution or untouched holdout is claimed. Known historical data and extensive prior project trials limit any interpretation of the best retrospective result.

## Actual options data acquisition

The owner supplied an exact current credit balance and April 18, 2027 expiration. Two of the nine registered schema requests were acquired, vendor hashes verified, and all **51,604 quote rows plus 2,716 definitions** inspected. Actual recorded cost was **$0.01224264502525 in credits**. No cash purchase was authorized. The stock allocation run used **$0 new data/model API spending**.

The 2013 sample has legacy bad-receive-timestamp flags on every quote and undefined multipliers in the definitions. It also includes 4,373 zero-bid/size records and nine locked quotes. This is direct data-quality evidence, not options P&L or an annual backtest. [Complete sample inspection](evidence/2026-10-20-allocation/cbbo-sample-inspection.json).

Seven requests remain unacquired. The two serial vendor queues outlasted the existing quote-freshness window, stopping request index 2 before any reservation or submission; the original credit observation also aged. No observation timestamp was refreshed or backdated and no duplicate request was submitted. A durable authorization for an entire fixed plan needs a separate reviewed design; the earlier per-request reservation is not retroactively a plan reservation. This technical limitation did not stop the stock simulations, and no repeat balance request was sent in this turn.

## Evidence and continuation

The [validation receipt](evidence/2026-10-20-allocation/validation.json) distinguishes artificial software tests from historical simulations. The independent checker reconstructs cash, units, source prices, fees, annual returns and drawdown, and separately checks insurance targets, online weights, covariance conditions, selection and benchmark differences. Input/source/output hashes identify the exact run. All account CSVs and raw inputs remain private and travel in the owner's portable kit; aggregate results and code are backed up to the existing GitHub branch.

This completed batch rejects these registered candidates for the annual-floor objective. Continue with materially distinct, data-qualified hypotheses under a new registration; do not tune these parameters against the now-seen evaluation years. Suitable next research can use existing data without waiting for options billing. The options path requires resolved timestamp/contract-specification evidence and complete funded daily/lifecycle accounting before a multi-year performance claim. No strategy or broker migration follows from these results.
