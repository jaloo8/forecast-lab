# Registered six-asset allocation study

The binding protocol is [allocation-study-registration-2026-10-20.json](allocation-study-registration-2026-10-20.json), saved at **2026-10-20 06:18:46.810626 UTC before this study's performance was computed**. Its SHA256 is `55c0b3e4e593cb72a3454464e1b21f1a701809adc9e9e6ebf76a8d9a8751086e`. This explanatory document was written later; its publication time is not represented as the preregistration time. Outcomes belong in the separately dated results report.

The objective remains at least **10% net return in every complete calendar year**, with 20% an upper reference rather than a rejection threshold, starting from **$1,000**. An annualized average of 10–20% does not satisfy that annual-floor objective. No historical outcome establishes a future annual floor.

## Why this is another study

The [previous 28-policy study](STRATEGY-FAMILY-STUDY-2026-10-19.md) examined SPY, QQQ and nine sector ETFs through trend, breakout, relative-strength, reversal, volatility and blend rules. Its [results and failures](STRATEGY-FAMILY-RESULTS-2026-10-19.md) remain unchanged.

This registration tests **eight candidates and four controls**, producing **108 funded account paths**: 12 policies × three transaction-cost assumptions × three chronological windows. Costs and windows are sensitivity or evaluation scenarios, not additional independent algorithms. The controls are repeated reference mechanisms, not new discoveries.

Three mechanisms motivate the new candidates:

- Covariance-aware allocation considers relationships between asset returns. The previous study's volatility caps and low-volatility selection did not solve these five-asset covariance-allocation problems.
- Portfolio insurance changes exposure using each actual simulated account's funded wealth and a stated floor. It therefore responds to the account's own costs and losses.
- Online allocation updates a portfolio from completed monthly observations, using either virtual expert wealth or an exponentiated-gradient update.

The six-asset menu—**SPY, EFA, IEF, VNQ, GLD and BIL**—also differs from the previous sector menu. It is already present in the private parent project's earlier research. Reusing that known basket and its historical prices is not a newly discovered universe or an untouched experiment. This study's covariance rules, insurance rules and online rules are separate local adaptations; a family resemblance to earlier work does not erase earlier trials.

## Fixed policy inventory

| ID | Policy | Scheduled trading |
| --- | --- | --- |
| C01 | Zero-yield cash | None |
| C02 | BIL buy and hold | Initial purchase and terminal liquidation |
| C03 | SPY buy and hold | Initial purchase and terminal liquidation |
| C04 | Equal SPY/EFA/IEF/VNQ/GLD allocation | Monthly |
| A01 | Minimum variance across those five assets, with a 50% per-asset cap before the common budget multiplier | Monthly |
| A02 | Equal contribution to portfolio variance across those five assets | Monthly |
| I01 | Fixed-floor CPPI with SPY as the risk sleeve | Daily |
| I02 | Fixed-floor CPPI with an equal five-asset risk sleeve | Daily |
| I03 | Ratcheting-floor insurance with SPY as the risk sleeve | Daily |
| I04 | Ratcheting-floor insurance with an equal five-asset risk sleeve | Daily |
| O01 | Wealth-weighted finite-grid portfolio mixture | Monthly |
| O02 | Exponentiated-gradient allocation | Monthly |

The account engine applies the **0.98 total target multiplier once**. Thus a fully allocated policy targets 98% in its asset mix and leaves 2% uninvested at rebalancing. BIL is a priced ETF with its own return and trading costs; it is not identical to the zero-yield cash balance. Buy-and-hold weights can drift after entry.

For A01/A02, covariance uses the last **126 completed daily returns**, sample covariance with `ddof=1`, and the fixed matrix `0.5 × covariance + 0.5 × diagonal(covariance)`. A01 minimizes portfolio variance subject to nonnegative weights summing to one and each weight at most 0.5. A02 equalizes the five contributions `w_i × (Sigma × w)_i`. Missing warmup means no allocation until the feature is ready. Invalid or degenerate covariance and solver nonconvergence fail visibly; they do not silently switch to an easier policy.

