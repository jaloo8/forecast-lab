# Bankroll plan

Required to clear [Phase 5 readiness criterion #7](../ROADMAP.md#phase-5--real-money-decision-gate-)
before any real-money trading. Last updated 2026-05-03; review on every
material change to risk capital, Kelly fraction, or fee schedule.

## What "bankroll" means here

The Kalshi account balance dedicated **specifically** to the v1
forecast-lab system. Not commingled with any other trading capital.
This is the figure the §5 criteria gate against.

## Sizing limits (all coded as hard caps)

| Limit | Value | Setting | Source |
|---|---|---|---|
| Initial stake at gate-clear | ≤ 2 % of risk capital | manual | CLAUDE.md §5 #7 |
| Per-trade max stake | $50 | `BacktestConfig.max_stake_usd` (and the paper executor matches) | repo default |
| Per-position max | $200 | `Settings.kq_max_position_usd` | repo default |
| Per-day max loss | 3 % of bankroll | `Settings.kq_max_daily_loss_pct` | repo default |
| Kelly fraction | 0.15 (fractional) | `Settings.kq_kelly_fraction`, `BacktestConfig.kelly_fraction` | repo default |
| Min post-fee edge to trade | 4 % | `BacktestConfig.min_edge_pct` | repo default |
| Maker-route minimum edge buffer | 2 % above skip threshold | `BacktestConfig.maker_min_edge_pct` | maker/taker policy |

These are **hard caps** in code, not advisory: the live executor
refuses to size past them, and there is no override flag short of
editing the source.

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
