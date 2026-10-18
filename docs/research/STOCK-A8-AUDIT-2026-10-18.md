# A8 and stock-research audit — October 18, 2026

## A8: what actually works

Fresh read-only checks found the stock dashboard healthy (HTTP 200 on port
8502), all ten paper-account SQLite integrity checks clean, and account hashes
unchanged before and after verification. Prices represent Friday October 16;
October 18 is Sunday, so that session date itself is not stale.

The baseline $100 account is worth **$101.499345**, with **$0 realized** and
**$1.499345 unrealized simulated profit** after the existing exit-cost estimate.
Three positions remain open. The nine comparison books range from **$98.603430
to $101.811446**. Several books share identical trades and are not independent
evidence. These are paper balances, not brokerage profits or annualized returns.

The last scheduler audit still records a failed collection. October 17 recovery
was a manual, explicitly delayed recognition of precommitted orders, not proof
that the missed scheduled runs worked. Price collection depended on Codex and
an authenticated data connector on the desktop. No callable authenticated
connector is available in this session. Public Yahoo quotes **can** be fetched
directly from A8 (SPY October 16 close 763.25 in the read-only probe), but they
were not inserted into the differently sourced forward accounts. Converting
that probe into an independent account feed requires source reconciliation,
calendar/completeness checks, scheduler installation and an observed unattended
success; it has not been done by pretending the old workflow already works.

The Windows Schedule service is running. Broad task queries stalled; an exact
existing-task query also stalled. Reading task definitions directly found the
stock dashboard boot task at `StockPaperLab/Dashboard`. This verifies the
definition, not successful reboot recovery. The earlier guessed name
`stock-paper-dashboard` does not exist and is not evidence of an absent task.

The weather-submit definition was unexpectedly enabled. In accordance with the
owner's standing instruction to keep weather stopped, a bounded disable call
was made. Although the command timed out, its persisted task definition changed
from enabled=true to enabled=false. No service restart, weather order, database
deletion or sport-account change was made. Scheduler command completion remains
an operational issue; definition persistence alone is not an end-to-end run test.

## Reproduced historical evidence

The earlier return claim was recovered from Tester.zip and checked against Git
history rather than inferred from memory. The QQQ/BIL model allocates 98% to QQQ
above its ten-month moving average, otherwise BIL, with 2% cash. It uses monthly
signals and next-session adjusted opening proxies.

| Replayed history | CAGR | Maximum closing drawdown |
|---|---:|---:|
| QQQ/BIL, 2016–2025, 10bp/side | 16.40% | 28.04% |
| QQQ/BIL, June 2007–2025, 10bp/side | 12.12% | 28.07% |
| QQQ/BIL, same longer interval, 50bp/side plus two-session delay | 10.55% | 30.24% |

A8's independent replay matched all **18 scenarios** and all **13 available
daily paths**, with unchanged account hashes. The longer result covers 18.58
years because BIL did not exist throughout a full twenty-year window. Its
negative calendar years were 2008, 2010, 2015, 2016 and 2022; 2008 was -20.07%.
Final positions in this archived implementation are marked, not liquidated.
The same-vendor archive validates reproducibility, not independent price truth
or an untouched out-of-sample test.

A separate fresh replay used the previously reviewed sector engine recovered
from commit `02db162`, consuming selected hashed prices from Tester.zip. It
tested 15 fixed strategy/cost scenarios across 5,031 sessions, 2006–2025, with
terminal liquidation. At 10bp per traded side:

| Strategy | CAGR | Maximum closing drawdown | Worst calendar year |
|---|---:|---:|---:|
| SPY buy-and-hold | 10.87% | 55.19% | -36.80% |
| Equal-weight sectors | 10.18% | 53.51% | -35.48% |
| Sector momentum | 8.80% | 46.63% | -29.69% |
| SPY trend filter | 8.12% | 26.08% | -22.06% |
| Sector momentum plus trend | 6.27% | 25.22% | -12.03% |

