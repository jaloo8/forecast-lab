# Agent-assisted trading research: evidence and a bounded pilot

**Review date: October 19, 2026. Status: source review and proposed experiment; no new trading system activated.**

The objective remains 10–20% profit in **every calendar year**, with a $1,000 reference account. None of the studies reviewed establishes that outcome. A short backtest, an annualized return, and a well-written investment report answer different questions. No finite historical test can guarantee the annual floor in future markets.

**Recommendation — Inference:** use a small team to improve source checking, rule implementation and independent criticism. Keep P&L calculation and execution constraints in deterministic software. Test whether extra agents improve research quality enough to justify their costs before paying for a daily simulated trading floor.

**Evidence labels:** **Direct** describes what a cited primary source actually reports or implements; it does not mean we independently reproduced its results. **Inference** identifies our interpretation, arithmetic or proposed design. Links below were inspected for this review. Versioned papers anchor historical claims; repository default branches are mutable observations as of the review date.

## What the named systems actually demonstrate

| System and primary source | Direct: evaluation and frictions | Inference: relevance to forecast-lab |
|---|---|---|
| **TradingAgents**, [paper v7, June 3, 2025](https://arxiv.org/html/2412.20138v7), §§3–6 and Table 1 | Specialized analysts feed researchers, a trader and risk review. The simulation is January 1–March 29, 2024; the main results table reports AAPL, GOOGL and AMZN. Its footnote explains the three-month limit using 11 LLM calls and more than 20 tool calls per prediction. I did not find a quantified commission, spread, slippage, borrowing or inference-expense deduction in its experiment specification. This is **undisclosed**, not proof those costs were zero in every implementation. | Useful ideas: explicit roles and structured evidence handoffs. Three technology stocks over part of one year cannot establish an annual floor, cross-regime robustness or affordable $1,000 operation. The reported comparison does not isolate debate's contribution from extra data, tools or compute. |
| **FinRobot**, [platform paper v1, May 2024](https://arxiv.org/html/2405.14767v1) and [equity-research paper v1, November 2024](https://arxiv.org/html/2411.08804v1), §4 | The platform organizes financial tools and agents. The equity paper's concrete evaluation is a Waste Management research report, rated for accuracy, logicality and storytelling by analysts and GPT-4, with repeated-report stability checks. That evaluation does not specify an investable portfolio trial, trading window, realized fill process or net trading-cost result. | Stronger fit for organizing filings, checking calculations and drafting a sourced thesis than for claiming a demonstrated trading edge. Report quality must be evaluated separately from forecast accuracy and account returns. |
| **FinMem**, [paper v2, December 3, 2023](https://arxiv.org/html/2311.13743v2), §§4–6 | GPT-4-Turbo uses layered memory. Main training spans August 17, 2021–October 5, 2022; testing spans October 6, 2022–April 10, 2023. Assets are TSLA, NFLX, AMZN, MSFT and COIN, selected partly for available news volume. Five trials are averaged. Crucially, §5.1 selects the risk inclination with the highest **test-period** cumulative return. Its return equation sums action-weighted log returns; I found no explicit spread, commission, borrowing or LLM-expense deduction. | Test-based setting selection is direct evidence of selection bias; the final table is not a pristine holdout. Memory organization is worth borrowing, but reported “cumulative return” needs reconciliation with actual self-financing account equity. These tests do not establish an annual floor. |
| **FinRL**, [original paper v1, November 2020](https://arxiv.org/html/2011.09607v1), §§4–5, Tables 1–2 | Reinforcement-learning infrastructure, rather than an LLM debate team. Examples cover January 1, 2019–September 23, 2020: individual SPY, QQQ, GOOGL, AMZN, AAPL and MSFT accounts start at $100,000; DJIA portfolio examples start at $1 million. The framework supports chronological train/validation/test splits, flat or proportional fees and spread parameters. These capabilities alone do not identify the exact cost configuration behind each table. | Its separation of environment, policy and evaluation is useful. Importing another RL stack does not solve data provenance, selection bias or $1,000 position-size feasibility. The cited examples cannot establish profits in every calendar year. |

**Version caution — Direct:** TradingAgents v1 gives January–March 2024 price data but June 19–November 19, 2024 in its simulation subsection. The v7 simulation uses January–March. This review uses v7 for the comparison, rather than silently combining incompatible descriptions. [Original v1, experiment sections](https://arxiv.org/html/2412.20138v1).

**Current repository observations — Direct:** the [official TradingAgents README](https://github.com/TauricResearch/TradingAgents) describes research use and sensitivity to models, temperature, dates and data. Its [configuration](https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/default_config.py) exposes debate/tool limits, vendor choices, persistent memory and a five-session reflection horizon. These current defaults do not reproduce the old paper automatically. The [official FinRobot repository](https://github.com/AI4Finance-Foundation/FinRobot) now distinguishes its original AutoGen package from newer web and desktop systems; installing a familiar package name is not evidence of installing the evaluated architecture. The [FinMem paper repository](https://github.com/NathanDDDD/finmem-llm-stocktrading) separates train/test memory use and documents an external embedding dependency even with another backbone. The [FinRL repository](https://github.com/AI4Finance-Foundation/FinRL) distinguishes its original educational/research library from a newer stack. No repository was installed or executed for this review.

## Why historical agent results need a stricter interpretation

**Direct:** Glasserman and Lin distinguish future information embedded in an LLM from a separate effect in which company knowledge distracts its sentiment judgment. Their anonymized headlines sometimes outperform named ones; the evidence does not support the simplistic claim that every effect of model knowledge always inflates returns. [Original paper, 2023](https://arxiv.org/html/2309.17322v1).

**Inference:** putting “today is 2015” in a prompt cannot erase information already encoded in model weights. A developer-hidden historical test may be hidden from our runner while still overlapping model training or the researchers' existing knowledge. Describe that as historical validation, not an untouched prospective sample. Removing tickers is a diagnostic, not a certificate that dates, products, events or numerical details cannot identify the episode.

**Direct:** a 2026 position paper explicitly separates leakage through weights from leakage through retrieved context, and argues for accounting for latency and operating costs alongside trading frictions. It is methodological guidance, not an independent reproduction of these four systems. [Kong et al., February 15, 2026, §§2–3](https://arxiv.org/html/2602.14233v1).

**Inference — implementation requirements for any future pilot:**

- Archive each source's original publication/filing availability time, retrieval time, content hash and revision status. A fiscal quarter's end is not its filing date. Current web search, rewritten stories and later popularity rankings are unsuitable historical inputs without a verified snapshot.
- Isolate each experiment's memory and retrieval index. Reflections may enter only after their measured outcome becomes available; rerunning an earlier date with later memories is leakage. A future outcome can be an evaluator label without being an agent input.
- Preserve failed and delisted firms when the claim concerns a broad selection universe. A surviving-name or news-rich sample supports only that limited sample claim.
- Keep decisions, source citations, explicit assumptions and confidence/abstention fields. Agent agreement and persuasive prose are not calibrated probabilities. Require evidence references and deterministic calculations rather than treating a narrative as proof.

**Direct:** Bailey, Borwein, López de Prado and Zhu show why investment strategy selection can overfit backtests and propose a framework for assessing that probability. [Original paper, February 2015 version](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

**Inference:** record every tried prompt, model, memory policy, debate budget, stock universe and rule variant—not just the winning strategy name. A larger agent team can search more alternatives and manufacture an attractive historical winner without discovering a durable effect. A later statistical correction cannot repair genuinely future-contaminated inputs. The experiment register and temporal validity checks must precede performance comparisons.

## The $1,000 economic constraint

**Inference — arithmetic, not a vendor price quote:** 10–20% of $1,000 is $100–$200 in first-year profit before any separately billed operating expense. Charging $10 per month against that account's economics consumes $120 annually, or 12% of starting capital. An illustrative $0.10 **per complete ticker analysis**, five tickers and 252 sessions costs $126 annually; $1 per analysis costs $1,260. Actual token use and provider bills must be measured. A free tier or an existing subscription may reduce incremental cash cost without making the workflow free to replace.

Report two ledgers: trading-account performance after trading frictions, and economic performance after additionally allocating ongoing model/data/infrastructure expense exactly once. Also disclose one-time development costs separately, with a declared amortization assumption if used. Record actual billed expense and a **shadow replacement price** based on measured usage and a dated, documented rate schedule; do not invent a provider quote. Report latency and turnover because a slow multi-step response changes the executable opportunity.

**Inference:** reserve paid reasoning for a bounded research question or material new evidence. Recomputing the same bullish/bearish discussion every session has no established advantage here. Options add contract granularity, spreads, expiry/assignment and collateral requirements; evidence from these stock studies cannot substitute for an options quote-and-lifecycle simulation.

## Proposed three-role research team

This is a proposed workflow, not authorization to install software, spend API credits, submit orders or replace the paper writer.

| Role | Bounded responsibility | Required output |
|---|---|---|
| Evidence auditor | Inspect permitted original sources and timestamps; identify missing or revised data. | Small source register with facts, availability times, hashes, caveats and unavailable fields. |
| Research/implementation author | Translate one registered hypothesis into explicit causal rules and offline tests. | Specification, code diff and cost assumptions; no discretionary historical trade narration. |
| Independent critic | Try to falsify provenance, timing, accounting and feasibility claims. One review and one bounded correction pass. | Reproducible objections, rejected assumptions and a disposition for each issue. |

A deterministic evaluator computes fills, cash, positions, costs and performance from frozen inputs. It enforces permitted actions and cannot be overruled by an agent's confidence. Human review controls research promotion. Operational paper execution remains a separate, reconciled process under existing safeguards. The LLMs help write and inspect rules; they do not produce authoritative P&L by telling a convincing story.

## Controlled ablation before a larger system

**Proposed registration — Inference; not yet run.** Compare:

1. **Control:** the existing deterministic research/checking workflow and frozen strategy specification.
2. **Single agent:** one agent performs the evidence, implementation and critique tasks.
3. **Three roles:** the bounded team above, with the same task, source packet, hypothesis allowance and total resource ceiling as the single-agent arm.

Begin with a **process-quality pilot** on fixed research tasks: correct source attribution, timestamp violations found, accounting defects found, reproducible code, completion time, invalid outputs and cost. Use evaluator-created checks whose answers are withheld from the authoring agents. If every arm implements the same strategy correctly, its deterministic backtest should agree; do not manufacture a return advantage for the team.

For a subsequent financial experiment, preregister at most one candidate amendment per arm, the common universe/dates, development window, costs, exposure and selection rule **before** opening evaluation results. An evaluator keeps the test data/results inaccessible during authorship. Use the same fill engine and $1,000 constraints for every arm. Freeze prompts, model identifiers, retrieval snapshots, code hashes, seed/repeat policy, failure handling and an explicit dollar/token/call ceiling. Equalize total budgets, not just the number of agent names. Do not adopt a larger model or add debate rounds after seeing an unfavorable test.

Report all arm/repeat outcomes, the baseline and all rejected hypotheses. Include every complete calendar-year return, years below 10%, worst year, drawdown, turnover, cost/delay sensitivity, economic net dollars and feasibility failures. Separate partial years. Treat 10% as the requested annual lower bound and report years above 20% separately rather than disguising a target-band interpretation. CAGR remains useful context, not a replacement for the annual objective.

Use chronological historical evaluation with overlap controls where labels overlap, but preserve the model-knowledge caveat. A stronger next step is to freeze the candidate before collecting genuinely new prospective paper evidence. A brief pilot cannot establish annual reliability; it can establish whether the team finds more real defects or produces more reproducible research per dollar. Advance the team only for measurable incremental value over the cheaper arm. Advance a trading strategy only through a separate evidence and execution decision.

## Review boundaries

This is a targeted review of original papers' architecture, experiment, metric and limitation sections, plus the official repository documentation/configuration linked above. It is not a full third-party code audit, replication, security approval or live performance verification. No proprietary data, personal credentials or vendor payloads are included. No new paid service, autonomous live execution, installation, benchmark run or published deployment was performed. The immediate deliverable is this source review; implementation and any paid experiment require their own concrete registration and authorized budget.
