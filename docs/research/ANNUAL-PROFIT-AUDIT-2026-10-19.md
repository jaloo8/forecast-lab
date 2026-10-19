# Annual-profit feasibility review — October 19, 2026

**No reviewed or reproduced result establishes 10–20% profit in every calendar year.** This is a useful research repository, but it does not presently demonstrate dependable annual income. The user's current requirement is a minimum 10% net total return in each complete year, with years above 20% reported separately. The practical reference remains **$1,000**. This differs from the older QuantLab 66% overall-CAGR study; its results and frozen broker configuration remain preserved.

## Checkout and review coverage

Repository: `jaloo8/forecast-lab`, base commit `e1e1f4bc43e19ca862e1425ff637e7fa0d124db1`. The clean checkout was fast-forward checked before creating local branch `research/annual-profit-audit-20261019`. No GitHub login was needed for access.

The base checkout contains **638 tracked files and 124,580 lines**. Parent and three reviewers read the complete contents of **631 nonempty files / 120,658 lines**, including source, tests, documentation, generated model manifests and fixtures; five empty files were verified. `uv.lock` received complete TOML/structural inspection (211 packages, 1,753 artifact records), not word-by-word reading of its repeated wheel URLs and hashes. `secrets.enc.yaml` was inventoried but not decrypted. Thus this is a full source/documentation/test review, with those two explicit exceptions to literal every-word reading. It does not cover every historical commit, ignored private data, or the live A8 machine.

The exact deduplicated path/range/hash record is in `data/annual-profit-audit-20261019/review-coverage.json`, also retained in the audit evidence bundle. Narrow repairs have separate current hashes; original results are preserved. Full reading is not a claim that every possible defect has been discovered.

## Reproduced stock evidence

The [pre-result protocol](ANNUAL-PROFIT-AUDIT-PROTOCOL-2026-10-19.md) froze eight policies at three costs: **24 account paths, 480 calendar-year returns, 120,744 daily observations**, covering the same 5,031 sessions in 2006–2025. These are eight policies, not 24 independent algorithms.

Original provenance, pointers, manifests and price-file hashes matched. A new data-only wrapper was assembled from 27 verified local QuantLab members; it is explicitly not the original transfer ZIP. The original sector metrics, annual and block tables reproduced within `1e-10` numerical tolerance. The inverse-volatility runner also reproduced all 30 baseline daily/ledger files byte-for-byte. An independent Decimal calculation checked yearly returns, CAGR/worst-year consistency, cash identities and proportional fees; maximum cash-identity residual was below $0.00000000002.

| Policy | CAGR | Worst calendar year | Maximum close drawdown | Years at least 10% |
|---|---:|---:|---:|---:|
| SPY hold | 10.87% | -36.80% | 55.19% | 14 / 20 |
| Equal sectors | 10.18% | -35.48% | 53.51% | 14 / 20 |
| Sector momentum | 8.80% | -29.69% | 46.63% | 11 / 20 |
| SPY trend | 8.12% | -22.06% | 26.08% | 9 / 20 |
| Sector momentum + trend | 6.27% | -12.03% | 25.22% | 9 / 20 |
| Equal sectors, inverse volatility | 9.85% | -33.55% | 51.19% | 14 / 20 |
| Sector momentum, inverse volatility | 8.23% | -27.28% | 43.71% | 11 / 20 |
| Sector momentum + trend, inverse volatility | 5.88% | -11.96% | 25.16% | 7 / 20 |

Table: original **10 bp per-side cost**, $10,000 starting capital, fractional adjusted units, next-session opening execution, zero-yield cash and final liquidation. **Zero of 24 cases passes** at 10/25/50 bp. This is reproduction of known history, not an untouched holdout or a demonstration of $1,000 execution. Close-only drawdown omits intraday extremes. Session counts and year boundaries were checked; an independently sourced exchange calendar was not used. Taxes, fixed broker charges and real fills were not modeled.

## Public options benchmarks

The fixed supplement requested BXM, PUT, PPUT, CLL and SPXTR from Cboe. SPXTR returned HTTP 403 and remains unavailable. The four accessible daily histories have a common complete-year window of **2009–2025**, not the requested 2000 start. Missing earlier years were not filled or spliced. Decimal results were independently checked against pandas year-end ratios: all 68 annual returns agreed within `1.95e-16`.

