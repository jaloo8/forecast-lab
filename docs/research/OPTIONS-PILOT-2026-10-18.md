# Databento pilot — October 18, 2026 (Pacific)

Owner approved the seven-request sample below $10 in historical credits, with zero cash spend. This implements the existing [one-day-expiry candidate](OPTIONS-CANDIDATE-2026-10-18.md), not the reel creator's undisclosed bots. No rule was tuned after viewing option returns. Three dates were selected from previously viewed underlying triggers; they are diagnostic, not a holdout or a multi-year options test.

## Conditional one-spread results

| Session | Call strikes | Entry debit incl. costs | Exit cash incl. costs | Net |
| --- | --- | ---: | ---: | ---: |
| October 8 | 775 / 776 | $61.30 | $44.70 | −$16.60 |
| October 14 | 776 / 777 | $52.30 | $33.70 | −$18.60 |
| October 15 | 768 / 769 | $56.30 | $74.70 | +$18.40 |
| Total | Three closed, no unresolved exits | $169.90 | $153.10 | **−$16.80** |

Buy long ask/sell short bid on entry; reverse at bid/ask on exit. The unchanged kernel adds $0.01 adverse slippage per leg per side and $0.65 commission per contract per side. Three spreads therefore incur $7.80 explicit commissions and $12 assumed slippage, in addition to quoted spreads. Bid/ask cash before those extra costs totals only +$3.00. A $10,000 research account would end at $9,983.20 under these conditional fills; do not annualize. No real or broker-paper orders were sent.

Extra slippage of one cent per leg per side would reduce the total by another $12 to −$28.80, if the same entries remain eligible. If entries never fill, there are no positions and no trading gain; if an entered position cannot exit, its debit remains unresolved rather than disappearing from the sample. Separate-leg displayed quotes do not prove an atomic spread could fill, especially when displayed size is only one contract.

## Causal and contract checks

The original Yahoo minute capture (SHA256 `4a46bea9a449ae4f9fad164e43e69cfc404e1c4602a3b67a9e5e4ba4985651aa`) drives the unchanged signal and exit times. At each signal, only same-New-York-day definitions already received are eligible. Nearest signal-close strike wins, ties lower; the exact $1 higher short must exist. OCC root, expiry, strike, multiplier and subsequent quote instrument IDs must agree. All three selected pairs reproduced the original proposed contracts.

Vendor definitions report multiplier `2147483647` (undefined), not a huge contract. The runner explicitly supplies the standard-SPY 100-share mapping supported by [Cboe's comparison](https://www.cboe.com/tradable_products/product_comparison/); nonstandard/mini roots and explicit non-100 multipliers are excluded. Encoded midnight-UTC expiry is a calendar date, not a New York instant to shift backward.

Quotes use the latest A/M/C/R book update received no later than execution. Future event times, bad flags, clears, crossed/empty books, age over five seconds and inter-leg timestamp gaps over one second refuse the fill. A bad newest row cannot fall back to an older favorable quote; trades do not refresh book age. Nanosecond comparisons are retained. See [Databento CMBP fields](https://databento.com/docs/schemas-and-data-formats/mbp-1) and [timestamp/flag definitions](https://databento.com/docs/standards-and-conventions/common-fields-enums-types).

## Acquisition and reproducibility

Raw CSV bytes, vendor SHA256/size manifests, job IDs, exact requests, free estimates and actual costs are retained under `C:\Users\jloo1\Documents\MarketData\databento`. The reusable cache is outside Git and worktrees. Batch submissions are serial and persisted before the network request; an uncertain response blocks new submissions. Reservations count against a $9.99 cumulative ceiling. The account's usage-based service itself has no spending limit, so local controls and fresh portal reconciliation are essential; this is not a vendor-enforced per-job guarantee.

The billing page confirmed historical credits, no subscriptions and $0 due before acquisition. The credit row expires April 18, 2027; the header showed a later May 1 date, so the earlier date was used conservatively. [Databento billing guidance](https://databento.com/docs/faqs/usage-pricing-and-data-credits) says historical credits apply before cash and batch jobs are billed once. Replays use local verified bytes without a network fallback. Paid quote payloads are not committed or redistributed.

All seven jobs completed: **$0.41967466473580 credits**, 5,968,870 vendor-reported records (39,496 definitions, 5,468,765 quote events and 460,609 minute bars). Portal reconciliation displayed $124.59 credits and $0 due; subtracting exact job costs from $125 gives $124.58032533526420, so treat the displayed cent as rounded rather than an exact ledger. No subscription was added. All payload hashes passed in the original cache, backup and restored cache.

The extended EQUS.MINI diagnostic spans 893 supplied dates, March 28, 2023–October 16, 2026: 566 triggers, 318 no-signal days and nine incomplete/short sessions excluded. Conditional share returns average +0.03081% before costs, **−0.06917% after 5 bp per side**, with 245/566 positive raw outcomes. These are mean trade returns, not CAGR, portfolio returns or option returns. All seven overlapping dates reproduce Yahoo's signal/no-signal states and signal/entry/exit times. This does not prove full-SIP equivalence or complete historical calendar coverage; the nine exclusions remain in the output.

Local evidence: `runs/20261018-replay/{options-results.csv,quote-evidence.json,underlying-extended.csv,underlying-overlap.csv,summary.json}` and `runs/20261018-final-acquisition.json` under the cache root. Raw quotes and manifests remain private. Backup and restore directories are siblings `databento-backup-20261018-pilot` and `databento-restore-check-20261018-pilot`. Reproduce with `uv run python -m scripts.run_options_pilot` supplying `--plan`, `--root`, a fresh `--output`, the original `--yahoo` capture and `--yahoo-receipt`; no key or network is required.

Verification: 38 adapter/kernel tests and seven runner tests cover causal quotes, contract selection, cash arithmetic and missing evidence. Read-only review found and regression-tested wrong-job delivery, missing unlimited-record evidence, date-boundary selection, nonstandard eligibility and all-unresolved summary defects. A restored-cache replay with network connections blocked reproduced all five result/evidence files byte-for-byte and created zero API jobs. Repository gate results are recorded in the final PR validation. A8 and the production trading configuration are unchanged. **Neither this pilot nor inverse-volatility weighting establishes a new profitable strategy.**