The active rules reduced some drawdowns but none exceeded SPY's full-period
CAGR. No tested rule delivered at least 10% every calendar year. Negative
results and the higher-cost scenarios are retained.

## Expanded universe and actual source coverage

Official SPY holdings dated October 15 supplied **503 share classes**. A
timestamped, non-atomic social snapshot supplied 837 unique mentions: 185
already in SPY, 132 ETF/test entries, 28 excluded security types, 21 requiring
security-type review, 42 unmatched listings and **429 additional common-share
candidates**. This is 71 short of the requested 500 extras. It does not establish
that every candidate has adequate history, liquidity or useful news coverage.

The [source register](STOCK-SOURCE-REGISTER-2026-10-18.md) records the named
ratings/news sites and additional academic, exchange, fund-sponsor and social
sources, including locked or failed access. Today's ratings and popularity
cannot be inserted into a 2006 signal. Price-only simulations do not substitute
for a full stock-by-stock fundamental/news review.

An expanded price-history replay is governed by the [frozen finite protocol](STOCK-EXPANDED-REPLAY-PROTOCOL-2026-10-18.md).
Current membership/popularity makes it explicitly survivor-selected. It is
diagnostic, never a promotion test or a promise of achievable future returns.
IPOs without its required 253-session history are ineligible: this does not
test buying new listings on their first trading day.

## Completed expanded replay: all arms, including failures

The sequential capture completed **933/933 requests**: 503 SPY share classes,
429 additional shares and SPY itself. It contains 3,850,607 returned rows;
42,097 failed the positive/finite/coherent OHLCV checks and remained unavailable.
Only 534 symbols have a valid first observation by January 3, 2006; this is
not a claim that all 534 have uninterrupted histories. Forty start after
January 1, 2025. Historical ticker identity, mergers and listing changes have
not been independently reconciled.

