# Fifty-year research results: every registered attempt retained

**All 3,672 registered accounts completed and independently reconciled.** This is 200 candidate configurations across 20 related families, plus four controls, under three costs, two information lags and three fresh-capital windows. It is not 3,672 algorithms or 200 independent discoveries.

The primary full-period accounts cover **1976–2025: 50 complete years, 600 months**. Training is 1976–2010 and later evaluation is 2011–2025. The run took 7.19 minutes on the existing computer; source downloads and independent verification time are separate. Additional data fees were **$0**; no paid model calls, new Databento spending or broker orders occurred.

Read the [period interpretation](LONG-HISTORY-INTERPRETATION-2026-10-20.md), [protocol](LONG-HISTORY-PROTOCOL-2026-10-20.md), [source dossier](LONG-HISTORY-SOURCE-DOSSIER-2026-10-20.md), [frozen rules](long-history-registration-2026-10-20.json), [all 3,672 result records](evidence/2026-10-20-long-history/results.jsonl), and [independent reconciliation](evidence/2026-10-20-long-history/independent-accounting.json). Every annual vector, cost case and failure to meet a threshold is retained.

## Requested research buckets

Primary means 25 basis points per risky traded side and observations through t−2 for holding month t. Robust checks cover all three costs and both lags, in both full and later periods. The owner chose **less drawdown than the matched market** as the stability definition.

| Screen | Configurations | Interpretation |
|---|---:|---|
| Positive primary full-period CAGR | 200/200 | Fifty-year nominal growth |
| Positive primary later-period CAGR | 199/200 | Fifteen-year nominal growth |
| Positive in every full/later cost and lag case | 194/200 | Twelve positive-growth comparisons |
| Positive plus lower market drawdown in all twelve comparisons | 87/200 | Requested relative-stability screen |
| At least 10% CAGR in both primary periods | 94/200 | Cost robustness remains separately reported |
| At least 25% CAGR in both primary periods | 0/200 | No leverage added to fill this bucket |

**These categories overlap.** Their counts cannot be added to claim 200 distinct winners. The union of stable/10%/25% screens contains 156 configurations; the 200 primary full accounts have 198 exact machine-computed monthly-return paths. Neither count measures statistical independence. These are research-index candidates, not broker-qualified strategies.

Across all scenarios, 0 accounts achieved at least 10% in every calendar year. The earlier every-year objective remains a separate test from annualized compound growth.

## Representative comparisons and selection

The highest primary full-period CAGR is **MOM_05**, selected here retrospectively for description. The highest later-period CAGR may come from a different candidate. Training-only choices were saved before evaluation/full simulations:

- Stable: CPPIRATCHET_06, CPPIRATCHET_01, CPPIRATCHET_07, CPPIRATCHET_08, CPPIRATCHET_09.
- Growth at least 10%: MOM_05, SKIPMOM_05, MOM_07, SKIPMOM_03, SKIPMOM_07.
- Growth at least 25%: none.

| Policy | Full CAGR | Full drawdown | Later CAGR | Later drawdown | Full ending $1,000 |
|---|---:|---:|---:|---:|---:|
| MOM_05 | 15.32% | -59.51% | 11.34% | -29.80% | $1,245,383.28 |
| VOLMOM_07 | 13.86% | -60.19% | 14.07% | -21.04% | $658,211.46 |
| CPPIRATCHET_06 | 5.87% | -9.28% | 3.82% | -4.35% | $17,292.89 |
| CMKT | 12.19% | -50.18% | 13.67% | -24.73% | $314,925.46 |
| CEQ49 | 12.49% | -51.93% | 11.76% | -25.49% | $360,244.40 |
| CRF | 4.25% | 0.00% | 1.41% | 0.00% | $8,026.77 |

The market control is the French broad US market research return, not a pre-1993 SPY history. Lower drawdown may come with lower growth. Monthly marks can miss larger losses within a month. Historical compounding of a synthetic $1,000 portfolio does not establish attainable security quantities.

