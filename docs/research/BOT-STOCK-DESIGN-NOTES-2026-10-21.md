# Bot-style stock research: data and proposed rules

Prepared October 21, 2026, before this reviewer ran or inspected any new strategy performance. This is a design recommendation to the integrating researcher, **not the final preregistration or a backtest result**. The final registration must settle exact conventions before execution. No market-data requests, model calls, orders or charges were made for this inventory.

## What can be tested now

The private QuantLab sibling workspace already has 27 real-instrument daily series. All 27 CSV SHA-256 values were recomputed and matched their saved manifests on October 21. This checks preservation of those inputs, not independent correctness of the vendor's historical prices. Paths below are relative to that sibling workspace, one level above this Git checkout.

| Snapshot | Instruments | Coverage | Manifest SHA-256 |
|---|---|---|---|
| `research/millennium_study/data/raw/20261006T235316726732Z` | SPY, QQQ, XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY | SPY from 1997-01-02; QQQ from 1999-03-10; nine sectors from 1998-12-22; all end 2026-10-05 | `ed4881322ebb2a760da4d8873b2eaf256c4ccad8d8d6ad44f25b59f39578403c` |
| `research/timing_study/stock_data/raw/20261007T164807615675Z` | AAPL, MSFT, INTC, CSCO, ORCL, IBM, NVDA, AMZN, GOOGL, META, TSLA | All end 2025-12-31; first dates below | `0ed2582080c0d91a79635bc1dbea1ef77f846819ec13f5135713aa72e5cf54ea` |
| `research/high_return_study/actual_funds/data/raw/20261007T050106804318Z` | SSO, QLD, UPRO, TQQQ, TECL | All end 2026-10-05; first usable dates below | `8d62739016612f44c25fa3559ad98fe76a9cec661784cf59ee423613d34aa698` |

The common schema is `Date, Open, High, Low, Close, Adj Close, Volume, Dividends, Stock Splits`; ETF series also have `Capital Gains`. Provider is Yahoo Finance through yfinance 1.7.0. Retrieval used `auto_adjust=False`, `actions=True`, `repair=False`. Saved OHLC already use the vendor's split adjustments; `Adj Close / Close` supplies the additional distribution adjustment for research OHLC. Do not add distributions again to an adjusted total-return ledger.

Stock first dates and row counts: AAPL/MSFT/INTC/CSCO/ORCL/IBM 1997-01-02, 7,296 each; AMZN 1997-05-15, 7,203; NVDA 1999-01-22, 6,778; GOOGL 2004-08-19, 5,377; TSLA 2010-06-29, 3,902; META 2012-05-18, 3,425. These are eleven deliberately selected surviving companies, including famous winners, not a historical investable universe with delisted failures.

Actual leveraged-fund first saved dates and row counts: SSO/QLD 2006-06-21, 5,104 each; UPRO 2009-06-25, 4,346; TQQQ 2010-02-11, 4,187; TECL 2008-12-30, 4,468. TECL's **XLK-matched** comparison must start no earlier than 2012-07-02 because the predecessor fund used a different benchmark. The preserved issuer definitions and source URLs are in `research/high_return_study/actual_funds/definitions.json`. Actual fund prices already include their expenses and financing; adding synthetic carrying charges would double charge. Unavailable pre-inception history must stay absent.

For a uniform new study, end all performance at 2025-12-31. Suggested main window is 2000-2025 where available; a separate common 2014-2025 window supports the complete 27-instrument sample. Older prices can warm indicators. This known history is retrospective; it is not an untouched holdout.

## The practical $1,000 distinction

Use the established, explicitly **fractional adjusted total-return research ledger** with fresh $1,000, a $1 minimum trade and self-financed costs for this screen. Actual whole-share feasibility remains unverified. Rounding these adjusted units down to integers would not repair it: historical vendor prices reflect later splits, so an integer adjusted unit is not an actual historical share.

