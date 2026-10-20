# Databento credit plan and schema findings — October 19, 2026

The owner reports **approximately $116 remaining**, expiring **around April 2027**. This is enough for planning; it is not an exact or independently verified account snapshot. Do not invent a day of expiry, refresh an old observation timestamp, or mark this estimate as verified billing evidence. Frugal free-credit research is authorized; cash charges and subscriptions are not.

## Concrete next pilot

A [registered schema probe](cbbo-schema-probe-registration-2026-10-19.json) contains nine bounded requests: SPY option definitions and opening/16:00-boundary minute-quote samples on April 2, 2013, March 16, 2020 and January 2, 2025. Dates cover two older-data samples and a modern sample; they are not independent profitability tests or representative annual histories.

Fresh free metadata estimates total **$0.226768702267**. Per-request 20% contingency, rounded upward to $0.0001, totals **$0.2726** in planned reservations, within an agent-selected **$0.50 pilot ceiling**. The ceiling implements the owner's general frugality instruction; it is not an owner-specified allowance or active enforcement mechanism. [Exact estimates](evidence/2026-10-19-credit-plan/cost-estimates.json), [arithmetic](evidence/2026-10-19-credit-plan/cost-summary.json), and [requests](cbbo-schema-probe-requests-2026-10-19.json) are preserved.

**No billable job, market-data download or new backtest was performed in this follow-up. New data charges: $0.** The previous 279 stock paths and six short options cases remain unchanged.

## Why this check comes before a larger purchase

CBBO uses interval snapshots; modern `ts_recv` marks interval end, while `ts_event` refers to the last trade. Quotes can carry forward on trade-only intervals, and inactive intervals can be absent. Therefore these records do not establish exact quote freshness or intraminute fills. CBBO-1m uses record type 193. [Official schema](https://databento.com/docs/schemas-and-data-formats/cbbo).

Earlier cost-probe bounds excluded the exact 16:00 label. The new requests use twenty-minute envelopes, including 15:50–16:10 New York time, to inspect that boundary. The API end is exclusive. Here 16:00 is the underlying regular-session reference; it is not a claim about every SPY option's trading close. Modern first-ten-minute interval labels are strictly after 09:30 and through 09:40. Older timestamp behavior requires separate inspection. [Historical API conventions](https://databento.com/docs/api-reference-historical?historical=http).

Before March 28, 2023, OPRA history is subsampled: receive timestamps are substituted, `F_BAD_TS_RECV` is always set, and best-venue identifiers are not reliable NBBO venues. The current OPRA page also clarifies that `F_PUBLISHER_SPECIFIC` adds no meaning for this dataset. This corrects our earlier unresolved description of that flag. Preserve the old strict/sensitivity outputs and record a new adapter version before applying this interpretation; do not erase old results or waive unrelated bad-book checks. [Current OPRA specifications](https://databento.com/docs/knowledge-base/datasets/opra-pillar).

## Implementation and acquisition status

The existing batch allowlist admits the legacy event-quote pilot, not these `cbbo-1m` chain samples. The current replay expects event records, an action field and five-second freshness. Feeding minute records into it would be invalid. No parser or acquisition code was changed in this planning follow-up.

Next engineering work is a separately reviewed CBBO reader and narrowly scoped operator. Retain deterministic request identities, durable reservations, vendor hash/size verification, serial acquisition and lookup-only recovery after uncertain submission. The local reservation ceiling is not a vendor-enforced charge cap. Cache every acquired file so future strategy tests reuse it.

The existing `CreditSnapshot.validate` in `src/kq/equities/_options_cache_io.py` requires a verified balance, a credit observation no older than five minutes and an exact future expiry. The approximate owner report is retained as planning evidence, not silently converted into that object. Obtain current billing evidence when the operator is ready; do not repeatedly request it while implementation is unfinished. Reconcile account usage before submission, without fabricating the missing original catalog's history.

The pilot's output will be a schema/coverage verdict. Annual options research still needs funded $1,000 cash/collateral accounting, integer contracts, daily marks, costs and lifecycle handling. These nine small requests cannot prove annual profitability.
