# Registered sector portfolio comparison — October 10, 2026

Frozen before computing these portfolio outcomes. The owner requested literature research and a roughly 20-year backtest targeting 10–20% annual returns. This is an exploratory historical test, not a guarantee, an untouched holdout, individual-stock selection proof or permission for execution. Previously inspected prices/results are not new out-of-sample evidence.

## Universe and input

SPY plus the nine original sector funds XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY; all existed before 2006. Do not add newer sectors, choose past-winning stocks or tune the universe after outcomes. This is a fixed historical fund menu, not the complete investable universe; fund/category evolution and current-vintage corrections remain limitations.

Read only the frozen millennium snapshot from local Tester.zip. Verify the timing-study provenance, pointer, manifest and individual CSV SHA-256 using the existing safe archive helpers. Pointer: `research/millennium_study/data/latest.json`; snapshot `research/millennium_study/data/raw/20261006T235316726732Z`; manifest SHA-256 `ed4881322ebb2a760da4d8873b2eaf256c4ccad8d8d6ad44f25b59f39578403c`. Never execute archive code or extract unrelated members. All ten funds have 5,031 matching observed sessions during 2006–2025; provider sessions are not an independent exchange-calendar audit.

Adjusted open = Open × Adj Close / Close; adjusted close = Adj Close. These are current-vintage distribution-adjusted wealth proxies, not literal historical executable quotes. They approximate reinvested distributions and embedded fund expenses; actual distribution timing, tax, bid/ask and reinvestment differ. Use pre-2006 history solely for warmup. Reject invalid, duplicate or missing fund/session prices rather than silently skipping them.

## Five frozen strategies

Signals use each last observed monthly close; trade only at the next observed session's open. At a month ending t, momentum is C[t−1]/C[t−12]−1 (skip the most recent month); ranks descending, ties by ascending ticker. The SPY trend gate is its close strictly above the mean of its last ten monthly closes, including t. Rank and gate use only data through the decision close.

1. **SPY buy-and-hold:** buy at the first 2006 session open, retain until the study endpoint.
2. **Equal sectors:** target 1/9 in each sector, rebalanced monthly. This controls for sector exposure and rebalancing.
3. **Sector momentum:** target 1/3 in each of the top three ranked sectors, rebalanced monthly; no positive-return threshold.
4. **SPY trend:** target 100% SPY when the trend gate is true, otherwise cash; reassess monthly.
5. **Sector momentum + trend:** target top-three sectors when the same gate is true, otherwise cash.

No short positions, options, leverage, volatility targeting, stops, fitted parameters, social filters or parameter sweep. Cash earns zero; this is an explicit conservative cash assumption, not a Treasury-bill strategy replication. Fees below are isolated research assumptions and do not change live/paper account fee or sizing code.

## Portfolio accounting and endpoints

Start with $10,000 at the first observed open on/after January 1, 2006. Initial tactical decisions use December 2005 month-end data. End December 31, 2025 using the last observed adjusted close and a costed terminal liquidation; this endpoint exit is a fixed study convention. Monthly orders elsewhere execute next-session opens. Fractional adjusted units are allowed; no external deposits or withdrawals. No data after December 2025 enter signals or outcomes.

For each rebalance, mark existing units at that open, including the overnight return before trading. If pre-trade wealth is V and current asset dollar amounts are a_i, solve post-cost wealth N from N = V − c Σ|w_i N − a_i|. Set units to w_i N / price_i and cash to N(1−Σw_i). This accounts for fees on the actual buy/sell notional, including partial rebalances, without creating capital. Charge terminal sell costs too. Daily NAV is cash plus units × adjusted close; drawdown uses daily close wealth and the initial capital, not intraday prices.

Run 10, 25 and 50 basis points per dollar bought or sold (three scenarios, all five rules). Baselines face the same proportional costs when they trade. Cash is not charged as a traded asset. Record decision UTC as_of (simulated 16:00 New York, not historical retrieval or early-close precision), next-open execution date, target weights and paid costs. Archive exact input/protocol/code hashes and timestamp.

## Report everything and do not optimize to the requested return

For all 15 cases publish 20 calendar-year returns, compound annual growth over those 20 calendar-year investment periods, arithmetic mean annual return, terminal wealth, worst daily-close drawdown, best/worst year, positive years, years at/above 10% and 20%, and years beating SPY. Calculate each year's return from the prior year's ending NAV; the first year starts at initial cash. Final liquidation is included in 2025. Clearly distinguish CAGR from a one-year forecast.

Report five-year subperiod returns and monthly observed rolling-12-month extremes where possible. These overlapping windows are descriptive, not independent trials. Compare sector momentum to both equal sectors and SPY. No post-result winner becomes a current stock recommendation. Success on the owner's literal minimum requires every calendar year to reach at least 10% after costs; a high average with losing years fails that requirement. A historical pass would still not guarantee future performance.

The stock-quality/value and earnings/relationship/social candidates remain untested without historical membership, delistings, as-filed fundamentals and original event availability. The study cannot estimate their returns. Retain negative results, cost sensitivity and every strategy; any modification needs a separately dated hypothesis and new prospective validation.