The stock action audit has columns `ticker,date,Dividends,Stock Splits,prior_vendor_split_adjusted_close,dividend_fraction_of_prior_close,adjusted_overnight_proxy_return,nominal_open_plus_dividend_return_approximation,intraday_price_return`. The leveraged-fund action file has `ticker,date,Dividends,Stock Splits,Capital Gains`. Neither supplies a complete dividend payable-date ledger, historical broker eligibility or settlement timeline. The previous stock audit already documented IBM's 2021 factor 1.046 as a Kyndryl distribution and GOOGL's 2014 factor 1.998 as a different-share-class distribution. Treating every nonzero `Stock Splits` value as a literal same-share split would invent holdings. See the preserved `research/timing_study/stock_sources.json` and [IBM distribution FAQ](https://www.ibm.com/investor/services/faqs-about-the-kyndryl-holdings-inc-distribution).

A later executable $1,000 model needs verified nominal prices, genuine split/deliverable mappings, dividend receivables/payment dates, settlement and actual order constraints. This should not be silently substituted with fictional integer shares to make a research screen look operational.

## Finite proposed screen

The following twelve rules are deliberately simple local adaptations. They are not twelve independent discoveries, nor a replication of a named social bot. The final integrating registration may choose a documented subset or superseding exact conventions **before** seeing new performance. No threshold search is proposed.

All signals use completed daily bars. Execution follows at the next available opening, or a separately declared additional-delay stress. Use adjusted OHLC consistently; gaps are adjusted overnight proxies. No signal may use the completed close to obtain that same session's opening. For actual leveraged wrappers, use the corresponding unleveraged SPY/QQQ/XLK signal and actual fund execution prices. No shorting or margin borrowing.

Notation: `C,O,H,L,V` are completed bars; `SMA_n` is an n-close arithmetic mean; `SD_n` for Bollinger bands is population standard deviation of n closes; `EMA_n` uses recursive alpha `2/(n+1)`, seeded at the first available close. Root's integration decision fixes **252-bar warmup for every rule**. `TR=max(H-L,abs(H-Cprev),abs(L-Cprev))`. `ATR20` here is a simple 20-TR mean, a local convention. Missing or invalid inputs give no new entry. Conditional exits take priority, and a just-exited trade cannot reopen at the same decision. Timed holds mean N signal bars translated by a constant execution lag, so a one-bar hold earns one complete opening-to-opening interval rather than merely the entry session's daytime move.

| ID | Exact proposed mechanism | Relationship to old work / source |
|---|---|---|
| B01 | Long while `EMA12(C)-EMA26(C) > EMA9(MACD)`, otherwise cash. | New expression of trend; official MACD example uses 12/26/9, but this binary allocation is local. [MACD documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/moving-average-convergence-divergence). |
| B02 | Enter when `C > SMA20+2*SD20`; exit when `C < SMA20`. | Volatility breakout, related to the previously tested closing Donchian family. [Bollinger's own rules](https://www.bollingerbands.com/bollinger-band-rules). |
| B03 | Enter when previous close was below its lower Bollinger band and current close recovers to or above its current lower band; exit at/above SMA20 or after five held sessions. | Local recovery/contrarian hypothesis, **not** Bollinger's instruction to buy every lower-band touch. Same family as B02; not independent evidence. |
| B04 | Compute fast K from the trailing 14-bar high/low range, slow K as its 3-bar mean. Enter on `Kprev<=20<K`; exit at K>=80 or after ten held sessions. Flat ranges invalidate entry. | New expression of short-term reversal; thresholds/holding period local. [Stochastic implementation documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/stochastic). |
| B05 | Enter above `EMA20+2*ATR20`; exit below EMA20. | Related volatility breakout; local Keltner-style variant, not independent from B02. |
| B06 | Previous Bollinger 20/2 envelope lies strictly inside `EMA20 +/- 1.5*ATR20`; current envelope no longer does and C>SMA20. Enter, then exit below SMA20 or after ten held sessions. | Local squeeze-release adaptation. [Official squeeze-indicator documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/squeeze-momentum). |
| B07 | Enter when C exceeds the previous 20 closes and V exceeds 1.5 times the previous 20 volumes; exit below SMA10 or after ten held sessions. | Adds volume confirmation to old Donchian; does not establish a new independent source of alpha. Vendor volume conventions need explicit treatment. |
| B08 | After an observed upward gap `2%<=O/Cprev-1<=15%`, current volume at least 1.5 times the previous 20-volume mean, and positive same-day body C>O, buy the following session and hold one opening-to-opening interval. | Local delayed gap continuation; the source catalog records the proposed Grok-bot screen being adapted. A nominal-price filter is omitted because these are adjusted prices. This is not an exact bot replication or news classifier. |
| B09 | After an observed downward gap `-15%<=O/Cprev-1<=-2%`, current volume at least 1.5 times the previous 20-volume mean, and recovery C>O, buy the following session and hold one opening-to-opening interval. | Local delayed gap recovery with the same proxy limitations, related reversal hypothesis. No unobserved intraday fill. |
| B10 | If one-day return is at most -2 times the sample SD of the **previous** 20 returns, and C>SMA200, enter for five sessions. | Local volatility-normalized shock reversal; related to prior pullback/RSI work. |
| B11 | If TR exceeds twice the previous 20-TR mean and `(C-L)/(H-L)>=0.8`, enter for three sessions. Zero range excludes entry. | Local range/close-position continuation; previous IBS work used the opposite range location. |
| B12 | Long when at least two of `MACD histogram>0`, `C>SMA50`, and `C/C_lag20-1>0` pass; otherwise cash. | Fixed vote ensemble; all three are related price-trend information, not independent analysts. |

The frozen registration retains the vendor volume series without adding an action-window exclusion. Volume confirmation remains limited by one vendor's current-vintage adjustment conventions; it is not an audited historical tape. No additional split filter may be introduced after observing results.

Root's integration choice fixes same-product buy-and-hold, SMA200 and closing Donchian55/20 as controls. A repeated old rule is a control, not a new algorithm. Cost cases should vary 10/25/50 bps per side independently from lag1/lag2, rather than combine both into a single stress that cannot explain which assumption caused failure.

## Short-period evaluation that addresses the reels

Record every account's net CAGR, actual duration, maximum opening/closing drawdown, every calendar year, turnover and costs. Record all eligible fresh-start outcomes over 1/5/20/63/252 sessions for the preregistered universe and rules, or a transparently bounded subset if full cohort storage is too large. Preserve zero-trade/zero-return cases. Report median, lower quantiles, maximum, fractions losing, doubling, increasing tenfold and increasing one hundredfold, and the most severe interim loss. A maximum must include its exact start/end dates and selection status. Overlapping windows are correlated; counts are historical frequencies, not future probabilities. An 18-hour social claim cannot be replicated with daily bars, and no short-period return should be mechanically annualized as an expected annual earning rate.

Select any headline candidate on the old training interval only, then fund it afresh in the later interval. Keep the full retrospective leaderboard as a separately labelled description. Reusing this already-known history means even chronological validation is not pristine out-of-sample discovery. Distinct signals may produce identical paths: count unique paths as well as rule IDs and scenarios.

## Primary source reading scope and limits

On October 21 this reviewer retrieved the full public text of [John Bollinger's rules](https://www.bollingerbands.com/bollinger-band-rules), and the introduction/usage portions of QuantConnect's three indicator pages linked above. Bollinger cautions that a band touch alone is not a signal, that outside closes initially suggest continuation, and that bands do not justify a normal-distribution confidence claim. The documentation specifies indicator calculations/examples; it does **not** validate these proposed trading policies or promise profits.

The [QuantConnect strategy-library index](https://www.quantconnect.com/docs/v2/writing-algorithms/strategy-library) was inspected for candidate scope. It includes short reversal, volume/momentum, leveraged ETFs, intraday momentum, fundamental and options strategies. The index is an inventory, not evidence that every strategy was read or reproduced. A direct attempted short-reversal tutorial page was inaccessible. Intraday tutorials require intraday data; fundamentals require point-in-time reports/universes; neither can be honestly inferred from these daily files.

The public NBER abstracts for [Lehmann's short-run reversal research](https://www.nber.org/papers/w2533) and [Lo, Mamaysky and Wang's technical-pattern research](https://www.nber.org/papers/w7613) were read. They motivate investigating conditional return behavior and objective rule definitions. The full papers were **not** read during this inventory, and their empirical profits are not attributed to these local rules. Earlier parent studies already cover momentum, SMA, RSI/IBS, volatility sizing, sector rotation and blends, so similar new expressions must retain their family relationships.

Local reading scope: both AGENTS files; latest handoff/state sections; repo CLAUDE beginning/current scope and ROADMAP latest sections; full parent high-return and study-v2 preregistrations; high-return/timing/millennium specifications; combo rule specification; relevant high-return, timing and combo interpretation sections; all three input manifests, CSV headers/date counts/hashes, actual fund definitions and action-file headers/samples. This is not a claim to have read every line of either repository or every data row semantically.
