# Stock direction experiment: results and decision

Completed October 10, 2026. **The registered price controls did not establish useful up/down prediction.** All seven rule/horizon combinations had lower absolute-direction accuracy than an always-up diagnostic on the same completed observations. We retain the negative result and do not promote or retune a strategy. Earnings, corporate relationships and social/news enhancements remain **not tested** because their point-in-time inputs were not supplied.

All **504 aggregate groups**, including empty/status/epoch groups and every metric, are published: [10 bps](STOCK-DIRECTION-GROUPS-2026-10-10-c10.csv), [25 bps](STOCK-DIRECTION-GROUPS-2026-10-10-c25.csv), [50 bps](STOCK-DIRECTION-GROUPS-2026-10-10-c50.csv). These are derived results; vendor prices remain local.

## What actually ran

- Research/protocol published first in PR #199; engine/runner/tests published in #200–#202 before performance computation. Runtime commit: `1f015d2`; protocol clarification fixed open-to-open exits before any outcomes. No rules changed after results.
- Eleven preselected surviving stocks (AAPL, MSFT, INTC, CSCO, ORCL, IBM, NVDA, AMZN, GOOGL, META, TSLA), with SPY as comparator; decisions in 2006–2025 and earlier warmup. Later IPOs do not receive invented earlier histories.
- Three rules, seven rule/horizon pairs, three transaction-cost assumptions. Every cost pass has 52,228 cohort rows: **49,001 complete, 2,677 excluded for insufficient history, 550 pending, zero unavailable mature endpoints**. That is 156,684 rows across costs, not independent trades, accounts or discoveries.
- Short signals every five observed SPY sessions; long signals every 21. Entries are next-session adjusted opens; exits are exact future adjusted opens. Short horizons are 5/20 sessions; long horizons are 6/12/18 calendar months.
- Current-vintage Yahoo adjusted prices were retrieved in October 2026. Simulated historical availability is explicitly marked; this is not original historical price receipt, historical index membership or a delisted-inclusive universe.

## Direction accuracy and a simple diagnostic

Hit rates measure the direction of distribution-adjusted wealth (including dividends), **not raw quoted-share-price changes**. A dividend can offset a quoted price decline. Fees are excluded from these direction labels and included separately in net returns. The always-up/always-outperform diagnostic was calculated **after** the registered run to expose the sample’s upward drift. It is a descriptive reference, not a newly selected or simulated investment strategy. These overlapping observations do not support binomial confidence intervals or future success probabilities.

| Rule | Horizon | Complete cohorts | Up/down accuracy | Always-up reference | Relative-direction accuracy | Always-outperform reference |
|---|---|---:|---:|---:|---:|---:|
| L12-1 | 12m | 2,353 | 53.55% | 75.31% | 52.95% | 62.56% |
| L12-1 | 18m | 2,287 | 55.40% | 78.92% | 54.09% | 63.10% |
| L12-1 | 6m | 2,419 | 51.76% | 70.57% | 50.64% | 59.61% |
| S20 | 20s | 10,466 | 50.64% | 60.04% | 50.63% | 54.17% |
| S20 | 5s | 10,499 | 50.15% | 55.72% | 50.20% | 51.63% |
| S5 | 20s | 10,472 | 50.34% | 60.04% | 50.20% | 54.16% |
| S5 | 5s | 10,505 | 49.98% | 55.73% | 50.20% | 51.64% |

S20 follows prior 20-session relative strength; S5 bets on reversal of prior five-session relative strength; L12-1 uses the prior twelve months excluding the latest month. `s` means trading sessions; `m` means calendar months. The simple references also beat every rule on relative-direction hit rate. No statistical significance or calibrated probability claim is made.

## All base-cost bullish and bearish results

10 basis points (0.10%) per side. Mean excess is percentage-point stock return minus the same-date, same-cost SPY return. **Every return shown is a hypothetical long holding**, including bearish rows. For bearish signals, a hit means a decline or underperformance respectively; positive long return is not profit from a bearish trade. These are complete-cohort descriptive means with pending counts still disclosed above, not qualified all-outcome aggregates or portfolio CAGR.

