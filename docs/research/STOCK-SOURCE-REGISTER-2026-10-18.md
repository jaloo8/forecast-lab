# Source coverage and evidence register — October 18, 2026

This records what was actually accessed during this audit. It is neither an
exhaustive survey of every article nor licensed bulk coverage of every rating.
The owner requires broader discovery than a fixed list of familiar websites;
future research should retain this distinction and extend this register.

## Named sources: actual access, use and gaps

| Source | Evidence inspected | Use and boundary |
|---|---|---|
| [Google Scholar](https://scholar.google.com/scholar?q=value+momentum+quality+stock+returns) | Browser result pages for value/momentum/quality and investor-attention/social/IPO research. Followed scholarly leads to authors, universities and publishers. | Discovery, not a performance dataset; citation counts do not validate a trading rule. |
| [Seeking Alpha ratings](https://seekingalpha.com/symbol/AAPL/ratings/quant-ratings) and [methodology](https://seekingalpha.com/article/4263303-quant-ratings-and-factor-grades-faq) | Actual AAPL rating page exposes the five-point scale but not a reliably readable selected score. Methodology describes valuation, growth, profitability, momentum and revisions. | Selected rating remains **unavailable**; do not mistake the displayed 1–5 legend for AAPL's score. No twenty-year ratings archive obtained. |
| [Morningstar AAPL](https://www.morningstar.com/stocks/xnas/aapl/quote) and [stock-rating definition](https://www.morningstar.com/investing-terms/morningstar-rating-for-stocks) | Actual browser page, rating dated October 16; star rating, fair value and uncertainty explicitly locked. Public company description, short analyst preview, valuation metrics and opposing bull/bear summaries visible. | Fair-value/risk research differs from momentum or next-week prediction. Locked fields remain missing. Public previews are not full analyst reports. |
| [TipRanks AAPL](https://www.tipranks.com/stocks/aapl/forecast) | Public page showed Moderate Buy, 16 Buy / 11 Hold / 4 Sell in its stated three-month window. | A retrieval-time snapshot only. Displayed quote differed from the October 16 close on other sites, so cross-site as-of consistency is unverified. No historical consensus panel established. |
| [Yahoo AAPL analysis](https://finance.yahoo.com/quote/AAPL/analysis/) and [analyst insights](https://finance.yahoo.com/quote/AAPL/analyst-insights/) | Browser earnings estimates, actuals, revisions and analyst recommendation table; for example JP Morgan maintained Overweight October 12, Morgan Stanley October 1 and Needham reiterated Hold October 1. | These are distinct views, not one universal rating. Current estimates and recent revision windows cannot reconstruct past releases. Historical chart endpoint works for a separately hashed research capture. |
| [Bloomberg IPO report](https://www.bloomberg.com/news/articles/2025-06-26/stock-market-us-ipos-surge-on-investor-optimism) | Search-indexed headline/description only; full article not read. | Discovery lead, **not** a verified full-text or historical news feed. No numerical strategy claim rests on it. |
| [Reddit-derived ApeWisdom API](https://apewisdom.io/api/) | Nine actual current stock-mention pages, archived privately with timestamp/hash; 837 unique symbols after deduplication. | Mention counts are attention, not expected return. Public pagination shifted while fetching; not an atomic snapshot or twenty-year history. Directory matching retained 429 additional common-share candidates, not 500. |
| [Stocktwits stream documentation](https://firestream.stocktwits.com/documentation/stream) | Documentation discovered; no authenticated stream or licensed history obtained. | Candidate second social source. Do not claim its historical observations are ingested. |

## Additional independent sources and falsification checks

| Primary source | What was read / supports | Implication for this project |
|---|---|---|
| [State Street SPY holdings](https://www.ssga.com/us/en/individual/etfs/state-street-spdr-sp-500-etf-trust-spy) | Actual official XLSX, holdings as of October 15, 503 share-class rows. | Current S&P exposure proxy, not the largest 500 ranked anew and not historical constituents. Multiple share classes explain the count. |
| [Nasdaq symbol-directory definitions](https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs) | Definitions plus actual Nasdaq/other-listed files with ETF/test/security-name fields. | Exclude funds, test symbols, ambiguous identities and non-common securities before treating social tickers as stocks. Domicile and liquidity still need separate checks. |
| [NYSE hours and calendars](https://www.nyse.com/trade/hours-calendars) | Official 2026 holiday dates through October 16 checked against the partial-year benchmark. | Verify evaluation sessions before computing a duration-based return; the long-window archived-calendar comparison remains a separate, same-vendor check. |
| [Ritter IPO statistics](https://site.warrington.ufl.edu/ritter/files/IPOs-long-run-returns-on-IPOs.pdf) | Full PDF available; read methodology and underwriter/long-run table. 2012–2024 sample: 1,645 IPOs, average first-day gain 23.4%, subsequent three-year return 7.6%, market-adjusted -25.5 percentage points. | Offer-price access is not ordinary aftermarket execution. IPO growth is a hypothesis, not a blanket advantage. Sample excludes several security types and very small offerings; three-year returns are not annualized. |
| [AQR: Value and Momentum Everywhere](https://www.aqr.com/insights/research/journal-article/value-and-momentum-everywhere) | Authors' abstract and cross-market result. | Complementary mechanisms justify controlled blend comparisons, not a promise that any retail five-stock blend wins. |
| [AQR: Quality Minus Junk](https://images.aqr.com/-/media/AQR/Documents/Insights/Working-Papers/Quality-Minus-Junk.pdf) | Author-hosted paper available; construct combines profitability, growth, safety and payout. | Requires timed fundamentals. Our price-only low-volatility component is **not quality** and is never labeled QMJ. |
| [Moreira and Muir: Volatility Managed Portfolios](https://law.yale.edu/sites/default/files/area/workshop/leo/leo17_moreira.pdf) | University-hosted paper, opening methodology and data section: lagged realized variance scales factor exposure. | Exposure control is distinct from ranking low-volatility stocks. Published leverage/scaling and factor results cannot be transplanted into a cash-capped account. |
| [AQR: Trading Costs of Asset Pricing Anomalies](https://www.aqr.com/insights/research/working-paper/trading-costs-of-asset-pricing-anomalies) | Authors' study summary, institutional trading-data basis and reversal versus momentum cost distinction. | Explicit two-sided cost stress, turnover and missing-liquidity evidence are necessary. Institutional execution is not a retail fill guarantee. |
| [Patton and Weller: What You See Is Not What You Get](https://www.sciencedirect.com/science/article/pii/S0304405X20300453) | Publisher-indexed abstract accessible; direct page returned 403. | Counterevidence: implementation costs can materially attenuate anomaly returns. Full paper was not read this session; retained as a conflict to investigate, not silently omitted. |
| [Chen et al.: Wisdom of Crowds](https://bhwang.com/pdf/wisdom-of-crowds.pdf) | Author-hosted paper; sample/data limitations checked: Seeking Alpha articles/comments, 2005–2012, matched to financial datasets; deletions acknowledged as a limitation. | Supports investigating dated social information. It does not validate today's trending list, modern Quant ratings, or automatic sentiment-as-probability. |
| [Bailey et al.: Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) | Author-hosted paper, definition and multiple-testing argument. | Freeze a finite family and disclose every result. Repeatedly searching until 10–20% appears does not establish an investable edge. |
| [Kenneth French Data Library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html) | Actual library and data-format notes, including the 2025 FIZ/CIZ transition. | Useful independent factor controls; portfolio-level series are not stock-level point-in-time membership or filings. Preserve dataset versions. |
| [Novy-Marx gross profitability](https://www.nber.org/papers/w15940) | NBER abstract discovered; direct page/PDF access later returned 403. | Gross-profit/assets is a potential distinct fundamental feature; no claim of reproducing that paper or loading its required history. |
| [McLean and Pontiff publication decay](https://onlinelibrary.wiley.com/doi/pdf/10.1111/jofi.12365) | Publisher/author discovery results; full text not retrieved in this session. | Track publication dates and subsequent evidence; do not treat published backtest returns as current expected returns. |
| [Zacks estimate research](https://www.zacks.com/help/est_research) | First-party documentation discovered, not a licensed stock-history dataset. | Additional analyst-revision source for a later timed-data comparison; not counted as an ingested signal. |

## Durable due-diligence checklist

Owner decision, October 18: use public data for now. Paid subscriptions are
only candidates for a later proposal, not authorized purchases. The owner's
criterion is that added profits outweigh costs. Do not promise that outcome
in advance or infer it from the provider's marketing or an optimized backtest.
Before proposing a purchase, identify the missing data it supplies, verify
historical coverage and usage rights, and seek a sample or trial. Compare a
frozen method with and without the data on identical evaluation periods;
include subscription/API costs, trading costs, uncertainty and the owner's
intended capital. Require prospective paper evidence where feasible. Report
data-quality benefits separately from demonstrated incremental returns. If
there is insufficient evidence of net value, retain public data and the gap.

For each future study: document the economic mechanism and contrary evidence;
search beyond the named sites; inspect primary methods and actual accessible
ratings; record publication time, retrieval time, revision history and access
limitations. Distinguish news discovery from numeric inputs and vendor ratings
from independent truth. Correlated syndicated reports are not independent votes.
Record failed hypotheses, trials, missingness, costs and realistic execution.

No exhaustive stock-by-stock review of 1,000 companies or twenty-year social,
ratings, fundamentals and delisting coverage has been completed here. Those
gaps must stay visible rather than being concealed by a large price-only test.
