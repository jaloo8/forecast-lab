# Company pilot: dated watchlist and frozen research rules

**Snapshot: 2026-10-10T18:52:27Z. Status: financial review and current feature calculation completed; forward rules specified, no paper fills or mature outcomes.** Eight deliberately chosen surviving companies form four approximate business comparisons, not a representative stock universe. These judgments identify research priorities, not proven winners or buy instructions. No forecast probability or expected one-year gain has been established.

## What the research favors examining

| Company | Oct 9 regular-session last trade, USD | Provider trailing P/E | Research judgment and main obstacle |
| --- | ---: | ---: | --- |
| MSFT | 535.10 | 29.82 | Quality watch: distribution and growth; heavy infrastructure spending reduced annual cash FCF. |
| CRM | 229.08 | 20.88 | Conditional recovery watch: reconcile acquired growth, investment gains and higher debt. |
| COST | 946.75 | 45.61 | Quality watch: repeat demand and growing FCF; high price relative to current earnings/cash generation. |
| TGT | 153.70 | 15.94 | Turnaround watch: remove tariff refunds before judging earnings recovery. |
| V | 385.505 | 33.08 | Quality watch: network activity and margins; incentives, litigation and cash conversion matter. |
| PYPL | 55.5123 | 10.49 | Turnaround watch: low multiple alone cannot resolve weak monetization and shrinking margins. |
| AMD | 608.12 | 156.06 | Growth watch: strong deployment demand; valuation, export exposure and dilution constrain the case. |
| INTC | 104.70 | Not meaningful | Complex turnaround: loss distorted by escrow accounting; Foundry losses and capital obligations remain. |

Financial evidence, exact periods, original publication dates, source links and thesis-failure conditions: [software/retail](COMPANY-PILOT-ENTERPRISE-RETAIL-2026-10-10.md), [payments/chips](COMPANY-PILOT-PAYMENTS-CHIPS-2026-10-10.md). Moats are reasoned hypotheses, not numerical probabilities. MSFT/COST/V are qualitative business-quality priorities; this label does not override quantitative trial rules or establish attractive prices.

Market source: Robinhood connected read-only quote/fundamental tools, captured October 10. These prices are October 9 regular-session last trades, not current executable quotes or official settled closes; the official-close response was dated October 8. Provider P/E denominators have not all been reconciled. INTC's negative P/E is retained in the CSV for reproducibility but is not an interpretable valuation measure. Raw responses stay in ignored local research storage; no account or position data were requested.

Two cross-checkable valuation examples: MSFT price / FY26 GAAP EPS = 535.10 / 17.95 = **29.81x**; removing only the issuer's OpenAI adjustment gives 535.10 / 17.28 = **30.97x**, illustrating sensitivity around a 30x threshold. COST price / FY26 EPS = 946.75 / 20.76 = **45.60x**, before refund normalization. Annual cash FCF / provider market capitalization gives MSFT **1.69%** and COST **2.24%**. These are trailing cash yields, not expected returns, and exclude financing leases and dilution costs. TGT guidance less the disclosed $1.65 refund gives $8.25–9.25 EPS; the reference price implies **16.62–18.63x** that scenario, not consensus or a fair-price estimate.

## Actual calculation completed

The [eight-row feature file](COMPANY-PILOT-FEATURES-2026-10-10.csv) contains UTC availability stamps, source dates/URLs, dated prices, financial inputs and each rule's membership. Retrieved 49 regular-session daily bars for each company and SPY, August 3–October 9: 441 observations. All dates aligned; no zero-volume or explicitly flagged interpolated bars appeared. The interpolation field was absent, so this is not independent proof that no values were synthesized. Daily bars and quote last trades differ slightly; each is kept separate.

Price controls use provider bar closes requested with split adjustment; the response does not echo the adjustment setting and corporate-action accuracy was not independently verified. Return over n sessions = close[t] / close[t-n] - 1; relative return subtracts SPY over identical dates. Five and twenty sessions are backward-looking measurements, not predictions or a backtest. Twenty-session relative returns range from CRM **-9.37 percentage points** to AMD **+15.95 points**. Dividends are excluded from this diagnostic; full outcome evaluation below must include distributions. The shared UTC stamp records completion of collection, not an original issuer publication or provider-certified capture time.

## Long-horizon pilot: separate additions, no fitted blend

Freeze these exploratory rules at this research commit; do not optimize thresholds against subsequent outcomes. They were chosen after seeing today's inputs and are prospective assumptions. This simple proxy is **not** the French operating-profitability/book-equity strategy that produced the earlier 13.27% gross CAGR. Reconstructing that strategy remains the primary twenty-year historical task.

