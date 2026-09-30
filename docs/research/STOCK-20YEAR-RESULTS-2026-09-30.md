# First long-history stock comparison: results and limits

The first bounded study completed on A8 using genuine daily observations from **October 2, 2006 through September 28, 2026**. It tests 100 current catalogue candidates chosen by a deterministic hash before their histories were fetched. This is a survivor-selected exploratory study, not all stocks, a historical membership reconstruction, or an untouched validation dataset.

Seven fixed methods (momentum excluding the latest week, five-day reversal, low volatility and their four equal-rank combinations), three selection sizes (1/3/5) and three holding periods (21/63/105 sessions) create **63 rules**. Three transaction-cost assumptions make **189 comparison rows**. These are related comparisons, not independent discoveries or newly funded accounts.

## Results without hiding incomplete or losing variants

| Cost each side | Attempted rules | Complete rule histories | Positive average net cohort return | Positive average excess over cash-matched SPY |
|---|---:|---:|---:|---:|
| 10 basis points | 63 | 50 | 50 | 17 |
| 25 basis points | 63 | 50 | 45 | 17 |
| 50 basis points | 63 | 50 | 32 | 17 |

Thus 127/189 rows have positive average net returns and 51/189 have positive average benchmark excess. **Those 51 rows represent only 17 selection/hold rules repeated across cost scenarios**, not 51 distinct successful methods. Thirteen rules have an unavailable mature outcome, so their complete-history aggregates are withheld at every cost level. There are 22,704 completed, 39 unavailable and 189 pending cohort rows; cost/arm/size variants reuse market observations.

At the base cost, the 21/63/105-session groups have 18/17/15 complete rule histories, respectively, and 8/6/3 positive-excess rules. Holding periods have different durations and exposures; these counts are not a ranking of expected profitability per day.

**No comparison has positive mean matched-SPY excess in all four fixed time blocks** (2006–2012, 2013–2019, 2020–2025 and partial 2026). Cross-boundary outcomes remain in overall results but are excluded from individual-block aggregates. The partial 2026 block is short, particularly at 105-session holds. This is descriptive robustness evidence, not a significance test or proof that every method is unusable.

All seven methods remain visible. At 10bp, complete histories / positive-excess histories are: M 9/5; R 5/2; V 5/0; MR 9/4; MV 7/2; RV 6/2; MRV 9/2. Do not select M just because this already-inspected sample looks better. The blend has not demonstrated a general advantage over its components.

Each cohort resets to a hypothetical $100 budget, with $10 all-in per chosen stock and the rest in cash. Returns include both cost legs and next-open entry. These are **not twenty years of compounded $100 account equity**. Operational loss pauses, realized spreads, dividends, tax and economic delisting outcomes are not simulated. No annual growth rate, trading win rate or probability of success follows from the positive-mean counts.

## Source and validation evidence

- Raw collection: 22 requests, two nonoverlapping ten-year intervals, 100 catalogue candidates plus SPY. The preserved collection manifest SHA-256 is `30cab5855096bf441acfb0f86ce7c427461b4ca649894127d1054ed7a70d2f98`.
- 288,351 usable OHLCV rows; 101,208 excluded synthetic, zero-volume, nonregular or malformed observations. Seventeen malformed optional observations have individual symbol/date/error evidence; another 17 otherwise usable observations beyond the latest genuine SPY session are withheld. Real benchmark malformation remains fatal. No pre-listing history is invented.
- Actual decision eligibility ranged from nine to 33 stocks after history/price/liquidity gates. The 100-name catalogue does not imply 100 eligible choices on every date. Historical price/liquidity gates use split-adjusted prices as a proxy; original unadjusted dollar eligibility is not reconstructed.
- Initial HTB validation refusal is preserved. Optional invalid observations were made explicit missing data before any strategy outcomes were examined; trades requiring missing observations cannot silently disappear from the aggregates.
- A8 run: `20260930T064649477827Z-f1582b35`. Immutable report SHA-256: `75e70600ebcfaf3f2dfe81735fb9cc013685da68947f96e668808ae7237421a7`. [Report](../../data/equities/strategy-lab/long-history/runs/20260930T064649477827Z-f1582b35/report.json), [manifest](../../data/equities/strategy-lab/long-history/runs/20260930T064649477827Z-f1582b35/manifest.json), [source coverage](../../data/equities/strategy-lab/long-history/runs/20260930T064649477827Z-f1582b35/source.json).
- All 28 new tests passed locally and on A8. Independent review reproduced and fixed output-directory isolation and malformed-boolean benchmark validation. All 12 account/event/advisory SQLite hashes, the prior short-study/scanner pointers and scheduler audit were unchanged. Ten result/evidence files were mirrored after archive and individual SHA verification.

## Decision

No new paper account or method is promoted from this study. The bounded first pass is complete, but the search for a validated advantage is not. Next, validate candidate mechanisms on delisted-inclusive price/total-return data with original financial availability, preserve the full trial log, and freeze a shortlist before a genuinely future paper test. Do not expand or retune the grid solely until a desired number of winners appears. [Data-access audit](STOCK-20YEAR-DATA-2026-09-30.md), [method evidence](STOCK-METHOD-EVIDENCE-2026-09-30.md), [frozen first-study design](../superpowers/specs/2026-09-30-long-stock-research-design.md).