| Rule | Horizon | Signal | Complete | Mean long return | Mean excess vs SPY | Absolute-direction hit | Relative-direction hit | Worst long cohort |
|---|---|---|---:|---:|---:|---:|---:|---:|
| L12-1 | 12m | bearish | 898 | 35.70% | 22.19% | 21.49% | 37.42% | -70.14% |
| L12-1 | 12m | bullish | 1,455 | 25.12% | 14.04% | 73.33% | 62.54% | -79.37% |
| L12-1 | 18m | bearish | 868 | 58.79% | 37.38% | 19.01% | 38.13% | -65.44% |
| L12-1 | 18m | bullish | 1,419 | 42.04% | 25.09% | 77.66% | 63.85% | -76.66% |
| L12-1 | 6m | bearish | 919 | 15.55% | 9.26% | 25.24% | 38.19% | -69.51% |
| L12-1 | 6m | bullish | 1,500 | 11.92% | 6.20% | 68.00% | 58.27% | -63.34% |
| S20 | 20s | bearish | 4,834 | 1.72% | 0.92% | 39.82% | 46.17% | -47.73% |
| S20 | 20s | bullish | 5,632 | 1.84% | 1.12% | 59.93% | 54.46% | -58.99% |
| S20 | 5s | bearish | 4,850 | 0.28% | 0.24% | 43.96% | 48.45% | -36.22% |
| S20 | 5s | bullish | 5,649 | 0.31% | 0.26% | 55.46% | 51.71% | -35.62% |
| S5 | 20s | bearish | 5,377 | 1.78% | 1.03% | 40.56% | 46.14% | -58.99% |
| S5 | 20s | bullish | 5,095 | 1.79% | 1.02% | 60.67% | 54.48% | -47.73% |
| S5 | 5s | bearish | 5,393 | 0.29% | 0.24% | 44.39% | 48.60% | -36.22% |
| S5 | 5s | bullish | 5,112 | 0.31% | 0.27% | 55.87% | 51.90% | -35.62% |

The long-term bullish means look attractive in isolation, but the bearish-labelled stocks also rose substantially. At twelve months they averaged **35.70% long return versus 25.12% for bullish-labelled stocks**. This survivor-selected sample contains famous eventual winners; positive historical growth is not evidence that the signal identifies the winners beforehand. This comparison is descriptive and is not a newly fitted contrarian rule.

## Cost sensitivity: bullish cohort mean long returns

| Rule | Horizon | 10 bps/side | 25 bps/side | 50 bps/side |
|---|---|---:|---:|---:|
| S20 | 5s | 0.31% | 0.01% | -0.49% |
| S20 | 20s | 1.84% | 1.54% | 1.03% |
| S5 | 5s | 0.31% | 0.01% | -0.49% |
| S5 | 20s | 1.79% | 1.49% | 0.98% |
| L12-1 | 6m | 11.92% | 11.59% | 11.03% |
| L12-1 | 12m | 25.12% | 24.75% | 24.13% |
| L12-1 | 18m | 42.04% | 41.62% | 40.91% |

The five-session bullish variants are approximately flat at 25 bps/side and negative at 50. Benchmark-relative excess does not prove positive net profit: equal costs charged to both stock and SPY can leave an excess-return comparison positive while both lose money. No borrow fees, shorts, leverage, options, taxes or real spread measurements are modeled.

## Fixed-period checks

Base cost, mean long excess versus SPY. Each epoch includes only cohorts whose decision **and exit** fall inside it; cross-boundary outcomes remain in overall results and their own local report group. Pending/excluded rows remain unresolved. Values below are not risk-matched sector alpha.

