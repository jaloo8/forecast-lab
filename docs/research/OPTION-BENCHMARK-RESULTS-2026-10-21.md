# Published option-strategy histories: actual analysis, October21,2026

**25 option-strategy indices were evaluated in150 registered scenarios:147 completed and3 refused for missing coverage.** The later common2014–2025 window has23 positive indices,3 at least10% CAGR and none at least25%, before additional cost drag. None earns10% in every complete calendar year. These are calculations on observed published hypothetical index histories, not newly reconstructed individual option trades, a Grok bot backtest, or funded $1,000 accounts.

The finite [registration](option-benchmark-registration-2026-10-21.json) was frozen before this new performance run, SHA256 `762d644219a365d22885507e499374e29134d0cc4075c08768e4a2f1d0359020`. Earlier four-index results and market history were already known. No rule or index was selected for inclusion after seeing these new results.

## What ran

All25 downloaded series, two windows, and0%/1%/2% additional annual cost drag. The first window uses complete years after each series' last gap over31 calendar days and excludes its leading partial year; the second uses2014–2025. Each year needs at least240 rows. CLL's full window fails because2013 contains231 observations; all three cost cases remain refused. No missing dates or values were filled.

Each series is normalized to1000 at its baseline close. That is an index comparison scale, not a claim that a retail account can purchase fractional SPX/RUT/NDX contracts, fund all collateral or obtain the index's modeled fills. Costs use `exp(-annual_drag * elapsed_calendar_days /365.2425)`; the stress is not an estimate of actual commissions, spreads, taxes, funding or tracking error. Annual growth uses actual elapsed calendar days. Drawdown uses observed daily closes and omits intraday extrema.

The separate Decimal checker re-read the original source CSVs and reconciled **2,095,872 level calculations and107,058 monthly fresh-start windows**, all annual results, costs, endpoints and three refusals. It does not independently reproduce Cboe's option-selection, pricing or historical index calculation. [Accounting receipt](evidence/2026-10-21-option-benchmarks/independent-accounting.json), [all147 completed results and three refusals](evidence/2026-10-21-option-benchmarks/summary.json).

## Every index, before additional annual drag

| Index | Full eligible years | Full CAGR | Full observed DD | 2014–2025 CAGR | 2014–2025 DD | Worst year2014–2025 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| BXM | 2003–2025 | 6.60% | -40.14% | 7.00% | -30.26% | -11.37% |
| BXMC | 1991–2025 | 9.61% | -42.40% | 8.40% | -30.85% | -10.97% |
| BXMD | 1987–2025 | 10.64% | -47.01% | 9.36% | -32.33% | -16.14% |
| BXMH | 1991–2025 | 9.96% | -47.77% | 10.36% | -32.03% | -14.69% |
| BXMW | 2013–2025 | 7.19% | -30.61% | 6.52% | -30.61% | -11.97% |
| BXY | 1989–2025 | 10.17% | -44.83% | 8.93% | -31.45% | -15.82% |
| PUT | 2008–2025 | 6.86% | -37.09% | 7.71% | -28.93% | -7.66% |
| PUTY | 1987–2025 | 6.82% | -40.57% | 6.20% | -27.32% | -2.51% |
| WPUT | 2007–2025 | 4.00% | -28.62% | 2.74% | -25.92% | -14.25% |
| CMBO | 1987–2025 | 9.33% | -42.67% | 7.79% | -30.87% | -13.81% |
| BFLY | 1987–2025 | 3.59% | -54.92% | -2.19% | -42.38% | -14.98% |
| CNDR | 1987–2025 | 5.31% | -19.82% | 0.51% | -19.47% | -6.11% |
| CLL | Refused:2013 sparse | — | — | 9.61% | -17.23% | -15.05% |
| CLLZ | 1987–2025 | 8.05% | -47.22% | 9.20% | -30.91% | -12.92% |
| PPUT | 1987–2025 | 8.15% | -41.96% | 10.43% | -22.14% | -19.81% |
| RXM | 1987–2025 | 7.97% | -30.91% | 8.87% | -26.51% | 0.30% |
| BXR | 2001–2025 | 5.36% | -51.40% | 5.19% | -40.14% | -12.62% |
| BXRC | 2005–2025 | 4.57% | -51.63% | 4.60% | -43.14% | -12.58% |
| BXRD | 2002–2025 | 7.08% | -55.77% | 6.16% | -42.69% | -18.84% |
| BXRH | 2007–2025 | 6.27% | -54.59% | 6.74% | -40.90% | -16.44% |
| PUTR | 2002–2025 | 7.69% | -46.15% | 5.38% | -40.10% | -9.95% |
| WPTR | 2012–2025 | -5.70% | -72.86% | -8.82% | -72.86% | -23.91% |
| CLLR | 2002–2025 | 6.39% | -54.10% | 6.40% | -39.19% | -16.03% |
| BXNH | 2006–2025 | 11.28% | -49.22% | 14.10% | -29.83% | -25.80% |
| BXNT | 1995–2025 | 8.38% | -56.58% | 9.14% | -25.34% | -18.71% |

The rows cover different full histories and related variants of common families; they are not25 independent discoveries. Full-history comparisons require their stated dates. Raw source histories include retrospective backfill before launch; those dates are in the [inventory and source table](OPTIONS-DATA-INVENTORY-2026-10-21.md). For example, BXNH launched June22,2015, BXMH September8,2020 and BXRH September28,2022. The 1980s histories are not decades of live operation.

