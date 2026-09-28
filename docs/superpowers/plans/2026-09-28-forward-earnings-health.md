# Forward earnings experiment and collection health

User approved the four next steps in chat: verify daily collection and failure alerts, improve timestamped evidence, test one fixed challenger on unseen future data, and show risk/benchmark results. Existing paper trades and risk caps remain unchanged. This continues the approved design without another approval round.

## Fixed design (recorded before forward outcomes)

Use the existing assistant-authorized read-only provider; do not pretend A8 has independent brokerage authentication. Record an actual health check of A8, the paper import/session, evidence collection and scheduler configuration. A configured schedule is not a successful run. Sunday evening has no new completed US session; do not fabricate one or execute a duplicate paper import. Prefer the existing heartbeat over another scheduler. UI warnings and heartbeat failure notifications are the available alert channel; do not configure external messaging or new services.

Capture the unfiltered market-wide trailing seven-day earnings calendar and requested quarterly financials. Save immutable raw JSON with actual retrieval timestamps and hashes. Current provider estimates and financials are usable only from first observation, not at their fiscal-period end dates. Archive verified official filing/release excerpts through the existing event store. Report missing fields and limited coverage; no sentiment probabilities.

The single challenger is a research-only prospective earnings/momentum screen. Universe: the captured US stock candidates intersecting the unfiltered earnings calendar. Eligibility uses at least 21 identical completed SPY sessions, last close >= $5 and median of the last 20 close-times-volume values >= $20 million. These are predeclared research selection rules, not changes to trading risk caps. Earnings report must be verified, dated within the last seven calendar days and conservatively available only after the following UTC midnight. EPS estimate must be positive; actual must exceed estimate by >=5%. Require positive 20-session excess momentum. Select up to three by descending excess momentum, ticker tie-break. No optimization over the failed historical sample. Explicitly distinguish this event-conditioned universe from the full market.

Record the same-universe liquidity-filtered momentum-only selection as the ablation baseline. Preserve the original failed broad study separately. Each research decision stores actual creation time, input and method hashes, eligibility/exclusion reasons and all selected names. No backdated decisions, real orders or paper-ledger writes. Empty selection is a valid outcome. Evaluate next regular US market open strictly after creation, exit at the 20th subsequent held session close, use 10bp per side and matched SPY; report pending until real subsequent bars exist. These are isolated cohorts, not a funded account; overlapping daily decisions are not independent observations. Missing sessions/revisions invalidate comparison rather than being repaired.

## Implementation tasks

- [ ] Collection health: `src/kq/equities/health.py`, focused tests. Read-only report with explicit never-run, stale, failure, no-new-session states and aware UTC as_of; injected evaluation time for deterministic tests. Test weekend vs weekdays, corrupt/future timestamps and absence of side effects.
- [ ] Challenger: `src/kq/equities/challenger.py` and focused tests. Pure typed DataFrame candidate screen from validated raw daily bars and captured calendar. Isolated write-once decision artifact and evaluator if they fit separate reviewed modules; test unknown/future EPS, liquidity/missing history, no-lookahead next-open timing, losing outcomes and pending states. Do not mutate existing ledger.
- [ ] Primary-source research note and actual provider/official-source captures. Verify that delayed response after earnings is only a hypothesis and trading costs can erase apparent advantage; document observation timing limits of available tools.
- [ ] Dashboard health/challenger panels, real A8 checks and evidence archive import, automation refresh instructions. Show research selection/pending status with no fabricated results.
- [ ] Independent review, focused/full tests, Ruff/types; small stacked draft PRs <=400 changed lines each; deploy only reviewed new code/data to the isolated A8 release, preserve paper.sqlite and events.sqlite, verify hashes and actual dashboard.

## Acceptance

Collection health is visible and failures are covered by tests; first scheduled run remains unverified until it occurs. A real dated evidence capture and fixed forward challenger are inspectable. No retrospective profitability is invented. A8 reproduces the screen and preserves its paper ledger. Any data gaps preventing genuine prospective evaluation remain explicit on the dashboard and in the runbook.