| Published index | Strategy family | CAGR | Worst year | Years at least 10% |
|---|---|---:|---:|---:|
| BXM | Covered calls | 8.14% | -11.37% | 7 / 17 |
| PUT | Collateralized put writing | 9.26% | -7.66% | 7 / 17 |
| PPUT | Equity plus protective puts | 10.55% | -19.81% | 10 / 17 |
| CLL | Equity collar | 7.93% | -15.05% | 7 / 17 |

All four fail the annual minimum, including negative years. These are published hypothetical index histories, **not retail net account backtests**. The methodologies model premiums, dividends and—in PUT—Treasury collateral, with defined option-pricing conventions. They do not establish this account's actual commissions, liquidity or fills; their disclosures explicitly distinguish theoretical index returns from actual portfolios. PPUT launched August 3, 2015, so its earlier values in this window are backtested. No matched SPXTR excess-return claim is made. Primary methods: [BXM](https://cdn.cboe.com/resources/indices/governance/Cboe_BuyWrite_Indices_Methodology.pdf), [PUT](https://cdn.cboe.com/resources/indices/governance/Cboe_SP_500_PutWrite_Indices_Methodology.pdf), [PPUT](https://cdn.cboe.com/resources/indices/governance/Cboe_SP_500_Put_Protection_Indices_Methodology.pdf), [CLL](https://cdn.cboe.com/resources/indices/governance/Cboe_Collar_Indices_Methodology.pdf).

## Private options replay: not completed here

The user confirmed the Databento cache must be transferred from the other PC. The committed [original results](OPTIONS-RESULTS-2026-10-18.md) report **172 strict closed spreads / -$1,675.20**, and **370 conditional closed spreads / -$3,484.00**. Those totals were read, **not independently reproduced on this PC**. Eight strict exits ($475.40 entry debit) and 39 conditional exits ($2,230.70 debit) remain unresolved, rather than being counted as zero. Strict coverage has zero 2023 closures and one in 2024; the nominal 2023–2026 input span does not establish full annual execution coverage.

The replay evaluates individual spread cash flows. It does not produce a continuous funded portfolio with daily NAV, evolving available cash, overlapping-position limits, settlement, exercise/assignment and complete missing-exit treatment. Therefore dividing its closed dollar P&L by $1,000 would be invalid. Separate displayed leg quotes also do not establish an atomic spread fill. Publisher-flag semantics and a retrospective complete-session filter need resolution before a new strategy claim.

Transfer the **complete** `Documents/MarketData/databento` directory privately, including `catalog.sqlite`, `raw/`, `runs/` and derived inputs. The existing handoff reports about 15.09 GiB of raw payloads plus extra derived data. The cache backup helper alone excludes `runs/`. The intended destination on this PC can be `C:/Users/jaloo/Documents/MarketData/databento`. Preserve original selections, session census, result directories and restore/source manifests. Replay needs **no API key**. Once present: verify catalog/payload/input hashes, block network, run the two frozen handoff commands into new output directories, and compare all original report/observation/cost-case outputs. Do not redownload missing inputs or treat prior acquisition approvals in old documents as current spending authorization.

## AlphaLedger

