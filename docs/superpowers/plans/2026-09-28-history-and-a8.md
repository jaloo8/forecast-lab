# Historical stock study and A8 paper readiness

User explicitly requested use of A8 (existing always-on server), historical gains/losses research, and primary-source investigation of successful investors and open-source tools. No real trades, new dependencies, paid data or Kalshi changes are authorized.

## Design locked before viewing historical strategy results

Use the existing six-stock universe and SPY, 2010-01-01 through 2026-09-25, split-adjusted regular daily prices. Store the actual provider response in a separate ignored research file. This is survivor-biased exploratory research, excludes dividends/delisting returns, and must never populate the prospective ledger.

Compare exactly three fixed historical-strength rules: lookback/holding sessions 5/5, 20/20,126/126. At each signal close, choose the strongest three stocks with positive stock-minus-SPY past return; use the next session's open and the holding window's last close. Equally weight selected names in a research cohort; if none qualify hold cash (zero return). Compare with SPY over precisely the same holding dates and apply 10 basis points friction each side to both active cohorts and SPY. Report all dates, selections, gains and losses. No parameter sweep or re-selection of horizons after observing outcomes.

Use nonoverlapping cohorts within separate chronological blocks 2010–2018,2019–2022,2023–2026. Warm-up may use earlier prices; exit must stay within its block. Report cohort count, invested count, mean/median net return, positive fraction, mean excess vs SPY and worst/best cohort, plus full raw cohort rows. These are study returns, not compounded account returns, independent observations or investable portfolio proof. No Sharpe/CAGR or fake confidence level. Missing/duplicate/synthetic/non-finite bars fail validation; all symbols must share sessions, verified in actual payload. Every result records signal_as_of, entry/exit dates and source capture hash.

## Tasks

- [x] Save primary-source investor/tool research with decisions and evidence limits.
- [x] Add offline `historical_study.py` + meaningful tests for next-open timing, cost math, missing data, block boundaries and no historical ledger writes; run locally then on A8 if runtime exists.
- [x] Inspect A8 read-only, preserve its live Kalshi checkout/tasks. Stage a separate equity-paper release with verified hashes and existing runtime, no dependencies. Run tests and historical study there.
- [x] Prepare persistent private dashboard operation and a single-writer paper refresh plan. Do not falsely claim Task Scheduler can call chat-only authenticated MCP tools; verify actual data access before migrating daily imports. Existing local heartbeat remains authoritative until cutover is verified.
- [x] Add historical-study output to dashboard, clearly labeled separately from live paper results, if valid study runs. Document actual A8 outcomes and remaining data-access blocker. Update ROADMAP.

Files: src/kq/equities/historical_study.py; tests/test_equity_historical_study.py; dashboard.py; docs/research/STOCK-RESEARCH-TOOLS-2026-09-28.md; docs/STOCK-PAPER-LAB.md; ROADMAP.md; this plan. Operational scripts, if needed, remain specific to equity research/dashboard and never change existing scheduled jobs.

## Verified outcome and remaining operational limits

Completed 1,077 fixed-rule cohorts on the captured 7 x 4,207-bar source. A8 reproduced the exact JSON bytes: output SHA-256 63d1dfc1956aa382a5d9150d1da0ff6d99af3718e778873c6482182920e298ae. Initial release archive SHA-256 46a18a4d26236817560e8d86534163a56968fefe555debb4d8c444c971191b18; subsequent study-panel/docs edits were copied and matching hashes checked. The initial package seeded the paper DB once via SQLite backup; do not deploy that seed over the authoritative server ledger again.

Local full pytest passed (exit 0; 24 platform skips), ruff and strict mypy passed; A8 passed 64 equity tests using its existing Python3.12/pandas3 environment. The final panel update passed focused tests locally and on A8. Independent review verified next-open timing, cost parity, holding-period separation, cash benchmarks and no forward-ledger writes. Boolean prices are rejected; the actual nested worst-cohort result is rendered correctly. Shared missing provider sessions remain undetected without an independent exchange calendar and are disclosed.

A8's actual paper import replay passed without adding trades: cash/equity100, reserved30, three pending. Existing stock-paper-pilot heartbeat now writes only A8 and mirrors results locally. This first scheduled remote refresh has not yet occurred; the Robinhood connector still requires the Codex app/session. A8 dashboard PID20652 survived its launching SSH session and the private desktop tunnel uses port8503. In-app tunnel preview was denied by browser policy; actual-data AppTest is verified but that browser page is not.

Reboot task configuration was submitted as \StockPaperLab\Dashboard; its task file exists but creation/status responses stalled, so execution and reboot recovery remain unverified. No existing Kalshi jobs were edited. scripts/run-stock-dashboard.py provides the isolated loopback launcher. This is a documented operational follow-up, not an achieved always-on service claim. No paid feeds, dependencies, real orders, or winning-strategy claims were introduced.
