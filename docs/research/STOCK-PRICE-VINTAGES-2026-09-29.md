# September 28 stock price-source review

The September 29 morning refresh refused seven baseline and 56 research-bar revisions. That refusal protected existing paper records. The owner's requested repair is a finite, explicit source-vintage review, not a tolerance for future revisions or evidence that either source reproduces a brokerage fill.

## Evidence

Preserved MCP responses under ignored `data/equities/scheduled-20260929T130037Z/` reproduce all 60 earlier session-statistics observations and all 60 official-close observations unchanged. Their archived evidence and raw-file hashes verify. The daily endpoint now supplies different September 28 values. Its documented `close_price` is the last trade in the bar, not the official settled close supplied by the quote endpoint. The provider metadata does not explain the opening-price differences; no auction or consolidation explanation is assumed.

Of 56 research differences, 49 involve earlier supplements assembled from regular session statistics and official SIP closes. Seven ordinary daily bars have later volume increases only: AMST, EONR, LGCY, LITS, PTN, SCHL and SNX. UXIN's supplemented bar is unchanged. Three closes differ: ADXN 2.95 versus 2.81, CGTL 4.02 versus 4.03, and RBNE 2.38 versus 2.3581. All baseline closes agree, but their opening prices and volumes differ. These are material source differences, not rounding noise.

## Repair boundary

Each existing lane receives an immutable review binding its original accepted capture, the full normalized old/new bars, original supplement evidence, actual review time and rationale. The compatibility view preserves the exact earlier observations used by the existing books. Both primary and legacy inputs remain archived. A missing bar, unrelated date, tampered evidence or previously unseen revision still fails.

This one-time policy is limited to September 28. Later completed sessions and new scanner research use primary regular split-adjusted daily bars without new statistics/quote supplements. Primary bar closes must not be described as official settled closes. Missing genuine daily publication remains a collection delay; no intraday aggregation or current-session bar is permitted.

Existing fills, orders, journals, failed attempts, rules and costs remain unchanged. Same-session validation does not generate another decision or make pending orders fill early. Subsequent compatibility captures must retain the original review binding and original source timestamps. A manual repair does not rewrite a failed scheduler audit or establish profitability.
