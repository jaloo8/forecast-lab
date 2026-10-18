# October 18 audit checkpoint

This is a recovery record for the completed bounded audit, not a profitability verdict.

## Owner scope and resource budget

Keep weather stopped; all stock work remains simulated. Use sequential, bounded
jobs and minimal agents. One bounded read-only reviewer checked the new engine;
all collection and replay jobs ran sequentially. Research must include the owner's named
sources (Google Scholar, Seeking Alpha, Morningstar, TipRanks, Yahoo Finance,
Reddit/forums and Bloomberg) AND relevant independent sources. Record which
pages and ratings were actually accessible; do not imply that search snippets
or a methodology page establish a complete historical ratings archive.

The requested universe is S&P 500 constituents plus up to 500 independently
screened additional social/news candidates. Current membership or popularity
cannot be projected backward into a twenty-year unbiased universe. Report
coverage shortfalls, delistings, IPO availability and unavailable sources.
Do not pad a list to 1,000 or promise 10–20% in every calendar year.

## Evidence captured this session

- Authoritative A8 stock release: `C:/Users/jloo1/Documents/stock-paper-lab-20260928`.
- Fresh read-only audit: all ten paper SQLite accounts passed quick_check;
  before/after hashes match. Baseline equity $101.499345 from $100, zero realized
  profit and $1.499345 unrealized simulated profit. Latest genuine session is
  Friday October 16; October 18 is Sunday.
- The stock dashboard health endpoint on port 8502 returned HTTP 200.
- Price collection depended on the desktop Codex/authenticated data connector.
  Last scheduler audit records failure; October 17 manual recovery is separately
  labeled delayed recognition. A running dashboard is not proof of collection.
- Local recovery/accounting/history tests: 61 passed. Recovered sector-engine
  tests: 22 passed. These are targeted tests, not a full-repository run.
- Replayed all 15 declared sector-study scenarios over 5,031 sessions in
  2006–2025. At 10bp per side: SPY 10.87% CAGR, equal sectors 10.18%, sector
  momentum 8.80%, SPY trend 8.12%, sector momentum plus trend 6.27%.
  Active drawdown reductions did not deliver higher full-period CAGR than SPY.
- Recovered the earlier QQQ/BIL evidence: 16.40% CAGR in 2016–2025 and 12.12%
  June 2007–2025, approximately 28% closing drawdown. This is not 20 full years,
  not a result from the small A8 account, and not 10–20% every year.

## Artifacts and provenance

Research worktree base: `45de9575aa5960b8a7d361d91c5e9cbbac86c15d`.
Sector engine recovered read-only from Git commit `02db162`; no archive code
was executed from Tester.zip. Its selected price/artifact files were consumed
by the reviewed repository replay. Private evidence is under ignored
`data/audit-20261018/`, including A8 JSON, JUnit reports and sector rerun outputs.
The original dirty checkout was preserved.

## Completed after the initial checkpoint

- Deployed-source tests: 61 passed on A8; 18 QQQ scenarios reproduced.
- Full local suite: 2,236 passed, 25 skipped. Four later calendar regressions
  bring the new focused suite to ten passing tests locally and on A8.
- Universe: 503 current SPY share classes plus 429 verified additional social
  candidates, not the requested 500 extras. All 933 price requests including SPY
  completed, covering 3,850,607 raw rows; unavailable rows remain explicit.
- Frozen nine-arm blend/trend study and SPY: 60 scenarios; 54 complete, six
  unscored on missing held prices. All 56 local/server result CSVs matched.
- A8 dashboard and account integrity are healthy; unattended collection is
  still unverified and requires its desktop/authenticated connector. Direct
  public research prices were not relabeled as original account-feed data.
- Weather-submit was unexpectedly enabled. Its persisted task definition is
  now disabled; the disable command timed out, so scheduler execution remains
  unverified. No weather or live-money orders were submitted.
- Complete findings and all tested-arm results are in
  [the audit](STOCK-A8-AUDIT-2026-10-18.md), with the durable broad-source research
  standard in [the source register](STOCK-SOURCE-REGISTER-2026-10-18.md).

## Remaining work, in order

1. Repair the independent unattended feed/scheduler contract, then observe a
   genuine scheduled completed-session collection. Do not erase the failure
   audit or alter original fills to make a status green.
2. Acquire point-in-time constituents, delisted outcomes, corporate-action
   identity history and dated ratings/fundamentals before interpreting today's
   universe as an investable twenty-year test. Resolve the 71-name shortfall
   through evidence, not arbitrary padding.
3. Compare predeclared strategy blends on that evidence and then freeze a
   prospective paper challenger; do not retune until a desired CAGR appears.

No purchases, credentials, account resets or real-money orders occurred.
