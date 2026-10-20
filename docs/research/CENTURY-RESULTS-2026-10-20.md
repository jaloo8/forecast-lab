# Century stock research: complete registered results

**4,896 funded accounts completed and independently reconciled:** 200 configurations in 20 related families, four controls, four date windows, three cost levels and two information lags. These are 4,896 scenarios, not 4,896 algorithms or 200 independent discoveries.

Additional data charges: **$0**. Simulation runtime: 18.86 minutes; acquisition, review and independent checking are separate. All accounts begin with fresh $1,000 cash. No paid model calls or broker orders occurred.

Read the [registered design](CENTURY-DESIGN-2026-10-20.md), [frozen 200 rules](century-registration-2026-10-20.json), [pre-performance amendment](evidence/2026-10-20-century/pre-performance-amendment.json), [every account and annual vector](evidence/2026-10-20-century/results.jsonl), and [independent audit](evidence/2026-10-20-century/independent-accounting.json).

## What 100 years means here

The century account spans **July 1926 through June 2026: 1,200 complete months, exactly 100 years**. The candidates hold RF cash for the first 78 months, then activate January 1933, giving 93.5 years with strategy eligibility. Controls invest from the first month. This warmup mechanically bypasses much of the 1929 crash; it is not demonstrated crash forecasting or protection. No missing early return was invented.

The fully active primary comparison is 1933–2025 (93 years/1,116 months), with training 1933–1975 (43 years/516 months) and fresh evaluation 1976–2025 (50 years/600 months). Century 1926/2026 are partial calendar years and are reported separately; its annual-floor diagnostic uses only 99 complete years. No account inherits gains from another window. Century CPPI retains its own accrued cash wealth/peak at activation without a 1933 reset.

The original 49-industry universe cannot cover this period without missing data. Thirty industries were selected on complete data coverage before strategy performance. They are reconstructed research portfolios, not 30 historically available ETFs or an executable $1,000 individual-stock basket. Rankings still choose 5 or 10 industries, so changing 49 to 30 changes concentration. Old and new outcomes are related robustness comparisons, not identical portfolios.

## Same requested screens

Primary cost is 25 bp per risky traded side; primary month *t* allocations use observations through t-2. Costs 10/25/50 bp and lags 1/2 produce six cases per window. Stable requires positive CAGR and strictly less drawdown than identically dated/costed market in all 12 full/evaluation comparisons. The 10%/25% CAGR groups require the threshold in both primary windows. Categories overlap; desired 100/50/50 counts are aspirations.

| Screen | Century plus later 50 years | Active 93 years plus later 50 years |
|---|---:|---:|
|Positive primary CAGR in both periods|200|200|
|Positive across all 12 cost/lag comparisons|199|199|
|Stable across all 12 comparisons|108|95|
|At least 10% CAGR in both primary periods|120|132|
|At least 25% CAGR in both primary periods|0|0|

Unique configurations passing at least one stable/10%/25% screen: 180 century-based and 183 active-based. Do not add overlapping groups. **0 of 4,896 accounts earned at least 10% in every complete calendar year.** Lower relative drawdown can still mean severe absolute losses.

## Training choices and descriptive comparisons

Saved choices were fixed after training and before evaluation/full/century execution: stable=['CPPIRATCHET_06', 'CPPIRATCHET_01', 'CPPIRATCHET_07', 'CPPIRATCHET_08', 'VOLCAPEQ_06']; growth 10=['MOM_05', 'SKIPMOM_03', 'MOM_06', 'MOM_03', 'SKIPMOM_05']; growth 25=[]. Known market history and revised inputs prevent calling the split an untouched holdout.

