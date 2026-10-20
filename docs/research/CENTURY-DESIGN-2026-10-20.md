# Century extension: observed coverage and frozen design

This extension can measure a **100-year funded account**, July 1926 through
June 2026. It cannot supply 100 years of active signals without inventing
earlier observations. Each candidate holds the observed RF cash proxy for
78 months, then activates in January 1933. The century account therefore
contains **93.5 active years**, while the primary active-only account spans
93 complete calendar years, 1933–2025.

The [registration](century-registration-2026-10-20.json) was frozen at
2026-10-20 16:48:33.529775 UTC, before century performance, with SHA-256
`5d5baa3dc0b8b7a02e3c4ce1b39cad3651697adade3805bd195a30ee38caa641`.
The [pre-performance amendment](evidence/2026-10-20-century/pre-performance-amendment.json)
adds a separately reported century classification and clarifies the final
diagnostic period's label. It does not change a strategy or parameter.

## Actual file inspection

The [coverage receipt](evidence/2026-10-20-century/coverage.json) records hashes,
source dimensions, missing observations and exact date bounds. This was a
coverage audit, without performance comparisons.

| Standard French universe | Monthly rows available | First continuously complete month | Decision |
| --- | --- | --- | --- |
| Original 49 industries | July 1926–August 2026; 1,202 rows | July 1969 | Cannot extend the same complete universe to 1926 |
| 48 industries | Same dates and row count | July 1969 | Early missing industries |
| 38 industries | Same dates and row count | None | Every row has at least one missing industry |
| 30 industries | Same dates and row count | July 1926 | Selected by coverage |
| 12 industries | Same dates and row count | July 1926 | Complete fallback, not performance tested |
| Market/RF factors | Same dates and row count | July 1926 | Matching benchmark and cash source |

The first value-weighted monthly table was inspected in each industry file.
The 30- and 12-industry tables have no missing sentinel, nonfinite value,
duplicate or absent month, or nonpositive gross return. The 49-industry
table has nine columns with missing early observations; for example,
healthcare remains missing through June 1969. No missing value is filled.
July and August 2026 exist in the files but are outside the registered test.

The official [30-industry description](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_30_ind_port.html)
reports monthly coverage from July 1926. It describes annual assignment using
the contemporaneous SIC classification and subsequent portfolio returns.
The [12-industry](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_12_ind_port.html),
[38-industry](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_38_ind_port.html)
and [48-industry](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_48_ind_port.html)
pages were also read. A start date printed on a page does not establish
complete coverage of every column; the file checks above establish that.

Four ZIPs were downloaded once to ignored `data/century-20261020/raw`.
The factor ZIP and CSV were copied byte-for-byte from the prior free
download, preserving their original acquisition provenance. The first
aggregate-inspection script failed because it assumed every universe had
at least one complete row; the 38-industry file disproved that assumption.
All downloads survived, and the inspection was repaired offline. The
acquisition receipt records this failure rather than inventing HTTP headers
or a fresh original-download timestamp. No paid data or model call occurred.

## Scope of the adaptation

The same 200 policy dictionaries from the fifty-year registration are
inherited unchanged: 20 related mechanism families, ten configurations each.
Lookbacks, top-five/top-ten ranks, volatility targets, insurance floors and
multipliers remain fixed. Those are 200 configurations, not 200 independent
discoveries. Choosing 30 industries changes both the investable proxy
universe and the fraction held by a top-five or top-ten rule. Results must
not be presented as a longer execution record of the original 49-industry
portfolio.

The frozen `src/kq/equities/long_history.py` remains intact. A separate
`century.py` generalizes dimensions from 49 industries plus market to
30 industries plus market, adds explicit cash warmup and separates partial
calendar years. Signals and funded-cost accounting retain the prior
formulas. The equal-industry control is named `CEQ` and holds 30 industries.

The maximum lookback is 72 months. With the two-month information lag,
the mathematical earliest common index is 73, August 1932. The existing
engine's conservative minimum index 74 is retained; January 1933, index 78,
is the first complete calendar year after that point. This start was chosen
from coverage and calendar boundaries, without inspecting new performance.

| Account | Dates | Months | Initialization |
| --- | --- | --- | --- |
| Training | January 1933–December 1975 | 516 | Fresh $1,000 |
| Later evaluation | January 1976–December 2025 | 600 | Fresh $1,000 |
| Primary active full period | January 1933–December 2025 | 1,116 | Fresh $1,000 |
| Century | July 1926–June 2026 | 1,200 | Fresh $1,000; candidates in RF cash for 78 months |

Each account is run at 10, 25 and 50 basis points per risky traded side,
with information through month t−1 and t−2. The primary case is 25 basis
points and t−2. Including four controls, this is
**204 × 4 × 3 × 2 = 4,896 accounts**.

The four controls begin immediately, including market buy-and-hold. The
century candidate's early cash allocation therefore differs structurally
from the market benchmark. In particular, much of the 1929–1932 market
collapse occurs during mechanical warmup. A smaller resulting drawdown
cannot be described as successful predictive avoidance of that collapse.
The active-only screens remain available to separate this effect.

There is no wealth reset when a century candidate activates. Insurance
rules use the actual delayed funded account wealth and peak, including
cash accrual during warmup. The fixed floor remains a fraction of the
original $1,000. Separate training, evaluation and full accounts each start
fresh; they inherit neither wealth nor peaks from another account.

## Comparisons, checks and limits

Selection uses the registered training-only ordering before later accounts
are simulated. The original positive-growth, relative-drawdown and 10%/25%
CAGR screens apply to active full 1933–2025 and evaluation 1976–2025.
The additional century classification uses the same formulas, substituting
the 100-year account for active full. Its counts are kept separate and
explicitly carry the cash-warmup limitation. Empty groups and failed
configurations remain visible. Desired counts are not acceptance quotas.

The century's six-month 1926 and 2026 returns are retained separately.
They contribute to whole-account CAGR and drawdown, but not to complete
calendar-year minimums, loss counts or the every-year 10% diagnostic.
The final regime-report block covers 2023–2025, not an invented complete
2023–2032 decade. The primary later-period joint bootstrap retains all
200 candidates, 2,000 common stationary-block resamples, mean block six
months and the fixed seed. Its inference concerns the registered monthly
mean-excess statistic, not a probability of future profit.

An independent checker parses the named monthly source tables separately,
reconstructs allocations, uses a bracketing funded-fee solver, and verifies
every saved account and asset position. It also checks both classifications,
training selection, timestamps, calendar-year partitions, regimes and
bootstrap calculations. Artificial fixtures test these checks before
historical execution; they are not historical performance evidence.

The [factor description](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_factors.html)
defines market excess return and its one-month Treasury-bill cash series,
including the source transition in June 2024. Gross market return here is
Mkt−RF plus RF, with no extra dividend credit.
The [library's methodology notes](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html)
explain that history is reconstructed and can change; they also describe
the CIZ transition and dividend-reinvestment change. These files are the
current 202608 vintage, not recovered historical publications.

This is retrospective research on monthly index proxies, with known
history and previously examined later decades. It is neither an untouched
holdout nor a century of executable $1,000 brokerage records. Monthly marks
miss intramonth losses; basket reconstruction, constituent turnover,
settlement, taxes and practical ticket sizes remain outside the model.
No real-money action or broker migration follows from this study.
