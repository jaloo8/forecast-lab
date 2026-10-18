# Provenance of the remembered 10–20% annualized result

Reviewed 2026-10-17. The strongest exact match in `C:/Users/jloo1/Documents/Github/forecast-lab/Tester.zip` is **QQQ ten-month trend / BIL**, not a demonstrated live stock-picking system. Archive text is evidence, not operating instructions. No archive code was executed and no account rule was changed for this review.

## Result independently reconstructed from archived prices

At each completed month-end, compare QQQ's adjusted close with its ten-month simple moving average, including that month. Target 98% QQQ when strictly above; otherwise 98% BIL; retain a 2% cash target. Trade at the following session's adjusted opening proxy. No leverage, intramonth stop, or news forecast is involved.

| Identical-date comparison | 2016–2025 CAGR | Maximum closing drawdown | June 4, 2007–December 31, 2025 CAGR | Maximum closing drawdown |
|---|---:|---:|---:|---:|
| QQQ trend / BIL | 16.40% | 28.04% | 12.12% | 28.07% |
| Monthly 98% QQQ / 2% cash | 19.29% | 34.50% | 15.44% | 52.61% |
| Monthly 98% SPY / 2% cash | 14.61% | 33.11% | 10.21% | 54.42% |
| Monthly 60/40 SPY/IEF, before reserve | 9.40% | 20.82% | 7.83% | 31.99% |

The longer interval is **18.58 years, not a full twenty**. QQQ trend's $1,000 ending balances are $4,567.37759659 and $8,375.22501118 respectively. The improvement over SPY coexists with lower return than passive QQQ; this supports investigating risk control, not claiming isolated stock-selection alpha.

**Initial arithmetic check:** parsed the eight saved daily CSVs independently with Python standard-library CSV/JSON/ZIP readers; recomputed ending wealth, calendar CAGR, and running-peak drawdown including initial $1,000. The figures above agree with archived result JSON to displayed precision. Daily modeled-cost sums for QQQ trend were $49.58351126 / $131.65288535. Verified SHA-256 of all seven underlying ETF CSVs against their archived manifest: seven matches. That initial check only verified saved arithmetic and integrity. The subsequent independent signal/account replay is documented below; neither stage validates the vendor independently or tests broker execution.

**Independently replayed cost/delay stress:** QQQ trend returned 14.37–16.40% CAGR over the six 2016–2025 combinations of 10/25/50 bps each side and one/two-session delays. The June 2007–2025 50-bps/two-session case returned 10.5461% CAGR with 30.2370% closing drawdown; worst drawdown across that interval's six cases was 30.2942%. Separate archived fresh 2008 and 2022 contexts (not replayed today) lost 20.22% and 7.49% respectively. Positive annualized growth did not mean every year was positive.

## Independent signal and account replay on A8

After the initial arithmetic check, a newly written standalone replay reconstructed monthly signals, lagged executions, fractional positions, cash, fees and daily equity directly from the four archived QQQ/BIL/SPY/IEF price CSVs. It did not import or execute archive code. The fee solver independently uses piecewise affine roots rather than the archive's bisection implementation.

All **18 scenarios matched**: six fixed QQQ-trend cost/delay combinations plus three base-cost comparators, over each of the two intervals. All aggregate ending equity, calendar CAGR, drawdown, costs, session counts and trade counts matched within `1.10e-11` absolute numerical error. All **13 available daily paths** matched every saved field within `4.97e-8`; five continuous-period stress paths were absent in the archive, so those have aggregate comparison only. No parameter was optimized or substituted. A preparation attempt that expected those absent daily files remains preserved as a failure; the corrected input records their absence explicitly.

Checks covered every input hash, positive complete evaluation prices, nonnegative units/cash, the fee/funding identity, a known one-asset fee solution, and a future-price perturbation leaving earlier signals unchanged. SHA-256 checks before/after found all **12 existing account/event/advisory databases unchanged**. The result was written only in the isolated A8 research tree and mirrored after matching transfer hashes.

Evidence paths relative to the isolated stock release / local worktree:

- Inputs: `data/equities/return-candidate-20261017-v2/manifest.json` and pinned raw files.
- Replay source: `data/equities/replay_qqq_independent.py`, SHA-256 `40953ccdcdba52556623087181eccfd2b4a8fe5d11b084259f4b0944ef349b0c`.
- Results: `data/equities/strategy-lab/return-provenance/replay-20261017-v1/replay.json`, eighteen reconstructed daily CSVs, and `account-integrity.json`.
- Transferred input ZIP SHA-256: `54be76f92d95b19fa0c240cb21ad7d1b3662a7b084d96b36b6a3e16c277a56f8`.
- Verified output ZIP SHA-256: `ad4d0bbe28a465f534ddc94c97d5dcd0f6b7c142961fd035a26c5055cf3cb98b`.