## Which periods were favorable?

The following are slices of each continuous primary account, not newly fitted strategies or fresh-capital restarts. Boundaries were fixed before performance. They describe the observed path and cannot by themselves explain causation.

| Policy | 1976–1985 | 1986–1995 | 1996–2005 | 2006–2015 | 2016–2025 |
|---|---:|---:|---:|---:|---:|
| MOM_05 | 20.70% | 19.18% | 17.82% | 7.51% | 11.92% |
| VOLMOM_07 | 21.83% | 15.51% | 11.62% | 7.21% | 13.63% |
| CPPIRATCHET_06 | 10.48% | 7.33% | 4.81% | 2.31% | 4.58% |
| CMKT | 15.69% | 14.22% | 9.11% | 7.51% | 14.67% |
| CEQ49 | 17.69% | 13.38% | 10.93% | 7.78% | 12.93% |
| CRF | 9.03% | 5.56% | 3.64% | 1.12% | 2.11% |

Values above are decade CAGR. The next table reports total return over fixed stress intervals, not annualized rates:

| Policy | Oct 1987 | Mar 2000–Oct 2002 | Oct 2007–Mar 2009 | Feb–Apr 2020 | 2022 |
|---|---:|---:|---:|---:|---:|
| MOM_05 | -29.34% | -0.73% | -47.19% | -8.34% | 9.53% |
| VOLMOM_07 | -25.43% | -30.19% | -51.36% | -10.10% | -6.18% |
| CPPIRATCHET_06 | -3.95% | -0.17% | -7.60% | -1.54% | -2.60% |
| CMKT | -22.41% | -37.04% | -44.56% | -9.36% | -19.90% |
| CEQ49 | -25.44% | -1.07% | -46.05% | -14.15% | -12.20% |
| CRF | 0.60% | 10.54% | 2.57% | 0.24% | 1.41% |

The [complete regime file](evidence/2026-10-20-long-history/regimes.json) also reports all 204 policies' lagged up/down and high/low-volatility states: month counts, mean net monthly return, hit rate, risky exposure, cash gains, risky gains and fees. These accounting components can explain defensive exposure or cost drag. They do not prove a specific news story caused a price move.

## Search bias and protection claims

