# Fixed pairs diagnostic — registered before the result

Owner request: investigate and backtest methods in the pasted reel discussion,
using public data, minimal resources and no live orders or paid subscriptions.
This is an independently specified illustration, not reproduction of private
bot code, a fitted Ornstein–Uhlenbeck model or the original Gatev stock universe.

The guide names Coca-Cola/Pepsi as an example. Freeze that one pair (KO/PEP);
do not search other pairs or thresholds after seeing results. Reuse the hashed
October 18 Yahoo capture. Evaluation: January 2006–December 2025, exact 5,031 SPY
sessions, with 2005 warm-up. Report 2026 separately only if explicitly added in
a subsequent registered experiment; it is not part of this test.

For each completed close when flat, compute the log adjusted-close KO/PEP
ratio and its mean/sample standard deviation over the preceding 252 sessions,
excluding the signal day's ratio. At absolute z >= 2, buy the laggard and short
the leader at the next session's adjusted opening proxies. Freeze that training
mean until exit. Close at the next open after the ratio crosses the frozen mean,
after 63 held sessions, or after closing gross exposure exceeds account equity.
Do not reopen on the exit session. Final-day close liquidates remaining positions.
This finite time exit and gross-exposure rule are our assumptions, not rules
published by the reel creator. No claim of stationary spread or proven arbitrage.

Starting virtual equity $1,000. Each leg is 25% of pre-entry equity: 50% gross,
zero initial dollar net exposure. No pyramiding or reuse of short proceeds for
another trade. Cash earns zero. Charge 10/25/50 basis points on each traded
leg at entry and exit; cross these with annual short-borrow rates 0%/3%/10%.
Nine scenarios are cost sensitivities of one rule, not nine alpha discoveries.
Borrow accrues on the prior closing short value for actual calendar days,
including weekends, through exit morning. Adjusted total-return prices proxy
both long distributions and short distributions owed; do not deduct dividends
twice. Actual borrow availability, recalls, broker margin and historical bid/ask
are unavailable. Never interpret the 0% borrow case as guaranteed free borrowing.

Validate dates, alignment, positive prices and complete OHLCV before running.
No forward-filling or silently dropping missing positions. Preserve all trades,
signal/entry/exit times, costs, daily net/gross equity, annual outcomes and the
source/protocol hashes. Compare cash and a separately labeled 50% SPY/50% cash
buy-and-hold benchmark, with identical terminal-liquidation costs. Neither is
a perfect risk match. This history is already researched, not a sealed holdout.

Before using actual returns, test long/short P&L against hand arithmetic, both
legs' fees, calendar-day borrow, lagged fills, terminal liquidation and a
future-data perturbation. Run sequentially on one thread. Do not change A8's
forward accounts, scheduler, weather pause, production costs or sizing limits.

References: [creator guide](https://www.raycfu.com/guides/ai-trading-strategies-gpt-6-astra),
[Gatev/Goetzmann/Rouwenhorst author paper](https://repec.som.yale.edu/icfpub/publications/2573.pdf).
