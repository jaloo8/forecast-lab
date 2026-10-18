# A daily adaptive stock-signal challenger

**Proposed decision for review:** one transparent, versioned hypothesis whose inputs change daily. Keep the nine approved baseline portfolios, their strategies, caps, $100 starting balances and 10 bp per-side costs frozen. This note supports the [proposed design](../superpowers/specs/2026-09-29-adaptive-stock-signals-design.md); it activates no challenger, establishes no edge, authorizes no real trading, and promises no return.

## Primary evidence and its limits

| Primary source | Supported lesson | Boundary for this experiment |
|---|---|---|
| Moskowitz, Ooi and Pedersen, *Time Series Momentum* (2012), abstract and sections 4–5 ([paper](https://fairmodel.econ.yale.edu/ec439/mosk.pdf)) | Past returns and risk scaling can define a systematic hypothesis; time-series momentum and cross-sectional momentum are distinct constructions. | Main evidence covers 58 futures instruments across several asset classes, including long/short positions and longer formation horizons. It does not validate daily SPY-relative signals in a selected long-only stock universe. |
| Moreira and Muir, *Volatility-Managed Portfolios*, author manuscript (2016; published 2017), Table I and Tables IV–V ([paper](https://law.yale.edu/sites/default/files/area/workshop/leo/leo17_moreira.pdf)) | Their managed factor portfolios use lagged realized variance to change exposure, with explicit cost and leverage analyses. | Evidence concerns portfolio/factor exposure management, including long/short factors. Dividing a stock momentum score by volatility is our hypothesis, not a replication or a guarantee of lower portfolio drawdown. |
| Novy-Marx and Velikov, *A Taxonomy of Anomalies and Their Trading Costs*, section 5.1 ([author-hosted paper](https://mysimon.rochester.edu/novy-marx/research/ToAatTC.pdf)) | Stricter entry than continuation criteria can reduce turnover and costs; their buy/hold spread retains positions outside the entry range. | Their broad stock anomaly portfolios include long/short constructions. Their percentile examples and estimated costs are not calibrated thresholds or costs for this $100 book. |
| Bailey, Borwein, López de Prado and Zhu, *The Probability of Backtest Overfitting*, introduction and section 2 ([author-hosted paper](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)) | Selection across many tested configurations can create apparent performance; an ordinary holdout alone does not account for that search. | Their CSCV/PBO procedure requires a usable historical performance matrix. A short forward pilot cannot supply a credible PBO estimate or prove alpha. |
| SEC, *Webmaster Frequently Asked Questions*, “How can I understand EDGAR Timestamps?” ([official FAQ](https://www.sec.gov/about/webmaster-frequently-asked-questions)) | Reporting period, filing date and acceptance time are different; SEC states it has no timestamp for first website availability. | A quarter-end date or acceptance timestamp alone cannot prove that our pipeline had an earnings fact at decision time. |

These sources motivate mechanisms and research controls. None establishes that this combination beats SPY, the nine baselines, or cash after costs. A selected surviving-stock universe also limits generalization to the wider market.

## Candidate `adaptive_relative_momentum_v1`

The following is a **new, unvalidated design choice**, not a formula taken from those papers. Freeze its exact definition before its first eligible forward observation. Use one completed-session capture daily, with UTC `as_of`; do not infer execution at that already-known closing price.

Let `P_i,t` and `P_SPY,t` be positive, consistently split-adjusted closing prices available in that capture. Require 61 synchronized real, positive-volume completed regular-session prices, with no forward-filling missing sessions. The current source omits dividends: label results price-only. Freeze the adjustment policy and preserve original captures so later revisions cannot rewrite earlier decisions. The linked design retains the existing entry eligibility filters; they do not prevent evaluating an already-held name for exit.

```text
x_i,d = log(P_i,d / P_i,d-1) - log(P_SPY,d / P_SPY,d-1)
m_i,L = sum(x_i,d over the last L completed trading sessions)
sigma_i,20 = sample_standard_deviation(stock i daily log returns over last 20 sessions; ddof=1)
z_i,L = m_i,L / (sigma_i,20 * sqrt(L))
score_i,t = 0.5 * z_i,20 + 0.5 * z_i,60
```

Here “relative” means benchmark-relative returns, not a cross-sectional winner-minus-loser portfolio. Each numerator also equals the log change in the stock/SPY price ratio over its window. The denominator uses **own-stock daily log-return volatility over 20 sessions for both horizons**. Zero or nonfinite volatility makes the signal unavailable; no arbitrary denominator substitution is permitted. The score is a dimensionless descriptive statistic, **not** a probability, expected return, calibrated confidence or independent-observation t-statistic. The 20/60 horizons, equal weights, volatility normalization and thresholds below are all unvalidated choices. Changing any creates a new protocol version and fresh evaluation period.

| Valid score and current challenger holding | Daily action | Meaning |
|---|---|---|
| No holding, score >= 0.5 | BUY | Eligible to enter, subject to the separately frozen challenger allocation and cash rules. |
| Holding, score <= 0 | SELL | Exit that position when a valid future execution price is captured; never open a short. |
| Holding, score > 0 | HOLD | Keep existing shares. A high score does not trigger repeated top-ups. |
| No holding, score < 0.5 | WATCH | Remain in cash. |
| Missing/stale/invalid input | WAIT_DATA | Signal unavailable; suppress new model actions and record the reason. Do not present a fabricated HOLD as a valid evaluation. |
| Entry or exit already pending | PENDING | Retain recorded intent without duplicating it on a retry. |

The gap between entry and exit is hysteresis: scores can move within the band without generating trades. A position can still lose money while outperforming a falling benchmark; this candidate includes no absolute-return protection. Volatility normalization does not change account caps and does not replace portfolio risk controls. A new earnings/news observation can update context without forcing a trade.

**Signal versus portfolio contract:** this note fully specifies the candidate score and action mapping, not a complete allocation engine. Any funded paper challenger must have its own protocol ID, launch time, $100 virtual cash ledger, input hashes and explicitly frozen allocation/cap rules before launch. Reuse approved caps unchanged unless the owner authorizes a change. Capital-blocked BUY actions remain visible as unfilled; an action is not a fill. Freeze deterministic tie-breaking, fractional-share assumptions, execution timing, stale-price policy and corporate-action accounting. This must not alter any baseline ledger or redistribute their cash.

## Earnings and news are verified context

Attach structured context to each daily row: event type, matched issuer, source URL, first-observed text/hash, publisher timestamp, first retrieval time, revisions and `usable_at`. For a prospective observation, use `usable_at = max(verified publication time, first retrieval time)`; if publication time is unavailable, use first retrieval and label that limitation. Preserve source timezone and normalized UTC. SEC acceptance time can be retained as a separate field, not substituted for first retrieval. This conservative pipeline policy follows from the [SEC timestamp distinction](https://www.sec.gov/about/webmaster-frequently-asked-questions).

For earnings, distinguish a scheduled announcement from a released result. Archive calendar versions; never treat the eventual announcement date as if it had always been known. Verify reported figures and fiscal periods against an issuer release or filing. A “surprise” requires the consensus snapshot captured before the release; today's consensus cannot recreate it. News must have an unambiguous entity match and actual source content; a search snippet or revised headline is insufficient.

For v1, context explains what was observable and flags missing coverage. It does **not** add LLM sentiment points, change score weights, or override actions. An event gate or news response belongs in a separately predeclared challenger after point-in-time event capture exists. Do not infer “no relevant news” from a failed feed. No new endpoint or dependency is authorized by this research note.

## Evaluation and stopping unlogged retuning

1. Register the formula, universe eligibility, execution rule, cost model and outcome before the future start. Preserve every attempted variant, including this research-driven choice and earlier failed experiments. Daily new inputs are adaptation; changing rules after inspecting results is another trial.
2. Use chronological walk-forward replay for debugging and descriptive robustness: for every decision, compute only from the prefix available then and simulate at the next eligible captured executable price. Do not repeatedly tune against a nominal “test” period. This candidate needs no fitted parameters. Any later fitted challenger must train only before each test block, prevent overlapping future outcome labels from leaking across its boundary, and reserve a fresh prospective period. Walk-forward ordering alone does not remove selection bias; that follows from [Bailey et al.'s search critique](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).
3. Account for **10 bp on each filled buy and sell**, applied to transacted notional, plus declared spread/slippage treatment. A $100 buy-and-sell turnover of roughly $200 costs roughly $0.20 before price changes. Ten bp is a simulation assumption, not a verified executable quote. A separate sensitivity report may show higher friction without changing the frozen official ledgers. Track turnover and zero-trade days so hysteresis can be assessed directly; [Novy-Marx and Velikov](https://mysimon.rochester.edu/novy-marx/research/ToAatTC.pdf) motivate measuring the net effect rather than assuming it.
4. Report net marked equity including open positions, drawdown, cash exposure, turnover, costs, coverage/staleness, filled versus blocked actions and common-date comparisons with the nine baselines and SPY. Keep passive SPY's different cash/risk exposure visible. Reuse the [parallel-book multiple-testing controls](PARALLEL-STOCK-TESTING-2026-09-28.md); this is an additional tested hypothesis, not an independent replication. The 60-session review remains operational and descriptive.
5. Preserve daily state and trade intent/fill IDs so reruns cannot duplicate an entry or erase an exit. If data or bookkeeping are invalid, mark the run invalid and repair provenance; do not silently substitute data or tune the signal. Keep original results and amendments. A later rule version needs a new start and its own outcomes, without rewriting the old track record.

**Falsifiable claim to examine:** this frozen challenger may retain useful benchmark-relative momentum exposure while reducing unnecessary turnover through a continuation band. Test net performance and turnover jointly against the frozen comparators. Lower turnover alone is not alpha; positive short-run P&L is not proof, and no result promises future returns.
