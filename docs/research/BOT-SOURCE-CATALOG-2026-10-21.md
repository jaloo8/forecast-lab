# Trading-bot source catalog — 2026-10-21

This is an executed source investigation, not a claim that these external bots were run or that their advertised returns were reproduced. The useful output is a set of inspectable rules, data leads and implementation lessons for separately registered local tests. No reviewed source verifies the user's reported $80-to-$8,000 result in 18 hours. That would be a 100-fold ending balance, or a 9,900% return.

The review found real engineering behind some agent systems, including explicit stock filters, multiple-agent decision flows and options accounting tools. It did not find evidence that six agent roles, Grok access, or a collection of profitable examples establishes repeatable account growth. Short-term windfalls and sustained annual performance need different measurements.

## Scope and receipts

Access date is **2026-10-21** throughout. Seventeen public repository heads were identified; this is **not seventeen complete code audits**. The [repository pins](evidence/2026-10-21-bot-sources/repository-pins.json) preserve full observed commit IDs and retrieval failures. GitHub's unauthenticated metadata API returned HTTP 403; public repository HTML supplied the observed head IDs instead. The source-reading receipts preserve paths, SHA-256 hashes and the ranges actually displayed: [A](evidence/2026-10-21-bot-sources/reading-receipts-a.json), [B](evidence/2026-10-21-bot-sources/reading-receipts-b.json). Web-normalized line numbers are explicitly distinguished from raw file line numbers.

Two new Grok source files were read completely: a 235-line screener and 147-line example configuration. The options-data notice was read completely; its downloader was reviewed selectively. Other new repositories received README/documentation inspection, not a full implementation audit. Papers were read in the sections named below. No third-party trading code, installation script, model API job or broker operation was executed for this catalog. No paid data was acquired for this source investigation.

Earlier review remains separately attributable to its original scope and pins: [agent source review](AGENT-TRADING-SOURCE-REVIEW-2026-10-19.md), [framework code review](AGENT-FRAMEWORK-CODE-REVIEW-2026-10-19.md), and [trading-skill review](TRADERMONTY-REVIEW-2026-10-19.md). Earlier reads and tests are not counted as new work here.

## Social claims and current LLM systems

### 1. The supplied Instagram posts

