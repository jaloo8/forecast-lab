# Historical options data: source audit and acquisition plan

Checked October 18, 2026. This follows the unchanged
[SPY 1DTE call-spread specification](OPTIONS-CANDIDATE-2026-10-18.md).
No subscription purchased, account created, paid request made, or options
return established. The longer backtest is **blocked on suitable data access**.
One bounded research agent compared paid providers; the parent inspected free
sources and streamed a 36.4 MB sample locally. No production changes were made.

## Recommendation and advertised costs

Try Databento's introductory credits first for a recent, exact-rule test.
For earlier history, ThetaData is the lowest confirmed subscription price
among the tick-quote products checked, subject to sample and license validation.
Prices below are USD personal-use access prices, not guaranteed all-in totals.

| Source | Relevant history | Cost and suitability |
| --- | --- | --- |
| Databento OPRA CMBP-1 | Quote updates from March 28, 2023 | Usage-priced; no subscription necessary. Eligible new teams receive $125 historical credits. Exact SPY request cost is not yet estimated. Best initial candidate. |
| ThetaData Options Standard | Tick quotes from January 1, 2016 | $80/month for options. Separate SPY minute bars and retention rights must be resolved. |
| ThetaData Options Pro | Tick quotes from June 1, 2012 | $160/month for options. Same underlying-data and licensing gaps. |
| QuantConnect / AlgoSeek | Minute options from January 2012 | Free cloud backtesting access; account required. Useful for a separately labelled coarse experiment, not proof of our five-second quote-age rule. |
| Massive Options Advanced | Historical quotes from March 7, 2022 | $199/month. The cheaper options plans do not include historical quotes. |
| Cboe DataShop | Standard minute snapshots from January 2012 | SPY-specific price depends on configuration; tick data requires a custom quote. Tick start date not established. |
| ORATS Live Intraday | Minute API history from August 2020 | $599/month, one million requests. Separate leg quote-age provenance remains unverified; not the economical first choice. |

