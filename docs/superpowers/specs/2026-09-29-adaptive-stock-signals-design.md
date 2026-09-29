# Daily adaptive stock signals: proposed research design

Status: owner approved implementation on September 29 UTC. The first release implements the advisory signal and immutable journal, using the original pilot's read-only positions as reference states. Dynamic account execution remains a separate phase. No profitability is established. The existing pilot and nine frozen portfolios retain their orders, exits, method hashes and histories.

## Choice and scope

Recommend one transparent, stateful price/risk rule, refreshed after each completed session. A fitted multi-factor model is an alternative, but our short survivor-selected price study and incomplete point-in-time news/financial archive cannot support an honest validation of it yet. Daily optimization of whichever recent rule made money is rejected because it would confound adaptation with repeated selection of lucky outcomes.

Adaptation means prices, volatility and the resulting actions change under an unchanged published formula. Changing weights, thresholds, universe policy or execution assumptions creates a new version with a new prospective start. Retain every losing and empty version.

The first slice is an isolated research signal journal, not another funded account or a modification to current paper exits. A later separate virtual account can test dynamic exits after its state transitions and execution semantics pass review. No live brokerage calls, options, new dependencies or risk-cap changes belong to this design.

## Candidate formula

Use completed regular-session, split-adjusted prices and the existing verified session-source reconciliation. Let P be a stock close and B be SPY's close on the same session t. All returns below use natural logarithms.

```
E(h) = log(P[t] / P[t-h]) - log(B[t] / B[t-h])
v    = sample standard deviation of the stock's last 20 daily log returns
S    = 0.5 * (E(20) / (v * sqrt(20)) + E(60) / (v * sqrt(60)))
```

S is a dimensionless ranking feature. It is neither an expected return, a statistical significance test nor a probability. The 20/60-session windows, equal weights and thresholds below are predeclared research choices, not optimized or proven by the cited literature. This remains a momentum hypothesis; volatility normalization cannot be assumed to cure the failed historical momentum baseline.

Require 61 aligned real, positive-volume SPY/stock sessions and finite positive v. Retain the existing $5 entry-price floor and $20m median 20-session dollar-volume entry floor. An invalid feature is unavailable, never zero. Future observations, history revisions, missing required sessions and unverified exchange-calendar gaps invalidate a decision rather than authorizing a guessed action.

| Position state | Condition | Research action |
| --- | --- | --- |
| No position | Invalid/stale inputs or quarantined new-entry candidate | WAIT_DATA; explain the missing evidence |
| No position, valid eligible candidate | S >= 0.5 | BUY candidate |
| No position, valid eligible candidate | S < 0.5 | WATCH; remain in cash |
| No position, valid prices | Entry price/liquidity filter fails or outside current candidates | WATCH with exclusion reason; remain in cash |
| Held position, valid price evidence | S <= 0 | SELL the owned position; never short |
| Held position, valid price evidence | S > 0 | HOLD |
| Held position | Invalid price evidence | WAIT_DATA; retain last known holding and visibly stale mark |
| Pending entry or exit | Any same-session retry | PENDING; never create a duplicate instruction |

Eligibility and capacity are separate from the score. An eventual account ranks BUY candidates by descending S, then symbol, selects at most three per session and applies the unchanged $10 order, five-active-position, cash and loss-pause controls. No held stock is sold simply for falling out of today's earnings calendar or top-three ranking. Entry-only price/liquidity filters do not suppress an otherwise valid exit signal. Held names remain in the data-fetch union regardless of candidate membership.

The different entry/exit thresholds create a hold band to reduce churn. This is a design hypothesis motivated by transaction-cost research, not a claim that 0.5 is optimal. No minimum holding duration, stop order or fixed-time exit is introduced by the signal journal.

## News, earnings and availability

Archive verified official-company releases and filings with URL, content hash, source publication metadata and actual first observation time. A newly verified event triggers data refresh and attaches context to the next daily decision. The daily execution clock does not become intraday merely because an article arrives.