## Insurance uses funded account state

Every window begins with a fresh $1,000 account, a $1,000 closing-wealth peak and an $800 initial floor. I01/I02 keep the nominal $800 floor. I03/I04 set the floor to 80% of the maximum of $1,000 and all completed closing NAVs in that account.

At each decision, let `V` be the account's previous completed closing NAV and `F` its applicable floor:

```text
e = clip(3 × (V − F) / V, 0, 1)
risk sleeve target = e
BIL target = 1 − e
submitted asset weights = 0.98 × these targets
```

The first entry uses fresh `V = 1000` and `F = 800`; subsequent decisions use that particular cost/window account's actual closing wealth. There is **no annual reset**, no inheritance of another window's positions or cash, and no use of current opening NAV to decide exposure. A gap between the previous close and execution open changes trade sizing and wealth, but not the already formed exposure fraction.

These rules are local CPPI/TIPP-style adaptations. The floor is an input to exposure, **not guaranteed protection**. Overnight gaps, costs and losses in BIL can breach it. The daily and transaction records preserve the reference NAV, peak, floor and risky fraction. Reports count breach sessions and measure the lowest observed opening/closing NAV relative to the applicable floor.

## Online portfolios are signal models

O01 uses the complete six-asset grid with weights in 25% increments: integer coordinates `k_i / 4` with `sum(k_i) = 4`. There are **126 virtual experts**. Each starts with equal weight; each completed monthly price-relative vector multiplies an expert's gross virtual wealth by its portfolio-weighted price relative. The next target is the expert-weighted mean portfolio, computed in log space.

Those 126 expert calculations are **not 126 additional funded backtests**. They exclude trading costs and serve only to construct O01's signal. The actual O01 account executes its next-open target and pays the registered costs.

O02 starts with equal six-asset weights and updates after each completed month:

```text
w_new_i ∝ w_i × exp(0.05 × x_i / (w · x))
```

The updated weights are normalized. Both online signals begin with the first common month-end in May 2007; June 2007 supplies their first complete monthly price-relative observation. They inherit historical signal state across evaluation windows, while each funded account starts from fresh cash. A final partial month is not treated as complete before the next observed month begins.

## Inputs, execution and chronological evaluation

The source is the already captured, private Yahoo Finance/yfinance snapshot `data/raw/20261006T212733Z` in the parent workspace. The source manifest SHA256 is `8fff017534111692e2a8af7288faeccca156aace022eaf1bbbfcc2ea8d688d9b`; the registration pins all six CSV hashes separately.

Common history starts on **May 30, 2007**, BIL's first observation in this snapshot. All six calendars must agree from that date. Rows after **December 31, 2025** are excluded before signal construction. There is no pre-inception synthesis, forward fill or backfill. This remains an observed provider calendar, not an independent exchange-calendar audit.

Prices are adjusted wealth units: close equals `Adj Close`, and open equals `Open × Adj Close / Close`. Distributions already embedded in those prices are not credited a second time. These units are a research accounting convention, not literal quantities of broker shares.

| Window | Dates | Purpose |
| --- | --- | --- |
| Training | 2008–2015 | Select one candidate using only this window at the primary cost |
| Evaluation | 2016–2025 | Start the selected unchanged rule from fresh cash; publish every other rule too |
| Full history | 2008–2025 | Describe the complete registered history; do not use it to revise the choice |

All paths use **10, 25 or 50 basis points per traded side**, with 25 bp primary. The same account funds entry, all rebalances and final liquidation. The reviewed self-financing solver accounts for both purchases and sales when setting post-cost holdings. Signal decisions use completed closes; orders execute at the next relevant observed open. Every account is liquidated with costs at its final observed close.

The training selector considers A01, A02, I01–I04 and O01–O02. It ranks by highest worst calendar-year return, then highest CAGR, then smallest event-drawdown magnitude, then ascending policy ID. The runner saves the training selection before computing evaluation or full-history account performance.

## Validation and limits

