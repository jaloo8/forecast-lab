# Free stock-selection evidence — October 10, 2026

Actual computation using five freely downloaded Kenneth French research datasets, not another ETF test. The strongest of the four primary hypotheses was larger-company operating profitability: 13.27% gross compound annual growth during 2006–2025 versus 11.06% for the broad-market research benchmark. This is a promising research lead, not a validated executable stock picker or a forecast. No subscription was purchased.

## What was calculated

Before calculating outcomes, fixed 2006–2025, all three Big value-weight portfolios in four families (12 portfolios), plus market Mkt-RF + RF. Primary hypotheses: high prior 12–2 returns, high operating profitability, high book-to-market, and low prior-month returns. Other rank groups remain published controls. No parameter search, fitted blend, leverage or shorting. All 13 series have 240 monthly observations. Compute calendar returns by multiplication, CAGR across 20 complete years, four nonoverlapping five-year CAGRs, and drawdown from month-end wealth including starting capital. This month-end drawdown understates possible daily/intraday losses.

These are existing published portfolio returns, not a reconstruction of company holdings, orders or next-open fills. The current August 2026 CRSP vintage may contain revisions unavailable historically. Historical research universes avoid selecting only today's surviving tickers, but this download does not independently validate every delisting or original filing. Library construction changed to CIZ, including dividend reinvestment on ex-dates. Gross returns exclude our trading costs and taxes. [Official library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html).

| Primary hypothesis / benchmark | Gross CAGR | 2025 return | Worst year | Positive years | Years >=10% |
| --- | ---: | ---: | ---: | ---: | ---: |
| Broad US market | 11.06% | 17.54% | -36.66% | 17/20 | 14/20 |
| Larger, high operating profitability | 13.27% | 16.74% | -28.55% | 17/20 | 15/20 |
| Larger, high momentum | 10.64% | 9.53% | -36.36% | 16/20 | 12/20 |
| Larger, high book-to-market (value) | 9.67% | 32.85% | -38.24% | 14/20 | 12/20 |
| Larger, recent losers (reversal) | 7.97% | 6.02% | -47.05% | 15/20 | 11/20 |

All worst years above were 2008. The profitability portfolio also lost in 2018 and 2022; worst month-end drawdown was -40.28%. Its five-year CAGRs were 6.40%, 12.76%, 19.33%, 14.99%, versus market 3.14%, 12.09%, 16.41%, 13.05%. It beat the market in 14/20 calendar years and all four five-year blocks, gross. Among published controls, low book-to-market (growth) also earned 13.19% CAGR; profitability is not the only explanation to investigate. This is not a risk-adjusted alpha test or untouched holdout.

## Costs and the actual next stock rule

An assumed fixed 1% annual wealth drag reduces high-profitability CAGR to 12.14%; 2% reduces it to 11.01%, slightly below the gross market. The 1%-drag candidate no longer beats the gross market in the 2011–2015 block. These are sensitivity checks, NOT measured transaction costs: each monthly gross wealth multiplier is multiplied by (1-drag)^(1/12). Turnover, spreads, market impact, taxes and executable fills still require company-level testing. All 39 scenarios and 780 annual outcomes, including controls and failures, are retained in the linked CSVs.

The next candidate to reconstruct is precise: at each June end, select eligible US common stocks above the NYSE median market capitalization whose prior-year operating profitability exceeds the NYSE 70th percentile; weight by market capitalization, implement after the signal becomes available, and refresh the selection annually. Operating profitability here is (revenue - cost of goods sold - interest - SG&A) / positive book equity. The library permits some missing expense inputs under its documented eligibility rules; our eventual implementation must explicitly reconcile that choice and original filing availability. This differs from the previously proposed gross-profit/assets plus value blend. [Profitability construction](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/six_portfolios_me_op.html).

This supports investigating roughly annual selection/holding, with corporate-action handling, not a claim that profitable companies rise next week. This larger-company monthly reversal specification did not outperform the market; that does not reject every short-term strategy. Momentum uses months 2–12 and refreshes monthly; value refreshes in June using prior-year book equity and December market equity. [Momentum](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_6_port_form_sz_pr_12_2.html), [reversal](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_6_port_form_sz_pr_1_0.html), [value](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/six_portfolios.html), [market definition](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_factors.html).

## Paid data decision, with a specific purpose

The best currently verified price fit for combined price/fundamental research is Sharadar Direct Full History Bundle: $69/month or $499/year. Full History Prices alone is $39/month, but cannot test historical profitability; the $29 Bundle covers only five years. These are documented USD prices, not a purchase or guarantee of dataset fitness. [Official pricing](https://sharadar.com/subscribe).

Sharadar documents active/delisted prices from December 1997 and as-reported ARQ/ARY/ART fundamentals from 1998. Those address the precise missing inputs. Before relying on them, validate stable identity mapping, failed-company coverage, original filing availability, dividends, spinoffs and terminal delisting consideration. Its advertised fundamentals coverage is 99% survivorship-bias-free, not complete. No downloaded paid sample has been validated here. The bundle does not establish historical Reddit/Instagram/news timestamps, executable short borrowing, or intraday earnings-event history. [Prices](https://sharadar.com/docs/stocks), [fundamentals](https://sharadar.com/docs/fundamentals).

Personal-use terms exclude professional/commercial use. On termination, stop using the underlying data and delete it within 30 days; permitted nonreconstructive research outputs/models/backtests can remain. Thus one month is a research window, not permanent data ownership. Publication of vendor-data evaluations also requires permission under its terms. Keep any eventual licensed data outside Git; a future product needs an appropriate license. [Terms](https://sharadar.com/terms). Free evidence should narrow hypotheses before any purchase; no subscription can guarantee a profitable strategy or 10–20% every year.

## Reproduction and verification

- [Input URLs, retrieval time and SHA-256 hashes](FREE-STOCK-FACTOR-INPUTS-2026-10-10.json); raw files remain local under `data/free-factor-screen/2026-10-10/`.
- [All scenario metrics](FREE-STOCK-FACTOR-METRICS-2026-10-10.csv) and [all annual returns](FREE-STOCK-FACTOR-ANNUAL-2026-10-10.csv), decimal units.
- Offline runner: `python scripts/run_free_factor_screen.py --input data/free-factor-screen/2026-10-10 --output data/free-factor-screen/reproduction`. Input CSV hashes are verified before calculation.
- Nine new tests cover table selection, percentages, sentinels, nonfinite values, missing/duplicate months, compounding, initial loss, drag and partial-year rejection; 73 focused research tests and the full default suite passed (25 environment/data skips; integration excluded). Repository lint, formatting and strict source typing passed.
- Independent standard-library calculation confirmed the five primary/benchmark gross series from raw files without importing the runner. This verifies arithmetic, not investment effectiveness. Production execution and paper-ledger behavior are unchanged.
