# Inverse-volatility allocation study — 2026-10-18

## Frozen protocol (written before loading data or computing new outcomes)

Owner-approved allocation-only comparison. ALL history has previously been viewed;
this is exploratory research, never an untouched holdout. No parameter search or
post-result changes. Preserve the original sector protocol and five strategies.

Use SPY and the same nine original sector ETFs, cached Tester.zip through the existing
verified `load_bars`, with 2004–2005 warmup and exactly the same 5,031 sessions in
2006–2025. Initial capital $10,000; monthly last-observed-close decisions execute
at the next observed session open. Reuse accounting, terminal liquidation, adjusted
prices, zero-yield cash, and 10/25/50 bp per dollar bought or sold without changes.

For each allocation decision use exactly 13 prior completed month-end closes,
including the decision close, to obtain 12 simple monthly returns. Volatility is
the sample standard deviation (`ddof=1`); weights are inverse standard deviations
normalized over the selected sectors. No volatility targeting, leverage, shorts,
clipping or alternative lookbacks. Missing, zero or nonfinite selected volatility
aborts the simulation (no fallback weights or dropped sectors). The unchanged trend
gate may select cash, in which case no volatility-based allocation is required.

Pairs: `equal_sectors_invvol` versus `equal_sectors` (all nine sectors);
`sector_momentum_invvol` versus `sector_momentum`; and
`sector_momentum_trend_invvol` versus `sector_momentum_trend`. Top-three selection,
skip-most-recent-month momentum, alphabetical ties and strict ten-month SPY trend
threshold stay identical. `spy_hold` is the benchmark; rerun `spy_trend` too solely
to verify all original results. Long-only, fully invested when active, otherwise cash.

Report every cost/strategy: CAGR, daily-close maximum drawdown, worst calendar year,
paid dollar costs, sum of traded notional / pre-trade NAV (both sides, including
entry/exit), and that turnover divided by 20 years. Report all annual returns and
fixed 2006–10/2011–15/2016–20/2021–25 block CAGRs, with inverse-vol minus original
paired differences. Supplement with daily mean return / sample standard deviation
× sqrt(252), assuming zero risk-free rate; include first-day entry cost and terminal
cost. This is a descriptive Sharpe-like ratio, not excess-return evidence.

Raw daily paths, ledgers, summaries, paired differences and hashes go under
`data/inverse-vol-20261018` (gitignored). Compare every original daily path and ledger
exactly with the existing October 18 sector rerun. No network or new dependencies.

## Results (single frozen run; no tuning)

All 24 scenarios used the same 5,031 dates. All 30 daily/ledger CSVs for the 15 original cases are byte-identical to `data/audit-20261018/sector-rerun`. No original protocol or threshold changed.

At 25 bp per traded dollar (percentages below are percent, not fractions):

| Strategy | CAGR % | Max DD % | Worst year % | Fees $ | Turnover NAV/year | Zero-RF ratio |
|---|---:|---:|---:|---:|---:|---:|
| spy_hold | 10.853 | -55.189 | -36.795 | 221.71 | 0.100 | 0.6295 |
| equal_sectors | 10.118 | -53.552 | -35.525 | 594.53 | 0.389 | 0.6123 |
| sector_momentum | 7.917 | -46.919 | -30.218 | 5027.99 | 5.402 | 0.4933 |
| spy_trend | 7.859 | -26.739 | -22.524 | 1955.46 | 1.598 | 0.6634 |
| sector_momentum_trend | 5.352 | -26.347 | -13.004 | 5165.49 | 5.773 | 0.4453 |
| equal_sectors_invvol | 9.718 | -51.268 | -33.618 | 1075.39 | 0.791 | 0.6196 |
| sector_momentum_invvol | 7.257 | -44.055 | -27.939 | 5216.22 | 6.029 | 0.4739 |
| sector_momentum_trend_invvol | 4.890 | -26.344 | -12.950 | 5216.92 | 6.240 | 0.4197 |

Inverse-vol minus original CAGR, in percentage points; all nine comparisons are negative:

| Pair | 10 bp | 25 bp | 50 bp |
|---|---:|---:|---:|
| equal_sectors | -0.334 | -0.400 | -0.510 |
| sector_momentum | -0.563 | -0.660 | -0.817 |
| sector_momentum_trend | -0.392 | -0.462 | -0.576 |