Version 1 assigns no numerical sentiment or invented news probability. News alone cannot change S. Current coverage is incomplete; the dashboard must show the actual count and last collection time. Future earnings features require matched fiscal period, currency and accounting basis, plus an estimate archived before the announcement. Currently captured post-announcement estimates cannot stand in for historical consensus. Missing financials remain null.

## Data and component boundaries

Implement a pure typed signal function returning a DataFrame: symbol, as_of, session_date, source_hash, method_hash, price_as_of, E20, E60, volatility20, score, state, action, reason, candidate_eligible and event references. Separate feature validity, entry eligibility and position state so unavailable data never looks like a bearish zero.

A read-only preview can consume verified local mirrors for engineering checks. A8 alone writes the prospective research journal with actual decision times, immutable inputs and one accepted decision per method/session. Retries return the recorded result; changed same-session evidence is retained as a revision, never silently replacing a decision. No current ledger or automation is changed by creating this document.

Implementation uses an isolated `adaptive-research/journal.sqlite` and original pilot states, explicitly labelled as advisory. A BUY row is a candidate, not an order. A HOLD/SELL row refers to an existing pilot holding without changing that pilot's fixed exit rule. The journal stores invalid attempts and full input evidence, including unencodable input literals; current dashboard advice is withheld after a failure or when capture, price or reference source exceeds 24 hours. The new scorer pins the [official 2026 NYSE closures](https://ir.theice.com/press/news-details/2025/NYSE-Group-Announces-2026-2027-and-2028-Holiday-and-Early-Closings-Calendar/default.aspx), verified September 29 UTC, and refuses unknown years or unexplained weekday gaps. Existing lanes' calendar handling is unchanged.

A later execution adapter must process previously recorded orders against the next regular New York open strictly after their actual creation time, once a genuine completed daily bar is captured. A new after-close SELL cannot fill at that same close. Once queued, an order is not retrospectively canceled because a later score changed. The research account keeps existing 10bp costs on each side, no borrowing or shorting, and marks open losses as well as realized outcomes.

Show each symbol's action, position state, reason, score components, evidence time, data status and method version on the dashboard. Label output as a research hypothesis, not brokerage advice or an estimated chance of profit. Existing nine-account results remain visible separately.

## Evaluation and implementation sequence

1. Review this precise candidate and its data limitations; freeze the protocol before generating a prospective decision.
2. Add the pure signal function and meaningful boundary tests: rising/falling risk, BUY/HOLD/SELL transitions, no-position WATCH, held-calendar removal, zero volatility, synthetic bars, missing sessions and future timestamps.
3. Add the isolated journal and tests for actual-time decisions, revisions, immutable retries, stale evidence and pending orders. Preview against existing captures only as an engineering check, never as a historical prospective decision.
4. Add the read-only dashboard view and deploy reviewed source to the isolated A8 release with verified hashes. Preserve all current databases and schedules.
5. Test a separate virtual execution adapter with losing paths, gaps, next-open exits, costs, cash/cap checks and recovery before requesting any activation that changes account behavior.

Use a contemporaneous fixed-20-session-exit control with the same new entry rule to isolate the effect of dynamic exits; the existing nine books provide broader context but have different entry dates and selections. Do not compare a new late-starting account directly with their lifetime returns as if start dates matched. Predeclare the control before launching either new account.

Report every attempted method, net marked equity, costs, turnover, exposure, maximum daily drawdown, number of completed trades, overlapping holdings and matched SPY returns. Include all open and losing positions. A 60-completed-session initial review is descriptive; it is not sufficient proof of reliable alpha or approval for real money. No annualization or 66% return target is a pass criterion. A profitable period with a worse drawdown or different exposure is not automatically a better strategy.

Existing history can test arithmetic and expose failure modes. It is a selected-survivor sample, omits dividends/delistings and has already informed us of a failed momentum baseline. Any retrospective comparison on it is exploratory. Preserve a fresh forward period and prohibit threshold search on that period. Revisions require a new method ID and a future evaluation window.

Primary-source support and applicability limits are recorded in [the research note](../../research/ADAPTIVE-STOCK-SIGNALS-2026-09-29.md). None validates this exact formula, thresholds, event-conditioned universe or implementation costs.
