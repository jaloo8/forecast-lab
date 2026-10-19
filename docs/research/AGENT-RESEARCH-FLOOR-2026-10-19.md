# ADR: a bounded agent research team

Status: proposed research workflow; not an installed agent runtime or trading system.
Date: October 19, 2026.
Scope: forecast-lab stock/options research, $1,000 practical reference, and the owner's 10–20% profit-in-every-calendar-year aspiration.

## Decision

Use agents to propose explicit rules, inspect data, implement experiments and challenge results. Keep pricing, signals, accounting, backtests and execution permission in deterministic code. Start with a small controlled comparison before funding a daily multi-agent debate. A persuasive consensus is not a validated edge, and a historical winner is not a promise of future annual profit.

The owner requested this investigation and a GitHub handoff. This document does not authorize live trading, paid subscriptions, new data purchases, new leverage or an always-on agent service. No third-party skill has been installed and no external model or market-data job has been launched for this investigation; ordinary coding-assistant usage is separate. API provider/balance are still needed for an informed budget; keys must be configured locally, never in chat or Git.

## What the sources support

Read the [original-source review](AGENT-TRADING-SOURCE-REVIEW-2026-10-19.md) and [pinned trading-skills code review](TRADERMONTY-REVIEW-2026-10-19.md). The former distinguishes research-report quality from demonstrated trading returns; the latter distinguishes usable checklists/software from a complete, validated trading engine. Findings are dated and scoped to the exact sources inspected.

Direct evidence: our existing annual-profit reproduction rejects all 24 stock/cost paths and all four public option-index comparisons against the annual minimum. The original stock simulation uses $10,000 fractional adjusted units; it does not establish $1,000 tradability. Historical options cash-flow results are negative and have unresolved exits, and the private cache has not been transferred here. See the [annual audit](ANNUAL-PROFIT-AUDIT-2026-10-19.md).

Inference: the next useful improvement is research quality and reproducibility, not adding more optimistic strategy proposals. More tested variants increase the opportunity for selection bias. The [probability-of-backtest-overfitting paper](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) provides a formal treatment; it does not make any particular local strategy valid.

## Alternatives considered

1. **Current deterministic research plus human/agent review.** Lowest integration effort and no required runtime LLM cost. Reuses existing causal engines and evidence. It still needs better point-in-time stock inputs and options account accounting.
2. **Small research team around the same engines — recommended pilot.** Adds role-specific review and a durable experiment record. It can improve specifications and detect defects without putting an LLM in every simulated trading day. The extra review must earn its token and maintenance cost.
3. **A full analyst/researcher/trader/risk-manager framework.** Useful as a reference architecture and perhaps a later experiment. Daily multi-agent calls add cost, nondeterminism and data leakage surfaces. Several agents sharing a model and inputs are not independent expert votes. We have no local evidence that this alternative improves net outcomes.

## Roles and decision rights

- **Research lead:** converts a source-backed hypothesis into a versioned rule. Records every proposal, rejected idea and revision; sets the trial cap before results.
- **Data reviewer:** verifies origin, permitted use, availability time, corporate actions, membership/delistings and missingness. Vetoes a test when inputs cannot support the claim. Today's financial statements/news cannot be silently queried for a historical decision.
- **Implementation agent:** writes a pure signal and an adapter to the existing deterministic engine. Cannot change evaluation dates, costs, benchmark or acceptance thresholds after results appear.
- **Independent reviewer:** checks look-ahead, event timing, leakage, counting, cash conservation and practical sizing. Receives the frozen specification and evidence, not instructions to make the strategy profitable.
- **Risk/accounting reviewer:** checks drawdown, concentration, integer option contracts, collateral, turnover, unresolved states and the $1,000 implementation limit. It can reject a candidate; it cannot authorize real orders.
- **Archivist/orchestrator:** stores spec/code/data/prompt/model hashes, calls and costs, results and failures, and the exact next action. Schedules bounded jobs only after an explicit run specification exists.

These are responsibilities, not a requirement for six paid concurrent model calls. One coding session can perform several roles sequentially, with a separate reviewer where it adds value. Broker execution is a separate system and authority boundary. A8 remains the existing stock paper writer; this research clone is not a second writer.

## Experiment record required before a new backtest

Every materially new rule needs an ID/version and timestamp, source citations, economic rationale, eligible universe and membership dates, exact formulas, finite parameter list, timing, sizing, entry/exit and missing-data policy. Hash the specification and implementation before evaluation. Record data file hashes, licenses, acquisition cost, known revisions and availability timestamps. Agent prompts/model versions/tool settings and stochastic seeds are research inputs too.

Freeze identical evaluation dates and benchmarks across alternatives. Report all complete calendar years, CAGR, worst year, drawdown, turnover, exposure, capital usage, costs, missing/unresolved cases and parameter sensitivity. Preserve losses and empty/zero-return periods. Compare fee/slippage/delay stresses with the same source data. Never substitute a profitable trade total for funded-account NAV.

