# SPY options extension: completed, negative after costs

Study dated October 18, 2026 Pacific; validation completed October 19 UTC.
Frozen replay implementation: `08821bf27afed7eb8bf4072c47eb62eaa51ec451`.
[Protocol and acquisition history](OPTIONS-EXTENSION-2026-10-18.md).

**This candidate did not demonstrate a tradable edge.** Strict-quality results:
172 closed one-spread trades, **−$1,675.20** after costs.
The broader publisher-flag sensitivity closes 370 trades for
**−$3,484.00**. No parameters were tuned after viewing these results.
Neither result is real-money account P&L or an annualized portfolio return.

## Scope and data quality

March 28, 2023–October 16, 2026: 893 supplied sessions, 444 new weekday
candidates, 434 dated contract selections and ten no-eligible-chain refusals.
All 245 new definition intervals and 833 unique quote windows completed.
The 318 no-signal sessions, 119 weekend-expiry signals, nine incomplete/short
sessions and three original pilot dates remain visible. The pilot's −$16.80
is separate, not mixed into either extended result.

Strict policy refuses publisher-specific flag bit 2. The conditional sensitivity
allows it only for OPRA publisher 30, CMBP-1 rtype 177. Both continue to reject
bad-book/timestamp flags, stale/unsynchronized/invalid quotes and wrong contracts.
Its historical meaning remains unresolved: [vendor flag definitions](https://databento.com/docs/standards-and-conventions/common-fields-enums-types)
and [OPRA example containing flag 194](https://databento.com/catalog/opra/OPRA.PILLAR/options/META)
establish the field and its presence, not that accepting it is safe.
**The conditional report is not an unqualified validated execution history.**
Strict coverage is heavily concentrated in 2025–2026; no strict trade closes
in 2023 and only one in 2024. This is a material coverage limit.

## Results by year

Every net figure below includes observed bid/ask crossing, $0.65 commission per
contract per side and one cent adverse slippage per leg per side. Fixed assumed
commission plus slippage totals $6.60 per completed spread, before bid/ask costs.
Displayed quotes and sizes do not guarantee an atomic spread fill. Unresolved
exits do not simulate exercise, assignment or a substitute settlement exit.

| Condition | Strict closed | Strict net | Conditional closed | Conditional net |
| --- | ---: | ---: | ---: | ---: |
| 2023, from Mar 28 | 0 | Unscored | 63 | −$452.80 |
| 2024 | 1 | −$8.60 | 94 | −$1,015.40 |
| 2025 | 75 | −$731.00 | 117 | −$1,080.20 |
| 2026, through Oct 16 | 96 | −$935.60 | 96 | −$935.60 |

Strict closed win rate: 31.4%; mean −$9.74;
closed-trade maximum drawdown $1,704.00.
Conditional closed win rate: 30.5%; mean −$9.42;
closed-trade maximum drawdown $3,510.80.
These drawdowns exclude unknown open-position values and are not portfolio NAV drawdowns.

## Different market conditions

Labels were frozen before extended option outcomes. Volatility is prior
20-session close-return sample volatility, annualized by sqrt(252).
Trend compares the previous close with its trailing 60-session mean.
Current/future closes do not enter either label; warmup remains explicit.

| Condition | Strict closed | Strict net | Conditional closed | Conditional net |
| --- | ---: | ---: | ---: | ---: |
| Volatility below 15% | 138 | −$1,354.80 | 303 | −$2,823.80 |
| Volatility 15%–25% | 31 | −$269.60 | 51 | −$451.60 |
| Volatility at least 25% | 3 | −$50.80 | 7 | −$100.20 |
| Volatility warmup | 0 | Unscored | 9 | −$108.40 |

| Condition | Strict closed | Strict net | Conditional closed | Conditional net |
| --- | ---: | ---: | ---: | ---: |
| Above trailing 60-session mean | 135 | −$1,220.00 | 293 | −$2,705.80 |
| Below trailing 60-session mean | 37 | −$455.20 | 57 | −$687.20 |
| Trend warmup | 0 | Unscored | 20 | −$91.00 |

High-volatility samples are too small to establish crisis robustness. The range
does not contain 2008, 2020 or 2022. Raw underlying prices are not total-return
or historical publication-vintage data. This is a fixed-rule retrospective test,
not a pristine holdout: pilot and underlying outcomes were already viewed.

## Missing exits, costs and uncertainty

Strict: 8 unresolved exits, $475.40 entry debits retained;
254 entry refusals.
Conditional: 39 unresolved exits, $2,230.70 debits retained;
25 entry refusals.
Those exits are **unknown outcomes**, not zero-profit trades or assumed settlement
values. Refusals and unresolved results may be non-random, so resolved-trade
statistics do not measure all opportunities' profitability.

| Additional adverse cost per leg per side | Strict closed net | Conditional closed net |
| --- | ---: | ---: |
| None beyond baseline | −$1,675.20 | −$3,484.00 |
| 1 cent; +$4 per round trip | −$2,363.20 | −$4,964.00 |
| 2 cents; +$8 per round trip | −$3,051.20 | −$6,444.00 |

Each cost case reapplies the $100 entry-plus-exit-reserve funding rule. Independent
cash checks found no unfunded trade with a separate $10,000 starting balance,
all unresolved debits retained and $1.30 exit fees reserved for each. This checks
fundability only; cash excluding unresolved claims is not NAV or a CAGR.

Exploratory 95% five-session block intervals for mean resolved-trade net:
strict −$12.10 to −$7.31;
conditional −$10.93 to −$7.80.
Fixed seed, 2,000 resamples of census-session blocks. These intervals do not fix
missing outcomes, publisher ambiguity, exploratory comparisons or selection bias.

## Spending, preservation and verification

- Extension conservative reservation total: **$9.6680**, below the approved
  additional **$10 historical-credit cap**. No subscription or older-data purchase.
- Completed extension metadata estimates: **$8.46164386869721**; retained allowance
  for the one abandoned attempt: **$0.0305**; combined estimate plus allowance
  **$8.49214386869721**. These are not claimed as exact vendor-invoiced charges.
- Post-download billing page: **$0 cash due**. The abandoned attempt is not assumed
  refunded. Cache accounting deliberately retains conservative stream reservations.
- Final catalog: 1,085 complete jobs including seven pilot jobs, one documented
  abandoned attempt, no outstanding/uncertain acquisitions. Stream receipts verify
  85,036,560 records against independent counts; stream hashes are local integrity
  hashes, not vendor-signed hashes. Batch deliveries retain vendor hashes.
- Frozen implementation/input hashes matched. Independent Decimal arithmetic
  checked every closed trade; sampled first/last and largest gain/loss per year
  were traced back to raw quotes. All 893 census dates and grouped totals reconcile.
- Cache backup and restoration verified. With socket connections and DNS disabled,
  both policies replayed from the restored cache: **all ten report/observation/
  cost-case files matched byte-for-byte**. No credits are needed to repeat these tests.
- Raw licensed quotes and credentials are not committed to Git. Aggregate results
  only; no A8 configuration, weather trading or real-money execution change.

Local evidence is under `Documents/MarketData/databento/runs/`:
`20261018-extension-results`, `20261018-extension-results-publisher-sensitivity`,
`20261018-extension-acquisition-audit.json`, `20261018-extension-final-billing.json`,
`20261018-extension-replay-source.json`, and
`20261018-extension-restore-verification.json`. Each result directory includes
independent cash-flow, cost-stress and raw-quote audits. Preserved audit scripts
are in `extension-audit-scripts/`.

Backup: `Documents/MarketData/databento-backup-20261018-extension`.
Restore check: `Documents/MarketData/databento-restore-check-20261018-extension`.
These are local copies on the same drive, not protection against drive loss.

## Decision

**Do not buy older data for this candidate on the strength of these results.**
The tested closed-trade samples are negative across measured regimes under
both policies. Resolve the publisher flag with the vendor and improve exit
coverage before considering a new, separately frozen hypothesis. Replaying the
same cached contracts and quote windows requires no new credits. Different strikes
or execution times may need separately estimated data. This rejects promotion of
this candidate, not every possible options strategy, and does not justify tuning a
winner on the same outcomes and calling it out-of-sample evidence.