Primary references: [Databento coverage](https://databento.com/blog/opra-improvements-coming-soon),
[credit/billing rules](https://databento.com/docs/faqs/usage-pricing-and-data-credits),
[Theta pricing](https://www.thetadata.net/pricing) and
[entitlements](https://http-docs.thetadata.us/Articles/Getting-Started/Subscriptions.html),
[QuantConnect dataset](https://www.quantconnect.com/data/algoseek-us-equity-options),
[Massive pricing](https://www.massive.com/pricing?product=options) and
[quotes](https://massive.com/docs/rest/options/trades-quotes/quotes),
[Cboe product](https://datashop.cboe.com/option-quote-intervals),
[ORATS pricing](https://orats.com/data-api) and
[intraday history](https://orats.com/intraday-data-api).

The options subscription is not the full experiment price. Theta's own SPY
stock history starts in 2017, despite earlier option coverage; stock access
is separately entitled. A licensed minute-bar source for earlier SPY remains
necessary. Do not advertise a $160 subscription as a complete 2012 dataset.
Theta's general terms restrict archiving and terminate rights with service;
product-specific agreements can override them. API use and local retention
permission need clarification before purchasing. No permanent archive rights
were verified. See [terms sections 2.1, 12 and 13.4](https://www.thetadata.net/terms-and-conditions).

## Free-source reality check

The [OptionsDX field guide](https://www.optionsdx.com/option-chain-field-definitions/)
links a [SPY sample](https://www.optionsdx.com/wp-content/uploads/2021/03/spy_sample-1.csv)
labelled minutely. The downloaded file has:

- 150,598 contract rows, all dated Friday March 6, 2020.
- 31 distinct snapshots, nominally 09:30 through 12:00 New York time.
- 29 timestamp gaps of 300 seconds and one of 290 seconds.
- Zero contracts expiring the next calendar day, March 7.
- No separate last-update timestamp for each option leg, no complete
  one-minute signal history, and no 15:30 exit observation.

Therefore **zero exact-candidate option trades were scored**. This is a
coverage rejection, not a zero-return backtest. The sample's SHA-256 is
`44e8a4c63ff97a0cd3b871fe77549bc65d7ee9a660d74916c5d2b6d8465153c1`.
Local receipts, sample, and admission summary are retained under ignored
`data/options-source-study-20261018/`; vendor rows are not committed.

Other free routes have different limitations:

- QuantConnect offers cloud access to its historical minute options dataset.
  Its [QuoteBar representation](https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Data_1_1Market_1_1QuoteBar.html)
  aggregates bid/ask bars and sizes; period boundaries do not prove last-quote
  freshness. No authenticated cloud test was run here.
- Alpaca's options history starts in February 2024. Its free indicative feed
  is not a substitute for actual OPRA executable quotes. See
  [history](https://docs.alpaca.markets/us/docs/historical-option-data) and
  [feed entitlements](https://docs.alpaca.markets/us/docs/about-market-data-api).
- Public daily-chain archives cannot reconstruct intraday entries/exits.
  No long, anonymous, downloadable tick archive meeting this experiment's
  requirements was established in this search.

## Avoid turning old snapshots into fresh quotes

Databento's minute CBBO starts in April 2013, but its timestamp semantics
matter: `ts_recv` is the interval boundary and `ts_event` describes the last
trade. Neither is a separate last-update clock for both selected legs.
Consequently the longer minute series cannot silently replace tick evidence.
Use CMBP-1 quote events and validate action/size updates; a trade event must
not reset the quote-age clock. Preserve dataset condition flags. See the
[schema definitions](https://databento.com/docs/schemas-and-data-formats/cbbo).

Long history also does not imply twenty years of today's expiration schedule.
SPY Wednesday expirations were added in 2016; Tuesday/Thursday introductions
followed in November 2022. Use dated contracts and skip absent next-calendar-day
expirations; never substitute Friday-to-Monday. See the
[2016 SEC notice](https://www.sec.gov/files/rules/sro/cboe/2016/34-78686.pdf)
and [Cboe historical-data FAQ](https://datashop.cboe.com/faqs).

## Bounded acquisition and longer-test protocol

1. Obtain owner-controlled account access without sending keys in chat.
   Verify entitlement, remaining credits, date ranges, and request estimates
   before any billable retrieval. Databento credits are one set per team,
   expire after six months, and apply before charges; eligibility is not yet
   verified for this user. Its portal provides request-specific pricing.
2. Estimate the entire experiment: original SPY minute bars, dated definitions,
   and selected option quotes. Credits may or may not cover it. Present any
   out-of-pocket total for approval before requesting paid data. Configure
   account budgets and enforce a local request ledger; do not rely on a
   marketing estimate or assume the displayed default dataset price is OPRA.
3. Validate a small sample spanning ordinary and stressed sessions. Check
   timestamp meaning, DST, quote conditions, sizes, chain availability,
   contract multipliers, and both-leg synchronization before scoring returns.
4. Target March 28, 2023 through October 16, 2026 first. Freeze 2023–2024 as
   implementation/diagnostic history and 2025–2026 as chronological evaluation;
   do not tune the fixed strategy on either period. Identify the already-viewed
   October 8–16 underlying pilot separately; do not call those sessions unseen.
   If older data is obtained, report 2012/2016–2022 as a separate structural era.
5. Derive signal/exit times from underlying bars, discover the dated contracts,
   then fetch only the two required contracts in narrow event windows with
   sufficient lookback. Retain every session, rejected entry, failed exit,
   degraded day and missing input. Missing exits remain unresolved. No
   full-market download or parallel parameter sweep is needed.
6. Run the existing spread arithmetic against actual quotes, preserving the
   frozen fees, adverse fills and cash reserve. Add explicit 2x/3x slippage
   and no-fill sensitivity reports, never select the cheapest case as truth.
   Include yearly returns, drawdown, exposure, trade counts, missingness,
   session-clustered uncertainty, and the same signal in SPY shares.
7. Reproduce results on A8 only after local data/causality checks pass, using
   isolated research outputs. This is not permission to enable trading.

No expected profit is assigned to buying data. The spending case is obtaining
enough evidence to reject or evaluate the hypothesis, not assurance that
returns will exceed subscription costs. Access and a validated sample are
the next dependencies; the requested extended options backtest remains open.