The frozen protocol tested nine stock rules and SPY at three cost levels in
two windows: **60 scenarios, 54 complete**. The 2006–2025 window contains
5,031 exact benchmark sessions. A review identified and fixed a coverage hole
before metrics ran: a truncated input could otherwise receive a twenty-year
CAGR denominator. Four regression cases now reject missing first, interior or
last sessions and a one-year slice mislabeled twenty years. The long calendar
is checked against the hash-pinned archived benchmark replay, not an independent
exchange calendar. The partial 2026 calendar is checked against the
[NYSE holiday schedule](https://www.nyse.com/trade/hours-calendars).

M = twelve-month momentum excluding the latest month; R = five-session
reversal; V = low realized volatility. Combinations average percentile ranks.
All use five equal positions, 2% cash, completed monthly signals and next-session
adjusted-opening proxies. A trend gate uses SPY's 200-session average at rebalance.
V is not profitability/quality, and these are not copies of institutional factor
portfolios. All prices and selection are retrospective current-vintage evidence.

| 2006–2025 rule | CAGR, 10bp/side | Closing drawdown, 10bp | Worst year, 10bp | CAGR, 50bp/side |
|---|---:|---:|---:|---:|
| Momentum (M) | 28.74% | 69.53% | -49.12% | 24.11% |
| Reversal (R) | Incomplete | — | — | Incomplete |
| Low volatility (V) | 5.68% | 45.85% | -30.82% | 0.86% |
| Momentum + reversal (MR) | Incomplete | — | — | Incomplete |
| Momentum + low volatility (MV) | 6.98% | 57.73% | -42.47% | 0.95% |
| Reversal + low volatility (RV) | 9.76% | 46.25% | -22.71% | 0.43% |
| All three (MRV) | 11.47% | 37.73% | -28.14% | 2.23% |
| Momentum with trend gate | 25.79% | 61.84% | -23.84% | 21.70% |
| All three with trend gate | 9.85% | 24.74% | -20.13% | 2.44% |
| SPY control, 98% invested | 10.77% | 54.33% | -36.19% | 10.73% |

**These high momentum returns do not establish achievable alpha.** Today's
surviving stocks and current popularity selected the historical universe. The
largest historical winners can therefore be overrepresented before they became
known. Neither an apparently causal price formula nor a future-price perturbation
test removes this universe-selection look-ahead bias. No completed arm delivered
at least 10% in all twenty years, and no winner was promoted.

R stops on November 12, 2025 (FISV's captured OHLCV is missing), and MR stops on
November 8, 2024 (CLSK has a zero-volume, flat-price row rejected as invalid).
Each fails at all three costs. These paths are **unscored**;
we did not delete the affected position, set its return to zero or choose an
alternate universe after seeing results. Corporate-action/data repair requires
separate evidence and a versioned rerun.

For completeness, the separate January–October 16, 2026 diagnostic returned:

| Rule | Partial-year net return, 10bp/side |
|---|---:|
| M | 87.38% |
| R | 22.56% |
| V | 4.11% |
| MR | 117.85% |
| MV | 20.97% |
| RV | 10.36% |
| MRV | 27.02% |
| M with trend gate | 28.92% |
| MRV with trend gate | 11.88% |
| SPY | 11.71% |

Those figures are **not annualized, untouched out-of-sample evidence or forward
paper gains**. Current popularity was observed after this interval, so its
selection bias is especially direct. Complete 10/25/50bp results, yearly returns,
decision timestamps, daily costs and equity paths are retained privately in
`data/audit-20261018/expanded-results/`. The sector study uses a different exposure
convention and archived price vintage; its 10.87% SPY CAGR should not be confused
with this study's 98%-invested, freshly captured 10.77% control.

## Reproduction and crash recovery

A8 ran the identical capture and source in a new isolated research stage under
`C:/Users/jloo1/Documents/stock-paper-lab-20260928/data/equities/strategy-lab/audit-20261018/expanded-stage`.
The 2,095-file package SHA-256 is
`32cf94ec05fc8872bc7974624722fb08e7710cea637086d26c8eb542ff36b14c`.
Its ten new engine tests passed there. All **56 CSV files** (54 complete daily
paths, the all-scenario table and annual table) matched the local run at
relative tolerance 1e-10 / absolute tolerance 1e-8. All ten paper-account database
hashes remained unchanged. This validates reproducibility across the two hosts,
not independent vendor truth or profitability. It does not activate a new
production strategy or cure the unattended collector dependency.

The private package contains the exact capture, protocol, pure source, tests,
collectors and `data/audit-20261018/run_expanded.py`. With the existing dependencies
and `PYTHONPATH` pointing at that stage's `src`, the reproduction command is:

```powershell
python data/audit-20261018/run_expanded.py
```

Run from a **fresh extracted stage**: existing results are intentionally refused,
the protocol/capture/reference hashes are checked, and incomplete downloads
cannot silently become a partial-universe backtest. Do not overwrite prior
evidence or point research scripts at forward-account ledgers.

## Verification and remaining deployment boundary

- Local full test run: 2,236 passed, 25 skips; zero failures/errors. The skips
  comprise 24 platform/environment shell tests and one unavailable archived
  equity capture. Network integration tests were excluded by the project marker.
- Targeted equity/research suite: 382 passed, one skip.
- Existing recovery/history/accounting checks: 61 passed locally and 61 on A8.
- Recovered sector-engine checks: 22 passed.
- New engine accounting/causality/coverage checks: ten passed locally and on A8.
  The full run above preceded the four coverage regression cases; they were
  verified separately after the review fix.
- Strict mypy: 201 source files passed. Changed Python lint/format passed.
  This test invocation did not measure coverage; no new coverage claim is made.

Private evidence is in `data/audit-20261018/`, with source hashes, raw responses,
JUnit reports, complete result tables and A8 read-only receipts. The original
dirty checkout was preserved. Research code is on
`codex/expanded-stock-audit-20261018`; it is not merged or activated as a strategy.

Independent unattended collection, original historical index membership,
delisted-company returns, historical ratings/news vintages and realistic IPO
execution remain separate required work. A green test suite and a positive
survivor-selected simulation do not close those gaps.
