# A finite stock/ETF strategy-family study

Registered October 19, 2026, before this batch's performance calculations. The objective remains **at least 10% net return in every complete calendar year**, with 20% an upper reference rather than a rejection threshold and **$1,000** the account reference. This study can reject historical candidates; it cannot establish guaranteed future profits.

The authoritative [machine-readable registration](strategy-family-registration-2026-10-19.json) was frozen at **2026-10-19T22:35:44Z**, SHA-256 **`15c3a226c695aedf293be475bb76c9e515e92e7e1f12ad51a712eccda0a0f2b9`**. It specifies **28 policies**, comprising five controls and 23 candidates, at three transaction costs and three account windows: **252 fractional-unit account paths**. A separate three-policy SPY whole-share sensitivity adds **27 paths**, for **279 registered accounts**. These are 28 policies, not 279 independent algorithms. No new model API, market-data acquisition, subscription, live order or paper-writer migration is authorized or required.

The [pre-performance warm-up clarification](strategy-family-amendment-01-2026-10-19.json), frozen at **2026-10-19T22:39:46Z**, resolves the original phrase “earliest available history”: all policies use the complete common eleven-ETF panel beginning **March 10, 1999**, with no earlier per-symbol state. Breakout state starts flat at that common boundary and then requires 63 prior closes. This choice can affect latent state, so it is recorded explicitly before results rather than inferred silently. The original registration remains unchanged; run provenance must include both files and hashes.

## Why this batch, and what is already known

**Direct project evidence:** The [annual audit](ANNUAL-PROFIT-AUDIT-2026-10-19.md) found zero qualifying paths among 24 fixed stock/cost cases. The [earlier stock evidence](STOCK-MULTISTRATEGY-EVIDENCE-2026-10-17.md) includes 63 price-based rules at three costs on a survivor sample. The separate owner-private QuantLab timing and combination studies have also been read: the combination study tested twelve policies in 4,032 account scenarios, with no blend beating its strongest component's primary CAGR in the full and later windows. Those results and rejected rules remain part of the research history. This is not a fresh search with an erased trial count.

**Inference:** A useful next step is a small, transparent decomposition across different price mechanisms, with explicit control policies, rather than thousands of fitted window/threshold combinations. The available data supports an ETF comparison; it does not support a defensible all-stock value, quality, earnings-surprise or social-sentiment test. The fixed ETF menu also lacks bonds, international equity and commodity funds. Results must not be described as a test of every asset class or all investment strategies.

Passive exposure, SPY's ten-month trend and sector twelve-minus-one momentum are repeat mechanisms. Sector trend, volatility control and blends also have prior project evidence. Their inclusion tests consistent accounting, exposure and costs; they are not newly discovered independent ideas. New range-breakout and reversal implementations are still retrospective hypotheses, influenced by known market history.

## Primary-source rationale, with explicit adaptation limits