The registered 2,000-replicate shared stationary-block maximum-mean diagnostic produced **0 of 200 family-wise p-values at or below 0.05**; minimum 0.994003. The comparison is later-period mean monthly net return minus the matched market. It does not test CAGR or drawdown superiority. [Every candidate's statistic](evidence/2026-10-20-long-history/bootstrap.json).

The adjustment covers this registered candidate set, not all earlier project searches. Nonstationarity, current data vintages and nontradable baskets remain. A small p-value is not a future profit probability; a defensive candidate can serve a different objective while trailing the market's mean return.

The independent audit found **30 insurance accounts with recorded floor breaches**, totaling 2,198 account-month observations across overlapping windows, costs and lags; these are not unique historical months. The floor is a delayed exposure rule, not guaranteed capital protection. No breached account was repaired.

## Limits, costs and news

The [cost assessment](FIFTY-YEAR-DATA-COSTS-2026-10-20.md) distinguishes free aggregate research from paid security-level histories. This study's monthly industry baskets are not funds a $1,000 investor could buy throughout fifty years. Internal basket turnover, intramonth prices, minimum commissions, taxes, inflation and recurring service charges are unmodeled. All reported growth is nominal. Cost scenarios do not certify achievable execution.

This is not a 50-year options or news-sentiment backtest. The separate [news pilot](NEWS-RESEARCH-2026-10-20.md) actually collected 55 observations from three official feeds, with 51 content versions and 38 unique versions passing initial observation gates. Its timestamps support prospective data-quality work; it has produced no prediction or P&L claim. The source reading distinguishes news association, causal identification and tradable returns.

The [selected textbook reading log](RESEARCH-READING-LOG-2026-10-20.md) records the actual chapters, sections and author slides inspected. It does not claim whole-book reading. The new methods are transparent local adaptations, not replications of every cited paper.

## Every candidate at primary assumptions

These 200 rows retain losses and failed thresholds. Full is 1976–2025; later is 2011–2025. `Stable all12` requires positive growth and smaller matched-market drawdown across both periods and all costs/lags.

| Configuration | Family | Full CAGR | Full DD | Later CAGR | Later DD | Stable all12 |
|---|---|---:|---:|---:|---:|---|
| MOM_01 | MOM | 12.87% | -57.38% | 13.07% | -24.54% | no |
| MOM_02 | MOM | 12.85% | -53.73% | 11.44% | -23.93% | no |
| MOM_03 | MOM | 14.54% | -58.12% | 12.51% | -28.20% | no |
| MOM_04 | MOM | 14.30% | -51.17% | 11.73% | -28.31% | no |
| MOM_05 | MOM | 15.32% | -59.51% | 11.34% | -29.80% | no |
| MOM_06 | MOM | 14.72% | -52.76% | 13.24% | -25.20% | no |
| MOM_07 | MOM | 14.53% | -61.54% | 11.92% | -23.79% | no |
| MOM_08 | MOM | 13.03% | -54.15% | 12.07% | -22.38% | no |
| MOM_09 | MOM | 11.99% | -63.92% | 9.19% | -26.92% | no |
| MOM_10 | MOM | 12.33% | -56.82% | 10.17% | -27.32% | no |
| SKIPMOM_01 | SKIPMOM | 11.47% | -61.08% | 11.13% | -26.70% | no |
| SKIPMOM_02 | SKIPMOM | 12.22% | -56.78% | 10.80% | -26.22% | no |
| SKIPMOM_03 | SKIPMOM | 15.11% | -59.61% | 13.85% | -27.61% | no |
| SKIPMOM_04 | SKIPMOM | 14.20% | -54.89% | 13.08% | -27.47% | no |
| SKIPMOM_05 | SKIPMOM | 14.48% | -62.42% | 9.77% | -32.25% | no |
| SKIPMOM_06 | SKIPMOM | 13.52% | -56.04% | 10.27% | -27.32% | no |
| SKIPMOM_07 | SKIPMOM | 14.11% | -62.65% | 10.83% | -26.72% | no |
| SKIPMOM_08 | SKIPMOM | 13.10% | -57.67% | 11.52% | -23.56% | no |
| SKIPMOM_09 | SKIPMOM | 12.03% | -62.29% | 8.92% | -28.71% | no |
| SKIPMOM_10 | SKIPMOM | 12.06% | -57.00% | 9.47% | -27.31% | no |
| VOLMOM_01 | VOLMOM | 11.99% | -51.34% | 13.41% | -21.38% | no |
| VOLMOM_02 | VOLMOM | 11.74% | -52.09% | 11.55% | -22.59% | no |
| VOLMOM_03 | VOLMOM | 12.06% | -58.73% | 12.04% | -23.12% | no |
| VOLMOM_04 | VOLMOM | 13.34% | -54.16% | 12.50% | -21.41% | no |
| VOLMOM_05 | VOLMOM | 12.52% | -56.74% | 11.47% | -25.10% | no |
| VOLMOM_06 | VOLMOM | 13.49% | -51.21% | 11.84% | -22.43% | no |
| VOLMOM_07 | VOLMOM | 13.86% | -60.19% | 14.07% | -21.04% | no |
| VOLMOM_08 | VOLMOM | 13.35% | -54.66% | 12.37% | -19.46% | no |
| VOLMOM_09 | VOLMOM | 11.91% | -51.28% | 9.72% | -32.72% | no |
| VOLMOM_10 | VOLMOM | 12.43% | -52.55% | 11.16% | -24.40% | no |
| DOWNMOM_01 | DOWNMOM | 11.95% | -51.62% | 12.22% | -24.67% | no |
| DOWNMOM_02 | DOWNMOM | 11.47% | -51.15% | 10.01% | -20.53% | no |
| DOWNMOM_03 | DOWNMOM | 12.28% | -59.35% | 11.37% | -22.39% | no |
| DOWNMOM_04 | DOWNMOM | 13.16% | -54.82% | 11.40% | -22.60% | no |
| DOWNMOM_05 | DOWNMOM | 12.50% | -57.05% | 10.47% | -24.54% | no |
| DOWNMOM_06 | DOWNMOM | 13.68% | -50.90% | 11.37% | -22.09% | no |
| DOWNMOM_07 | DOWNMOM | 13.78% | -59.51% | 12.23% | -25.40% | no |
| DOWNMOM_08 | DOWNMOM | 13.22% | -54.99% | 11.39% | -19.97% | no |
| DOWNMOM_09 | DOWNMOM | 11.42% | -52.72% | 9.01% | -28.02% | no |
| DOWNMOM_10 | DOWNMOM | 12.39% | -54.68% | 10.89% | -23.49% | no |
| SHORTREV_01 | SHORTREV | 5.12% | -67.37% | -0.39% | -62.03% | no |
| SHORTREV_02 | SHORTREV | 6.01% | -65.18% | 3.88% | -41.22% | no |
| SHORTREV_03 | SHORTREV | 5.61% | -73.49% | 3.13% | -68.56% | no |
| SHORTREV_04 | SHORTREV | 7.68% | -61.39% | 5.01% | -46.17% | no |
| SHORTREV_05 | SHORTREV | 4.73% | -70.53% | 2.20% | -64.06% | no |
| SHORTREV_06 | SHORTREV | 7.10% | -62.03% | 5.62% | -36.69% | no |
| SHORTREV_07 | SHORTREV | 6.02% | -73.20% | 1.18% | -67.60% | no |
| SHORTREV_08 | SHORTREV | 8.00% | -61.10% | 6.01% | -43.02% | no |
| SHORTREV_09 | SHORTREV | 5.79% | -68.16% | 2.95% | -55.55% | no |
| SHORTREV_10 | SHORTREV | 8.22% | -62.49% | 6.39% | -41.16% | no |
| LONGREV_01 | LONGREV | 9.32% | -63.48% | 8.97% | -46.56% | no |
| LONGREV_02 | LONGREV | 8.73% | -65.85% | 9.14% | -36.17% | no |
| LONGREV_03 | LONGREV | 7.86% | -65.88% | 6.45% | -51.23% | no |
| LONGREV_04 | LONGREV | 9.57% | -59.05% | 9.81% | -39.00% | no |
| LONGREV_05 | LONGREV | 8.44% | -64.64% | 5.52% | -52.91% | no |
| LONGREV_06 | LONGREV | 10.13% | -61.21% | 8.38% | -36.00% | no |
| LONGREV_07 | LONGREV | 9.37% | -60.77% | 7.76% | -48.13% | no |
| LONGREV_08 | LONGREV | 10.57% | -57.71% | 7.77% | -38.53% | no |
| LONGREV_09 | LONGREV | 9.89% | -58.36% | 7.38% | -56.23% | no |
| LONGREV_10 | LONGREV | 10.40% | -57.21% | 7.99% | -38.83% | no |
| LOWVOL_01 | LOWVOL | 8.23% | -39.20% | 6.44% | -18.98% | no |
| LOWVOL_02 | LOWVOL | 9.19% | -45.67% | 8.74% | -19.35% | yes |
| LOWVOL_03 | LOWVOL | 9.38% | -41.93% | 8.16% | -21.83% | yes |
| LOWVOL_04 | LOWVOL | 10.39% | -43.26% | 9.61% | -20.98% | yes |
| LOWVOL_05 | LOWVOL | 10.25% | -38.48% | 6.76% | -20.96% | yes |
| LOWVOL_06 | LOWVOL | 10.56% | -45.17% | 8.85% | -20.68% | yes |
| LOWVOL_07 | LOWVOL | 10.42% | -37.50% | 7.77% | -21.12% | yes |
| LOWVOL_08 | LOWVOL | 11.14% | -45.49% | 9.80% | -20.88% | yes |
| LOWVOL_09 | LOWVOL | 10.96% | -39.32% | 9.34% | -20.60% | yes |
| LOWVOL_10 | LOWVOL | 11.81% | -43.23% | 10.24% | -20.92% | yes |
| LOWBETA_01 | LOWBETA | 9.67% | -48.17% | 10.60% | -20.56% | no |
| LOWBETA_02 | LOWBETA | 10.57% | -43.36% | 10.11% | -22.61% | no |
| LOWBETA_03 | LOWBETA | 11.01% | -31.52% | 12.73% | -17.27% | yes |
| LOWBETA_04 | LOWBETA | 10.82% | -47.93% | 11.03% | -19.12% | yes |
| LOWBETA_05 | LOWBETA | 11.41% | -36.05% | 8.44% | -26.04% | no |
| LOWBETA_06 | LOWBETA | 11.40% | -41.12% | 9.27% | -22.45% | yes |
| LOWBETA_07 | LOWBETA | 11.70% | -36.64% | 8.19% | -19.98% | yes |
| LOWBETA_08 | LOWBETA | 11.09% | -40.90% | 9.71% | -22.48% | yes |
| LOWBETA_09 | LOWBETA | 11.30% | -39.95% | 9.76% | -19.78% | yes |
| LOWBETA_10 | LOWBETA | 11.94% | -33.04% | 10.68% | -18.29% | yes |
| LOWDD_01 | LOWDD | 9.28% | -45.55% | 9.33% | -19.12% | no |
| LOWDD_02 | LOWDD | 10.45% | -43.82% | 10.26% | -20.34% | yes |
| LOWDD_03 | LOWDD | 11.96% | -42.37% | 10.02% | -19.60% | yes |
| LOWDD_04 | LOWDD | 11.87% | -42.54% | 10.39% | -22.40% | yes |
| LOWDD_05 | LOWDD | 11.17% | -43.25% | 8.36% | -18.75% | yes |
| LOWDD_06 | LOWDD | 12.07% | -44.95% | 9.70% | -18.60% | yes |
| LOWDD_07 | LOWDD | 11.50% | -43.51% | 9.91% | -20.77% | yes |
| LOWDD_08 | LOWDD | 11.43% | -45.53% | 10.27% | -22.31% | yes |
| LOWDD_09 | LOWDD | 12.16% | -49.16% | 11.73% | -23.11% | yes |
| LOWDD_10 | LOWDD | 11.76% | -46.48% | 12.21% | -21.24% | yes |
| ABSMOM_01 | ABSMOM | 7.13% | -29.28% | 6.57% | -20.52% | yes |
| ABSMOM_02 | ABSMOM | 8.47% | -27.54% | 7.17% | -18.20% | yes |
| ABSMOM_03 | ABSMOM | 8.87% | -30.17% | 7.98% | -20.08% | yes |
| ABSMOM_04 | ABSMOM | 9.30% | -29.16% | 8.13% | -20.26% | yes |
| ABSMOM_05 | ABSMOM | 8.99% | -26.70% | 8.50% | -18.45% | yes |
| ABSMOM_06 | ABSMOM | 8.02% | -29.38% | 8.05% | -19.56% | yes |
| ABSMOM_07 | ABSMOM | 7.92% | -30.13% | 8.29% | -19.74% | yes |
| ABSMOM_08 | ABSMOM | 8.56% | -29.42% | 8.58% | -19.96% | yes |
| ABSMOM_09 | ABSMOM | 8.77% | -32.94% | 8.46% | -19.96% | yes |
| ABSMOM_10 | ABSMOM | 9.24% | -33.07% | 9.12% | -19.72% | yes |
| SMA_01 | SMA | 7.55% | -28.60% | 6.98% | -15.16% | yes |
| SMA_02 | SMA | 8.40% | -30.61% | 7.79% | -19.39% | yes |
| SMA_03 | SMA | 8.91% | -30.94% | 7.73% | -20.41% | yes |
| SMA_04 | SMA | 9.27% | -30.94% | 7.77% | -19.79% | yes |
| SMA_05 | SMA | 9.40% | -30.93% | 7.83% | -20.03% | yes |
| SMA_06 | SMA | 9.43% | -30.27% | 8.12% | -19.73% | yes |
| SMA_07 | SMA | 9.45% | -30.26% | 8.42% | -19.80% | yes |
| SMA_08 | SMA | 9.33% | -30.99% | 8.84% | -19.78% | yes |
| SMA_09 | SMA | 9.45% | -30.95% | 8.82% | -20.26% | yes |
| SMA_10 | SMA | 9.50% | -30.93% | 8.70% | -20.20% | yes |
| CHANNEL_01 | CHANNEL | 9.30% | -43.11% | 7.36% | -31.24% | no |
| CHANNEL_02 | CHANNEL | 9.92% | -48.33% | 9.58% | -22.41% | no |
| CHANNEL_03 | CHANNEL | 9.17% | -49.09% | 7.14% | -29.97% | no |
| CHANNEL_04 | CHANNEL | 10.49% | -50.41% | 9.75% | -22.90% | no |
| CHANNEL_05 | CHANNEL | 10.04% | -50.01% | 8.53% | -27.65% | no |
| CHANNEL_06 | CHANNEL | 10.97% | -53.39% | 10.31% | -24.57% | no |
| CHANNEL_07 | CHANNEL | 9.58% | -49.13% | 6.40% | -35.14% | no |
| CHANNEL_08 | CHANNEL | 11.02% | -52.81% | 9.35% | -30.11% | no |
| CHANNEL_09 | CHANNEL | 9.38% | -49.22% | 5.15% | -37.73% | no |
| CHANNEL_10 | CHANNEL | 10.54% | -49.60% | 8.09% | -32.12% | no |
| REGTREND_01 | REGTREND | 11.81% | -56.06% | 10.76% | -22.24% | no |
| REGTREND_02 | REGTREND | 11.69% | -52.88% | 12.20% | -22.47% | no |
| REGTREND_03 | REGTREND | 12.74% | -61.54% | 13.94% | -24.36% | no |
| REGTREND_04 | REGTREND | 12.38% | -57.88% | 11.81% | -22.72% | no |
| REGTREND_05 | REGTREND | 12.29% | -64.35% | 11.04% | -25.11% | no |
| REGTREND_06 | REGTREND | 13.18% | -57.84% | 12.19% | -20.35% | no |
| REGTREND_07 | REGTREND | 12.70% | -58.90% | 10.63% | -21.03% | no |
| REGTREND_08 | REGTREND | 13.95% | -53.71% | 12.85% | -19.15% | no |
| REGTREND_09 | REGTREND | 11.82% | -54.80% | 9.99% | -25.73% | no |
| REGTREND_10 | REGTREND | 13.08% | -54.81% | 11.56% | -23.37% | no |
| CONSISTENCY_01 | CONSISTENCY | 9.93% | -46.18% | 10.76% | -26.37% | no |
| CONSISTENCY_02 | CONSISTENCY | 11.58% | -50.54% | 9.12% | -25.30% | no |
| CONSISTENCY_03 | CONSISTENCY | 10.61% | -56.84% | 10.60% | -27.11% | no |
| CONSISTENCY_04 | CONSISTENCY | 11.71% | -49.87% | 10.29% | -26.09% | no |
| CONSISTENCY_05 | CONSISTENCY | 13.12% | -50.62% | 12.66% | -25.03% | no |
| CONSISTENCY_06 | CONSISTENCY | 12.33% | -50.54% | 11.54% | -22.96% | no |
| CONSISTENCY_07 | CONSISTENCY | 13.04% | -56.27% | 13.80% | -27.24% | no |
| CONSISTENCY_08 | CONSISTENCY | 12.50% | -50.96% | 13.14% | -22.42% | no |
| CONSISTENCY_09 | CONSISTENCY | 12.30% | -51.44% | 12.77% | -21.71% | no |
| CONSISTENCY_10 | CONSISTENCY | 11.86% | -55.03% | 11.29% | -25.06% | no |
| INVERSEVOL_01 | INVERSEVOL | 10.53% | -50.84% | 10.28% | -23.23% | no |
| INVERSEVOL_02 | INVERSEVOL | 12.00% | -49.90% | 11.47% | -22.34% | no |
| INVERSEVOL_03 | INVERSEVOL | 12.19% | -50.17% | 11.54% | -23.77% | no |
| INVERSEVOL_04 | INVERSEVOL | 12.19% | -50.26% | 11.51% | -23.86% | no |
| INVERSEVOL_05 | INVERSEVOL | 12.31% | -50.42% | 11.57% | -24.00% | no |
| INVERSEVOL_06 | INVERSEVOL | 12.29% | -50.48% | 11.52% | -24.12% | no |
| INVERSEVOL_07 | INVERSEVOL | 12.32% | -50.47% | 11.60% | -24.10% | no |
| INVERSEVOL_08 | INVERSEVOL | 12.33% | -50.52% | 11.69% | -24.11% | no |
| INVERSEVOL_09 | INVERSEVOL | 12.37% | -50.64% | 11.79% | -24.03% | no |
| INVERSEVOL_10 | INVERSEVOL | 12.39% | -50.75% | 11.78% | -23.95% | no |
| INVERSEDOWN_01 | INVERSEDOWN | 9.54% | -52.50% | 10.54% | -23.32% | no |
| INVERSEDOWN_02 | INVERSEDOWN | 10.42% | -54.43% | 11.13% | -21.44% | no |
| INVERSEDOWN_03 | INVERSEDOWN | 12.10% | -49.47% | 11.40% | -22.34% | yes |
| INVERSEDOWN_04 | INVERSEDOWN | 12.47% | -49.26% | 11.71% | -23.14% | yes |
| INVERSEDOWN_05 | INVERSEDOWN | 12.37% | -49.67% | 11.69% | -23.33% | yes |
| INVERSEDOWN_06 | INVERSEDOWN | 12.36% | -50.00% | 11.46% | -23.67% | no |
| INVERSEDOWN_07 | INVERSEDOWN | 12.34% | -49.98% | 11.56% | -23.74% | yes |
| INVERSEDOWN_08 | INVERSEDOWN | 12.38% | -50.10% | 11.74% | -23.71% | no |
| INVERSEDOWN_09 | INVERSEDOWN | 12.42% | -50.09% | 11.83% | -23.85% | no |
| INVERSEDOWN_10 | INVERSEDOWN | 12.43% | -50.43% | 11.83% | -23.61% | no |
| VOLCAPEQ_01 | VOLCAPEQ | 7.49% | -24.33% | 5.52% | -10.96% | yes |
| VOLCAPEQ_02 | VOLCAPEQ | 8.41% | -31.83% | 6.70% | -14.60% | yes |
| VOLCAPEQ_03 | VOLCAPEQ | 9.11% | -38.11% | 7.62% | -18.16% | yes |
| VOLCAPEQ_04 | VOLCAPEQ | 9.58% | -42.93% | 8.29% | -21.66% | yes |
| VOLCAPEQ_05 | VOLCAPEQ | 10.16% | -47.78% | 9.31% | -24.99% | no |
| VOLCAPEQ_06 | VOLCAPEQ | 7.37% | -29.92% | 5.14% | -11.95% | yes |
| VOLCAPEQ_07 | VOLCAPEQ | 8.33% | -38.64% | 6.32% | -15.87% | yes |
| VOLCAPEQ_08 | VOLCAPEQ | 9.15% | -45.77% | 7.48% | -19.71% | yes |
| VOLCAPEQ_09 | VOLCAPEQ | 9.95% | -48.75% | 8.76% | -23.46% | yes |
| VOLCAPEQ_10 | VOLCAPEQ | 11.10% | -50.39% | 10.16% | -25.49% | no |
| VOLCAPMKT_01 | VOLCAPMKT | 7.72% | -24.71% | 6.72% | -10.48% | yes |
| VOLCAPMKT_02 | VOLCAPMKT | 8.67% | -32.22% | 8.18% | -14.00% | yes |
| VOLCAPMKT_03 | VOLCAPMKT | 9.40% | -38.02% | 9.34% | -17.45% | yes |
| VOLCAPMKT_04 | VOLCAPMKT | 9.86% | -42.44% | 10.29% | -19.72% | yes |
| VOLCAPMKT_05 | VOLCAPMKT | 10.56% | -46.71% | 11.73% | -21.96% | yes |
| VOLCAPMKT_06 | VOLCAPMKT | 7.61% | -30.80% | 6.29% | -9.56% | yes |
| VOLCAPMKT_07 | VOLCAPMKT | 8.65% | -39.59% | 7.88% | -12.73% | yes |
| VOLCAPMKT_08 | VOLCAPMKT | 9.57% | -45.36% | 9.53% | -15.84% | yes |
| VOLCAPMKT_09 | VOLCAPMKT | 10.36% | -47.43% | 10.94% | -18.90% | yes |
| VOLCAPMKT_10 | VOLCAPMKT | 11.29% | -49.15% | 12.45% | -19.83% | yes |
| CPPIFIXED_01 | CPPIFIXED | 11.21% | -48.55% | 7.53% | -16.02% | yes |
| CPPIFIXED_02 | CPPIFIXED | 11.94% | -49.55% | 12.67% | -24.38% | yes |
| CPPIFIXED_03 | CPPIFIXED | 12.07% | -49.55% | 13.28% | -24.38% | yes |
| CPPIFIXED_04 | CPPIFIXED | 12.10% | -49.55% | 13.56% | -24.38% | yes |
| CPPIFIXED_05 | CPPIFIXED | 12.10% | -49.55% | 13.56% | -24.38% | yes |
| CPPIFIXED_06 | CPPIFIXED | 11.06% | -48.32% | 6.12% | -13.03% | yes |
| CPPIFIXED_07 | CPPIFIXED | 11.81% | -49.55% | 11.53% | -24.38% | yes |
| CPPIFIXED_08 | CPPIFIXED | 11.95% | -49.55% | 12.79% | -24.38% | yes |
| CPPIFIXED_09 | CPPIFIXED | 12.05% | -49.55% | 13.01% | -24.38% | yes |
| CPPIFIXED_10 | CPPIFIXED | 12.10% | -49.55% | 13.42% | -24.38% | yes |
| CPPIRATCHET_01 | CPPIRATCHET | 6.65% | -14.49% | 5.01% | -6.81% | yes |
| CPPIRATCHET_02 | CPPIRATCHET | 8.37% | -24.13% | 8.19% | -12.85% | yes |
| CPPIRATCHET_03 | CPPIRATCHET | 8.94% | -28.93% | 10.89% | -17.95% | yes |
| CPPIRATCHET_04 | CPPIRATCHET | 7.23% | -32.26% | 12.73% | -20.96% | yes |
| CPPIRATCHET_05 | CPPIRATCHET | 7.09% | -35.87% | 13.31% | -22.84% | yes |
| CPPIRATCHET_06 | CPPIRATCHET | 5.87% | -9.28% | 3.82% | -4.35% | yes |
| CPPIRATCHET_07 | CPPIRATCHET | 7.07% | -15.96% | 5.94% | -8.36% | yes |
| CPPIRATCHET_08 | CPPIRATCHET | 7.56% | -19.30% | 7.74% | -12.07% | yes |
| CPPIRATCHET_09 | CPPIRATCHET | 6.67% | -23.34% | 9.15% | -16.02% | yes |
| CPPIRATCHET_10 | CPPIRATCHET | 6.86% | -28.96% | 9.87% | -19.90% | yes |
