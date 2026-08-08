# Bankroll plan

Required to clear [Phase 5 readiness criterion #7](../ROADMAP.md#phase-5--real-money-decision-gate-)
before any real-money trading. Last updated 2026-07-01 (PR-G: the Kelly
fraction + per-position caps became enforced clamps in code); review on every
material change to risk capital, Kelly fraction, or fee schedule.

## What "bankroll" means here

The Kalshi account balance dedicated **specifically** to the v1
forecast-lab system. Not commingled with any other trading capital.
This is the figure the §5 criteria gate against.

## Sizing limits

| Limit | Value | Setting | Source |
|---|---|---|---|
| Initial stake at gate-clear | ≤ 2 % of risk capital | manual | CLAUDE.md §5 #7 |
| Per-trade max stake | $50 | `BacktestConfig.max_stake_usd` (and the paper executor matches) | repo default |
| Per-position max | $200 | `Settings.kq_max_position_usd` (tighten-only; see below) | **enforced clamp** |
| Per-day max loss | 3 % of bankroll | `Settings.kq_max_daily_loss_pct` | circuit breaker (lands with the live executor, below) |
| Kelly fraction | 0.15 (fractional) | `Settings.kq_kelly_fraction`, `BacktestConfig.kelly_fraction` | **enforced clamp** |
| Min post-fee edge to trade | 4 % | `BacktestConfig.min_edge_pct` | repo default |
| Maker-route minimum edge buffer | 2 % above skip threshold | `BacktestConfig.maker_min_edge_pct` | maker/taker policy |

The Kelly fraction (0.15×) and the per-position cap ($200) are **hard
caps enforced as clamps** at the single sizing choke point,
`kq.execution.kelly.fractional_kelly_stake`, which every sizing path
(backtest engine, weather + NBA paper executors, future live executor)
flows through: a caller passing a larger fraction or stake cap is
clamped back to the limit with a structlog warning, never honored.
`KQ_MAX_POSITION_USD` can tighten the $200 cap but cannot raise it.
There is no override flag short of editing the source. The per-trade
$50 stake and the edge thresholds are shared defaults (backtest and
paper executor agree); the per-day loss cap is a circuit breaker
implemented with the live executor.

### ✅ RESOLVED (2026-08-07, #131) — aggregate cap now enforced in code

**The gap below is closed.** Sizing uses **free capital** — ``starting +
settled P&L − open-position cost``, per vertical (`vertical_free_capital_usd`,
`open_exposure_usd` in `storage/repositories/paper_trades.py`) — with a
running decrement *within* each submit pass. Kelly returns a $0.00 stake at
non-positive free capital, so a fully deployed lane stops submitting by
construction: total committed capital can never exceed starting + realized
P&L. No new tunable. Verified live on a8 the same day (weather free capital
−$249.03 → halted; nba/nfl/index at $1,000 each). Reporting still shows
equity on purpose — sizing and reporting answer different questions.

The original finding is preserved below as the record of what was wrong and
why it mattered.

### ⚠️ Known gap — every cap above is PER-POSITION; there is no AGGREGATE cap

**Discovered 2026-07-28 by audit; ~~must close before Phase 5~~ CLOSED by #131 (see above). Paper-only throughout, so nothing was at risk.**

Each submit run takes **one** bankroll snapshot and then sizes every market
in that run independently against the *same full figure*. Nothing subtracts
capital already committed — neither within a run (~74 markets priced against
one unreduced bankroll) nor across days (yesterday's unsettled trades are
invisible to today's sizing). There is no portfolio-level, per-run, or
concurrent-exposure limit anywhere in the code, and none was promised above
until this note — an unnoticed omission, not a documented trade-off.

Measured on the host 2026-07-28: **148 open trades, $1,659.22 premium +
$75.53 fees = ~$1,735 committed against a $1,000 bankroll (≈173 %)**. For
long binary contracts the premium paid *is* the maximum loss, so this is real
exposure, not a notional artifact. Part of that figure was backlog from the
settlement outage and drains once trades settle, but the structural cause
remains: at steady state (~2 days open, a new cohort daily) roughly 1.7×
bankroll is live simultaneously, and if Kelly saturated the $50 per-trade cap
across a full slate the ceiling would be ~7.4×.

Two consequences worth stating plainly:

- **CLAUDE.md §5 #7 ("0.15× Kelly coded as a hard limit") is true per position
  and false in aggregate.** N concurrent bets each at 0.15× Kelly *of the same
  dollars* sum past full Kelly, the region where Kelly's own math stops
  protecting against ruin.
- **The backtest cannot see this.** It advances bankroll one trade at a time
  and never models two open positions at once, so Phase 5 #2/#4 and the
  drawdown statistics can all pass while live aggregate exposure is unbounded.

Also noted: the bankroll snapshot compounds only on *realized* P&L from
settled trades and never debits capital tied up in open ones, so during a
losing streak the sizing input stays high while free capital drains. And
`KQ_KELLY_FRACTION` is currently wired to nothing — editing it in `.env` to
de-risk would silently do nothing.

Not fixed here: per CLAUDE.md §9 the sizing caps cannot change without
explicit owner sign-off. Recorded so the decision is made deliberately rather
than discovered live.

## Phased ramp

Per CLAUDE.md §5: "Only after all 10 (Phase 5 readiness criteria) →
enable `live` executor behind `--live --i-understand-the-risks` CLI
flag AND `KQ_LIVE=true` env var. **Start at 10 % of intended
bankroll.**"

The phased schedule that operationalizes the 10 % start:

| Phase | Trigger | Bankroll | Per-trade cap |
|---|---|---|---|
| Cleared gate | Day 0 | 10 % of intended | $50 |
| Cleared gate + 2 weeks of profitable live trading | Day +14 | 25 % of intended | $50 |
| Cleared gate + 4 weeks profitable | Day +28 | 50 % of intended | $100 |
| Cleared gate + 8 weeks profitable | Day +56 | 100 % of intended | $200 |

**"Profitable" definition**: rolling-2-week realized P&L > 0 net of
fees, with Brier-vs-NDFD ≥ +2 % over the same window. If either bar
slips, the ramp pauses and the prior tier becomes the new ceiling.

## Circuit breakers

The `kq_max_daily_loss_pct = 3 %` cap is the daily one. The other
circuit breakers we implement when the live executor lands:

- **Per-day loss > 3 %** → halt new trades for the rest of the UTC
  day. Settle existing positions normally.
- **Per-week loss > 7 %** → halt new trades through Sunday UTC
  midnight. Manual review before resuming.
- **Per-month loss > 12 %** → ramp back to the prior phase's tier;
  manual review before re-ramping.
- **Brier-vs-NDFD slip below 0 % over a 14-day rolling window** →
  halt new trades; investigate before resuming. (Not a P&L trigger
  but the calibration trigger; if the model loses to NDFD on
  forecast skill, the P&L upside has nothing to ride on.)

## Tax framing

§1256 contracts (60/40 capital-gains split) vs ordinary income is
the open question for Kalshi event contracts; case law is sparse and
CFTC guidance ambiguous. The Phase 5 #9 readiness criterion is
"CPA engaged for §1256 treatment decision." Until that's recorded,
**do not trade real money even if all 10 readiness criteria
otherwise clear**. The realized-PnL accounting depends on this
classification.

## Disclosure

CLAUDE.md §13 + the [Compliance addendum](COMPLIANCE-ADDENDUM.md):

- Kalshi weather + NBA = zero securities-law surface.
- §5 #10 readiness criterion: NVIDIA HR/Legal disclosure if required
  by the outside-activities policy. **Complete before live trading
  even if not strictly required** -- the cost of asking is zero,
  the cost of skipping and being wrong is large.

## Not legal or financial advice

This document operationalizes a personal-use trading system per
CLAUDE.md §1. It is not legal or financial advice. The §5 readiness
criteria (#9 CPA, #10 disclosure) explicitly require external
counsel before real-money activity.