For stock execution, state whether fractional shares are assumed and whether the intended broker supports the necessary order type. For options, use integer contracts and actual available cash/collateral, model spreads and lifecycle events, and retain uncertain exits. A paper fill is a separate evidence level from a simulated historical fill.

Use chronological training/validation and rolling evaluation only as registered; purge overlapping labels when relevant. Existing 2000/2006–2025 results are already known. Neither a new date split nor a prompt saying “pretend it is 2010” makes that history untouched. LLM pretraining can contain later events; a genuinely new prospective observation period must begin after a frozen registration. Do not create retrospective LLM-news-alpha claims from current web search.

All attempted configurations count toward the search budget, including agent-rejected variants whose outcomes were seen. A reviewer cannot invent an unlogged new parameter after seeing a failure. Stop when the preregistered budget is exhausted, even if nothing wins. Statistical diagnostics such as a deflated Sharpe or PBO need appropriate trial information and sample sizes; they are not a replacement for these controls.

## Proposed bounded process pilot

This is a proposed protocol, not a claim that any arm has run. See [machine-readable proposal](agent-floor-pilot.json).

First finish the frozen options reproduction when the cache arrives, and retain the negative result if reproduced. That task requires no model API credit. Next audit whether the existing stock inputs and account model can support the intended new experiment. Choose the precise candidate/data packet before activating the pilot.

Compare a deterministic control workflow, one research-agent workflow, and a small proposer/data-reviewer/skeptic workflow on the same three preassigned frozen process tasks. Allow at most three initial submissions per assisted arm, one critique round and one bounded revision per task in both assisted arms: at most six versioned submissions per arm. Equalize total call, token and dollar ceilings across assisted arms; roles share the budget. The evaluator withholds answer keys and test labels until submissions are hashed and frozen. This tiny pilot is an operational comparison, not a statistically powered estimate of trading alpha.

A later financial experiment is separate and not activated here. It requires another registration with at most one candidate rule amendment per arm, fixed dates and an evaluator-held evaluation set. Every outcome-inspected variant counts as a trial. Do not restart a trial cap after a loss or turn process-task revisions into unlogged financial searches.

Primary process outcomes: completeness of reproducibility records, independent accounting agreement, confirmed leakage/implementation defects found, failed runs retained, and total wall time/calls/tokens/cost. Financial diagnostics remain all-years net results and downside/feasibility metrics on identical dates. Do not select the preferred workflow solely by its best historical Sharpe or annual return. If extra agents only create more trials or prose, retain the simpler workflow.

Agent-assisted rule design and a trading policy that calls an LLM every day are separate experiments. The latter additionally requires archived point-in-time tool responses, timestamp-bound memory, stable model/prompt versions, repeated stochastic trials and all inference costs. It is not the first pilot.

## Credit and cost policy

Current external-model allowance is **$0 until the provider, credit balance/expiry and a numerical run cap are recorded**. This is a proposed policy; the JSON is not an implemented billing gateway. A future gateway must reserve the worst-case call cost before submission, count tool/data charges, halt on unknown usage and prevent automatic top-ups or unbounded retries. Provider dashboards remain the final billing evidence.

Use deterministic calculations locally, cache permitted source responses by content hash, retrieve a source once per task, and reserve stronger model calls for unresolved code/data issues. Limit debate rounds and context length; do not run multiple models merely to produce agreement. Provider-native batch/caching options can be assessed after identifying the provider; no pricing or feature availability is assumed here.

Track actual dollars/credits and a separate replacement-cost estimate at current published prices. Report them as alternative economic scenarios, not two expenses charged together. Allocate each recurring expense once, state the allocation method, and report economic net dollars/return alongside trading-account results. Free credit is temporary, not proof of sustainable economics. At $1,000, the target is $100–$200 per year; a hypothetical $10/month recurring service costs $120/year before trading costs. Show one-time research spending separately from ongoing strategy operation, and report both when judging practicality.

## Implementation boundary and next actions

- Prepared now: source/code reviews, this design, a bounded pilot proposal, prior corrected audit code/results and a portable GitHub handoff. Remote publication is confirmed separately by the pushed commit and PR, not by this document's existence.
- Not delivered or activated: an agent daemon, API budget enforcement, automatic strategy generation, a new funded options portfolio engine, new backtest results, paper orders or a profitable strategy.
- Next: restore private inputs and reproduce the frozen options result; identify API provider/budget; decide the first data-qualified hypothesis; then implement the smallest registry/orchestrator and its independent validation. Do not install the entire skills collection or replace existing engines as a prerequisite.

The [root handoff](../../HANDOFF.md) is the cross-computer entry point. No prior chat, account-specific memory or stored assistant conversation should be required to understand the current state.
