# Options data inventory — October 21, 2026

The useful expansion is **25 official published option-strategy index histories**. These support historical index analysis; they do not provide a $1,000 tradeable portfolio or individual option fills. Existing locally recovered executable-quote evidence still covers only three known dates. No Databento requests, credits, subscription or broker action were used in this inventory.

## Existing original quotes checked locally

The documented private data root is `Documents/MarketData/databento` below the producing Windows user profile. Its `recovered-batches-20261019/recovery.json` points to eleven eligible deliveries. An offline pass verified all 44 delivered files against original vendor SHA256/size receipts and scanned every CSV for row count, symbols and time coverage: **6,032,360 rows total**. This does not restore the absent original streamed extension.

| Original input | Actual local coverage |
| --- | --- |
| OPRA CMBP-1 | Oct8/14/15,2026; 1,989,028 / 1,139,304 / 2,340,433 rows; two SPY calls per date, 5,468,765 total. Each file spans the requested regular session. |
| Dated pilot definitions | 13,160 / 13,168 / 13,168 rows on those same dates; both calls and puts exist in definitions, but put quotes were not delivered. |
| EQUS.MINI one-minute SPY | 460,609 bars on893 UTC dates, Mar28,2023–Oct16,2026. Underlying bars are not option prices. |
| Four2023 definition deliveries | 16,036 /31,590 /7,700 /8,164 rows covering Mar28–29, Apr3–6, Apr10, Apr13. No matching new option quote deliveries. |
| Legacy CBBO probe | Apr2,2013 opening envelope only:51,604 rows/2,716 instruments/19 minute labels; no closing envelope. Existing inspection records unresolved availability timestamps and undefined multiplier metadata. |

Quote columns include receive/event time, instrument ID, action/flags, bid/ask prices/sizes and mapped symbol. Definitions carry raw symbol, strike, expiry, option type, underlying and multiplier. The recovered six calls are two adjacent strikes, expiring the following day; there are no put quotes, full option surfaces, Greeks or cross-expiry quote coverage. The prior18-account execution study remains unchanged. Its delays/cost cases are configurations, not eighteen independent strategies. [Preserved protocol and results](OPTIONS-NEXT-STUDY-2026-10-20.md).

Alternate time exits can be preregistered on these six calls, but their availability was selected by the earlier opening-range strategy. Earlier arbitrary entries could leak that later selection. Repeating many variants on three viewed dates cannot establish annual performance. Naked shorts, wheels, condors, calendars and volatility-surface strategies are unsupported by these raw quotes. Retain unknown marks/positions rather than pricing them with invented theoretical values.

## Free official index expansion