Fixed five-year paired CAGR differences at 25 bp (pp):

| Block | All sectors | Momentum | Momentum + trend |
|---|---:|---:|---:|
| 2006-2010 | -0.579 | -0.428 | -0.989 |
| 2011-2015 | +0.774 | -0.399 | -0.074 |
| 2016-2020 | +0.296 | -0.237 | +0.099 |
| 2021-2025 | -2.069 | -1.621 | -0.889 |

Annual paired wins out of 20 at 10/25/50 bp: all sectors 9/9/9, momentum 7/8/8, momentum + trend 7/7/7. Momentum loses in every five-year block at every cost; all sectors wins two blocks, and momentum + trend one, at each cost.

All sectors reduces maximum drawdown by 2.284 pp and improves the worst year by 1.907 pp at 25 bp, but annual turnover rises from 0.389 to 0.791 NAV and fees increase $480.86. Its zero-RF ratio improves only 0.0072 (just 0.0011 at 50 bp). Momentum reduces drawdown 2.864 pp but loses 0.0194 in the ratio. Trend momentum drawdown improves only 0.0022 pp at 25 bp and worsens 0.0844 pp at 50 bp; its ratio declines at all costs. Lower dollar fees for trend momentum at 50 bp reflect lower wealth, despite higher normalized turnover.

The worst year is 2008 for SPY hold, both all-sector rules and both ungated momentum rules; 2018 for both momentum + trend rules, and 2022 for SPY trend. Every inverse-vol variant has a losing year and fails any 10% annual minimum. No variant beats SPY hold CAGR at any tested cost. This does not support replacing an existing strategy on return grounds; the all-sector risk reduction is a tradeoff, not demonstrated new alpha.

## Complete evidence and verification

All costs and strategies: [metrics](../../data/inverse-vol-20261018/metrics.csv), [annual returns](../../data/inverse-vol-20261018/annual.csv), [annual paired differences](../../data/inverse-vol-20261018/annual_paired.csv) (180 pairs), [five-year CAGRs](../../data/inverse-vol-20261018/blocks.csv), [five-year paired differences](../../data/inverse-vol-20261018/blocks_paired.csv) (36 pairs). CSV values retain full precision; percentage-point differences above are rounded. Raw daily paths and trade ledgers are alongside these files.

TDD: observed 10 expected feature failures, then passing allocation tests; observed two report-helper failures before implementation. Final focused run: 35 passed (13 new, 22 existing); Ruff lint and format checks passed; focused strict mypy passed for engine and runner. Checks cover sample-vol weights/window, invalid inputs, unchanged selections/gate, next-session execution, future-data isolation, cost conservation, risk/turnover arithmetic and pairing direction.

Run: `PYTHONPATH=src:. python -m scripts.run_inverse_vol_study --archive C:/Users/jloo1/Documents/Github/forecast-lab/Tester.zip` (PowerShell: set `$env:PYTHONPATH = "src;."` first). Existing output directories are refused. Runner reuses the original loader/metrics and validates against the local baseline directory. No dependencies or network used.

Run UTC: 2026-10-19T01:02:04.553179+00:00 (October 18 Pacific). [Manifest](../../data/inverse-vol-20261018/manifest.json) retains input, source and output hashes; [frozen protocol](../../data/inverse-vol-20261018/protocol.md) preserves the pre-run text before these findings were appended. Archive SHA-256: `be6f95472460490f7dc743ce8f89571a3999b3afa044f230a81f55a06b7f2f9d`; frozen protocol SHA-256: `947b674af59357c3fddb68dd64de1e6a44ff5888983fbd78ecf4afe8641e514c`.

Limitations: all history previously viewed; descriptive exploratory evidence without a holdout, uncertainty estimates or independent tests. Current-vintage distribution-adjusted opens are wealth proxies, not executable historical quotes; fixed surviving ETFs, no taxes, zero-yield cash, simplified constant trading costs, no independent exchange-calendar verification, and daily-close (not intraday) drawdown. The zero-RF ratio is not a Treasury-excess Sharpe. No parameter, universe, selection or threshold tuning followed these results.