|Policy/window|CAGR|Drawdown|Worst complete year|Losing complete years|
|---|---:|---:|---:|---:|
|MOM_05/century|14.10%|-51.61%|-38.49%|23|
|MOM_05/full|14.67%|-51.61%|-38.49%|23|
|MOM_05/evaluation|13.94%|-51.61%|-35.82%|10|
|CPPIRATCHET_06/century|4.86%|-9.77%|-6.74%|7|
|CPPIRATCHET_06/full|5.01%|-9.77%|-6.74%|7|
|CPPIRATCHET_06/evaluation|5.87%|-9.28%|-6.51%|3|
|SKIPMOM_03/century|14.24%|-56.64%|-42.41%|20|
|SKIPMOM_03/full|14.95%|-56.64%|-42.41%|20|
|SKIPMOM_03/evaluation|14.69%|-56.64%|-42.41%|8|
|CMKT/century|10.34%|-82.85%|-42.91%|24|
|CMKT/full|11.60%|-50.31%|-36.65%|20|
|CMKT/evaluation|12.19%|-50.18%|-36.55%|10|
|CEQ/century|10.74%|-83.32%|-44.45%|28|
|CEQ/full|12.13%|-52.25%|-38.54%|24|
|CEQ/evaluation|12.24%|-52.25%|-38.54%|11|
|CRF/century|3.29%|-0.09%|-0.04%|2|
|CRF/full|3.33%|-0.09%|-0.04%|2|
|CRF/evaluation|4.25%|0.00%|0.00%|0|

Best century CAGR (SKIPMOM_03) and best active full CAGR (SKIPMOM_03) are labeled retrospective leaders, not deployable selections. Primary full paths have 200 exact machine-distinct return vectors among 200 configurations; numerical distinction is not economic independence.

## Selection and risk diagnostics

The registered 2,000-replicate shared-calendar stationary-block maximum-mean bootstrap produced 0 family-wise 5% rejections among 200 later-period monthly excess-return comparisons. Minimum adjusted p=0.319340. This tests mean monthly excess return, not CAGR, drawdown, probability of future profit or all previous project searches.

CPPI floors were breached in 69 account scenarios and 10,944 account-month observations across overlapping windows/costs/lags. These are not unique market events. No loss or floor violation was repaired.

Drawdown is measured at monthly pre/post-cost and closing/terminal marks. Intramonth losses may be larger. Returns are nominal after modeled trading costs, before taxes, inflation, recurring data/model bills and industry-basket implementation costs. Cash RF is a research proxy, not broker interest. Historical membership/revisions and original publication timestamps remain unresolved for executable point-in-time claims.

## Fixed periods and why performance differs

The following fixed slices show outcomes of the already selected training growth policy and the market. They explain accounting and exposure, not causal news effects or a proven forecasting rule. Historical regime labels use lagged market trend and expanding past volatility only.

|Fixed period|MOM_05 CAGR/return|Market CAGR/return|
|---|---:|---:|
|1933-1942 CAGR|8.42%|9.75%|
|1943-1952 CAGR|21.81%|16.32%|
|1953-1962 CAGR|18.21%|13.30%|
|1963-1972 CAGR|17.06%|10.05%|
|1973-1982 CAGR|14.38%|7.57%|
|1983-1992 CAGR|17.00%|15.49%|
|1993-2002 CAGR|12.98%|8.82%|
|2003-2012 CAGR|7.57%|7.88%|
|2013-2022 CAGR|16.40%|12.36%|
|2023-2025 CAGR|11.30%|22.92%|
|1937-03:1938-03 total return|-50.53%|-49.14%|
|1973-01:1974-12 total return|-11.25%|-41.72%|
|1987-10:1987-10 total return|-27.54%|-22.58%|
|2000-03:2002-10 total return|-24.41%|-37.16%|
|2007-10:2009-03 total return|-41.81%|-44.68%|
|2020-02:2020-04 total return|-9.88%|-9.37%|
|2022-01:2022-12 total return|14.66%|-19.92%|

The 2023–2025 tail is 36 months; the other decade blocks are 120 months. Stress totals are not annualized. Full conditional state exposures, cash/risky contributions and fees for every primary policy are in [regimes.json](evidence/2026-10-20-century/regimes.json).

## What the held positions explain

The training-selected MOM_05 rule ranks trailing 12-month industry returns and holds the top five at a 98% total risky allocation. It has no market crash exit. The [descriptive attribution](evidence/2026-10-20-century/stress-attribution.json) reconciles all 1,116 monthly risky-P&L rows and all seven registered stress slices; [separate review](evidence/2026-10-20-century/attribution-independent-review.json) checks the arithmetic. The complete analysis source is preserved as [attribution-code.py.txt](evidence/2026-10-20-century/attribution-code.py.txt); copy it to repo `tmp/attribute_century.py` before running. This is post-performance explanation of frozen outcomes, not a new strategy or validation sample.