| Window | Added annual drag | Completed | Positive CAGR | CAGR ≥10% | CAGR ≥25% | Every year≥10% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| dense_complete_years | 0% | 24 | 23 | 3 | 0 | 0 |
| dense_complete_years | 1% | 24 | 23 | 1 | 0 | 0 |
| dense_complete_years | 2% | 24 | 23 | 0 | 0 | 0 |
| common_2014_2025 | 0% | 25 | 23 | 3 | 0 | 0 |
| common_2014_2025 | 1% | 25 | 22 | 1 | 0 | 0 |
| common_2014_2025 | 2% | 25 | 22 | 1 | 0 | 0 |

BXNH, the Nasdaq100 half-covered-call benchmark, has14.10% CAGR in2014–2025, a29.83% observed decline and a25.80% losing calendar year. Its CAGR falls to12.96% with1% annual drag and11.84% with2%. Over2006–2025 it is11.28% before added drag,10.17% with1%, and9.07% with2%, with a49.22% observed decline before added drag. This is a retrospective candidate for feasibility research, not a selected live strategy. [Nasdaq methodology](https://cdn.cboe.com/api/global/us_indices/governance/Cboe_NASDAQ_BuyWrite_Indices_Methodology.pdf).

The preserved adjusted-close SPY reference has13.42% CAGR and33.72% observed decline on BXNH's exact2014–2025 dates. It is a broad-stock reference, not the matching Nasdaq underlying. A claim that BXNH beats a matched Nasdaq total-return benchmark has not been tested here. For other indices the exact date-intersection comparison, including any shorter available SPY history, is stored separately; no pre1997 SPY values were invented.

BFLY loses2.19% annualized in2014–2025; WPTR loses8.82%, with a72.86% observed decline. The latter is collateralized weekly Russell2000 put-writing, not a risk-free income strategy. RXM has no negative complete calendar years in this particular later window but still a26.51% observed decline and only0.30% in its weakest year before extra drag. The full RXM history includes losing years. [Butterfly](https://cdn.cboe.com/api/global/us_indices/governance/BFLY_Methodology.pdf), [put-write family](https://cdn.cboe.com/api/global/us_indices/governance/Cboe_PutWrite_Indices_Methodology.pdf), [risk reversal](https://cdn.cboe.com/api/global/us_indices/governance/RXM_Methodology.pdf).

## Short periods and large gains

For every completed scenario, a fresh normalized1000 starts on each month's first available observation and is measured after5,21 and63 observations. These are overlapping, dependent historical windows, not independent forecasts. Calendar-day elapsed time is retained in the private ledger. No short-window return was annualized.

Across the fixed107,058 cost/window/start combinations, **zero doubled and zero gained100-fold**. The largest was37.41% over63 observations in BXRH's longer history. The sample contained no50% endpoint loss over these fixed horizons, while the full paths still had substantial peak-to-trough losses. Starting only monthly can miss worse arbitrary starting dates; daily closing observations can miss intraday losses. No18-hour claim was tested with daily index data.

Premium selling exchanges some upside for premium and retains underlying/tail exposure; protective options incur recurring hedge costs; half-covered calls retain more of their equity exposure. These mechanical differences motivate comparing regimes, but they do not establish why a particular year's move happened or a forecasting edge. The registered source rules were not retuned after viewing results. [Covered-call methods](https://cdn.cboe.com/resources/indices/governance/Cboe_BuyWrite_Indices_Methodology.pdf), [half-covered methods](https://cdn.cboe.com/api/global/us_indices/governance/Cboe_Half_Buywrite_Indices_Methodology.pdf), [protective-put methods](https://cdn.cboe.com/resources/indices/governance/Cboe_SP_500_Put_Protection_Indices_Methodology.pdf).

## Reproduce and practical next step

The runner is `scripts/run_option_benchmarks.py`; pass the frozen registration hash, private `data/bot-research-20261021/options-indices-source` directory, the preserved parent SPY CSV and a new nonexistent output directory. Then run `scripts/check_option_benchmarks.py` on that output. Full inputs remain private; the source inventory contains their URLs/hashes. Current provider downloads may change, so hashes must match for this exact replay. The public evidence contains derived results and receipts only.

Nineteen artificial tests cover drawdown recovery, leap-year/weekend costs, annual losses, sparse histories, no-filled years, observation horizons, tail truncation, large-gain thresholds, invalid data, exact benchmark intersection and checker tampering. Independent code review then reran all19 and the complete Decimal checker. [Review receipt](evidence/2026-10-21-bot-sources/options-benchmark-independent-review.json). Initial test work exposed an artificial fixture that inadvertently triggered the registered dense-segment restart; the fixture was corrected to scattered missing days. Checker hardening also required cross-platform manifest path normalization. Neither changed the registered performance outputs.

The valuable next options step is to test an affordable actual instrument and whole-contract implementation, using a small preregistered quote acquisition after a current request quote. The existing six-call pilot cannot model these25 index strategies. No new paid data, model calls, quote simulation, broker action or paper bot was launched in this sub-study. Published index performance cannot establish the user's every-year profit target or social-media claims.