| Arm | Fixed rule, applied to the frozen eight companies | Today's membership |
| --- | --- | --- |
| Q | Latest disclosed revenue YoY >0, GAAP operating profit >0, and cash FCF >0 for the disclosed cash-flow period | All eight; this weak gate currently adds no selection value |
| Q+V | Q and positive provider trailing P/E <=30 | MSFT, CRM, TGT, PYPL |
| Q+G | Q and latest reported revenue YoY >=10% | MSFT, CRM, COST, V, AMD, INTC |
| Q+B | Q and reported cash plus identified investments >= reported debt | MSFT, COST, PYPL, AMD |

The controls are the eight-stock basket and SPY. Differences in sector economics, acquisitions, seasonal cash flow, lease obligations and customer/restricted funds limit these proxies; Q+B does not establish accessible surplus cash. FCF periods are explicitly preserved in the CSV, never annualized or ranked against one another. Keep a separately labeled normalized-earnings sensitivity; do not silently switch MSFT's membership after seeing returns. The notes' qualitative failure thresholds are observations to record, not discretionary portfolio exits.

For each arm use an independent hypothetical $10,000, eight fixed $1,250 slots; an excluded name's slot stays cash at 0%, so filtering does not increase remaining positions. Enter eligible slots at the first regular-session open strictly after the immutable research record and verified availability of every input. No October 9 retroactive fill. Check corporate actions between signal and entry; inability to resolve one leaves that slot unfilled with the reason retained. These specifications do not launch a runner or write the A8 ledger.

Hold separate cohorts to 6, 12 and 18 calendar months after entry, exiting at the close of the first regular session on/after each anniversary. No interim rebalancing, leverage, shorting or options; resolve mergers, splits, distributions and terminal delisting proceeds rather than dropping failures. Credit cash dividends without simultaneously using dividend-adjusted prices. Apply 10/25/50 basis points per executed side as explicit research sensitivities, not measured costs or changes to production sizing/fee rules; charge matching SPY entries/exits consistently. Track each arm's whole-account wealth, including idle cash.

Report net total return versus SPY and the eight-stock control, maximum daily drawdown, turnover, exposure, winners/losers, and all three cost cases. Report 12-month results as one-year gains only after outcomes exist; do not annualize the 5/20-session studies. Eight selected companies cannot establish statistical reliability or generalize across market regimes.

## Short-horizon pilot: earnings events, separate from quality holds

Eligible events are the next quarterly earnings releases first captured after this commit. Retain original URL, release timestamp (or date-only uncertainty), retrieved_at and as_of. For date-only releases, treat availability as the end of that issuer's local date, then require an observed capture and the next session's open. No reconstructed historical social sentiment or undated consensus surprises.

E+ requires reported revenue YoY >=10% and GAAP operating margin >= the corresponding prior-year quarter. E- requires revenue YoY <0 and a lower GAAP operating margin. Other events are neutral; missing comparable figures are ineligible. Acquisitions and one-offs are retained as flags, not subjective exceptions. These event rules are experimental, with no asserted edge.

For every eligible event record E+/E-/neutral and, from the last completed session before entry, the signs of 20-session SPY-relative momentum and the inverse of 5-session relative return. Freeze these price controls separately. Measure next-open to fifth/twentieth-session close total returns against same-date SPY; entry session is session one. Also report direction against an always-up diagnostic and balanced accuracy across observed up/down outcomes.

Keep one event per company open at a time until its twentieth-session exit; retain skipped overlaps. E- is a bearish research label, not a short-sale P&L calculation. Show event counts, missing captures, cost sensitivity, failures and dependence; do not combine overlapping event returns into fictional compound account returns. No fresh qualifying earnings event has been captured under this forward protocol, so **there is no active event signal yet**.

## Historical-data decision and remaining work

Verification: independently recalculated all 32 five/twenty-session stock/relative returns and checked all rule memberships and valuation examples; the existing factor-screen tests passed (9). Local raw files are under `data/company-pilot/2026-10-10/`; SHA-256: `bars.json` = `b4970bff5d42a68529b20b1e1b28dec203c87aa08985c4a17a09ccf79f211b0c`, `market-snapshot.json` = `7e657f7d80f62efbadf0cc90baae03692a494d9b80e91075bb2afa777b78da88`. Hashes identify local responses; they do not authenticate the upstream facts or establish historical point-in-time availability.

The [actual free sample test](HISTORICAL-DATA-SAMPLE-2026-10-10.md) retrieved AAPL statements/dividends and metadata containing delisted securities, but detailed TWTR actions hit an entitlement limit. No subscription was bought. Before recommending a tier, verify original filing availability, stable IDs, prices, dividends/splits and terminal outcomes on failed/acquired names. Then reconstruct the existing profitability rule over 2006–2025 with a historical universe, subsequent-session fills, transaction costs and time-ordered comparisons. Today's eight survivors cannot supply that validation.

Private creator work: [three finished narration/storyboard drafts](COMPANY-PILOT-REELS-2026-10-10.md) and [tool/business feasibility](STOCK-CREATOR-FEASIBILITY-2026-10-10.md). Scripts are ready for voice auditions; audio/video and narrator-quality comparisons have not been produced. No public posts, purchases, orders or recurring jobs were made.