The [official benchmark directory](https://www.cboe.com/us/indices/benchmark_indices/) identifies the selected equity-option families. All25 requests returned CSVs with two columns, `DATE` and ticker, increasing unique dates, ending October20,2026. The frozen study ends December31,2025. The source URL pattern is `https://cdn-api.cboe.com/api/global/us_indices/daily_prices/TICKER_History.csv`; exact URLs, bytes and SHA256 values are in the [source inventory](evidence/2026-10-21-option-benchmarks/inventory.json). SPXTR returned403 and remains unavailable.

| Index / approach | Download first date | Rows | Provider launch |
| --- | --- | ---: | --- |
| BXM — S&P500 monthly ATM covered call | 2002-03-22 | 6,182 | 2002-04 (day unspecified) |
| BXMC — S&P500 volatility-conditional full/half covered call | 1990-01-31 | 9,242 | 2015-08-03 |
| BXMD — S&P500 30-delta covered call | 1986-06-20 | 10,156 | 2015-08-03 |
| BXMH — S&P500 half covered call | 1990-01-31 | 9,244 | 2020-09-08 |
| BXMW — S&P500 four staggered covered-call sleeves | 2012-06-29 | 3,594 | 2015-08-03 |
| BXY — S&P500 2% OTM covered call | 1988-06-01 | 9,664 | 2006-03-20 |
| PUT — S&P500 collateralized monthly ATM put | 1991-03-04 | 4,988 | 2007-06-20 |
| PUTY — S&P500 collateralized 2% OTM put | 1986-06-30 | 10,152 | 2019-02-15 |
| WPUT — S&P500 collateralized weekly ATM put | 2006-01-31 | 5,210 | 2015-08-03 |
| CMBO — S&P500 covered call plus collateralized put | 1986-06-30 | 10,150 | 2015-08-03 |
| BFLY — S&P500 iron butterfly plus Treasury collateral | 1986-06-20 | 10,156 | 2015-08-03 |
| CNDR — S&P500 iron condor plus Treasury collateral | 1986-06-20 | 10,156 | 2015-08-03 |
| CLL — S&P500 95/110 collar | 2008-08-26 | 4,525 | 2008-09-04 |
| CLLZ — S&P500 put-spread collar | 1986-06-20 | 10,156 | 2015-08-03 |
| PPUT — S&P500 5% OTM put protection | 1986-06-30 | 10,150 | 2015-08-03 |
| RXM — S&P500 collateralized risk reversal | 1986-06-20 | 10,156 | 2015-12-30 |
| BXR — Russell2000 monthly ATM covered call | 2000-12-29 | 6,486 | 2004-06-18 |
| BXRC — Russell2000 conditional full/half covered call | 2004-01-30 | 5,713 | 2015-11-23 |
| BXRD — Russell2000 30-delta covered call | 2001-01-31 | 6,465 | 2015-11-23 |
| BXRH — Russell2000 half covered call | 2006-05-18 | 5,138 | 2022-09-28 |
| PUTR — Russell2000 monthly ATM put | 2001-01-31 | 6,465 | 2015-11-23 |
| WPTR — Russell2000 weekly ATM put | 2011-02-28 | 3,932 | 2015-11-23 |
| CLLR — Russell2000 put-spread collar | 2001-01-31 | 6,465 | 2016 (day/month unspecified) |
| BXNH — Nasdaq100 half covered call V2 | 2005-09-19 | 5,304 | 2015-06-22 |
| BXNT — Nasdaq100 covered call V2 | 1994-12-30 | 7,996 | 2015-06-22 |

A source first date is not proof of daily continuity. PUT has only seven isolated older rows before its dense2007 segment. CLL contains231 rows in2013 and eleven-calendar-day gaps in2008/2013. The preregistered density rule refuses CLL's full-history window rather than filling it. [All annual row counts and long gaps](evidence/2026-10-21-option-benchmarks/coverage-gaps.json).

Launch dates come from the methodology index-information tables, with exact links/hashes in [strategy metadata](evidence/2026-10-21-option-benchmarks/strategy-metadata.json). Earlier history is retrospective backfill. BXMH and BXRH launched only2020 and2022; historical1980s/1990s values must not be presented as live strategy track records. CLLR's source specifies only2016; BXM only April2002. No day was invented.

The PDFs define different collateral, roll, premium and reinvestment conventions. For example, BFLY/CNDR retain Treasury collateral based on ten times their spread payoff exposure; their normalized returns are not uncollateralized maximal-leverage condor profits. Current methodology is not proof that every historical revision was applied identically. [Condor methodology](https://cdn.cboe.com/api/global/us_indices/governance/CNDR_Methodology.pdf), [butterfly methodology](https://cdn.cboe.com/api/global/us_indices/governance/BFLY_Methodology.pdf).

Reading was selective: objectives and launch tables across14 substantive documents, selected construction sections, and theoretical/backfilled-history disclosures. The two initial Nasdaq URLs returned a one-page moved-document notice; the actual linked consolidated methodology was then fetched and read. Failed guessed legacy links are retained; later official search found their family documents. [Exact reading scope](evidence/2026-10-21-option-benchmarks/reading-scope.json).

## Next executable-options data experiment

If index research justifies a concrete candidate, preregister a small set of ordinary and stressed dates and exact strike/expiry rules, then price only the required definitions and selected-contract entry/exit/valuation windows using the existing Databento catalog. Require real quotes for every leg, causal timestamps, integer contracts, bid/ask crossing, commissions, reserves, settlement and exercise/assignment treatment. Expensive full-chain years are not the first purchase. This is a design recommendation, not a submitted job or cost quote. The existing $0.50 probe reservation does not cover arbitrary new requests, and its old billing observation is historical.

For this batch, the free published indices provide broader regime and short-window evidence without pretending to solve the missing $1,000 contract-feasibility model. [Actual completed analysis](OPTION-BENCHMARK-RESULTS-2026-10-21.md).