Fresh requests for the [post](https://www.instagram.com/p/Deqbt9GFJo9/) and [reel](https://www.instagram.com/reel/DerlYaFiEU_/) returned online-fetch throttling. Their content, account identity and trading ledger could not be independently inspected. The claim remains **unverified**, not disproven. No inference is made about whether the trades were stocks, options or cryptocurrency. A complete return assessment would need starting equity, deposits/withdrawals, all positions and orders, fees and an independently reconcilable ending balance. Screenshots and selected winners alone cannot supply that accounting.

### 2. `zostaff/grok-trading-desk`

**Pin:** `ec900a85a8a0fbb6123ee100b5c10d48e25fdcdb`. Read README architecture and both complete files linked below. The project combines agent opinions with US-stock and Solana workflows. Its stock screener selects current movers/active symbols, applies price, average-volume, relative-volume and absolute-price-change filters, then ranks candidates. Defaults include relative volume 1.5 and absolute change 2–15%; missing auxiliary fields skip corresponding guards. Its “gap” uses latest price versus previous close, so it is not necessarily an opening-auction gap. The example config has 20% profit/8% stop levels and a $2,000 budget. These are settings, not verified performance. Historical replay additionally needs timestamped candidate lists, agent inputs and decisions. Sources: [repository](https://github.com/zostaff/grok-trading-desk), [screener](https://github.com/zostaff/grok-trading-desk/blob/ec900a85a8a0fbb6123ee100b5c10d48e25fdcdb/src/stocks/screener.py), [configuration](https://github.com/zostaff/grok-trading-desk/blob/ec900a85a8a0fbb6123ee100b5c10d48e25fdcdb/config.example.yaml).

**Intake:** a transparent completed-session price/volume adaptation can be tested separately. Calling it a reproduction of Grok's discretionary choices would be false.

### 3. xAI's official X-search tooling

Read tool parameters, search behavior and cost-control guidance in the [official documentation](https://docs.x.ai/developers/tools/x-search). Searches support date bounds, but thread-fetch behavior does not inherit those filters. A historical run must inspect each retrieved item rather than assume a date argument quarantines all context. The model chooses tool calls; bounded turns, cached inputs and a deterministic spending gateway matter. A search tool can help collect potential catalysts. It does not establish a profitable decision rule or remove historical information from model weights.

### 4–6. TradingAgents, Vibe-Trading and tradermonty's skills

| Source | Current observed pin | New inspection and implication |
|---|---|---|
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) | `e8f5503e9b86d5c2710b0c76b1f686703968c9df` | Head unchanged from prior code review; fresh repository/README inspection. Prior audit evaluated independent ticker/date recommendations, not a funded $1,000 account ledger. Useful division of analytical roles; no new execution or reproduction here. |
| [Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) | `8665a53514c37e1cd8fe7c84bfed163a2a066ba1` | Head changed from reviewed `097b29f…`; current page inspected, new tree not fully audited. Prior synthetic option-pricing and equity-curve-slicing observations apply to the old audited commit only. Do not automatically carry its approval or criticisms to every new file. |
| [claude-trading-skills](https://github.com/tradermonty/claude-trading-skills) | `cb0f3aadffed6d1089db4b224162c964368baa46` | Head unchanged from prior review. Skills describe workflows; they are not a validated options fill engine. Preserve prior theoretical-price and narrow stock-adapter findings. No skill was installed or wrapper executed. |

### 7. AI Hedge Fund

**Pin:** `4e1657ddc689e3939c481a8f0955444b10f02dc9`. The pinned README was read fully (88 returned lines), plus current repository presentation. This educational project offers research/backtesting and paper-workflow infrastructure and depends on model/financial-data inputs. Those are useful integration examples; neither role personas nor an available UI proves profitable selection. This review did not audit its accounting implementation or reproduce its results. Source: [repository](https://github.com/virattt/ai-hedge-fund).

### 8. LumiBot's leveraged-ETF agent example

**Framework pin:** `05c04fd122512ddf6a7e93b20c802f63cb07c22f`. Read selected framework documentation and the substantive [TQQQ multi-agent example](https://lumibot.lumiwealth.com/agents_example_tqqq_strategy_ai_trading_bot.html). A researcher and bull/bear/judge arrangement chooses among twelve leveraged/inverse ETFs using natural-language instructions. The published example covers only January 5–16, 2026, with $100,000 starting equity and about 3.5% reported growth. That is the author's short demonstration, not our measured result or an annual forecast. Exact historical reconstruction needs the prompt/model version, tool responses, decisions and fills. [LumiBot](https://github.com/Lumiwealth/lumibot) is a framework for implementation, not an independently proven leveraged strategy.

### 9–10. Qlib and RD-Agent

**Pins:** Qlib `54355232463878d2eebb91fe0ee5fa7fa1f5976c`; RD-Agent `484776c211e4fbbeef03e0ec00d6bbee7362a4f4`. Read selected current project descriptions and short pinned README fetches; no engine audit. [Qlib](https://github.com/microsoft/qlib) organizes factor/model research and portfolio evaluation. [RD-Agent](https://github.com/microsoft/RD-Agent) automates proposal, implementation and iterative evaluation. This can accelerate engineering and rejection of weak ideas. It also makes it easier to select the luckiest of many experiments. A finite trial register, saved failures and fixed evaluation rules are prerequisites to using those capabilities honestly.

## Transparent stock and leveraged-fund approaches

### 11. QuantConnect's leveraged ETF trend example

**LEAN pin:** `de116c0de654108bc9b3bcb643571ab0b754cbb4`; only repository metadata was pinned. The [official strategy tutorial](https://www.quantconnect.com/research/15351/leveraged-etfs-with-systematic-risk-management/) was read for its method: hold SSO above its 200-day moving average, otherwise SHY. This is an inspectable strategy hypothesis. Trend timing already overlaps existing local research; a different bot wrapper does not make it a new independent alpha. Any actual-ETF comparison must use matching dates, genuine fund history and an explicit next-tradable-price convention. LEAN's full engine was not audited or run.

### 12. `sam-bateman/trading-orb`

**Pin:** `23f2400a696296cddb00166dd429c0d048bee1bb`; README read, not engine. The [author's specification](https://github.com/sam-bateman/trading-orb/blob/23f2400a696296cddb00166dd429c0d048bee1bb/README.md) uses a 20-minute opening range, subsequent morning breakouts, relative volume, a range-scaled stop/target and a same-day exit. The author reports about 8,000 parameter trials and 2.71% CAGR on $100,000. Those are source claims, not reproduced results. They illustrate why an impressive trade statistic can coexist with modest account growth. A faithful test needs intraday bars, session timing, stop/target ordering and short-borrow feasibility. Daily candles cannot recreate it. Scaling the claimed returns linearly with risk is not accepted.

### 13. `spookyspaghett/claude-trading-bot`

**Pin:** `eb51999fe4deeaeda21fe58b99384bf008eaa01f`; README strategy sections read. Its [listed rules](https://github.com/spookyspaghett/claude-trading-bot/blob/eb51999fe4deeaeda21fe58b99384bf008eaa01f/README.md) include opening-range breakout, EMA crossover, daily Donchian breakout and trend/support-resistance variants. These are mostly conventional deterministic strategies inside a paper platform. “Claude” in a project name is not evidence that a language model produces superior trades. Donchian/EMA ideas require deduplication against the local registry; ORB requires separate intraday inputs. No application or order gateway was executed.

### 14. `Luadja/alpaca-trading-bot`

**Pin:** `04e146e49fde6c5659133bcfbdfa14d0bf62ba50`; README strategy sections read. The [README](https://github.com/Luadja/alpaca-trading-bot/blob/04e146e49fde6c5659133bcfbdfa14d0bf62ba50/README.md) describes a 50/200 moving-average policy and retains a failed StochRSI/MFI variant. Keeping rejected ideas is useful process evidence; the author's “validated” description is not our independent validation. Trend crossover substantially overlaps the existing family. Regulatory, package-status and broker-pricing assertions elsewhere in its README were not adopted as verified facts.

## Options tools and evidence

### 15. Optopsy

**Pin:** `40bb8b2aa07ef8763caeadf752961faecb494efd`; minimal pinned README plus [official documentation](https://goldspanlabs.github.io/optopsy/) read. The docs advertise 38 built-in structures, historical chain inputs and account simulations with cost controls. Thirty-eight payoff structures do not imply thirty-eight profitable algorithms. This is a useful interface reference for enumerating defined-risk spreads and organizing input requirements. Contract selection, quote eligibility, assignment and lifecycle behavior still need implementation-level review before trusting an account result. No external simulator was run.

### 16. `lambdaclass/options_portfolio_backtester`

**Pin:** `afdbacc0b9b9c137edc38d656778f81b84093b2f`. Read README method/presets, all [DATA_NOTICE.md](https://github.com/lambdaclass/options_portfolio_backtester/blob/afdbacc0b9b9c137edc38d656778f81b84093b2f/data/DATA_NOTICE.md), and [downloader lines 25–145](https://github.com/lambdaclass/options_portfolio_backtester/blob/afdbacc0b9b9c137edc38d656778f81b84093b2f/scripts/fetch_data.py#L25). Presets include puts, strangles, condors, covered calls and collars; its externally funded hedge example cannot be treated as a self-financing $1,000 account. The data notice advertises SPY/IWM 2008–2025 and QQQ 2011–2025 mirrors but explicitly says upstream sourcing was undocumented. Hashes establish byte consistency, not quote authenticity or redistribution rights. The downloader warns on a hash mismatch and continues. Any local importer should fail closed and retain provenance uncertainty. No mirrored options data was downloaded by this source-review subtask.

**Value:** a potentially inexpensive historical sensitivity source, subject to independent schema/quote/coverage checks and a clear provisional label. It is not restoration of the missing original Databento cache. The notice's third-party alternatives are leads, not independently verified coverage promises.

### 17. Alpaca's official options wheel

**Pin:** `3698429289065ceb0c13ffcdc31a966c576779ad`; [README strategy and example](https://github.com/alpacahq/options-wheel) read. The implementation describes selling cash-secured puts, accepting 100-share assignment and selling covered calls. Its two-week $100,000 paper example reports $951.89 account growth versus $1,240 premiums collected: premium receipts and profit are different quantities. This is not evidence of a durable annual return. Contract affordability and lifecycle handling dominate a $1,000 adaptation; a SPY cash-secured wheel cannot simply use fractional contracts. The documented fresh-start operation liquidates positions, so it was not invoked. No broker state was accessed.

### 18. Options SOTA paper, arXiv 2610.10407v1

Read abstract, methods/results and selected appendices in the [October 2026 paper](https://arxiv.org/html/2610.10407v1). It studies model selection among option structures with deterministic sizing/resolvers and detailed market inputs. The authors report 18.32% over March–August 2025, using $1 million NAV and midpoint option fills. Appendix G.3 evaluates multiple training checkpoints on that same test window before selecting the reported checkpoint. Consequently it is not an untouched evaluation of the selected system. A news-input variation performed worse in the reported experiment. This suggests hypotheses about volatility and structure selection; it does not establish that news agents or an $80 account reproduce the result. The paper's option surfaces, contract economics and available data are materially different from the local three-session replay. No model was trained or paper result reproduced.

### 19. Bayesian wheel paper, arXiv 2512.01123v1

Read abstract, empirical protocol, cost/tables and limitations in the [paper](https://arxiv.org/html/2512.01123v1). It advertises 15.3% CAGR and a 2007–2025 history, while its empirical-protocol text says all reported results are restricted to 2020–2025; tables retain the longer dates. Historical option-chain provenance and a reproducible implementation were not established by this inspection. It uses $100,000 and cannot directly establish $1,000 whole-contract feasibility. These unresolved scope and data issues mean its headline should not be used as a trusted benchmark. A transparent wheel can be investigated independently, with actual quotes and account constraints, without asserting this publication was reproduced.

## Independent agent benchmarks and engineering references

### 20. StockBench

Read abstract/introduction, task/data sections and main results of [arXiv 2510.02209v1](https://arxiv.org/html/2510.02209v1). Its experiment spans March–June 2025 and a selected twenty-stock universe. Agents receive opening-price information and trades are modeled at opening prices; execution latency therefore needs scrutiny. The introduction and results discussion give differing broad descriptions of how often models beat the baseline. Use the table and exact configuration, not an appealing summary sentence. This is useful evidence that a benchmark can evaluate agents; it is not decades of verified account profitability or proof of an uncontaminated modern-model backtest.

### 21. Agent Market Arena

Read evaluation and results sections of [arXiv 2510.11695v1](https://arxiv.org/html/2510.11695v1). The paper compares model/framework combinations over short stock/crypto intervals and reports wide variation across configurations. A description of live evaluation is not by itself a broker-confirmed fill ledger. This is evidence to test framework sensitivity and retain failures, not to select the best reported pair and promise the same outcome. Its markets/windows do not verify the user's Instagram examples.

### 22. Alpha Arena / Nof1

The [official Nof1 site](https://www.nof1.ai/) was accessible and linked to [Alpha Arena](https://www.alphaarena.ai/), whose page returned HTTP 403. Current competition return claims and a full account ledger were not verified. Search-result and social summaries about Grok winning a contest were therefore excluded as performance evidence. Alpha Arena is also distinct from the user's earlier **Alphaledger** bond-infrastructure question; the names must not be conflated.

### 23–24. Freqtrade and Hummingbot

**Pins:** Freqtrade `0db79d391f646eafbdf3c0976dd55dc90b296522`; Hummingbot `9af100d6822da7d2d0291a906c730ef172284ee2`. These crypto-oriented tools are engineering references, not new stock/options results. Read [Freqtrade's lookahead analysis](https://www.freqtrade.io/en/stable/lookahead-analysis/): comparing recomputed indicators and shifted decisions is useful for detecting future-data dependence; its detector's large wallet assumptions are not small-account feasibility tests. Read [Hummingbot's strategy overview](https://hummingbot.org/strategies/): market making requires order-book, queue, latency and fee assumptions. Daily stock bars cannot credibly reproduce that edge. Neither stack was installed or audited end to end.

## What should actually enter local research

These are intake recommendations, not a claim that new tests have already completed. Each adopted rule must appear in a separate frozen registration before its performance is viewed.

| Candidate or control | Why it belongs | Inputs and limits |
|---|---|---|
| Gap/relative-volume continuation and fade | Concrete new hypothesis from the inspected Grok screener, without pretending to reconstruct agent opinions | Completed-session features; next-open orders; fixed thresholds; volume completeness; stock survivor bias disclosed. Check prior registry before calling the family new. |
| Opening-range breakout | Distinct intraday timing mechanism in multiple bots | Minute bars, opening auction/session rules, realistic intrabar ordering and execution. Missing inputs must be a recorded blocked test, not an invented daily-bar substitute. |
| Actual leveraged-ETF trend and breakout controls | Measures incremental value over already studied trend exposure | Actual fund inception dates, benchmark matching, next-open fills and deep-drawdown stress. Synthetic long histories remain separate models. |
| Defined-risk debit/credit spreads, collars and long premium | Tests option structures rather than treating stock predictions as options returns | Real bid/ask quotes, expirations, integer contracts, fees, collateral, exercise/assignment, financing and total equity. A fixed dollar account must fund its own premiums. |
| Implied-versus-realized-volatility conditions | Mechanistic options hypothesis motivated by the new paper | Reliable contemporaneous option surface and lagged underlying volatility. No invented implied volatility or midpoint-only profitability claim. |
| Cash-secured wheel and covered-call control | Tests frequently advertised premium income against total return | Full cash/stock collateral and lifecycle; $1,000 may legitimately generate no eligible contract. Do not count collected premium as standalone profit. |
| Catalyst/news experiment | Measures whether information adds anything to a price-only baseline | Publication and first-seen timestamps, archived payloads, same-time price controls, fixed prompts/models and prospective shadow decisions. Today's search results cannot reconstruct missing historical news exposure. |

EMA/200-day trend, Donchian and common momentum variants should first be mapped to existing registrations. Rebranding an existing rule with a new model or changing one threshold does not create independent evidence. Parameter and account-scenario counts must remain distinct from strategy-family counts.

## A useful agent floor for this project

The practical design is a coordinated research process with auditable artifacts:

1. A scout records primary sources, exact proposed rules, reading scope and missing inputs.
2. A data reviewer checks timestamps, corporate actions, quote coverage and provenance.
3. A researcher submits a finite preregistration, including failures that must be retained.
4. A deterministic simulator computes cash, positions, costs and all candidate results.
5. An independent skeptic reconstructs selected accounts and checks causality, overfitting and account feasibility.
6. A coordinator ranks evidence, records decisions and hands off a frozen candidate for prospective paper evaluation.

This role allocation is a proposed workflow, not an active service or evidence that six agents multiply alpha. The simulator and budget checks must enforce constraints in code; prompts are insufficient. Models should summarize and propose, while numeric position limits, spending limits and account reconciliation remain deterministic. Separate news-without-LLM, price-only and LLM-assisted variants are needed to measure incremental value.

For a $1,000 reference account, a hypothetical $10/month service costs $120/year, or 12% of starting equity, before trading costs. This arithmetic is not a vendor quote. Cache public research, batch requests, reuse existing qualified data and reserve paid models for decisions whose incremental benefit can be measured.

## Measuring a short-period windfall honestly

For each permitted policy, report the full distribution of fresh-start 1-, 5-, 21- and 63-session outcomes where data supports it, alongside account drawdown, loss frequency, worst path, costs and the share of starts reaching predefined multiples. Preserve failed/depleted accounts and all starts. Report whole-account return, not the best option trade's percentage gain. An 18-hour outcome cannot be turned into a credible annual forecast by exponentiation.

The new local simulation report should remain the authority for what was actually tested and what passed. This catalog establishes sources and candidate mechanisms only. None of the source results above establishes future 10–20% profit in every calendar year, or a repeatable 100-fold short-period return.