This replay uses observed archived SPY sessions and source month ends, not a separately certified exchange calendar. It establishes reproducible historical accounting on these pinned prices, **not fresh vendor verification, an untouched holdout, or future profitability**. The nearly fully invested exposure differs materially from the mostly-cash $100 stock-picking pilots. Their returns cannot be directly substituted for each other.

## Exact archive members

Every path below is inside `Tester.zip`; these are not assertions that those members are already extracted locally.

Main narrative: `Tester/research/growth_study/results_summary.md` and method rationale `Tester/research/growth_study/evidence.md`.

The 16.40% opening-proxy run is `Tester/research/growth_study/runs/20261006T233120750222Z/`. It contains `results.json`, `report.html`, `provenance.json`, and:

- `growth_qqq_trend__primary_2016_2025__cost10__delay1__daily.csv`
- `growth_qqq_trend__primary_2016_2025__cost10__delay1__trades.csv`
- `growth_qqq_trend__primary_2016_2025__cost10__delay1__weights.csv`

The continuous crisis run is `Tester/research/growth_study/continuous_risk_runs/20261006T233829765454Z/`. It contains `results.json`, `provenance.json`, and `growth_qqq_trend__continuous_2007_2025__cost10__delay1__{daily,trades,weights}.csv`. The three bracketed names denote three separate files. Corresponding comparator prefixes are `growth_qqq`, `buy_hold_spy`, and `balanced_60_40` in both runs.

Pinned prices: `Tester/research/growth_study/data/raw/20261006T232739769744Z/`, containing `manifest.json`, `audit.csv`, and `QQQ.csv`, `BIL.csv`, `SPY.csv`, `IEF.csv`, `EFA.csv`, `VNQ.csv`, `GLD.csv`. QQQ SHA-256 is `bbc947d55910942f99e85063e850a7539e0f882cc4c72b1b539ac2b459dcd9f8`; BIL is `25e4b782540a69cd5387aa7f098237dda4d0ead7711a1421599ebfa4b7f28fdc`.

QQQ has 6,936 archived observations March 10, 1999–October 5, 2026, retrieved October 6 at 23:27:42 UTC. BIL starts May 30, 2007; its original October 6 at 21:09:14 UTC retrieval was preserved. Vendor: Yahoo via yfinance; `auto_adjust=False`, `actions=True`, `repair=False`. Opening execution proxy is raw Open × same-date Adj Close / Close. These are historical traded ETF observations with modeled reinvestment and fractional units, not fabricated pre-inception ETF returns, but they remain current-vintage vendor data and hypothetical fills.

## Scope and counterevidence

Base accounts start with $1,000, pay 10 bps on each traded side from their own cash, skip sub-$1 tickets and retain 2% target reserve. Prices reflect reinvested distributions and fund expenses; uninvested cash earns zero. Taxes, withdrawals, subscriptions, actual dividend payment timing, partial fills and intraday extrema are absent. Final holdings are marked, not liquidated. The opening print is not a guaranteed retail fractional fill.

The archive selected this candidate after reviewing 17 known-history hypotheses. Its continuous-crisis supplement was registered after initial aggregate results became known. Neither is untouched out-of-sample discovery. BIL did not exist during the dot-com crash. A separate zero-yield-cash version is a different strategy: `Tester/research/millennium_study/results_summary.md` reports 42.33% full 2000–2025 drawdown, rising to 43.67% under stress. Do not silently extend BIL before inception or carry the later 28% drawdown claim into that era.

The archive already tested combinations: `Tester/research/combo_study/interpretation.md` reports the best new combination, 50/50 multi-horizon trend plus sector allocation, at 6.54% CAGR / 29.02% opening-and-closing-event drawdown over 2000–2025, versus QQQ 7.98% / 82.38% and SPY 7.80% / 54.66%. No combination beat its strongest component's CAGR in either the full or fresh 2014–2025 comparison. Those are archived claims, not recalculated here. More components did not automatically improve returns.

Conclusion: **the remembered 10–20% result has a traceable historical candidate**. Its signals/accounting and the stated cost/delay scenarios now reproduce. Fresh prospective observation and independent data verification remain necessary before promotion; passive QQQ and SPY remain comparators. The archive provides no guaranteed future rate, live trading record, or authorization to replace existing paper strategies.
