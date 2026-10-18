# Twenty-year sector strategy results — October 10, 2026

**No tested strategy delivered at least 10% in every calendar year. No active rule beat SPY buy-and-hold in full-window compound growth.** This is a completed exploratory portfolio experiment, not an individual-stock selector, a new unfair advantage or a forecast of next year.

## What was frozen and run

The [protocol](SECTOR-STRATEGY-PROTOCOL-2026-10-10.md) and [26-source literature review](EQUITY-EDGE-LITERATURE-2026-10-10.md) were published before new outcomes in PR #207 (`de70b9f`). Engine and runner were pushed before computation; runtime commit `b6560f3`. No parameters changed after returns were seen. Five rules × three cost levels × 5,031 sessions = 75,465 daily NAV observations across repeated scenarios, not independent trades.

Universe: SPY and all nine original sector ETFs, 2006–2025, with 2004–2005 warmup. Monthly signals execute at the next observed open; buys/sells pay 10, 25 or 50 basis points per traded dollar, including initial entry and final liquidation. Long-only, no leverage, fractional adjusted units, zero-yield cash and no taxes. Vendor-adjusted prices approximate reinvested distributions/embedded fund expenses; they are current-vintage wealth proxies, not historical executable quotes.

## Base costs: 0.10% on each purchase or sale

| Strategy | CAGR | 2025 return | Worst calendar year | Max daily-close drawdown | Years ≥10% | $10,000 ending wealth |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SPY buy-and-hold | 10.87% | 17.60% | -36.80% (2008) | -55.19% | 14/20 | $78,749 |
| Equal-weight nine sectors | 10.18% | 13.33% | -35.48% (2008) | -53.51% | 14/20 | $69,542 |
| Top-three sector momentum | 8.80% | 15.62% | -29.69% (2008) | -46.63% | 11/20 | $53,980 |
| SPY trend / cash | 8.12% | 11.31% | -22.06% (2022) | -26.08% | 9/20 | $47,636 |
| Sector momentum + trend | 6.27% | 10.39% | -12.03% (2018) | -25.22% | 9/20 | $33,742 |

CAGR is compounded growth across 20 calendar-year investment periods, not an amount earned every year. The 2025 column is one historical year, not a next-year projection. For example, SPY’s 2025 return corresponds to about $1,760 on $10,000 present at that year’s start under this study; SPY’s 2008 result corresponds to a loss of about $3,680. The initial $10,000 was invested in 2006, with no subsequent deposits. Drawdowns measure declines from initial capital or prior daily-close peaks and can exceed any calendar-year loss.

The old 50–55% classification accuracy was not an advantage: always-up was more accurate in the selected-stock sample. This new study answers a different question using compounded portfolio wealth; do not combine the two statistics as evidence of prediction skill.

## Costs, consistency and tradeoffs

| Strategy | CAGR at 10 bps | CAGR at 25 bps | CAGR at 50 bps | Positive years at 10 bps |
| --- | ---: | ---: | ---: | ---: |
| SPY buy-and-hold | 10.87% | 10.85% | 10.83% | 17/20 |
| Equal-weight nine sectors | 10.18% | 10.12% | 10.01% | 16/20 |
| Top-three sector momentum | 8.80% | 7.92% | 6.47% | 17/20 |
| SPY trend / cash | 8.12% | 7.86% | 7.43% | 15/20 |
| Sector momentum + trend | 6.27% | 5.35% | 3.84% | 13/20 |

SPY trend reduced the measured maximum drawdown from 55.19% to 26.08%, while surrendering 2.75 percentage points of annual compound growth. Its 2022 loss was 22.06%, worse than SPY that year: a trend filter is not a loss guarantee. Sector momentum lagged both SPY and the equal-sector baseline; increasing costs hurt it substantially. Gating sector momentum reduced drawdown but compounded at only 6.27% under base costs. Positive returns alone do not establish an advantage.

All four five-year blocks, all 300 annual returns, all 15 summary rows and rolling-12-month extremes are published below. The reported rolling windows use month-end observations, not every possible daily starting date; drawdown is daily-close, not intraday. Cash interest omission disadvantages cash-heavy rules when bill yields are positive. No tax, capacity, historical quote or original data-vintage validation is claimed.

## What deserves the next stock-specific test

The strongest research candidates from the review are (1) liquid-stock momentum with turnover buffers and (2) value combined with gross profitability. Their next experiment needs a historically defined universe including delisted names and, for fundamentals, original filing availability. The cached 100-stock sample selects current survivors and omits dividends; the eleven-stock sample is illustrative. Neither can validate these strategies or an unbiased 20-year stock picker. Current SEC frames also cannot substitute for as-known-then fundamentals.

A practical advantage to investigate is patient implementation, modest turnover and disciplined evidence handling, rather than reacting faster than professional feeds. This is a hypothesis. For short-term earnings/news/relationship/social ideas, build an immutable forward event sample, retain losing calls, compare price-only and combined arms, and test delay/cost sensitivity. No complete callsbyjmo history or 20-year social archive was established. No current stock picks or future annual returns follow from this experiment.

Decision: retain the negative results, preserve the existing paper baseline and do not promote these rules. A 10–20% annualized objective can be evaluated with downside constraints; a 10% annual floor was not achieved. Do not hunt parameter combinations until one appears to satisfy the target.

## Reproduction and complete evidence

- [All metrics](SECTOR-STRATEGY-METRICS-2026-10-10.csv), [every calendar year](SECTOR-STRATEGY-ANNUAL-2026-10-10.csv), [five-year blocks](SECTOR-STRATEGY-BLOCKS-2026-10-10.csv), [run and audit record](SECTOR-STRATEGY-AUDIT-2026-10-10.json). Returns are decimals in CSVs; annual CSV has a two-level strategy/cost header.
- With the existing environment and `PYTHONPATH=src`, run `python -m scripts.run_sector_study --archive <local-Tester.zip> --output <new-output-directory>`. The archive is private and is not uploaded. Every output/input/code hash is retained in the generated manifest.
- An independent implementation re-read verified raw CSVs, reconstructed targets and solved transaction costs analytically instead of reusing engine bisection. All 75,465 daily rows, 2,898 ledger rows, 300 annual returns, 60 block CAGRs and summary metrics matched; maximum absolute monetary discrepancy was $1.223e-9. This verifies arithmetic, not an economic edge.
- Validation: 22 new synthetic tests and all 64 new/existing directional-focused tests passed; repository lint/format and strict typing passed. The full local non-integration suite passed: 2,253 passed, one integration test deselected and 25 documented skips (24 POSIX/logrotate cases on Windows and one unavailable archived capture). GitHub CI is separate and must pass before merge.