In 2022, MOM_05 gained 14.66% while the matched market lost 19.92%. Coal contributed +16.40 percentage points and Oil +11.44; Autos contributed −6.96 and Business Equipment −4.60, with costs subtracting 1.54 points. These are contributions relative to starting period wealth, not each industry’s standalone return. Energy exposure explains much of this account’s gain; this does not show that a bot predicted the news.

The same type of exposure hurt in 2007-10 through 2009-03: Coal contributed −9.76 points and Chemicals −6.52, within a 41.81% account loss. During 1937-03 through 1938-03 the rule lost 50.53%; during October 1987 it lost 27.54%. Rank-based momentum can stay invested in falling prior winners. In 1973–1974 it still lost 11.25%, although the market lost 41.72%; “worked better” in that slice meant a smaller loss. Cash, every industry contribution and fees are retained for all seven slices, including the unfavorable ones.

## Every candidate, including rejected screens

All values below use primary cost/lag. C=century 1926-07–2026-06 with 78 cash warmup months; A=active 1933–2025; E=fresh 1976–2025. Stable is the all 12-case screen, not a single primary drawdown comparison.

|Policy|Century CAGR|Century drawdown|Active CAGR|Evaluation CAGR|Century stable|Active stable|
|---|---:|---:|---:|---:|---|---|
|MOM_01|11.39%|-55.02%|11.84%|11.39%|no|no|
|MOM_02|11.90%|-50.74%|12.45%|11.80%|no|no|
|MOM_03|14.16%|-51.88%|14.87%|14.74%|no|no|
|MOM_04|12.91%|-49.27%|13.53%|13.12%|yes|no|
|MOM_05|14.10%|-51.61%|14.67%|13.94%|no|no|
|MOM_06|13.72%|-48.33%|14.38%|13.74%|yes|yes|
|MOM_07|12.85%|-60.77%|13.47%|12.83%|no|no|
|MOM_08|12.59%|-53.08%|13.18%|12.57%|no|no|
|MOM_09|11.65%|-66.73%|12.25%|11.56%|no|no|
|MOM_10|11.80%|-53.58%|12.32%|11.70%|no|no|
|SKIPMOM_01|11.97%|-61.44%|12.55%|11.41%|no|no|
|SKIPMOM_02|11.67%|-53.57%|12.21%|11.25%|no|no|
|SKIPMOM_03|14.24%|-56.64%|14.95%|14.69%|no|no|
|SKIPMOM_04|13.01%|-50.73%|13.64%|13.08%|no|no|
|SKIPMOM_05|13.45%|-57.33%|14.12%|13.49%|no|no|
|SKIPMOM_06|12.68%|-50.75%|13.28%|12.96%|no|no|
|SKIPMOM_07|12.15%|-64.42%|12.74%|12.51%|no|no|
|SKIPMOM_08|12.12%|-53.08%|12.67%|12.27%|no|no|
|SKIPMOM_09|11.35%|-66.74%|11.85%|11.20%|no|no|
|SKIPMOM_10|11.44%|-54.84%|11.90%|11.70%|no|no|
|VOLMOM_01|11.13%|-49.46%|11.59%|11.36%|no|no|
|VOLMOM_02|11.29%|-53.67%|11.79%|11.54%|no|no|
|VOLMOM_03|12.08%|-57.47%|12.61%|12.10%|no|no|
|VOLMOM_04|12.26%|-51.20%|12.81%|13.05%|no|no|
|VOLMOM_05|12.65%|-52.39%|13.18%|12.28%|no|no|
|VOLMOM_06|13.35%|-51.55%|13.93%|13.77%|yes|no|
|VOLMOM_07|12.21%|-57.09%|12.79%|11.90%|no|no|
|VOLMOM_08|12.27%|-52.35%|12.92%|12.83%|no|no|
|VOLMOM_09|11.76%|-58.37%|12.27%|12.11%|no|no|
|VOLMOM_10|11.77%|-54.44%|12.34%|11.89%|no|no|
|DOWNMOM_01|10.90%|-54.56%|11.38%|11.02%|no|no|
|DOWNMOM_02|11.19%|-54.49%|11.68%|11.25%|no|no|
|DOWNMOM_03|12.44%|-54.65%|13.00%|12.58%|no|no|
|DOWNMOM_04|12.28%|-51.90%|12.82%|13.03%|no|no|
|DOWNMOM_05|12.78%|-55.64%|13.28%|12.53%|no|no|
|DOWNMOM_06|13.28%|-50.74%|13.87%|13.76%|yes|no|
|DOWNMOM_07|11.56%|-58.68%|12.13%|11.30%|no|no|
|DOWNMOM_08|12.20%|-52.35%|12.83%|12.70%|no|no|
|DOWNMOM_09|11.54%|-60.90%|12.03%|11.71%|no|no|
|DOWNMOM_10|11.92%|-54.35%|12.50%|12.34%|no|no|
|SHORTREV_01|4.97%|-65.80%|5.08%|5.13%|no|no|
|SHORTREV_02|6.72%|-61.81%|6.92%|8.05%|no|no|
|SHORTREV_03|6.48%|-64.30%|6.70%|6.74%|no|no|
|SHORTREV_04|7.98%|-60.88%|8.27%|8.59%|no|no|
|SHORTREV_05|6.01%|-70.41%|6.11%|5.87%|no|no|
|SHORTREV_06|7.59%|-59.85%|7.83%|7.89%|no|no|
|SHORTREV_07|6.88%|-64.06%|7.09%|7.48%|no|no|
|SHORTREV_08|7.96%|-59.02%|8.23%|8.70%|no|no|
|SHORTREV_09|6.95%|-61.67%|7.21%|7.88%|no|no|
|SHORTREV_10|8.18%|-59.76%|8.51%|9.11%|no|no|
|LONGREV_01|8.48%|-65.12%|8.80%|8.30%|no|no|
|LONGREV_02|9.84%|-55.86%|10.34%|10.28%|no|no|
|LONGREV_03|8.93%|-65.49%|9.36%|7.71%|no|no|
|LONGREV_04|10.23%|-61.28%|10.74%|11.06%|no|no|
|LONGREV_05|8.84%|-68.43%|9.26%|8.32%|no|no|
|LONGREV_06|10.01%|-59.39%|10.50%|10.39%|no|no|
|LONGREV_07|9.52%|-68.03%|10.04%|8.61%|no|no|
|LONGREV_08|10.55%|-57.91%|11.15%|10.76%|no|no|
|LONGREV_09|9.00%|-63.31%|9.52%|8.31%|no|no|
|LONGREV_10|10.93%|-57.94%|11.54%|10.99%|no|no|
|LOWVOL_01|8.84%|-45.45%|9.26%|9.83%|yes|yes|
|LOWVOL_02|9.72%|-46.50%|10.17%|10.37%|yes|yes|
|LOWVOL_03|9.47%|-46.46%|9.93%|10.25%|yes|yes|
|LOWVOL_04|10.20%|-45.61%|10.74%|11.26%|yes|yes|
|LOWVOL_05|9.95%|-44.05%|10.47%|10.43%|yes|yes|
|LOWVOL_06|10.76%|-45.39%|11.34%|11.60%|yes|yes|
|LOWVOL_07|9.93%|-45.66%|10.42%|10.65%|yes|yes|
|LOWVOL_08|10.91%|-42.81%|11.51%|11.78%|yes|yes|
|LOWVOL_09|10.09%|-48.26%|10.64%|11.31%|yes|yes|
|LOWVOL_10|11.10%|-44.27%|11.70%|12.13%|yes|yes|
|LOWBETA_01|9.99%|-40.10%|10.68%|9.50%|yes|yes|
|LOWBETA_02|9.96%|-45.83%|10.55%|10.31%|no|no|
|LOWBETA_03|10.19%|-43.46%|10.81%|10.85%|yes|yes|
|LOWBETA_04|10.73%|-44.90%|11.33%|11.21%|yes|yes|
|LOWBETA_05|10.55%|-44.92%|11.12%|11.10%|yes|yes|
|LOWBETA_06|11.19%|-42.69%|11.82%|11.31%|yes|yes|
|LOWBETA_07|10.72%|-39.03%|11.30%|10.80%|yes|yes|
|LOWBETA_08|11.29%|-41.91%|11.91%|11.63%|yes|yes|
|LOWBETA_09|10.63%|-40.44%|11.19%|11.49%|yes|yes|
|LOWBETA_10|11.36%|-41.94%|11.99%|11.97%|yes|yes|
|LOWDD_01|10.11%|-40.65%|10.55%|9.83%|yes|yes|
|LOWDD_02|10.14%|-44.99%|10.61%|10.33%|yes|yes|
|LOWDD_03|11.56%|-41.70%|12.23%|12.15%|yes|yes|
|LOWDD_04|11.61%|-44.12%|12.21%|11.95%|yes|yes|
|LOWDD_05|11.53%|-44.58%|12.20%|11.97%|yes|yes|
|LOWDD_06|11.44%|-44.24%|12.09%|11.71%|yes|yes|
|LOWDD_07|10.36%|-45.72%|10.93%|10.97%|yes|yes|
|LOWDD_08|11.00%|-44.52%|11.64%|11.35%|yes|yes|
|LOWDD_09|11.31%|-44.06%|11.87%|12.55%|yes|yes|
|LOWDD_10|11.44%|-42.72%|12.03%|11.95%|yes|yes|
|ABSMOM_01|7.62%|-30.05%|7.98%|7.13%|yes|yes|
|ABSMOM_02|8.26%|-32.15%|8.64%|8.62%|yes|yes|
|ABSMOM_03|9.07%|-42.11%|9.50%|9.12%|yes|yes|
|ABSMOM_04|8.47%|-42.01%|8.84%|9.39%|yes|yes|
|ABSMOM_05|8.18%|-38.00%|8.52%|8.85%|yes|yes|
|ABSMOM_06|7.77%|-40.25%|8.09%|8.03%|yes|yes|
|ABSMOM_07|7.48%|-41.61%|7.77%|7.68%|yes|yes|
|ABSMOM_08|7.92%|-49.25%|8.22%|8.48%|yes|yes|
|ABSMOM_09|8.14%|-47.01%|8.45%|8.67%|yes|no|
|ABSMOM_10|8.63%|-47.00%|9.00%|9.35%|yes|yes|
|SMA_01|7.78%|-28.44%|8.14%|7.66%|yes|yes|
|SMA_02|8.46%|-30.35%|8.86%|8.69%|yes|yes|
|SMA_03|8.62%|-38.70%|9.02%|9.10%|yes|yes|
|SMA_04|9.01%|-41.17%|9.45%|9.51%|yes|yes|
|SMA_05|8.81%|-39.68%|9.21%|9.53%|yes|yes|
|SMA_06|8.89%|-37.24%|9.29%|9.61%|yes|yes|
|SMA_07|8.74%|-35.68%|9.12%|9.43%|yes|yes|
|SMA_08|8.51%|-39.03%|8.86%|9.31%|yes|yes|
|SMA_09|8.50%|-43.13%|8.87%|9.41%|yes|yes|
|SMA_10|8.55%|-46.00%|8.92%|9.59%|yes|yes|
|CHANNEL_01|9.73%|-48.49%|10.26%|10.44%|yes|no|
|CHANNEL_02|10.16%|-49.77%|10.59%|10.28%|yes|no|
|CHANNEL_03|9.84%|-51.74%|10.30%|11.06%|yes|no|
|CHANNEL_04|10.27%|-49.86%|10.69%|10.56%|no|no|
|CHANNEL_05|10.52%|-51.13%|10.98%|11.32%|yes|no|
|CHANNEL_06|10.74%|-50.38%|11.17%|11.11%|no|no|
|CHANNEL_07|10.83%|-53.55%|11.21%|11.24%|yes|no|
|CHANNEL_08|11.06%|-51.71%|11.54%|11.26%|no|no|
|CHANNEL_09|10.26%|-56.86%|10.57%|10.50%|yes|no|
|CHANNEL_10|10.76%|-52.98%|11.22%|11.13%|no|no|
|REGTREND_01|10.74%|-53.59%|11.15%|11.12%|no|no|
|REGTREND_02|11.02%|-56.93%|11.55%|11.48%|no|no|
|REGTREND_03|12.08%|-59.97%|12.60%|12.89%|no|no|
|REGTREND_04|12.13%|-53.69%|12.65%|12.89%|no|no|
|REGTREND_05|13.24%|-55.62%|13.82%|13.80%|no|no|
|REGTREND_06|12.72%|-52.79%|13.32%|13.22%|no|no|
|REGTREND_07|12.68%|-57.84%|13.42%|12.75%|no|no|
|REGTREND_08|12.68%|-52.04%|13.36%|13.56%|no|no|
|REGTREND_09|12.14%|-55.87%|12.85%|12.53%|no|no|
|REGTREND_10|11.90%|-52.69%|12.54%|13.05%|no|no|
|CONSISTENCY_01|11.49%|-48.84%|11.96%|10.90%|yes|no|
|CONSISTENCY_02|11.03%|-48.48%|11.51%|11.09%|yes|no|
|CONSISTENCY_03|12.00%|-46.08%|12.48%|11.45%|yes|yes|
|CONSISTENCY_04|11.65%|-52.17%|12.15%|11.38%|no|no|
|CONSISTENCY_05|12.19%|-48.31%|12.69%|11.49%|yes|yes|
|CONSISTENCY_06|12.17%|-52.00%|12.67%|12.13%|no|no|
|CONSISTENCY_07|11.73%|-53.43%|12.29%|11.78%|yes|no|
|CONSISTENCY_08|11.89%|-52.48%|12.46%|12.23%|no|no|
|CONSISTENCY_09|11.34%|-54.36%|11.87%|12.35%|no|no|
|CONSISTENCY_10|11.29%|-51.43%|11.81%|11.81%|no|no|
|INVERSEVOL_01|9.66%|-51.76%|10.13%|10.15%|no|no|
|INVERSEVOL_02|11.05%|-49.64%|11.60%|11.88%|no|no|
|INVERSEVOL_03|11.15%|-49.94%|11.70%|11.96%|yes|yes|
|INVERSEVOL_04|11.18%|-49.87%|11.74%|11.96%|no|no|
|INVERSEVOL_05|11.30%|-50.09%|11.87%|12.10%|no|no|
|INVERSEVOL_06|11.30%|-50.16%|11.88%|12.08%|no|no|
|INVERSEVOL_07|11.32%|-50.11%|11.90%|12.10%|no|no|
|INVERSEVOL_08|11.37%|-50.15%|11.96%|12.15%|no|no|
|INVERSEVOL_09|11.45%|-50.34%|12.04%|12.18%|no|no|
|INVERSEVOL_10|11.46%|-50.37%|12.05%|12.19%|no|no|
|INVERSEDOWN_01|10.13%|-45.97%|10.64%|9.90%|no|no|
|INVERSEDOWN_02|10.77%|-49.04%|11.24%|10.79%|no|no|
|INVERSEDOWN_03|11.38%|-49.49%|11.89%|11.92%|no|no|
|INVERSEDOWN_04|11.45%|-49.35%|12.06%|12.18%|no|no|
|INVERSEDOWN_05|11.35%|-49.83%|11.94%|12.11%|yes|yes|
|INVERSEDOWN_06|11.37%|-50.04%|11.95%|12.13%|no|no|
|INVERSEDOWN_07|11.37%|-49.91%|11.95%|12.13%|yes|yes|
|INVERSEDOWN_08|11.40%|-49.95%|11.99%|12.18%|yes|yes|
|INVERSEDOWN_09|11.54%|-50.04%|12.13%|12.25%|yes|yes|
|INVERSEDOWN_10|11.53%|-50.27%|12.12%|12.27%|no|no|
|VOLCAPEQ_01|6.74%|-24.34%|6.98%|7.46%|yes|yes|
|VOLCAPEQ_02|7.71%|-31.84%|8.02%|8.36%|yes|yes|
|VOLCAPEQ_03|8.53%|-38.28%|8.88%|9.03%|yes|yes|
|VOLCAPEQ_04|9.12%|-43.04%|9.52%|9.46%|yes|yes|
|VOLCAPEQ_05|9.65%|-47.94%|10.08%|10.02%|yes|yes|
|VOLCAPEQ_06|6.48%|-29.77%|6.73%|7.30%|yes|yes|
|VOLCAPEQ_07|7.48%|-38.44%|7.79%|8.23%|yes|yes|
|VOLCAPEQ_08|8.38%|-45.65%|8.74%|9.00%|yes|yes|
|VOLCAPEQ_09|9.09%|-48.87%|9.50%|9.79%|yes|yes|
|VOLCAPEQ_10|9.86%|-50.69%|10.30%|10.87%|no|no|
|VOLCAPMKT_01|6.59%|-24.71%|6.84%|7.72%|yes|yes|
|VOLCAPMKT_02|7.54%|-32.22%|7.84%|8.67%|yes|yes|
|VOLCAPMKT_03|8.37%|-38.02%|8.72%|9.40%|yes|yes|
|VOLCAPMKT_04|8.93%|-42.44%|9.32%|9.86%|yes|yes|
|VOLCAPMKT_05|9.52%|-46.71%|9.95%|10.56%|yes|yes|
|VOLCAPMKT_06|6.38%|-30.80%|6.62%|7.61%|yes|yes|
|VOLCAPMKT_07|7.36%|-39.59%|7.65%|8.65%|yes|yes|
|VOLCAPMKT_08|8.28%|-45.36%|8.63%|9.57%|yes|yes|
|VOLCAPMKT_09|8.98%|-47.43%|9.37%|10.36%|yes|yes|
|VOLCAPMKT_10|9.70%|-49.15%|10.15%|11.29%|yes|yes|
|CPPIFIXED_01|9.99%|-49.53%|10.13%|11.21%|yes|yes|
|CPPIFIXED_02|10.78%|-49.55%|11.19%|11.94%|yes|yes|
|CPPIFIXED_03|10.91%|-49.55%|11.28%|12.07%|yes|yes|
|CPPIFIXED_04|10.93%|-49.55%|11.35%|12.10%|yes|yes|
|CPPIFIXED_05|10.93%|-49.55%|11.45%|12.10%|yes|yes|
|CPPIFIXED_06|9.76%|-49.52%|9.73%|11.06%|yes|yes|
|CPPIFIXED_07|10.69%|-49.55%|10.91%|11.81%|yes|yes|
|CPPIFIXED_08|10.76%|-49.55%|11.14%|11.95%|yes|yes|
|CPPIFIXED_09|10.88%|-49.55%|11.17%|12.05%|yes|yes|
|CPPIFIXED_10|10.93%|-49.55%|11.12%|12.10%|yes|yes|
|CPPIRATCHET_01|5.63%|-14.70%|5.82%|6.65%|yes|yes|
|CPPIRATCHET_02|7.32%|-24.13%|7.62%|8.37%|yes|yes|
|CPPIRATCHET_03|7.99%|-28.93%|8.32%|8.94%|yes|yes|
|CPPIRATCHET_04|6.61%|-32.26%|6.82%|7.23%|yes|yes|
|CPPIRATCHET_05|6.53%|-35.87%|6.74%|7.09%|yes|yes|
|CPPIRATCHET_06|4.86%|-9.77%|5.01%|5.87%|yes|yes|
|CPPIRATCHET_07|6.03%|-15.96%|6.25%|7.07%|yes|yes|
|CPPIRATCHET_08|6.56%|-19.30%|6.80%|7.56%|yes|yes|
|CPPIRATCHET_09|5.90%|-23.34%|6.08%|6.67%|yes|yes|
|CPPIRATCHET_10|5.71%|-28.96%|5.87%|6.86%|yes|yes|

## Verification and next practical step

Independent checker reconciled 4,896 accounts, 4,200,768 monthly rows, 348,840 complete-calendar annual returns, 2,448 partial returns and all 31 asset values/targets. Receipt includes comparison counts and numerical residuals. Original input files, full holdings and monthly ledgers are retained in the owner-private transfer kit. Git contains source, frozen rules, all derived account summaries/annual vectors and provenance.

Primary inputs: [French 30 industry construction](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_30_ind_port.html), [market/RF definitions](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_factors.html), and [historical revision/CIZ notes](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html). Method hypotheses retain the [original-source dossier](LONG-HISTORY-SOURCE-DOSSIER-2026-10-20.md); no new paper replication is claimed.

Keep these 200 rules frozen. Next useful stock work is actual-instrument mapping, $1,000 whole/fractional share feasibility, corporate actions and prospective simulation. Options evidence is the separate [18-account execution study](OPTIONS-NEXT-STUDY-2026-10-20.md), not a century options-chain test. The [A8 preparation tool](A8-PAPER-PREPARATION-2026-10-20.md) records missing evidence and keeps new accounts disabled.