The runner requires the frozen registration hash and a passing independent pre-performance review whose source hashes match the current implementation. Artificial tests cover causal prefixes, future-price changes, allocation calculations, funded insurance references, self-financing trades, terminal costs, source integrity and selection boundaries. Artificial tests are software evidence; they are not market returns.

The separate accounting checker reconstructs saved account cash flows and NAV from the source prices and recorded transactions. Results retain all cases, including losses, zero returns, low balances, floor breaches and failures. Required reports include all calendar years, CAGR, drawdown, costs, turnover, same-date SPY comparisons and sub-dollar traded legs.

The study has **no additional execution-delay stress**, no intraday-extreme observations, and no claim that the next-open price plus proportional cost reproduces actual fills. A $1,000 fractional adjusted-unit model does not establish broker support for fractionals, minimum tickets, settlement, dividend payment timing, taxes or subscriptions. Small trades are counted rather than silently discarded.

All these market years and substantial prior research are already known. The chronological split is useful process discipline but is **not an untouched holdout**. More trials increase the chance of an attractive historical accident; the best full-history result cannot be presented as statistically established alpha. The registration adds finite tests to the existing research record and does not reset that record.

No thresholds, assets, weights, costs or windows may be retuned within this version after viewing its results. Software defects require a documented correction with prior artifacts preserved; new hypotheses require a new registration. No result automatically changes a paper strategy or authorizes live trading.

## Reproduce from a private source snapshot

Run these commands from the `forecast-lab` repository with its existing environment. The source path is an argument, not a hardcoded user directory. The first example uses the current parent-workspace layout:

```powershell
$source = "../data/raw/20261006T212733Z"
$run = "data/allocation-study-20261020/replay-new"
$review = "docs/research/evidence/2026-10-20-allocation/pre-performance-review.json"

.venv/Scripts/python.exe -m scripts.run_allocation_study --source $source --output $run --review $review
.venv/Scripts/python.exe -m scripts.check_allocation_accounting --source $source --run $run --output "data/allocation-study-20261020/replay-new-accounting.json"
```

On another computer, restore the source manifest and six CSVs into a private folder and set `$source` to that folder instead—for example, `data/private-transfer/allocation-source-20261006T212733Z`. A public Git clone does not contain these market payloads. The exact registered bytes are required; obtaining newer prices is not reproduction of this study.

Use a new output directory and a new accounting-receipt filename. A changed implementation needs a genuine review of the changed code; editing review hashes to bypass the gate is not validation. These commands use local data and require no Databento key, market-data purchase or model API call.

## Research sources and adaptation boundaries

- [Cover, *Universal Portfolios*](https://isl.stanford.edu/~cover/papers/paper93.pdf): motivation for wealth-weighted portfolio mixtures. The registered finite-grid, monthly, next-open and costed-account implementation is a local adaptation.
- [Helmbold, Schapire, Singer and Warmuth, *On-Line Portfolio Selection Using Multiplicative Updates*](https://www.schapire.net/papers/HelmboldScSiWa98.pdf): motivation for the exponentiated update. The six-ETF monthly implementation and its execution costs are specified here.
- [Griveau-Billion, Richard and Roncalli, *A Fast Algorithm for Computing High-dimensional Risk Parity Portfolios*](https://arxiv.org/abs/1311.4057): numerical-method motivation for equal risk contributions. The local covariance estimator and asset universe are separately fixed.
- [Black and Perold, *Theory of Constant Proportion Portfolio Insurance*](https://www.sciencedirect.com/science/article/abs/pii/016518899290043E): proportional-cushion motivation. The source dossier used the publisher abstract; the local fixed nominal floor and BIL implementation are not an exact paper replication.
- [Grossman and Zhou, *Optimal Investment Strategies for Controlling Drawdowns*](https://onlinelibrary.wiley.com/doi/10.1111/j.1467-9965.1993.tb00044.x): running-maximum surplus motivation. At registration the source dossier used the indexed abstract after direct page access failed. This explanatory document's later source check reached the publisher abstract; the study does not claim to reproduce the paper's optimum.

The papers motivate testable mechanisms. They do not establish this implementation's returns or solve the user's annual-floor objective.
