# Expanded-universe retrospective replay (frozen before results)

This is a current-universe diagnostic, not an unbiased historical investment
universe or a new paper-trading instruction. Freeze the October 18 official SPY
holdings and independently classified additional current social candidates.
Record any shortfall versus 500 additional names. Do not search other samples
after seeing performance. New IPOs enter only when their required observations
exist; missing/delisted outcomes remain unavailable, not zero or silently dropped.

## Inputs and resource budget

Request daily Yahoo chart history from January 2005 through October 16, 2026,
one symbol at a time, at most one request per second, finite timeouts, no retry
storm. Persist each response, retrieval timestamp and SHA-256. Stop on 429/403.
The source is unofficial, current-vintage, and not independent evidence of
historical data availability. Keep data private. Do not feed these prices into
the Robinhood-based forward accounts or revise their past fills.

## Finite experiment

Use completed month-end signals, next-session adjusted opening-price proxies,
long-only fractional units, no leverage, a 2% cash reserve, monthly rebalancing,
10/25/50bp per traded side, and final liquidation. Evaluation is 2006–2025;
2026 through October 16 is a separately disclosed partial-year diagnostic.
All history has already been exposed to research, so neither interval is an
untouched holdout. Use SPY on the identical dates and cost assumptions.

Five equal-weight stock positions; no optimization of position count or weights.
Require 253 uninterrupted benchmark-session closes. Momentum is the previous
12 months excluding the latest 21 sessions: close[t-21]/close[t-252]-1.
Reversal is minus the latest five-session return. Low volatility is minus the
sample standard deviation of the latest 60 daily log returns. Require the
same 253-session history for every component, price and volume finite/positive,
and trailing 20-session median split-adjusted dollar-volume proxy >= $20m.
This proxy cannot establish original historical dollar eligibility.

Compare seven rank combinations: M, R, V, MR, MV, RV, MRV. Equal percentile
ranks, deterministic alphabetical tie-breaks, no sentiment probabilities and
no current analyst ratings inserted into past signals. If fewer than five
eligible names exist, stay cash. Two additional decompositions: M with a fixed
200-close SPY trend gate, and MRV with that same gate. The gate is evaluated
at rebalance and stays fixed until the next rebalance; it is not an intraday
stop. Cash earns zero. Report all nine arms at all three costs, including losses.

## Accounting and evidence gates

Use a self-financing rebalance with costs on both buys and sells and check the
cash/holdings identity every day. An absent held-price or invalid benchmark
halts that path, explicitly incomplete; do not forward-fill unknown outcomes.
Report actual sessions, CAGR, annual returns, maximum closing drawdown,
turnover/costs, missingness and performance versus SPY. Recheck future-price
perturbations leave earlier signals unchanged, and compare simple fixed-hold
and fee examples with independent arithmetic before using the engine.

There is no historical pass-to-trade gate in this diagnostic: current survivor
selection and current social popularity invalidate such a claim. Report the
full family; do not present the highest of 27 runs as a discovery. Formal
promotion requires point-in-time membership, delisted-inclusive prices,
prospective frozen evidence and independently verified execution. Existing
paper accounts, bankroll limits and weather pause remain unchanged.
