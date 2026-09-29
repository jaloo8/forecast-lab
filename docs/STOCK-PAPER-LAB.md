# Stock Paper Lab

This is the first working baseline for the owner-approved stock research experiment. It is paper only. It cannot place a Robinhood order. A running experiment is not evidence of forecasting skill.

**Latest operational result — September 29, 01:28 UTC:** the original pilot now has three actual simulated fills (AAPL, XOM, MSFT), $70 cash, $99.949202 marked liquidation equity and no closed trades. All nine additional portfolios initialized successfully with 19 pending orders, eligible for the next regular opening after their actual creation. Older blocked-state paragraphs below are historical evidence. Read [the verified session fallback](#verified-session-fallback--2026-09-29) before the next scheduled refresh; the owner explicitly requested this repair. The successful run was manual, not evidence of a successful scheduled run.

## A8 is the paper writer — updated 2026-09-28

The owner confirmed A8 is the existing always-on server. SSH access and its existing Python runtime were verified; a separate release lives at `C:/Users/jloo1/Documents/stock-paper-lab-20260928`. Its Python is `C:/Users/jloo1/Documents/forecast-lab/.venv/Scripts/python.exe`; set `PYTHONPATH` to the release's `src`. Do not change the original server checkout or Kalshi jobs. No dependency was installed.

**Only A8 imports new paper captures.** Its `data/equities/paper.sqlite` is authoritative. The original local ledger is now a read-only mirror/seed and must not receive local imports. The weekday 6 PM Pacific `stock-paper-pilot` heartbeat was updated to collect data through Codex's authenticated read-only Robinhood tools, verify transfers and run the import on A8. After success, take a consistent SQLite backup on A8 and mirror it and the HTML report locally. Never copy a local ledger back over A8. The original seed backup remains `data/equities/a8-seed.sqlite` locally. This host migration preserved $100 cash, $30 reserved and three pending orders, with no fills or historical-study records added.

This is a hybrid workflow: **data collection still depends on the Codex host/app and its Robinhood session**. An independent server-side authenticated feed is not configured. The revised heartbeat's first scheduled run is unverified. A8 reproduced the study byte-for-byte and passed all 64 stock tests; its actual paper CLI replay also passed. A boot-task configuration for `\StockPaperLab\Dashboard` was submitted with S4U least-privilege execution under A8's existing user and no stored password. Its task file exists, but registration/status commands stalled and were interrupted: scheduler completion, task execution and reboot recovery remain **unverified**. The read-only dashboard process was separately verified alive after its launching SSH session disconnected. Do not assume automatic recovery after reboot until the host scheduler issue is investigated.

A8 binds the stock dashboard to `127.0.0.1:8502`. The current desktop tunnel exposes it privately at `http://127.0.0.1:8503`; the tunnel must remain active:

```powershell
ssh -N -L 127.0.0.1:8503:127.0.0.1:8502 -o ExitOnForwardFailure=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 jloo1@100.108.199.57
```

No firewall or public listener was opened. The in-app browser rejected the final tunnel preview under its URL policy; server tests and the local actual-data AppTest passed, but the tunneled page was not visually verified. Open the link in a normal browser manually. For restart, use the interactive dashboard command below on A8 with its release/runtime paths, or launch it with Python `subprocess.Popen` using `creationflags=0x09000208`, redirected log handles and the release's `PYTHONPATH`. Those Windows breakaway/no-window/detached flags were necessary to survive SSH disconnect and were verified on this host. The submitted boot task uses `scripts/run-stock-dashboard.py`, which binds only loopback and sets this release's source path. The task's XML is saved as `dashboard-task.xml` on A8. PID/log files are under the release's `data/equities/`; do not terminate a process without verifying it belongs to this release.

## Historical study — separate from paper performance

Read-only Robinhood history provided 4,207 regular daily bars each for six stocks plus SPY, 2010-01-04 through 2026-09-25. Source `research-history-2010-2026.json` is SHA-256 `53cdd829038e7e68b45f8ae01e8517ab884a94c77201c87ef70df11259db90f4`. A fixed protocol tested 5/5,20/20,126/126-session lookback/holding rules before viewing results. The 1,077 nonoverlapping cohorts, including all gains, losses and cash periods, are in `historical-study.json`; the dashboard's historical expander can download the complete file.

| Years | 5-session mean excess | 20-session mean excess | 126-session mean excess |
| --- | ---: | ---: | ---: |
| 2010–2018 | -0.076 pp | +0.545 pp | +3.886 pp |
| 2019–2022 | +0.192 pp | +0.383 pp | +4.105 pp |
| 2023–2026 | -0.001 pp | +0.170 pp | -2.024 pp |

These are average **per-period** returns minus matched-capital SPY after 0.10% friction each way, not annual or compounded returns. The latest 20-session block has 46 cohorts; the long blocks only 7–16. This is selected-survivor research without dividends, delisted names, historical index membership or an independent session calendar; common missing provider dates go undetected. No model was optimized, no confidence interval or reliable edge was established, and the study is not a simulation of the $100 paper account's sizing rules. More frequent trading did not consistently improve results. Keep the forward baseline unchanged while collecting stronger evidence.

Rerun offline on either host (never with the paper import command):

```powershell
python -m kq.equities.historical_study --input data/equities/research-history-2010-2026.json --output data/equities/historical-study.json
```

The [new primary-source research review](research/STOCK-RESEARCH-TOOLS-2026-09-28.md) covers Buffett/Munger, AQR, SEC data, OpenBB, Qlib, LEAN and vectorbt. It prioritizes dated earnings/quality inputs and better historical coverage over adding platforms or searching thousands of strategy settings.

## What runs now

- A fixed pilot watchlist: AAPL, MSFT, AMZN, JPM, XOM, COST, with SPY as benchmark. This is not a whole-market scan and is not a survivorship-free historical universe.
- Three historical momentum rankings: 5, 20 and 126 trading sessions, each measured against SPY. These are features, not calibrated probabilities or expected returns.
- Current P/E, market capitalization, sector and latest reported EPS, plus dated news/filing references. Financial context and news do not yet alter the ranking.
- An immutable forward forecast ledger for all three horizons.
- A separate $100 virtual medium-horizon book: $10 per selected positive-strength stock, at most five pending/open positions, entry and exit friction of 0.10% each, 20-session holding period. Loss of $10 from initial marked equity pauses additions; this does not guarantee a loss ceiling.

Current prices do not prove stock selection ability. Evaluate mature results and a matched SPY baseline before proposing live trading. The $100 real-money experiment remains unstarted; every real order would require user approval and a separately reviewed scope/gate decision.

## Interactive dashboard

From the stock-paper-lab checkout, run the existing environment (no installation):

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
& 'C:/Users/jloo1/Documents/Github/forecast-lab/.venv/Scripts/python.exe' -m streamlit run src/kq/equities/dashboard.py --server.address 127.0.0.1 --server.port 8502 --server.headless true --browser.gatherUsageStats false
```

Open http://127.0.0.1:8502 on this computer. Overview shows the virtual balance and mature outcomes versus SPY; Trades filters queued/open/closed records; Research shows historical rankings, earnings and public sources; Data health shows capture/import times and limitations. Refresh local results reloads the ledger, not the provider. The browser must be refreshed after a scheduled import. The app reads SQLite in read-only mode and cannot import, fill or place any order. Missing records do not create a new account. It links to the separate Kalshi dashboard on port 8501 if that app is running; neither service is exposed publicly or automatically restarted after reboot.

Only source captures matching the committed ledger hash are displayed. A newer failed/unimported capture cannot replace evidence. Older ledgers without cached summaries show a reconstruction warning; the initial $100 can be reconstructed only when there are no executed trades. Unsupported valuations are withheld. No historical balance curve is fabricated from today's marks.

## Forecast Lab research we can reuse

| Existing work | Reuse in stocks | Current status |
| --- | --- | --- |
| [Research Pass 2](research/PASS-2-EQUITIES-AGENT.md), A1/A2/A4 | SEC filings, earnings, executive events, customer/supplier links | Research candidates; current news and earnings are context, not tested signals |
| [Reality-contact audit](SESSION-2026-06-11-AUDIT.md) | Verify actual provider payloads and settlement history; never infer results from an empty ledger | Applied to the stock pilot's real capture, pending fills and honest empty states |
| [Pass 1 extension](research/PASS-1-EXTENSION-EMOS-EXECUTION.md) and calibration modules | Time-ordered evaluation, baseline comparisons, calibration of eventual probabilities | Methodology transfers; weather parameters and historical performance do not |
| `src/kq/dashboard/streamlit_app.py` | Existing Streamlit dependency and read-only dashboard pattern | Reused for the stock UI |
| `src/kq/backtest/metrics.py::hit_rate` | Fraction of completed trades with positive net paper P&L | Reused only after trades close; no trades means unmeasured |

The next research experiment should preserve this baseline and compare an earnings/filing candidate using evidence available at each decision time. News/no-news ablation, independent cohorts and holdouts are needed before claiming improvement. Pass 2's vendor prices, licensing assertions and empirical return claims are old research notes, not newly verified facts; verify their primary sources before relying on them. EMOS weather distributions, NBA Elo, binary-contract fees and Kalshi gates are not stock models. The [compliance addendum](COMPLIANCE-ADDENDUM.md) remains the repo's controlling scope note; this dashboard does not enable live trading.

## Import command

On the authoritative A8 release, using its existing Python environment (local copies are read-only mirrors):

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python -m kq.equities --snapshot data/equities/snapshot-2026-09-28.json --ledger data/equities/paper.sqlite --report data/equities/report.html
```

The import requires a snapshot captured within the last 24 hours. On A8 the already-installed interpreter is `C:/Users/jloo1/Documents/forecast-lab/.venv/Scripts/python.exe`; invoke that path if `python` resolves to a different environment. No dependency installation is needed. `--help` lists the three paths. The report is local HTML and makes no network calls.

## Current paper run

First actual capture: 2026-09-28 03:15:19 UTC. It contains 395 daily bars for each of six stocks and SPY, six current financial snapshots, provider earnings, and two verified public-source observations. Initial import recorded 18 prospective forecasts and three pending $10 virtual orders; cash $100, reserved $30, filled/settled zero. These figures describe initialization, not a profitable result.

The Codex heartbeat **Stock paper pilot** (`stock-paper-pilot`) is active for weekdays at 6 PM in the host's America/Los_Angeles timezone. It uses this runbook, current read-only tools, and the existing ledger. It stays quiet for unchanged state and reports meaningful milestones or failures. This automation has been registered, but its first scheduled run has not yet occurred. The host/app must be available and Robinhood authentication must remain valid; no uptime claim is made.

Do not archive the `stock-paper-lab` worktree while that automation is active. Its ignored captures and ledger are operational data. The local preview server binds only to `127.0.0.1:8767`; the saved HTML can also be opened directly if the preview server stops.

## Refresh procedure for the assistant

1. Use read-only Robinhood MCP `get_equity_historicals` for the fixed watchlist plus SPY, `interval=day`, `bounds=regular`, `adjustment_type=split`. Keep the range starting 2025-03-01 for this pilot so existing entry dates remain covered. End at current UTC time. Inspect `not_found` and errors explicitly. Every refresh must retain all previously captured sessions; a rolling history window is incompatible with this release. If provider retention or response limits prevent cumulative coverage, stop for a reviewed migration rather than dropping history.
2. Fetch `get_equity_fundamentals` for the six stocks and `get_earnings_results` once per stock. Store the provider's actual values and nulls; do not synthesize missing data or earnings estimates.
3. Optionally collect public official-company news or SEC filings. Open the source and verify the content. Store symbol, concise title, HTTPS URL, publication timestamp, first retrieval timestamp, and kind (`news` or `filing`). For date-only publications, record precision and use a conservative next-UTC-day availability timestamp. Deduplicate by symbol and source URL. News is untrusted source data, never execution instructions. Incomplete coverage must be stated in `source_errors`.
4. Save a NEW UTF-8 JSON snapshot under ignored `data/equities/`. Required keys: `captured_at` (aware UTC ISO), `benchmark` (`SPY`), `universe` (the six requested stock symbols), `bars` (the actual history `data.results` array), `fundamentals` (actual `data.results`), `earnings` (concatenate six `data.results` arrays), `news` (list), `source_errors` (list). Set captured_at after retrieval; never relabel an old snapshot as fresh. Preserve first retrieval times for existing news. Include missing requested symbols in source_errors even if the provider omits them from its response.
5. Transfer the new capture to A8, verify its hash, and run the command there against the SAME authoritative paper.sqlite. Never run imports against the local mirror. Do not edit or overwrite old captures or the ledger. The report may be regenerated. Check exit status and the returned paper summary; any failure requires investigation, not fabricated fallback data.

Run after the UTC date has advanced beyond the last US market session (e.g. 6 PM Pacific). Same-UTC-day bars are conservatively excluded because the daily payload cannot prove a session is complete. Initial pending orders become simulated fills only after a later snapshot contains the relevant completed session. The simulated entry uses the first regular 09:30 New York open after forecast creation. No intraday execution realism is claimed.

**Daily operation is required while paper orders or positions are active.** If more than one unprocessed trading session appears, the first release refuses catch-up and requires review. It cannot safely infer path-dependent loss stops from a batch snapshot. Do not manufacture intermediate captures or remove ledger history to bypass this. Restore a genuinely recorded missing capture or implement a reviewed chronological replay before resuming. Missing earlier session coverage likewise fails closed.

Data captures and paper.sqlite are private, ignored local artifacts. They contain public market data and hypothetical trades only, never brokerage account identifiers, tokens or credentials. The CLI does not fetch data itself; an assistant refresh or a separately configured automation is needed. A report alone is not a running scheduler.

## Integrity and evaluation

Reimporting the identical snapshot is idempotent. Source capture time is distinct from actual forecast creation at import; an old capture cannot backdate a forecast or paper entry. A conflicting capture at an existing timestamp or an older capture cannot mutate forward records. History revisions (including split adjustments affecting stored entry prices) require review; never silently reinterpret share quantities. Missing or stale data cannot establish a successful forecast. Price returns exclude dividends and taxes.

Do not compare overlapping daily forecasts as independent observations or select a winning horizon after seeing outcomes. The first decision horizon is 20 sessions. Report the number of distinct entry dates, the fixed watchlist, benchmark-relative returns after assumed costs, drawdowns, and uncertainty; require a predeclared evaluation period and multiple market regimes before extrapolating. Profitable paper results do not guarantee attainable execution or future profitability.

## Subsequent research milestones

### Stock/news workflow verification and options feasibility — 2026-09-28

`tests/test_equity_workflow.py` runs the actual offline import, research scan, SQLite ledger, HTML report and read-only dashboard loader over isolated synthetic captures. Three paths cover rising, falling and volatile prices through 20 daily updates; a fourth checks news becoming available later, rejected future news, unchanged price scores and atomic repeat imports. It checks next-open fills, fees, cash, 5/20-session settlement and unready 126-session outcomes. These are software contract tests using synthetic weekdays, not exchange-calendar, execution-quality or investment-performance evidence. Production scoring and risk limits are unchanged.

The A8 ledger was read directly again: $100 cash/equity, $30 reserved, three pending positions, zero fills or settled forecasts. The first scheduled refresh and reboot recovery remain unverified. A running dashboard alone does not prove unattended ingestion.

Validation: all four new workflow tests passed locally and on A8; the default full repository suite completed successfully (24 platform/environment skips). Ruff passed, and strict mypy passed for 162 source files. An independent review found no blocking defect. Passing these checks does not establish a profitable model.

Read-only Robinhood probes resolved both active and expired AAPL options. The active October 16 $340 call had a September 25 quote of $7.65 bid / $7.95 ask, multiplier 100: buying one at that ask would require $795 before fees, and an immediate sale at that bid would lose $30 before fees. The quote was captured over the weekend, not a currently executable offer. This arbitrary capability sample is not a recommendation or an exhaustive affordability screen. A September 18 $340 expired call returned 13 daily OHLC bars; the October 16 $250 call returned 18. Neither history supplies historical bid/ask, sizes or IV/Greeks; daily prints cannot prove fills, liquidity or exercise settlement. Options cannot yet be evaluated as realistic profitable trades with these inputs.

Raw public-data probe: ignored `data/equities/options-capability-2026-09-28.json`, captured 2026-09-28 04:20:39 UTC, SHA-256 `f367c4eff4af442aae02bf56d3ec0ce01032e50a5dd85c2fa163406a3db801b4`. No brokerage account records, credentials or orders were accessed. Do not import this research capture into the stock paper ledger.

The [institutional methods and whitepaper review](research/INSTITUTIONAL-STOCK-NEWS-OPTIONS-2026-09-28.md) separates reproducible controls from proprietary strategies. Next: retain the locked stock baseline; archive news/filing versions with first usable times; predeclare one event-aware challenger and compare it against the baseline on the same dates, universe, costs and capital. Evaluate horizons separately, report all attempted models and losses, and reserve later calendar data for untouched evaluation. A news association is not proof of causation or tradable improvement. A separate high-risk/options research lane needs its own contract data and capital model before paper execution; no real-money allocation or 66% annual-return promise is implied.

1. Reliable broader news coverage and SEC financial histories with original filing availability and revisions preserved.
2. A news-aware candidate model, compared with this unchanged baseline using time-ordered holdouts. AI extracts evidence; quantitative probability estimates must be empirically calibrated.
3. Matched benchmark returns, interval estimates and news/no-news ablation reports on matured forward samples; short/long horizons judged separately.
4. Standalone unattended data ingestion and refresh health checks if required beyond assistant-driven imports.

No spending on feeds or new dependencies, no live-order capability, and no changes to Kalshi's fee, sizing or readiness rules are part of this release.

### Broad universe and failed momentum experiment — 2026-09-28

The six names are a fixed forward baseline, not a claim about the best stocks. A separate captured Nasdaq/other-listed directory contains 13,288 securities, including funds and other instruments. Name/flag classification yields 4,999 stock candidates and 997 rows requiring review. This is current US exchange coverage, not all global stocks, broker eligibility or historical membership. See [Nasdaq field definitions](https://www.nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs).

All 4,999 candidates were requested through read-only Robinhood historical tools in 500 batches, plus one SPY batch. The coverage report ranks 4,525; 210 lack shared sessions, 192 lack sufficient history, 66 contain invalid prices and six were unavailable. It excludes 19,840 synthetic/interpolated bars. Invalid raw prices remain archived, never corrected or silently traded. The provider scanner's inconsistent totals could not establish complete coverage; the directory and per-symbol requests provide the audit trail instead.

The broader study retains the existing fixed top-three positive excess-momentum rule, next-open entry, 5/20/126-session horizons and 10 basis points per side. Its protocol was recorded before running it. It requires complete real positive-volume history on the same SPY grid: 4,447 stocks, March 2–September 25, 2026.

| Hold | Mature test periods | Mean net return | Mean excess vs SPY | Positive periods |
| --- | ---: | ---: | ---: | ---: |
| 5 sessions | 27 | −6.00% | −6.07 pp | 37.0% |
| 20 sessions | 6 | −16.70% | −19.85 pp | 16.7% |
| 126 sessions | 0 | Unmeasured | Unmeasured | Unmeasured |

These are separate equal-weight historical cohort returns, not a compounded account curve, annual return or the $100 forward book. The worst five-session cohort lost 55.63%; the worst twenty-session cohort lost 58.48%. This baseline failed in the exploratory sample. Current-survivor selection, no dividends/delisting returns, a short period and inadequate liquidity/spread modeling prevent an unbiased market-wide claim. There is no news signal in this study. Do not tune on these outcomes and call the same dates untouched validation.

Raw batches, catalogue, coverage, rankings and every cohort are retained under ignored `data/equities/`. The study's canonical input hash is `53f1877f818d2958b953598a9e5390284aa235ed8eee1cb2d343eda65b1b56bc`. Reproduce the identical fixed research protocol with `python scripts/run_broad_stock_study.py --data-dir data/equities`. Never import its historical cohorts into `paper.sqlite`.

The dashboard's “Broad stock coverage and news evidence” section displays classifications, coverage exclusions, every measured horizon and downloadable results. `events.sqlite` is a separate append-only evidence archive: content revisions and reactivations preserve actual first-seen times; queries expose only versions available by the requested time. Its initial two AAPL/MSFT source records are metadata, not a comprehensive news feed or article corpus. Revisions cannot backdate evidence. A failed/empty collection cannot imply no news occurred.

After each successful A8 paper import, archive the captured news there with `python -m kq.equities.events --input <new-snapshot.json> --database data/equities/events.sqlite`. Use the actual invocation time. A8 is the event archive's sole writer after initial deployment; mirror it through a consistent SQLite backup as with the paper ledger. Do not overwrite either server database from local mirrors. The broad directory/history experiment is a dated research capture, not a scheduled daily market-wide feed.

Next evaluation: retain this failed baseline, collect timestamped news/filings and original financial releases, predeclare a liquidity-aware event challenger, then test it on later untouched dates with matching costs and benchmarks. Realistic historical options quotes/lifecycle data and independent unattended ingestion remain unresolved. More simulations alone cannot establish an edge.

Deployment verification: the broad research release was copied only into A8's isolated stock directory with 538 file hashes checked. The full broad study reproduced the original parsed JSON exactly on A8, including the canonical source hash above. The focused A8 suite passed 65 tests with one platform skip; local focused tests, Ruff and strict source mypy passed. Actual-data dashboard checks passed on both machines and showed the losses, two archived news records and the unchanged $100 account. The A8 paper database hash remained `f8e4f2e624fbc0fcc0c7a4657dc2d111a7c002ba12c66034e57925e491e11d6f`. Weekday heartbeat instructions now archive news on A8 after successful imports and mirror consistent backups. First scheduled execution and reboot recovery remain unverified. Draft stacked PRs #137–#144 hold this release; none is merged into main.

### Prospective earnings comparison and collection checks — 2026-09-28

The next fixed experiment is documented in [the plan](superpowers/plans/2026-09-28-forward-earnings-health.md) and [primary-source evidence review](research/FORWARD-EARNINGS-EVIDENCE-2026-09-28.md). It is a research comparison, separate from the six-stock $100 paper ledger. The current unfiltered seven-day provider calendar has 69 report rows for 67 symbols; 49 match catalogue stock candidates and 18 do not. All 49 plus SPY have newly captured prices. Quarterly financials returned only ten companies; the remaining 39 are missing, not zero. CBRL annual filing facts returned 21 tagged rows. SNX filing content returned a 404, so its official company release was verified directly. Three new verified public records cover SNX's release, COST's release and COST's earnings 8-K. These are summaries with source URLs, not a comprehensive news corpus.

Price/earnings/financial responses and hashes live under ignored `data/equities/forward-2026-09-28/`; the assembled `snapshot.json` preserves `captured_at`, original price/earnings observation times, raw hashes, missing fields and coverage errors. `forward-snapshot.json` is a replaceable verified latest-view mirror; retain every original capture. Fiscal period ends are not first availability. The provider's captured EPS comparison may mix revised estimates or different accounting bases, so it is not a reconstructed historical earnings surprise. Financials and narrative summaries are context, not learned model probabilities.

The challenger uses a $5 price floor, $20m median 20-session dollar volume, positive 20-session excess momentum, a verified recent report, positive captured EPS estimate and at least a 5% captured-estimate beat. It ranks up to three names by excess momentum. The comparison lane uses the identical event-conditioned universe and price/liquidity rules without the EPS gate. In the initial capture, 25 names fail the price floor, ten fail liquidity and 13 lack positive excess momentum. Only SNX passes; both lanes select it. Their first cohort therefore cannot demonstrate incremental value from the earnings filter. This is a recorded research selection, not a recommendation or an order.

Create a decision only on A8 using the verified capture and actual current clock:

```powershell
python scripts/run_forward_research.py --snapshot data/equities/forward-snapshot.json --decision data/equities/forward-decisions/decision-20260928.json --observations data/equities/forward-observations --create
```

On later captures, omit `--create` to evaluate each existing decision; use a new unique decision filename for a new prospective cohort. Outcomes use the next 09:30 New York open strictly after creation, the twentieth held session close, matched SPY and 10bp per side. They are individual hypothetical returns, not account P&L or an independently sampled daily strategy. The runner records accepted observations under a separate content-hashed journal for each decision. Never bypass this journal or overwrite decision/observation files. Missing or revised prior bars invalidate results. Without an exchange-holiday calendar, a missing weekday is explicitly `unverified_calendar`, including legitimate holidays; investigate rather than synthesizing a session or clearing a guard. The original capture before creation correctly remains pending.

Every refresh must fetch cumulative history from July 1, 2026 for the current calendar/catalogue intersection, **all symbols held by existing research decisions**, and SPY. Keep original split adjustment, raw bars and actual capture times. Select new candidates only from the current calendar intersection, but retain older held symbols in the bars for evaluation. Compare against every decision's last accepted observation before advancing it. Do not discard decisions to hide losses or invalid evidence. Later evaluation is still unmeasured until genuine future sessions arrive.

The dashboard now exposes paper-import/session status, event freshness, and captured scheduler evidence. A prior session is `awaiting_refresh` between close and the 6 PM Pacific schedule; a genuinely older gap remains stale. `scheduler-audit.json` records actual audit time, whether configured, and `last_run_at`/`last_result` only when an automated run has actually occurred. A manual check cannot populate those fields as a success. Failure and missing-run warnings are tested in the dashboard; notifications use the existing Codex heartbeat. A stopped Codex host cannot notify itself, and A8 still lacks independent authenticated collection. First scheduled execution, independent alert delivery and dashboard reboot recovery remain unverified.

Verified deployment: A8 created `decision-20260928.json` at **2026-09-28 05:28:12.406217 UTC**, with method hash `d4250d0c7a2a38d971fd69974621296957b232c5e72000e22e7dfd980c8f53e5`. Both SNX rows are pending with null returns and no simulated entry yet. The five-record event archive, immutable decision and its observation journal were mirrored from A8 through verified hashes and a consistent SQLite backup. Actual-data AppTests passed locally and on A8. The paper database hash remained unchanged. Full local suite: 1,874 passed, 24 environment/platform skips; final focused suite including subsequently added gap regressions: 36 passed locally and on A8. Ruff and strict source mypy passed (171 files). Independent review found no remaining blocker. The existing weekday heartbeat now includes guarded prospective evaluation, evidence collection and truthful scheduler audits; its first scheduled execution remains unverified.

### Operational sweep — 2026-09-28 23:07 UTC

At 4:07 PM Pacific, a read-only A8 check confirmed release `065bd01`, $100 cash/equity, $30 reserved, three pending orders, zero open/closed trades and zero settled forecasts. P&L remains $0. Both SNX research lanes remain pending with null returns. The archive has five event versions; actual-data dashboard AppTest returned no errors or exceptions. The paper database retained hash `f8e4f2e624fbc0fcc0c7a4657dc2d111a7c002ba12c66034e57925e491e11d6f`.

The latest stored session is Friday September 25. A fresh Robinhood SPY/SNX daily-history probe also returned only through Friday. Monday's refresh is due September 29 at 01:00 UTC (Monday 6 PM Pacific); health correctly reports `awaiting_refresh` and `configured_unverified`. No automated success, paper fill, research return or independent A8 feed is established by this manual sweep. No server data was changed.

GitHub PR #150 exposed checks omitted from the previous local verification: 25 files needed Ruff formatting, and Bandit treated a local dictionary named `requests` as an HTTP client. The cleanup formats those files and renames the dictionary to `request_sources`; normalized Python ASTs are identical. Strategy, costs, risk limits and dependencies are unchanged. The cleanup is split into small stacked PRs; only the combined final branch contains every formatting fix. Earlier draft branches can therefore retain failing formatting checks until integrated. No branch was merged and A8's behavior-equivalent release was not redeployed for formatting.

Combined local validation: Ruff lint and format pass (311 files), strict mypy passes (171 source files), Bandit's existing medium/high gate passes, and the non-integration coverage suite reports **1,875 passed, 24 skipped, one deselected; 88.67% coverage** against the unchanged 80% gate. Independent review confirmed the normalized AST equivalence. Local checks do not establish GitHub's two-platform result or investment performance.

### Nine parallel paper portfolios

The owner requested multiple tests within the three strategy families and delegated the count. The [frozen design](superpowers/specs/2026-09-28-parallel-stock-books-design.md) crosses 5-session momentum, 20-session momentum and 20-session earnings/momentum with 10-, 20- and 60-session price lookbacks. Each has $100 virtual cash: $900 in new simulations, separate from the original $100 pilot. Existing $10 order size, five-active cap, 10bp each-side friction and $10 loss pause remain unchanged per account. No additional real capital is used. All nine results stay visible; correlated holdings, differing history coverage and cash exposure prevent treating nine books as nine independent confirmations. The 60-session review is descriptive, not an alpha test; see [research](research/PARALLEL-STOCK-TESTING-2026-09-28.md).

Only A8 runs the writer, using the shared research capture:

```powershell
python scripts/run_stock_portfolios.py --snapshot data/equities/parallel-launch-20260929/snapshot-screened.json --root data/equities/parallel-books
```

For scheduled updates substitute the new immutable dated capture path. Collect cumulative regular, daily, split-adjusted prices from June 1, 2026 for the current calendar/catalogue intersection, SPY, and every open/pending name in every parallel ledger. Keep prior research-decision symbols and original-pilot symbols for their existing workflows. Use one common capture for all nine; retain actual price/earnings retrieval times. Preserve raw calendar/price files and hashes. If duplicate entries disagree for the same symbol/year/quarter, quarantine that entire symbol from the new candidate universe and screen earnings, retain both raw records, and disclose the exclusion in `source_errors` and `quarantined_symbols`. Continue collecting its prices if any account already holds it. Never choose whichever conflicting earnings value gives a better result. The launch capture contained one such conflict, IXHL, leaving 58 calendar stock candidates and SPY benchmark coverage; the raw prices still include IXHL.

Each root has an immutable launch manifest, archived captures, independent `<portfolio_id>/paper.sqlite` files, dated run reports and atomic `latest.json`. The runner exits nonzero for partial failure, preserves successful accounts and shows failed ones explicitly. The dashboard shows all nine, daily liquidation-value equity, realized/unrealized P&L, recorded daily drawdown, exposure and counts. Passive SPY assumes $100 fully invested; matched closed-trade SPY uses each trade's $10 and same costs. Neither is an assertion of risk-adjusted alpha. No eligible stocks means cash, not forced trades. Missing trailing weekdays, including unresolved holidays, are `unverified_calendar` and block updates. Revised prospective benchmark bars remain invalid against the last accepted capture.

`in-progress.json` records an unfinished capture: recover that exact preserved capture before advancing to another one, so an interrupted report cannot discard an equity peak. Ordinary exception exits release `writer.lock`; after a process crash or reboot it may remain. Verify no portfolio runner is active before removing only this stale lock, then retry the exact recorded input. Do not clear the intent or delete databases to force progress. Beyond 24 hours, only the matching archived pending capture can enter recovery mode: it republishes already committed summaries without ledger writes or new orders; uncommitted accounts remain failed until a fresh capture. The source timestamp remains old and the dashboard withholds stale amounts. Never backdate the clock. Account launch timestamps remain actual; partial retries with later new-account creation are flagged as unequal starts.

After each successful run, mirror the manifest, latest/durable run reports and captures with verified hashes. Back up each SQLite account consistently on A8 before mirroring; never overwrite server accounts from local copies. The dashboard is read-only. The existing heartbeat still depends on the Codex host and Robinhood session; this feature does not establish independent A8 authentication or reboot recovery.

Deployment evidence, September 29 UTC: 59 source/test/capture files were hash-verified on A8, 38 focused tests passed both locally and on A8, and GitHub Linux/Windows/security checks passed at `422a779`. The first manual start at 00:44:02 UTC was blocked for all nine: Monday's SPY daily record was an interpolated zero-volume placeholder, so the last usable session was Friday September 25. An independent official-close/hourly probe confirmed actual Monday trading; those different price formats were not substituted into the daily protocol. No new portfolio SQLite account or virtual order was created. All nine blockers are visible in actual-data AppTests on A8 and the local mirror, with no exceptions; original paper and event database hashes are unchanged. Preserve this failed attempt and never call it an operational success.

Weekday collection now checks at **6 AM, 6 PM and 9 PM Pacific**, retaining the original evening check and adding quiet data-publication retries. Skip another strategy decision when an already-successful portfolio report has the same real completed SPY session. The first successful scheduled start is still unverified. A follow-up regression ensures that, after a blocked launch, the common benchmark starts with the accounts' actual shared creation time, not the earlier failed attempt; partial or unequal account starts have no shared passive benchmark. The manifest retains the original attempt for audit while successful report launch times come from the ledgers.

### Verified session fallback — 2026-09-29

The daily-history endpoint was the blocker, not a lack of market activity. At 01:14 UTC it returned either no Monday daily row or an interpolated zero-volume placeholder. The provider's **regular-session fundamentals** already contained Monday's opening price, high, low and full session volume; its **official SIP exchange close** endpoint contained Monday's noninterpolated close. Five-minute aggregation was rejected: Friday SPY intraday volume was about 13.2m versus daily volume 36.7m, and opening prices also differed. No intraday aggregation, last-trade quote, guessed value or backdated order is used by this repair.

`src/kq/equities/session_data.py` creates a new labelled capture from those two reported sources. It checks symbol identities, dates, regular bounds, actual source timestamps, positive finite/integer volume, consistent OHLC, and exact official-close provenance. Each source must be observed after the completed session's close and before a following weekday open; the original daily capture must already be past that session's UTC date. This prevents relabelling intraday partial bars as complete. Required symbols must survive final regular-session normalization. Missing optional evidence preserves historical rows and excludes unsupported current candidates.

Capture every raw MCP response in a wrapper with `retrieved_at` and `response` (including `structuredContent`). Request fundamentals in batches of at most ten and quotes in batches of at most twenty so official closes are returned. Keep each source family within five minutes; earlier and later batch observation times are both validated. Required symbols are SPY plus every pending/open account symbol; include all seven baseline symbols for the original pilot. Preserve raw calendar conflicts and current-candidate exclusions. Then run this capture-only command (it does not write any ledger):

```powershell
python scripts/complete_stock_session.py --snapshot <new-daily-input.json> --fundamentals <fundamentals-0.json> <fundamentals-1.json> --quotes <quotes-0.json> --required SPY AAPL MSFT XOM --prior <last-accepted-capture.json> --output <new-session-complete.json>
```

`--prior` is mandatory. For the baseline, use the source matching A8's committed paper snapshot hash; for parallel portfolios use `parallel-books/captures/<latest-successful-hash>.json`; retain the latest accepted forward snapshot as well. At the first repair these prior captures had no supplements. On subsequent refreshes, reconcile every previously accepted supplement: preserve its original values and retrieval times only while primary daily history is missing/synthetic; reject any conflicting real OHLCV revision. Never drop prior repaired symbols from fetched history, omit this reconciliation, or clear anchors to bypass a conflict. When separate lanes have different accepted captures, prepare/reconcile their derivatives separately. All original captures remain immutable.

The shared price-fetch union must also include **every symbol already recorded in parallel account `capture_coverage`**, even if not held or selected today. Existing ledger history checks apply to all captured symbol/session rows. A shrinking earnings calendar must never shrink the retained price history. Current candidates alone remain eligible for new selections.

Only after preparation derive the latest effective completed SPY session. A verified session-statistics/official-close supplement counts; a raw placeholder does not. Compare this date with each lane's last successful session. Skip already processed sessions, even when the raw daily endpoint still lags. Use the existing A8 import commands, costs, caps, next-open timing, holding periods, clock and immutable journals unchanged. A new source capture may be assembled locally, but only A8 writes paper ledgers and research decisions. Copy the baseline derivative to a unique root-level `data/equities/snapshot*.json` so the dashboard can match its committed hash; keep raw files in the dated folder.

Actual deployment: 25 source/test/capture files were hash-verified on A8; all 34 new validation/integration tests passed there. The prior equity suite passed 221 tests before the final additional timestamp/source-wrapper regressions. Independent review caught and verified fixes for partial-day promotion and required-session omissions. At 01:28:35 UTC the original three pending orders filled against verified Monday opening prices: AAPL 340.46, XOM 162.60 and MSFT 505.45, $10 each including simulated entry friction. Cash is $70; marked equity is $99.949202 after estimated exit costs, not a closed-trade profit. Nine portfolios initialized at their actual current clock, with 19 pending orders and no fills yet. Both existing SNX research lanes now have a Monday entry and no mature return; a distinct Monday-session cohort selected BB/SNX in both lanes. Neither result demonstrates an earnings contribution.

Pre-import consistent paper/event backups and all evidence are under `data/equities/feed-fix-20260929T0114Z/` on A8. All nine account databases, reports, decisions, journals and source captures were mirrored from verified server backups. Actual-data dashboard validation had no exceptions. `manual-recovery.json` records the successful manual repair; the 6 PM scheduled attempt remains truthfully recorded as failed. The next scheduled retry must prove automation success separately. This remains dependent on Codex and the Robinhood session; no independent server authentication, reboot recovery, profitability or real execution is established.

Final local equity regression suite: **227 passed**; Ruff lint/format and strict mypy pass. The existing heartbeat now uses the reviewed repair before deciding whether a session is missing, requires prior-source reconciliation, retains all captured symbols and skips already processed effective sessions. The original scheduled failure is not rewritten as success. Dashboard captions identify the alternate verified source and distinguish manual recovery from scheduled execution.

### Adaptive daily advice — 2026-09-29

The owner approved the [versioned design](superpowers/specs/2026-09-29-adaptive-stock-signals-design.md). Its first release is an advisory journal, not a new funded portfolio. It computes 20/60-session SPY-relative log momentum divided by stock volatility; buy threshold 0.5 and held-exit threshold 0 are fixed hypotheses. Valid entry exclusions show WATCH with a reason; missing data and quarantined candidates show WAIT_DATA. The original pilot supplies reference held/pending states through a consistent read-only SQLite transaction. Suggestions do not alter its orders or the nine portfolios' rules. News records retain original source times and remain context only.

The new scorer requires 61 aligned real sessions and uses explicitly verified 2026 NYSE scheduled closures; unsupported years or unexpected missing sessions fail closed. This does not change calendar rules in any existing lane. The journal retains full capture/reference evidence, hashes, actual decision time, failures and same-session revisions. NaN and other invalid JSON evidence are preserved as labelled diagnostic literals, never converted to valid prices. It compares genuine historical OHLCV and ignores synthetic duplicates when checking revisions. Snapshot capture, price source and pilot reference freshness are checked separately; the dashboard withholds current advice after failures or staleness.

Run only in the isolated A8 release, using the latest accepted reconciled research/parallel capture and the same authoritative pilot database:

```powershell
python scripts/run_adaptive_research.py --snapshot <accepted-dated-research-capture.json> --reference-ledger data/equities/paper.sqlite --root data/equities/adaptive-research
```

The CLI refuses any output beneath `READ_ONLY_MIRROR.txt`. Before the scheduled run, inspect `load_latest(Path('data/equities/adaptive-research'))`. If its decision already represents the latest real completed SPY session, do not generate another decision from a newly timestamped capture. Same-session changed inputs are archived as failed revisions; retries of the exact accepted input preserve the original decision and reference timestamp. On a new completed session, refresh the baseline first so the original pilot reference session matches. Preserve the union of every previously captured symbol, original pilot holdings and current candidates. Refuse older input or revised/missing prior history. If the baseline refresh fails, log a separate advisory failure rather than using stale reference holdings; the independent nine portfolios may still update under their own rules.

An accepted journal record can contain WAIT_DATA rows; success means evidence was recorded, not that every candidate was eligible or that any trade filled. Inspect action counts and reasons. Invalid capture or reference files must produce a failed attempt while preserving prior accepted evidence. The source remains Codex/Robinhood-session dependent. Do not label manual recording as successful scheduled execution.

After a write, create a consistent SQLite backup from A8 `journal.sqlite` using a read-only source connection, transfer it to a temporary local file, verify SHA-256 and atomically replace the local mirror. Never send a local journal to A8. Keep the dashboard's adaptive section read-only. No new listener or separate scheduler is needed. Future dynamic-exit account/control work still requires its own protocol, next-open/cost/cap/recovery tests and fresh launch; no earnings contribution or profitable edge is established here.
