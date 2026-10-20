# Long-history study: primary sources and independent review requirements

Prepared 2026-10-20, before this study's performance was examined. This is a source and design dossier, not a results report. The binding rules and all 200 parameter configurations are in [the frozen registration](long-history-registration-2026-10-20.json). Sources motivate mechanisms; they do not establish that these local implementations will profit.

The inventory contains **20 related families, ten configurations each**, plus four controls. It does not contain 200 independent algorithms or 20 exact paper replications. Momentum, trend, consistency, volatility sorting and volatility sizing overlap economically. Changing a horizon or selection count is a parameter variant.

## Data and scope

The [French 49-industry documentation](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_49_ind_port.html) was read in full, including its construction paragraph. Industries are assigned annually using SIC information, with returns following the June assignment. These are reconstructed research portfolios, not 49 funds available for a $1,000 investor throughout 1976–2025.

The [French factor description](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_factors.html) was read, particularly the market and risk-free construction paragraphs. Gross market return is **Mkt-RF + RF**, using the same monthly observations. The RF source changes from Ibbotson through May 2024 to the ICE BofA US 1-Month Treasury Bill Index from June 2024.

The [library's data-format and revision notes](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html) were read, specifically the FIZ/CIZ explanation and research-return notes. The library reconstructs history and historical values can change. Its move to CIZ changes dividend reinvestment methodology. Missing-value sentinels must be rejected; regular total-return series must not receive an additional dividend credit.

The frozen snapshot is therefore current-vintage research evidence. Lag two means one entire month between the last observation used and the holding month. It reduces an obvious information-timing problem but does not produce historical publication timestamps or a point-in-time data vintage. Synthetic wealth closes are accounting indexes, not executable security prices.

Monthly observations cannot establish daily or intramonth maximum drawdown. The registered drawdown includes initial wealth, pre/post-cost rebalance marks, month ends and final liquidation. It is a lower-resolution loss measurement. Internal index turnover, instrument replication, settlement, taxes and actual ticket feasibility remain outside this experiment.

## Mechanism-to-source map

In the table, `L` and selection count mean the values already frozen in registration. All industry weights are subject to the registered 98% risky budget; remaining cash earns the modeled RF return. All calculations stop at the registered information cutoff.

| Family | Registered local rule | Source relationship and distinction |
|---|---|---|
| MOM | Rank compounded industry returns; hold the selected winners equally. | S1 motivates industry momentum. The local long-only allocation is not the paper's winner-minus-loser portfolio. |
| SKIPMOM | Rank an L-month compounded return ending one month before the information cutoff. | S2 documents the conventional recent-month exclusion. The extra information lag and industry universe are local choices. |
| VOLMOM | Rank compounded return divided by sample monthly volatility, with a fixed denominator floor. | Combines S1 momentum motivation with S3 risk scaling. This ratio ranking is a local construction, not either paper's strategy. |
| DOWNMOM | Rank compounded return divided by RMS negative industry-minus-RF returns. | S4 motivates distinguishing downside exposure. Its downside market beta is different from this local RMS denominator. |
| SHORTREV | Select the lowest recent compounded industry returns over the registered 1–5-month horizons. | S5 gives a direct previous-month reversal construction. The longer horizons and industry long-only implementation are adaptations. |
| LONGREV | Select the lowest compounded industry returns over 24–72 months. | S6 motivates longer-horizon reversal. The local universe, horizons and monthly holdings differ from the original stock portfolios. |
| LOWVOL | Select the lowest trailing sample volatility. | S7 sorts stocks on past total volatility. Applying the idea to industry indexes changes both exposures and implementation. |
| LOWBETA | Select the lowest OLS beta of industry excess returns against market excess returns, with an intercept. | S7 and S8 motivate low-beta selection. This does not implement leveraged low-beta versus short high-beta betting-against-beta. |
| LOWDD | Select the smallest rolling compounded-wealth drawdown, including initial wealth one. | S9 motivates drawdown as a path-dependent risk measure. The local relative drawdown rank is not its conditional-drawdown optimizer or uncompounded absolute-drawdown calculation. |
| ABSMOM | Allocate each 1/49 industry sleeve only if trailing compounded return exceeds compounded RF. | S3 motivates time-series momentum; S10 illustrates separate asset/cash sleeves. No futures short positions or source-paper volatility leverage are used. |
| SMA | Hold each industry sleeve when its last wealth close exceeds the mean of its last L wealth closes. | S10 explicitly defines a monthly moving-average cash switch. Our horizons, delay, costs, universe and RF proxy differ. |
| CHANNEL | Rank the last close's location within its L-close minimum/maximum range; flat ranges score 0.5. | S11 examines trading ranges. This continuous cross-sectional score is a local adaptation, not a breakout rule reproduced from that paper. |
| REGTREND | Rank OLS log-wealth slope divided by its standard error over L+1 points. | Locally constructed trend feature, motivated broadly by S3/S11. No exact primary-paper replication is claimed. Its score is not a valid trading-edge p-value. |
| CONSISTENCY | Rank the fraction of months with return strictly above RF. | S12 studies return-sign information and distinguishes it from other momentum measures. Our monthly excess-return frequency is not its daily information-discreteness statistic. |
| INVERSEVOL | Normalize inverse trailing industry volatility, with a fixed floor. | S13 supplies the risk-budgeting context. Inverse volatility is a diagonal-risk heuristic, not a full covariance equal-risk-contribution solution. |
| INVERSEDOWN | Normalize inverse RMS negative excess returns, with a fixed floor. | Local combination of downside-risk motivation S4 and risk-budgeting motivation S13; no exact paper strategy or optimality claim. |
| VOLCAPEQ | Scale equal-weight industries by capped target annual volatility divided by estimated annual volatility. | S14 motivates varying exposure with past risk. Its inverse realized-variance factor scaling is not our unlevered monthly volatility cap. |
| VOLCAPMKT | Apply the same capped volatility rule to the market sleeve. | Same S14 distinction; no full-sample scale normalization or leverage is borrowed from the paper. |
| CPPIFIXED | Market fraction is clipped multiplier times wealth above a fixed initial-capital floor, divided by reference wealth. | S15 supplies the cushion-multiple mechanism. The local delayed monthly rebalance, 98% budget and costs provide no capital guarantee. |
| CPPIRATCHET | Use a floor fraction of the account's running peak through the cutoff, without annual reset. | S16 motivates a running-maximum floor. This is a local CPPI-style adaptation, not its optimal continuous-time policy. |

For CPPI, reference wealth and peak must come from the **same cost/window/lag account** at the information cutoff. They cannot come from a frictionless shared signal portfolio. A fresh evaluation account starts with $1,000; no training-period wealth or peak carries into it.

## Original sources and actual reading scope

These are specific inspected sections, not claims that every page of every paper was read. Publisher abstracts and search-indexed publisher text are identified as such. No results from these papers are adopted as results of this repository.

| ID | Original source | Material actually read |
|---|---|---|
| S1 | Moskowitz and Grinblatt (1999), [Do Industries Explain Momentum?](https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00146) | Publisher abstract and publication metadata. Full empirical tables and exact original portfolio implementation were not inspected. |
| S2 | Kenneth French, [Monthly Momentum Factor construction](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor.html) | Entire short construction page, including prior months 2–12 and stock eligibility. This is the data author's method specification, not a new journal-paper claim. |
| S3 | Moskowitz, Ooi and Pedersen (2012), [Time Series Momentum](https://fairmodel.econ.yale.edu/ec439/mosk.pdf) | Abstract/introduction and section 4.1, equation (5), PDF page 9 / printed page 236. Source uses signed futures positions and volatility scaling. |
| S4 | Ang, Chen and Xing (2005 working paper; 2006 publication), [Downside Risk](https://www.nber.org/papers/w11824) | NBER's search-indexed abstract and publication record; direct page/PDF retrieval failed. It concerns sensitivity to declining markets, not a downside-RMS trading prescription. |
| S5 | Kenneth French, [Monthly Short-Term Reversal Factor construction](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_st_rev_factor.html) | Entire short page, particularly prior-month sorting and low-minus-high construction. |
| S6 | De Bondt and Thaler (1985), [Does the Stock Market Overreact?](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1985.tb05004.x/full) | Publisher-indexed abstract, section I empirical-test discussion and formation/test-horizon discussion. Original overlapping portfolios and selection issues are not silently inherited as independent tests. |
| S7 | Baker, Bradley and Wurgler (2011), [Benchmarks as Limits to Arbitrage](https://pages.stern.nyu.edu/~jwurgler/papers/wurgler_bradley_baker.pdf) | Author-hosted manuscript, introduction and stock volatility/beta sorting description, PDF pages 2–5. |
| S8 | Frazzini and Pedersen (2010 working paper), [Betting Against Beta](https://www.nber.org/papers/w16601) | NBER abstract and method description in the indexed abstract. Full paper not inspected for this dossier. |
| S9 | Chekhlov, Uryasev and Zabarankin (2005), [Drawdown Measure in Portfolio Optimization](https://www.math.columbia.edu/~chekhlov/IJTheoreticalAppliedFinance.8.1.2005.pdf) | Author-hosted original paper: abstract, section 3 definition 3.1/equation 3.2, and section 3.1; PDF pages 1 and 7–9. |
| S10 | Faber (2013 update), [A Quantitative Approach to Tactical Asset Allocation](https://mebfaber.com/wp-content/uploads/2016/05/SSRN-id962461.pdf) | Author-hosted paper: rule and assumptions on printed pages 19–22, separate sleeves on page 29, and horizon discussion on page 33. Original same-close execution and excluded costs are not copied. |
| S11 | Brock, Lakonishok and LeBaron (1992), [Simple Technical Trading Rules and the Stochastic Properties of Stock Returns](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1992.tb04681.x) | Publisher abstract describing moving-average and trading-range tests; no claim to have reproduced their bootstrap or exact rules. |
| S12 | Da, Gurun and Warachka (November 2011 manuscript), [Frog in the Pan: Continuous Information and Momentum](https://business.uq.edu.au/sites/default/files/events/files/mitch-warachka-paper.pdf) | Original authors' university-hosted manuscript: abstract and section 2, equation (1), PDF pages 7–10. This version predates the 2014 journal article. |
| S13 | Griveau-Billion, Richard and Roncalli (2013), [A Fast Algorithm for Computing High-dimensional Risk Parity Portfolios](https://arxiv.org/pdf/1311.4057) | Authors' manuscript, sections 1–2, PDF pages 1–2, including risk-contribution definition. Used for context, not to claim inverse-volatility weights solve its general problem. |
| S14 | Moreira and Muir (2016 manuscript), [Volatility-Managed Portfolios](https://conference.nber.org/confer/2016/LTAMs16/Moreira_Muir.pdf) | Authors' NBER-conference manuscript: abstract and sections 2.1–2.2, PDF page 7 / printed page 6. |
| S15 | Black and Perold (1992), [Theory of Constant Proportion Portfolio Insurance](https://www.sciencedirect.com/science/article/abs/pii/016518899290043E) | Publisher-indexed abstract describing cushion-multiple exposure and constraints; direct publisher access returned 403. Full mathematical derivation was not inspected. |
| S16 | Grossman and Zhou (1993), [Optimal Investment Strategies for Controlling Drawdowns](https://onlinelibrary.wiley.com/doi/10.1111/j.1467-9965.1993.tb00044.x) | Publisher abstract in full, including running-maximum floor and surplus allocation. No proof that its continuous-time assumptions apply to this monthly model. |

There is no verified exact published source for every local feature. In particular, the regression score and inverse-downside allocation are research constructions. Attaching a paper with similar vocabulary would not turn them into established strategies.

## Multiple testing and interpretation

[White (2000), A Reality Check for Data Snooping](https://users.ssc.wisc.edu/~behansen/718/White2000.pdf), was inspected in section 2b, printed pages 1103–1105 / PDF pages 7–9, including the stationary-bootstrap algorithm and centered maximum statistic; section 2c's extensions were also read. This motivates the registered joint resampling diagnostic.

For the 200 primary evaluation accounts, use monthly net return differences against the matched costed CMKT account. Center each candidate's series by its own mean. Each replicate applies the **same** stationary-bootstrap time indices to all 200 columns, preserving contemporaneous cross-strategy dependence. Restart a circular block with probability 1/6; otherwise advance one observation. Use the registered 2,000 replicates and seed 20261020, compare each observed mean to the maximum centered bootstrap mean across all candidates, and use `(1 + exceedances) / 2001`. A common square-root sample-size factor cancels in this comparison.

The stationary-bootstrap mechanism originates with [Politis and Romano (1994)](https://doi.org/10.1080/01621459.1994.10476870). The publisher's indexed abstract was inspected; its original scanned PDF was not text-readable here. The concrete resampling steps were read in White's paper instead. [Romano and Wolf (2005)](https://www.econ.uzh.ch/dam/jcr:ffffffff-935a-b0d6-ffff-ffffa286d4d1/etca.pdf), introduction and section 2 example 2.1, supplies broader multiple-testing context. **No Romano–Wolf stepdown implementation is claimed.**

This is an assumption-dependent resampling diagnostic. It does not establish a future profit probability, an annual return floor, lower future drawdowns, or protection against data-vintage errors. It does not correct for every previous repository trial or every strategy inspected by the researcher. Nonstationary market regimes weaken the stationary approximation. The statistic measures mean return difference, not CAGR or the probability of meeting a drawdown threshold. A drawdown-oriented candidate may reasonably trail the market in mean return; that economic tradeoff must remain visible.

## Minimum independent checks before relying on results

1. **Inventory and inputs:** hash the frozen registration, raw source manifest and code; require all 200 configurations and four controls across three windows, three costs and two lags: 3,672 accounts. Verify monthly continuity, exact 49-industry order, percentages-to-decimals conversion, market-plus-RF construction, no sentinels, no hidden additional dividends and complete required warmup.
2. **Signal causality:** independently reconstruct every target from only permitted months, including the additional SKIPMOM exclusion, regression starting wealth, volatility/downside denominator floors, stable tie-breaking, flat channels and cash sleeves. Perturb later input values and truncate histories in artificial tests. Warmup must not borrow from subsequent months.
3. **Self-financing accounting:** reconcile every risky dollar holding, residual cash, absolute risky turnover, proportional fee and monthly return. Independently solve post-cost NAV, verify no short/borrowed positions, charge initial and terminal transactions, and prevent duplicate RF or terminal returns. Fixed nominal weight targets cannot replace drifted pretrade holdings.
4. **CPPI state:** reconstruct reference NAV and peak separately for every account and information lag, including before-window initialization, cost losses, no annual resets and delayed response to gaps. Record floor breaches; do not repair the series to manufacture protection.
5. **Measurements:** reconstruct 50/35/15 complete calendar-year returns, monthly returns, CAGR, turnover, fees and drawdown from the full sequence of permitted marks, including initial $1,000. Compare each strategy with the matching CMKT window/cost/lag. Never substitute close-only or different-date benchmark loss.
6. **Selection:** reproduce the registered training-only eligibility, sort order, tie-breaks and up-to-five choices before evaluation. Empty groups remain empty. Later retrospective screens must not be relabeled unseen selection. Preserve all unsuccessful configurations and failed runs.
7. **Stability and regimes:** verify positive net CAGR and strictly smaller absolute drawdown wherever the registered screen requires them; stable robustness requires all twelve full/evaluation cost/lag comparisons. Reconstruct causal regime labels with expanding history only. Named crisis and decade slices are retrospective explanations, not causal discoveries.
8. **Multiplicity:** independently reproduce shared resampling indices, centering, maximum over all 200 candidates and every adjusted p-value. Include all candidates, including losers. Verify exact comparison convention and finite-replicate correction using small artificial matrices.

Passing these checks would establish internal consistency of the registered proxy simulation. It would not yet qualify any configuration for broker execution or prove that the owner's desired counts of stable, 10% or 25% candidates exist.
