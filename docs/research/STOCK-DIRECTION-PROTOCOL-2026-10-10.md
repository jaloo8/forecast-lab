# Stock direction research protocol — version 1

Registered October 10, 2026, before the new directional comparisons. The user approved separate short/long studies, research publication to GitHub, then simulation. This protocol fixes the initial rules; it does not assert profitable signals. Previously inspected market history remains exploratory.

## Objective and sequence

Find whether public evidence improves identification of absolute price rises/falls and market-relative outperformance/underperformance. These are different outcomes. Publish this protocol first, then implement and test, then run the cached-data experiment and publish every result. No orders, automatic account promotion, new paid data or dependencies. Downward signals are research/avoidance flags, not short-sale P&L.

## Mechanisms worth testing

| Mechanism | Falsifiable proposition | Required evidence |
|---|---|---|
| Earnings drift | Positive versus negative earnings changes predict later relative returns at 5/20 sessions | Original release clock and as-filed EPS; seasonal change is not analyst-consensus surprise |
| Intermediate momentum | Prior relative returns contain information about 6/12-month relative outcomes | Adjusted historical prices; 18 months is a persistence check |
| Short reversal | A recent relative price fall sometimes reverses over five sessions | Executable next-session prices and transaction-cost stress |
| Economic connections | A customer shock reaches publicly linked suppliers with delay | Relationship disclosures published before the event |
| News/social triggers | Timely independent event evidence improves a price-only comparator | Permitted original content, first-seen clocks, revisions and deduplication |

