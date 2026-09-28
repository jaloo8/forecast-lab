# Equity dashboard and research reuse

User requested a dashboard and reuse of Forecast Lab research, with standing authorization to drive coding and testing. Continue the approved paper experiment in its existing worktree. Default to stocks first with a separate Kalshi link; do not merge unlike strategies' returns.

## Design

Reuse installed Streamlit, as used by `src/kq/dashboard/streamlit_app.py`. Alternatives are enhancing the static HTML (simpler but weaker filtering) or building a new web stack (unnecessary dependencies). A read-only SQLite adapter opens an explicit transaction and loads the latest stored summary, orders, trades and forecast records consistently. Match the source capture by canonical hash before displaying news or rankings; a newer unimported file must not impersonate ledger evidence. Missing or corrupt inputs show errors, never a invented balance.

The dashboard has Overview, Trades, Research and Data health tabs. It displays marked equity, cash, reserved cash, net paper P&L, pending/open/closed counts and horizon results versus matched SPY. Trade filters and a refresh button reload local records without importing data or placing orders. Empty outcomes are labeled unmeasured; invalid marks/results are withheld. Capture age is distinct from market-session age and scheduler health is explicitly unverified. No equity curve is invented from current marks; closed-trade realized results are labeled separately.

Reuse research: Pass 2's SEC/earnings/event and customer-supplier ideas are hypotheses, not validated alpha. Preserve public evidence times and time-ordered evaluation from Forecast Lab; reuse its Streamlit and `hit_rate` utility for matured closed trades only. Weather EMOS, NBA Elo, Kalshi fees and readiness gates do not transfer to equities. Vendor pricing and empirical claims in old research require fresh primary-source verification before future integration.

## Implementation plan

Use executing-plans and test-driven-development. No new dependencies, network feeds, broker actions, or changes to ledger rules. Keep code and tests in at most ten files for this slice.

- [x] Add `tests/test_equity_dashboard.py`: missing ledger does not create a file; reads cannot mutate ledger; failed/unimported captures cannot replace evidence; no trades means no hit rate; Streamlit renders empty and populated states.
- [x] Add `src/kq/equities/dashboard_data.py`: read-only consistent ledger view and hash-matched source, with typed DataFrames carrying stored timestamps.
- [x] Add `src/kq/equities/dashboard.py`: four tabs, status and freshness warnings, filters and reload, sourced research context, separate Kalshi navigation.
- [x] Document reuse and launch in `docs/STOCK-PAPER-LAB.md`; update `ROADMAP.md`.
- [x] Run targeted equity/UI tests, ruff, mypy and full suite; inspect live dashboard; record exact evidence and local URL.

## Review and verification

The dashboard's ten targeted tests passed, including missing-ledger refusal, a read-only ledger hash check, canonical source matching, legacy balance reconstruction, completed forecast aggregation, and invalid-result suppression. Independent review confirmed the real ignored ledger reads as $100 cash/equity, $30 reserved and three pending orders without mutation. The review's invalid closed-profit display finding was fixed and regression-tested; reviewer confirmed no remaining blockers.

Repository-wide ruff and mypy passed (160 source files). The browser was inspected on all four tabs at http://127.0.0.1:8502; initial sidebar is collapsed for the app's narrow panel. Local Streamlit process remains running; reboot persistence and public/phone access are not configured. Full pytest suite passed (exit 0), with 24 platform skips; saved output: data/equities/dashboard-validation.txt. No ledger or source capture was changed by the dashboard work.