| Source and evidence read | Direct finding relevant to the hypothesis | Our adaptation and limit |
|---|---|---|
| [Faber, A Quantitative Approach to Tactical Asset Allocation, 2013 update](https://mebfaber.com/wp-content/uploads/2016/05/SSRN-id962461.pdf), abstract and rule/method passages | Uses a ten-month moving-average rule evaluated at monthly intervals. The paper's stated execution convention uses the signal day's close. | We use completed month-end information and the following observed opening proxy, 98% risky allocation and zero-yield cash. This is a changed implementation, not a replication of its reported performance. |
| [Moskowitz, Ooi and Pedersen, Time Series Momentum](https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum), authors' paper description | Studies own-return predictability separately from relative ranking across 58 futures/forward contracts; twelve-month excess returns are central. | Long-only ETF own-return gates compare against zero-return cash. We do not reproduce leveraged, volatility-scaled, diversified futures portfolios or their excess-return definition. |
| [Jegadeesh and Titman, Returns to Buying Winners and Selling Losers](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1993.tb04702.x), publisher abstract | Reports relative return continuation over intermediate holding horizons in stock winner/loser portfolios. | Sector ETF top-three ranking and SPY/QQQ top-one ranking are narrower, long-only hypotheses. They are not individual-stock long/short replications. The multi-horizon average is a separate fixed local score. |
| [Brock, Lakonishok and LeBaron, Simple Technical Trading Rules](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1992.tb04681.x), publisher abstract | Examines moving-average and trading-range rules on the Dow Jones index over 1897–1986. | A 63-session entry/21-session exit close-range rule is our fixed quarter/month adaptation. The paper motivates the family; it does not validate these ETF parameters, next-open fills or present-day net returns. |
| [Moreira and Muir, Volatility Managed Portfolios](https://www.nber.org/papers/w22208), NBER indexed abstract/version metadata | Studies exposure reduction when volatility rises across several equity factors and currency carry. | A lagged 63-return estimate and unlevered 10% volatility cap are a local exposure-control test, not the paper's portfolio normalization or an optimized volatility target. The direct NBER page/PDF fetch returned access errors; this review used its indexed primary abstract. |
| [Frazzini, Israel and Moskowitz, Trading Costs of Asset Pricing Anomalies](https://www.aqr.com/Insights/Research/Working-Paper/Trading-Costs-of-Asset-Pricing-Anomalies), authors' summary | Institutional execution evidence shows that cost sensitivity differs by strategy; short-term reversal is particularly fragile in their setting. | Weekly and monthly ETF reversal are deliberately small challengers with all costs retained. Institutional capacity/cost estimates are not this retail account's fills. No reversal profitability is presumed. |

**Inference:** None of these papers establishes a 10% annual minimum for the proposed policies. Similar names do not establish faithful replication. Fixed low-volatility selection is a separate price-risk comparator; it should not be labeled the full low-beta or quality factor. The three blends are local combination hypotheses, not published optimal allocations.

## Frozen policy inventory

All formulas first produce weights with sum at most one; the engine multiplies risky weights by **0.98 once**, leaving at least a 2% cash target. The nine sectors are XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV and XLY. `C[t]` means the adjusted close known at the decision. Monthly formulas use the last observed close of each calendar month. A strict inequality failing, including equality, means the gate is closed. Ties use ascending ticker.

| IDs | Family and exact rule | Decision schedule |
|---|---|---|
| C01 | All cash, zero yield | No trades |
| C02, C03 | Buy and hold SPY; buy and hold QQQ | First opening only, then terminal liquidation |
| C04, C05 | Equal nine sectors; 50/50 SPY/QQQ | Monthly rebalance |
| T01–T03 | SPY, QQQ or fixed sector sleeves: active when current monthly close is above the arithmetic mean of the latest ten monthly closes, including current | Monthly |
| T04–T06 | Same three baskets: active when current monthly close divided by the close twelve months earlier is greater than one | Monthly |
| B01–B03 | SPY, QQQ or fixed sector sleeves: while flat, enter above the maximum of the **previous** 63 daily closes; while invested, exit below the minimum of the **previous** 21 daily closes | Observe daily; rebalance only when any sleeve state changes, plus initial account entry |
| M01 | Rank sectors by `C_month[t−1] / C_month[t−12] − 1`; top three, equal weights | Monthly |
| M02 | Rank sectors by the arithmetic mean of current trailing 1-, 3-, 6- and 12-month simple returns; top three | Monthly |
| M03 | M01's score applied to SPY and QQQ; hold the higher-ranked one | Monthly |
| M04 | M01 selection, but each original one-third slot invests only if that selected fund's own twelve-month return is positive; failed slots remain cash without replacement | Monthly |
| V01–V03 | SPY, QQQ or equal sectors: multiply the base basket by `min(1, 0.10 / sigma)` | Monthly |
| V04 | Three sectors with the lowest trailing 63-return volatility, equal weights | Monthly |
| R01 | Three sectors with the lowest trailing five-session return | Weekly |
| R02 | Three sectors with the lowest trailing 21-session return | Monthly |
| R03 | R01, provided SPY's latest completed daily close is strictly above its trailing 200-close mean; otherwise cash | Weekly |
| E01 | Half T01 plus half M01 | Monthly |
| E02 | Half M01 plus half R02 | Monthly |
| E03 | Equal thirds T01, M01 and V04 | Monthly |

Sector own-trend and breakout sleeves retain fixed one-ninth slots; inactive sleeves become cash, rather than increasing the surviving sleeves. Breakout latent state starts flat at the earliest available history and evolves once its required prior closes exist, including during warm-up. Starting a fresh account inherits the signal state, **not positions, cash or prior returns**.

`sigma` is sample standard deviation (`ddof=1`) of 63 completed simple daily returns times `sqrt(252)`. V03 uses the arithmetic mean of the nine sectors' daily returns as its fixed-weight risk proxy, not a previously simulated account or a full-sample fit. Zero/nonfinite risk estimates produce cash. Blends combine their named monthly component targets at the same month-end into one portfolio. They do not average equity curves or reuse the same money in independent fully funded sleeves.

## Data and account mechanics

Use only the existing data-only wrapper, SHA-256 `4df237cec1ddc6049c628887108cf247f9d2e1041abbf36bc4fa7406d70b2f70`, and the original pointer, provenance, manifest and CSV hashes. Its ETF snapshot is `20261006T235316726732Z`; manifest SHA-256 is `ed4881322ebb2a760da4d8873b2eaf256c4ccad8d8d6ad44f25b59f39578403c`. No archive code is imported or executed. The runner must exclude all rows after December 31, 2025 before making signals. Raw price histories remain private inputs, not newly published data.

The broad panel uses **fractional adjusted wealth units**: adjusted opening proxy is `Open × Adj Close / Close`, and closing NAV uses `Adj Close`. Distributions are embedded and must not be added again. Vendor OHLC are already split-adjusted, and action entries can represent more than ordinary splits. Rounding these units down would not create literal historical shares. This panel therefore tests strategy economics under a declared proxy, not complete $1,000 broker feasibility.

Each account starts with $1,000 cash and no holdings. Signals use completed closes; orders execute at the next observed opening proxy. Existing positions receive overnight movement before rebalancing. For pre-trade wealth `V`, current asset values `a_i`, target weights `w_i` and one-way proportional friction `c`, solve `N = V − c × sum(abs(w_i × N − a_i))`; set units to `w_i × N / opening_price_i`, leaving the remainder as cash. Friction applies to actual buys and sells, including terminal liquidation. Run **10, 25 and 50 bp per side**, with **25 bp primary**. These aggregate friction scenarios are not measured fills, and no additional spread is deducted a second time. No shorts, borrowing, leverage, minimum ticket, interest on cash, taxes or external flows are modeled.

Monthly/weekly policies rebalance on every scheduled decision, including unchanged requested weights. The last observed session of each ISO week defines the weekly decision calendar. The observed calendars and simulated 16:00 New York `as_of` timestamps are not independent historical exchange-calendar, early-close or historical data-receipt audits. Invalid/missing required prices or incomplete account calendars fail visibly. Feature warm-up gaps produce cash with explicit counts, not retrospective filling or a shorter silently substituted window.

Record maximum drawdown using initial capital, opening marks before trading, opening marks after costs, closing marks and terminal liquidation. Also retain close-only drawdown for comparison. Neither observes the worst possible intraday price. Always include cash-only, losing, incomplete and rejected cases.

## Separate SPY whole-share sensitivity

Run C02, T01 and B01 at the same three costs and three windows. First verify SPY's split-action series is zero and raw price/dividend fields are valid throughout the required span; otherwise retain these cases as blocked. Signals remain identical to their adjusted-close counterparts. Orders and marks instead use nominal `Open` and `Close`.

At each order, available liquid wealth is cash plus shares valued at the opening price, **excluding locked dividend receivables**. Solve the continuous self-financed 98% target, floor the resulting share quantity, recompute fees from the actual integer change and retain the cash residual. Dividend entitlement is previous-session-held shares times the ex-date cash distribution; accrue it before the ex-date opening, including when shares are sold that morning. Receivables contribute to NAV but are never spent or reinvested, even at the endpoint. Terminal shares are liquidated with costs; report cash and locked receivables separately.

This deliberately conservative cash-availability model avoids inventing dividend payment dates. It is not exact broker settlement, spread, tax or cash-payment accounting. It is also not a replacement for the broad panel or a license to generalize SPY feasibility to every fund. No additional nominal-SPY strategy is selected after seeing this sensitivity.

## Selection, evaluation and complete reporting

Every policy has fresh-cash paths for **training 2006–2013**, **evaluation 2014–2025** and **full 2006–2025**. The implementation computes training first and saves the selected ID before evaluation/full performance. Select one of the 23 noncontrol policies at 25 bp using, in order: highest worst training calendar-year return; highest training CAGR; lowest event-drawdown magnitude; lexical policy ID. Use unrounded numbers. Freeze that choice for the later fresh-cash evaluation, and publish all other policies and costs as well. There is no annual adaptive selector or subsequent parameter search.

The eight training years and twelve evaluation years are chronological partitions of already known history. The full path is a descriptive diagnostic; it is not the selection sample. Neither fresh cash nor a new filename makes 2014–2025 an untouched holdout. Current-vintage revisions, previous project results, published literature and model pretraining all limit independence.

For every registered account retain annual returns and threshold counts, CAGR, final NAV, worst year, both drawdowns, turnover, trades, paid costs, cash/exposure and missingness. Compare to SPY on identical dates and costs; compare blends to their ingredients. Returns above 20% are reported, not treated as failures. A path passing every historical year is only a research lead; a failed year rejects the registered annual-floor claim for that path.

The bill for external model/data API calls in this batch is zero because none is used. Unknown subscription allocations and replacement-model prices remain unknown, rather than being called permanently free. For each year, report additional year-end dollar expense consistent with preserving 10% growth: `max(0, end_NAV − 1.10 × start_NAV)`, alongside a negative shortfall where applicable. This is a one-year budget diagnostic; subtracting such numbers independently is not a compounded fixed-expense simulation. At the initial $1,000 reference, 10–20% is $100–$200 before any otherwise unmodeled costs.

## Multiple trials, validation and stopping

**Direct research evidence:** [Bailey and coauthors](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) explain selection-induced backtest overfitting. [Harvey, Liu and Zhu](https://www.nber.org/papers/w20592) show why ordinary single-test thresholds are inadequate after many factor trials. **Inference:** Freezing this batch controls additional choices; it does not undo our earlier searches. No naive best-rule p-value, universal profit confidence or automatic promotion will be claimed. A prospective observation period with frozen rules would still be required before a new operational decision.

Before performance: capture the registration, implementation and data hashes; validate synthetic cash/fee/terminal accounting, calendar boundaries, strategy membership, future-price/prefix invariance and locked-dividend whole-share cases; independently review the rule-to-code mapping. Preserve all artifacts. No tests here establish real fills.

Do not expand the menu, alter thresholds, select a different universe, increase leverage or redefine a bad year after viewing results. Genuine implementation defects require a written erratum, old outputs retained, a new code hash and all affected cases rerun. Material rule changes require a new registration and additional trial count. If none qualifies, report that result and the exact reason rather than searching until a winner appears.
