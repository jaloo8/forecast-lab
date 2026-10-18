# Options candidate: what public data can actually test

The owner requested a plausibility backtest of the [fixed candidate](OPTIONS-CANDIDATE-2026-10-18.md).
No rule, threshold or risk limit was tuned after inspecting outcomes. Public
data only; no subscription purchased. This follow-up tests the underlying
trigger and data feasibility, **not historical option profitability**.

## Source checks

[ORATS' official minute-data manual](https://orats.com/readme-1min.pdf) links a
[free sample](https://orats.com/university/intraday-sample-data.zip). Downloaded
962,141 bytes and inspected all five CSVs without running vendor software:
4,600 rows, AAPL only, August 8, 2022, 10:00–10:04. There are **zero SPY rows**
and no candidate one-day expiration. It cannot evaluate the proposed trade.
Its `dte` field bottoms at 5; calendar expiration starts August 12. Do not
assume a vendor's DTE convention equals this protocol's calendar-day rule.

[Alpaca documentation](https://docs.alpaca.markets/us/docs/historical-option-data)
offers history from February 2024, but its free indicative quotes are derived
prices, not actual OPRA quotes. Authentication and feed eligibility remain
unverified here. Indicative prices are unsuitable as proof of historical
executable profit. [Cboe's quote product](https://datashop.cboe.com/option-quote-intervals)
is paid; end-of-day samples cannot substitute for intraday entry/exit quotes.
No sufficiently complete free historical SPY quote source was established.

## Actual SPY underlying diagnostic

One Yahoo public-chart request returned seven full regular sessions,
October 8–16, 2026. Each scored session has all 390 minute-start bars. Signal
uses the completed minute close; execution uses the strictly next minute
boundary's open. Opening range, entry cutoff and range-failure/time exits
follow the candidate. Report no-signal and incomplete/invalid sessions
explicitly. This checks conditional stock moves; it deliberately does not
invent options chains, implied volatility, fills or a compounded portfolio.

| Session | Underlying result | Raw return | Net at 5 bp per side |
|---|---|---:|---:|
| Oct 8 | Range-failure exit | −0.1154% | −0.2153% |
| Oct 9 | Time exit | +0.2252% | +0.1250% |
| Oct 12 | No signal | — | — |
| Oct 13 | No signal | — | — |
| Oct 14 | Range-failure exit | −0.1927% | −0.2925% |
| Oct 15 | Time exit | +0.5601% | +0.4595% |
| Oct 16 | No signal | — | — |

Four triggers, two positive. Mean per-trigger raw return **+0.1193%**;
at 5 bp per side **+0.0192%**. This is not an annual return, portfolio return
or statistical validation. The October 9 trigger was a Friday: it does not
imply a listed Saturday-expiring SPY contract. These are all underlying
triggers, before contract-availability filtering. No candidate option trade
can be scored from this capture. A long call spread can lose despite a
positive underlying move because of volatility, decay and bid/ask costs.

Conclusion: the rule is mechanically testable, but the available sample does
not establish a profitable edge or justify paying for data on expected-profit
grounds. Next evidence requirement is dated SPY chains and bid/ask snapshots
at actual candidate entry/exit times across substantially more sessions,
including adverse periods and a chronological untouched test interval. Keep
quote-missing outcomes unresolved, count all variants, and budget any data
purchase as research expense rather than assured profitable investment.

## Reproduction and scope

Code: `src/kq/equities/opening_range.py`; offline runner:

```powershell
uv run python scripts/run_opening_range_diagnostic.py --capture data/options-feasibility-20261018/spy-minute.json --receipt data/options-feasibility-20261018/spy-minute-receipt.json --output data/options-diagnostic-new
```

Private artifacts: `data/options-feasibility-20261018/diagnostic-reviewed/`.
Source SHA-256: `4a46bea9a449ae4f9fad164e43e69cfc404e1c4602a3b67a9e5e4ba4985651aa`;
retrieved October 18, 2026 17:20:49 UTC. Raw vendor data stays out of GitHub.
Seven focused tests cover delayed fills, missing bars, adverse stop gaps, future
perturbation, no-signal/invalid-price states timezone rejection and retention of dates with only out-of-hours bars. No live
orders, account writes, scheduler changes or production sizing adjustments.