Primary foundations: [earnings drift and momentum](https://www.nber.org/papers/w5375), [momentum persistence and later reversal](https://www.nber.org/papers/w7159), [liquidity and short reversal](https://www.nber.org/papers/w17653), [customer–supplier links](https://pages.stern.nyu.edu/~afrazzin/pdf/Economic%20Links%20and%20Predictable%20Returns%20-%20Cohen%20and%20Frazzini.pdf), [Seeking Alpha research](https://www.bhwang.com/pdf/wisdom-of-crowds.pdf). These studies motivate hypotheses; none validates our implementation, today's market, or transfer to Instagram/Reddit/YouTube. LLMs extract cited facts and entities, not numerical return probabilities or sentiment scores.

## First executable experiment: frozen price controls

Available now: Tester ZIP's 11 illustrative surviving stocks plus SPY adjusted daily OHLC, through December 31, 2025. Load only the two snapshot manifests referenced by timing-study provenance. Verify manifest and file SHA-256 before use; never execute archive code or extract browser profiles. Study 2006–2025; retain preceding observations only for warmup. This tests mechanics and price controls, not an unbiased stock selector. No new ticker or threshold is chosen after seeing performance.

Let C be adjusted close and B the SPY adjusted close on the same observed session. Relative return is `(C[t]/C[t-k])/(B[t]/B[t-k])-1`. Zero is neutral. Freeze three rules:

1. **S20 continuation:** sign of 20-session relative return; evaluate at 5 and 20 sessions.
2. **S5 reversal:** opposite sign of 5-session relative return; evaluate at 5 and 20 sessions.
3. **L12-1 momentum:** sign of `(C[t-21]/C[t-252])/(B[t-21]/B[t-252])-1`; evaluate at 6, 12 and 18 calendar months.

No fitted weights, trend gates, automatic strategy switching, author ranking, stop-loss tuning or selected winner. Short decisions occur every fifth SPY session from the first observed session on/after January 1, 2006; long decisions every 21st on the same anchor. Only complete aligned lookback windows qualify. Keep excluded insufficient-history decisions visible, including pre-IPO cases. Record every feature's simulated UTC `as_of`; it is a conservative 16:00 New York session-close assumption, not historical receipt time or an early-close calendar reconstruction.

Enter at the next SPY session's adjusted opening price, strictly after the decision close. For a session horizon h, exit at entry-session index plus h. For a calendar horizon m, exit at the first observed SPY session on/after entry date plus m calendar months. Missing stock entry/exit prices on mature dates means unavailable; never substitute a later stock quote. An exit beyond the dataset is pending. Missing benchmark sessions shared by all stocks remain an acknowledged calendar limitation.

Cost scenarios are 10, 25 and 50 bps on each side. For a hypothetical fully invested long cohort, `net=(exit/entry)*(1-c)/(1+c)-1`; SPY uses identical timing and costs. Report this same long outcome for both signal directions, clearly labeled: a bearish signal does not turn its negative return into realizable short profit. Gross absolute direction and gross relative direction hit rates are separate. Zero realized return/excess is a tie, not a hit. No account CAGR, short returns or portfolio drawdown follows from overlapping cohorts.

## Output and decision rules

Retain all seven rule/horizon combinations, both signs, each cost scenario, missing and pending outcomes. Report counts, mean/median long return, mean excess, absolute-direction hit rate, relative-direction hit rate, worst long cohort and best/worst observed excess. Group by 2006–2012, 2013–2019 and 2020–2025, retaining cross-boundary outcomes separately. Means describe complete observed cohorts; clearly disclose unavailable counts and do not qualify incomplete groups. The repeated names, dates, horizons and costs are not independent trials.

For upward signals, net excess and left-tail loss matter more than hit rate. For downward signals, separately evaluate actual declines and relative underperformance. An underperformer can still rise. A later useful avoidance study must simulate an explicit replacement/cash policy and its opportunity cost; this first study does not claim it.

No initial result promotes a strategy. Inspect stability, coverage and cost sensitivity, then validate a predeclared shortlist on historical-universe data and genuinely future observations. Already inspected 2006–2025 results cannot become an untouched holdout. [Backtest overfitting research](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) motivates full trial logs, date-block uncertainty and multiple-comparison controls rather than a winning-chart search.

## Evidence-enhanced study and data gates

Reuse the equity subsystem's immutable `events.py` and `observations.py`; do not copy the sports text-overwrite behavior. Each event needs stable security identity, original URL, publication, retrieval, first-usable time, revision hash, event identity, extraction evidence, and permitted retention. Distinguish source publication from our observation. A modern LLM can know later outcomes even when shown old material, so historical extraction is audited and never treated as an unknowing historical stock picker.

For earnings: compare event-only, price-only and combined arms under one eligibility universe; archive expectations before release or explicitly use as-filed seasonal EPS changes. For relationships: freeze a dated edge list with supporting disclosures; no present-day graph backfill. For social: curate sources without selecting them for already-seen winning returns; deduplicate syndicated events, log unsuccessful and ambiguous calls, and prohibit future likes/views from old feature rows. Callsbyjmo requires an auditable original-call sample; no verified full ledger is currently available.

Missing point-in-time earnings, relationship or social inputs cause **not tested**, not zero-valued features or synthetic headlines. Historical evidence uses verified availability plus realistic processing delay; prospective evidence uses actual observation clocks. The first cached study must state these three arms are untested. Platform access/retention and original-price/delisting gaps are catalogued in `EQUITY-SIGNAL-DATA-FEASIBILITY-2026-10-10.md`.

## Path from experiment to a useful tool

1. Reproduce these controls and reject arithmetic/timing errors before interpreting returns.
2. Audit a bounded original-event sample and delisted-inclusive price source before purchasing or collecting at scale.
3. Register each evidence-enhanced comparison before observing labels; purge overlapping labels across train/test boundaries (18 months for the longest label).
4. Measure incremental value against matched controls, market/sector exposure and alternative event-matched dates. Use date-block uncertainty and account for repeated trials; no optimization until a desired return appears.
5. Freeze a small surviving shortlist for prospective paper evaluation. Store predictions before outcomes, report calibration only if probabilities were actually fitted and evaluated, and disclose coverage failures.
6. Only after independent replication and a separately approved equity risk/operating standard consider an execution proposal. Existing Kalshi gates and sizing caps are unchanged.

A future watchlist should show bullish/bearish/neutral, horizon, source evidence, availability, invalidation condition, historical limitations and last update. It must say **insufficient evidence** where the system cannot support a call. No current stock recommendations are produced from the archive's stale 2025 endpoint.
