# Clarifications recorded before new performance

The original registration remains unchanged (SHA256
`d3b11968c2b8c8bcbe7050b61d317b0a9c980437a47a1d1c4403ee84cd2ebaf9`).
These implementation clarifications were recorded before any new historical
performance calculation, following independent specification and artificial-fixture review.

- The 252nd observation (zero-based row251) is the first eligible signal.
  State-machine entries themselves are gated; there is no hidden warmup position.
  Both execution lags use the common eligibility start from readiness shifted
  by two sessions, so lag comparisons have identical available dates.
- Bollinger bands are inside Keltner bands only when both inequalities are
  strict; equality is outside. The exact 12 rules and their thresholds remain frozen.
- Entry notional is `0.98 * available_cash / (1 + one_way_cost)`, leaving 2%
  cash after paying entry cost. Once held, units stay fixed until exit.
  Ordinary opening tickets below $1 are skipped and counted. A planned final
  liquidation sweeps any remaining dust and charges the same proportional cost.
- Timed rules hold N signal intervals, with execution displaced by the fixed
  lag. A fresh monthly/later account adopts the ongoing delayed rule state and
  its original remaining duration; it does not reset that rule's holding clock.
- CAGR uses the inclusive actual calendar span between the first and last
  recorded session, divided by365.25. It does not pretend an IPO or a fund with
  a later inception has26years of observations. Short-period results omit CAGR.
- Drawdown includes initial cash, pretrade opening NAV, postcost opening NAV,
  closing NAV before terminal liquidation and closing NAV after its cost.
  Intraday extrema are not known. An independent reviewer identified the need
  to include a new terminal prefee peak; this was fixed before execution.
- A complete calendar year must contain exactly the source SPY session dates
  for that year. Merely starting somewhere in January is insufficient. Partial
  years stay in the annual ledger but are flagged, including warmup/IPO starts.
- The source observes current-vintage adjusted wealth units and split-adjusted
  volume. No whole-share, dividend-payment, settlement or actual fill feasibility
  is certified. No historical news/LLM decisions are reconstructed.

All 405 rule/instrument combinations, all stresses, failures and monthly starts
remain in scope. No thresholds or selection criteria changed after an outcome.