| Rule | Horizon | Signal | 2006–2012 excess | 2013–2019 excess | 2020–2025 excess |
|---|---|---|---:|---:|---:|
| S20 | 5s | bullish | 0.24% | 0.29% | 0.23% |
| S20 | 5s | bearish | 0.17% | 0.19% | 0.38% |
| S20 | 20s | bullish | 1.04% | 1.11% | 1.11% |
| S20 | 20s | bearish | 0.64% | 0.80% | 1.33% |
| S5 | 5s | bullish | 0.30% | 0.29% | 0.22% |
| S5 | 5s | bearish | 0.14% | 0.20% | 0.39% |
| S5 | 20s | bullish | 0.91% | 0.99% | 1.15% |
| S5 | 20s | bearish | 0.80% | 0.96% | 1.28% |
| L12-1 | 6m | bullish | 4.97% | 6.41% | 8.33% |
| L12-1 | 6m | bearish | 9.07% | 7.29% | 8.02% |
| L12-1 | 12m | bullish | 10.74% | 17.21% | 16.53% |
| L12-1 | 12m | bearish | 19.09% | 11.03% | 15.83% |
| L12-1 | 18m | bullish | 20.20% | 32.59% | 25.91% |
| L12-1 | 18m | bearish | 22.32% | 15.51% | 27.36% |

Positive excess in both bullish and bearish groups is a warning against attributing this sample’s stock performance to signal discrimination. No strategy passes an investment qualification on these tables.

## Independent verification and reproduction

- Full local suite: **2,231 passed, 25 skipped, one integration test deselected**. Skips are 24 POSIX/logrotate host checks and one absent archived capture. All 42 new tests passed; repository lint/format and strict typing across 199 source files passed. Independent implementation review approved. GitHub CI is reported separately from these local checks.
- Independent standard-library recalculation from raw ZIP price rows checked all 156,684 output rows: feature windows, relative normalization, direction signs, UTC simulated clocks, cadence, next-open entries, separately implemented session/month endpoint mapping, returns, costs and both hit flags.
- **883,668 numeric comparisons passed**, maximum absolute discrepancy `3.56e-15`. Source/cohort hashes and decision uniqueness passed. This uses the same vendor source; it does not independently certify prices, survivorship or a predictive edge.
- Machine-readable audit: [STOCK-DIRECTION-AUDIT-2026-10-10.json](STOCK-DIRECTION-AUDIT-2026-10-10.json). Reproduction identifiers: [STOCK-DIRECTION-RUN-2026-10-10.json](STOCK-DIRECTION-RUN-2026-10-10.json).
- Full local cohort CSVs and all group/status tables are under `data/directional-study/2026-10-10-registered-v1/`. They stay out of Git along with vendor price files, the 2.7 GB ZIP and browser/runtime material.

```powershell
uv run python scripts/run_directional_study.py --archive C:/path/to/Tester.zip --output data/directional-study/a-new-run
```

Use the original archive whose SHA-256 is in the run manifest. The output directory must not already exist. The runner verifies the frozen input hashes and writes fresh code/protocol/source metadata. Reproduction is offline and executes no attached Python code.

## What happens next

1. Keep these controls frozen. Do not reverse the long signal or optimize thresholds simply because this sample now suggests it.
2. Audit a small authentic corporate-event sample: original release/filing availability, as-filed financials and immutable evidence versions. Compare event-only and event-plus-price with the same price-only control universe.
3. Verify a delisted-inclusive historical source, corporate-action handling and dated security/company mappings before a market-wide claim. Do not buy data until its sample coverage meets the protocol.
4. Add relationship/social triggers only after dated disclosures, original-call coverage and permitted access exist. For callsbyjmo, preserve wins, misses, edits and ambiguities; no verified complete ledger is available here.
5. Freeze any surviving evidence-enhanced candidate before future paper testing; evaluate net value and calibration only on genuinely unseen observations. No current stock calls can be justified from a dataset ending in 2025.

The result is a reproducible research tool and a useful rejection of these simple directional rules in this sample. The requested full news/social/fundamental stock-selection edge remains an open research question.