The [T12 product disclosure](https://www.alphaledger.com/products/t12/) specifies a **12% annualized distribution target before fees/expenses**, a 1% stated fee, $50,000 minimum, accredited-investor eligibility and inception on June 26, 2025. A distribution target is not a guaranteed total return; the page explicitly disclaims guaranteed distributions. That minimum is incompatible with the $1,000 reference. Public themes include options, futures and several asset classes, but disclosed holdings/themes do not supply reproducible signal, sizing, timing and execution rules. We can study transparent option overlays separately; we cannot claim to replicate T12 or infer a durable trading edge from tokenization. No signup or subscription is needed for the present public-source review.

## Corrections and remaining code limitations

Three narrow corrections were made locally:

1. **Percentage drawdown:** the legacy metrics helper previously used the percentage at the largest dollar drawdown. For NAV `[1000, 800, 2000, 1700]`, maximum loss is $300 but maximum percentage drawdown is 20%, not 15%. The two maxima are now computed independently, with a failing-before regression. This helper is separate from the reproduced sector engine; old reports were not silently rewritten.
2. **Windows cache paths:** extended-length native I/O paths fix the cache failures caused by long content-addressed filenames. Two explicit long-path regressions failed before and pass after. Cache layout and accounting are unchanged; all 172 related tests pass, including the 18 original failures.
3. **Evidence wording:** the weather nowcast dashboard now calls positive capture hypothetical sample results and no longer labels it a demonstrated bankable edge. All 39 associated tests pass. No financial rule changed.

Static review also found material legacy limitations, recorded without broadening this stock/options task into an operational rewrite:

- Weather backtesting can settle/reuse capital within the same day's loop, and its sizing does not match all paper fee assumptions. Synthetic market pricing is not historical executable evidence.
- Legacy paper fills are assumed locally at submission. Separate lanes start with independent bankrolls; their total cannot be divided by one $1,000 deposit. Missing sports results can become irreversible assumed VOID outcomes; ingestion failure is not proof of cancellation.
- Some sports quote queries lack freshness/as-of restrictions, and scheduled time is not enforced as a strict game-entry window. The purported append-only fantasy projection ledger can replace a same-key record.
- Some calibration/router and nowcast studies mix full-window decisions or approximate production features. Current-survivor equity universes and corrected historical tables are not a point-in-time universe or an untouched holdout.

These are constraints on interpretation and future validation, not claims of observed live losses. No broker order, production deployment, A8 writer or frozen QuantLab engine was changed.

Validation: the original offline suite had 2,536 passes, 18 cache failures and 25 skips. After the numerical/path fixes, the full offline suite had **2,563 passes, zero failures and 25 skips**. Twenty-four skips concern POSIX/logrotate on Windows; one needs an absent archived capture. Real-API integration tests were excluded. The final exact strategy/cost-membership guard then passed all ten focused audit tests and reproduced the original screen unchanged apart from its timestamp. Repository Ruff/format checks and mypy over 214 source files passed; the audit script also passed its focused type check. The wording change has its separate 39-test validation. No live vendor/broker validation is implied.

A second reviewer recomputed all 548 annual returns using summed daily log changes, independently of both the portfolio engines and the Decimal screen. Returns, CAGR, threshold counts and close drawdowns matched; maximum annual-return discrepancy was below `3e-15`. The reviewer also found and corrected the exact-case guard: 24 rows alone no longer suffice if a registered strategy/cost pair is duplicated or omitted. Windows verification covers long nested raw-payload paths; arbitrary long SQLite roots and actual UNC network paths were not tested.

## What to do next

1. **Finish the frozen options reproduction after transfer.** This is an integrity check of an already losing candidate. Do not buy more history or optimize this candidate merely to rescue its results.
2. **Keep the annual minimum as an explicit rejection test.** Also report CAGR, losing years, worst year, drawdown, turnover and implementation cost. Do not replace the user's objective with beating SPY or average return.
3. **Require a funded-account model before any new options annual-return claim.** Freeze integer-contract sizing, fees, cash/collateral, daily marks, missing data and lifecycle rules before seeing new outcomes. Keep unknown states visible. Do not fractionally scale option contracts to fit $1,000.
4. **For new stock-selection research, first obtain adequate historical membership, delistings and as-filed fundamentals.** Profitability/quality is a possible preregistered hypothesis, not a demonstrated solution; the repository's published profitability proxy already misses the every-year target. Preserve all trials and use prospective paper observation for genuinely new evidence.

At $1,000, 10–20% is $100–$200 per year. A hypothetical $10/month subscription alone costs $120/year. Research costs and fixed transaction charges must be separated from strategy gross returns and included when assessing practical net profit. There is no supported reason here to increase capital, leverage or subscriptions.

## Reproduction and evidence locations

From this checkout, with the pinned Python 3.12 environment:

```powershell
.\.venv\Scripts\python.exe -m scripts.audit_annual_target prepare --source .. --output data/NEW-AUDIT
.\.venv\Scripts\python.exe -m scripts.run_sector_study --archive data/NEW-AUDIT/frozen-data-wrapper.zip --output data/NEW-AUDIT/sector-replay
.\.venv\Scripts\python.exe -m scripts.run_inverse_vol_study --archive data/NEW-AUDIT/frozen-data-wrapper.zip --baseline data/NEW-AUDIT/sector-replay --output data/NEW-AUDIT/inverse-vol-replay
.\.venv\Scripts\python.exe -m scripts.audit_annual_target screen --run data/NEW-AUDIT/inverse-vol-replay --output data/NEW-AUDIT/annual-screen
```

`prepare` requires the preserved parent QuantLab source data and refuses an existing output. The saved run is `data/annual-profit-audit-20261019/`; calculations, independent checks, source receipts, all outcomes, coverage and the portable HTML report are retained there. Review findings, original failing tests and subsequent test evidence are under `tmp/annual-profit-audit-20261019/`. The audit bundle preserves these without environment files, credentials or licensed raw options data. The public raw Cboe/AlphaLedger documents remain local and are not redistributed in that bundle. Final checks and archive hashes are recorded in the adjacent delivery receipt.
