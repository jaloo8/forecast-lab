# Stock lab data-capability audit — 2026-09-29

The captured connector responses support financial-history inspection, filing-specific facts and prospective option-quote collection. They do **not yet provide a complete point-in-time fundamentals, historical news or executable historical options dataset**. The immediate build path is an immutable observation archive with availability timestamps and explicit coverage; the existing price comparison remains separately labelled exploratory research.

This audit applies the research skill to first-party connector responses and the tool metadata exposed in this session. It reads existing public-data captures only: no account tools, network requests, purchases, dependencies or source-code changes. It extends the [September 28 institutional and options review](INSTITUTIONAL-STOCK-NEWS-OPTIONS-2026-09-28.md) with measured coverage, rather than treating documented connector capabilities as verified dataset completeness.

## Raw evidence and reproducibility

All timestamps below are actual capture/retrieval times in UTC, **not historical public-availability timestamps**. SHA-256 values were recomputed from the raw file bytes during this audit. The ignored local captures must accompany any transferred research artifact; these links are not a claim that the data are committed to Git.

| Raw capture | Retrieval/capture time | SHA-256 |
|---|---|---|
| [Quarterly financials](../../data/equities/strategy-lab-capabilities-20260929/financials.json) | 2026-09-29T07:45:24.228Z | `e706949fde249f85e5285f5a75b0d32afc6de7a5481ac851daa0fcdddd11a76c` |
| [COST filing index](../../data/equities/strategy-lab-capabilities-20260929/filings.json) | 2026-09-29T07:45:24.331Z | `b9b01461a7dc0b9348e826feeecd6f21d863010e2fb40f80c9945b6512067e5d` |
| [COST filing facts](../../data/equities/strategy-lab-capabilities-20260929/filing-facts.json) | 2026-09-29T07:46:41.483Z | `3365adfbe8c3656b98253643dd21fc4d570f8310eaa2136843cf35ab3ad3ca69` |
| [Earlier options capability probe](../../data/equities/options-capability-2026-09-28.json) | 2026-09-28 04:20:39 UTC | `f367c4eff4af442aae02bf56d3ec0ce01032e50a5dd85c2fa163406a3db801b4` |

The three new files preserve request parameters, the raw connector response and `retrieved_at`. Findings below use `response.structuredContent.data`; the duplicated presentation text is not counted as extra observations. The options probe uses its separately recorded `captured_at` and quote-level `updated_at` values.

## Coverage and missing prerequisites

| Capability | Available in this sample | Missing or unverified | Prerequisite for a strategy experiment |
|---|---|---|---|
| Quarterly financial summaries | AAPL and COST each returned all eight requested fiscal periods; revenue, gross profit, net income and net margin. | SNX and BB returned positional nulls. No filing identifier, acceptance timestamp, first-public timestamp or revision history on the summary rows. Eight requested periods do not establish maximum available history. | Keep null symbols in coverage counts. Join verified filing vintages and conservative availability times before historical use; prospective features can use actual first capture. |
| Filing index | Six COST 10-K/10-Q entries dated March 12, 2025–June 3, 2026, with connector filing IDs and form types. | Only filing dates, with no precise acceptance/first-public timestamp, accession/source URL or complete amendment chain in this response. Other symbols and forms were not sampled. | Preserve exact filing content and identity; resolve timing and amendment lineage. Do not trade at the opening of a filing date from a date-only index. |
| Filing-specific financial facts | 86 rows covering all four requested concepts, with filing ID, entity, period, units, precision and dimensions. | One filing only. Comparative periods within it are not the original earlier filing vintages. Historical cross-universe coverage and consistent concept mappings remain untested. | Select entity, exact instant/duration, consolidated dimension and units explicitly; retain historical filing versions and reconcile synonyms without double counting. |
| Filing text/disclosures | Exposed read-only tools can retrieve a filing table of contents or section and a facts concept catalogue. | These text/catalogue paths were not exercised by this capture; publication timing and revision completeness remain unverified. | Archive a bounded set of exact documents/sections with immutable content hashes and first-seen times, before forming event features. |
| Historical news | No dedicated historical-news feed tool was identified in the exposed Robinhood connector inventory. | No timestamped, revision-aware news archive with entity coverage was captured. A date shown in a search result would not establish an immutable decision-time headline. | Establish an allowed source and freeze first-observed content, publication/retrieval timestamps, entity match and revision lineage. Keep missing coverage explicit. |
| Option contract discovery and current quotes | Exposed chain/instrument/quote tools; the earlier sample includes contract IDs, expiry/strike/type/multiplier examples and two timestamped bid/ask quotes with sizes, IV, Greeks, volume and open interest. | Captured quotes were already stale at weekend retrieval. Historical chain membership, full coverage, adjusted deliverables and ongoing quote freshness are unverified. | Prospectively record complete selected chains, underlying quotes, contract terms and fresh two-sided quotes before each decision and outcome; reject stale/crossed/zero-sided quotes. |
| Option historical prices | Real option OHLC bars for one active and one expired AAPL call, with contract IDs and regular-session markers. | No historical bid/ask, sizes, volume, IV or Greeks in those bars; no complete expiry/exercise/assignment ledger. Sparse bars do not reconstruct an executable chain. | Obtain historical quote observations with contract lifecycle coverage, or begin a frozen prospective quote study. Historical OHLC can support descriptive price research, with explicitly hypothetical assumptions. |
| Execution/capital feasibility | The sampled near-strike AAPL call has a recorded 100 multiplier and $7.95 ask: $795 for one contract before fees at that quote time. | This sample is unaffordable for a $100 account; it does not prove all contracts are unaffordable. Fill quality and affordable-chain coverage are not established. | Test whole-contract affordability and liquidity over a predeclared universe, including no-trade cases, fees and complete outcomes under a separate options protocol. |

Sources for measured rows are the four raw captures above. Capability-only rows refer to the locally exposed descriptions/schemas of `get_financials`, `get_sec_filing_index`, `get_sec_filing`, `get_sec_filing_facts`, `get_sec_filing_facts_catalog`, `get_option_chains`, `get_option_instruments`, `get_option_quotes` and `get_option_historicals`. Those descriptions establish interfaces, not successful coverage beyond the sampled responses. Absence of a news tool here is not a claim that no news source exists elsewhere.

## Financial summaries: four requested symbols, two populated

The request was `symbols=[AAPL,SNX,BB,COST]`, `period=quarterly`, `limit=8`. Results are positional: AAPL, null, null, COST. Thus **2/4 requested symbols have data in this particular sample**. Null means unresolved or unavailable financials according to the connector guide; this audit cannot distinguish those causes and does not infer that SNX or BB has no underlying financial reports.

| Symbol | Rows | Fiscal period-end coverage in returned rows |
|---|---:|---|
| AAPL | 8 | September 28, 2024–June 27, 2026 |
| SNX | 0 | Null response; unavailable |
| BB | 0 | Null response; unavailable |
| COST | 8 | September 1, 2024–May 10, 2026 |

The four financial metrics are present for all 16 returned periods. `net_margin` is already a percentage in this interface; multiplying it by 100 again would be wrong. Fiscal quarter and fiscal year identify the reporting period. They do not establish when those numbers were public, whether they were later restated, or whether this snapshot reproduces the earlier public vintage. The financial-summary rows also do not provide an explicit currency/unit field. Preserve their raw representation and resolve units from authoritative filing context before comparing values across issuers. [Evidence: financials capture](../../data/equities/strategy-lab-capabilities-20260929/financials.json).

## Filing facts: preserve period, dimensions and reported precision

The COST index request used `form_type=[10-K,10-Q]` and `since=2025-01-01`. It returned five 10-Qs and one 10-K. The selected 10-Q is connector filing ID `a27c092f-603a-4f37-8563-bc1edce7d630`, dated **June 3, 2026**. Its facts include the quarter ending **May 10, 2026**. That gap is a concrete example of why period end cannot be used as the feature's public availability time. A date-only filing record also cannot establish an intraday timestamp. [Evidence: index](../../data/equities/strategy-lab-capabilities-20260929/filings.json), [facts](../../data/equities/strategy-lab-capabilities-20260929/filing-facts.json).

| Requested concept | Returned rows |
|---|---:|
| `RevenueFromContractWithCustomerExcludingAssessedTax` | 40 |
| `NetIncomeLoss` | 8 |
| `Assets` | 8 |
| `StockholdersEquity` | 30 |
| **Total** | **86** |

Every row has numeric `value`, unit `iso4217:USD` and `decimals=-6`; 70 rows have dimensions in the source's `axises` field and 16 are undimensioned totals. The tool schema defines `decimals=-6` as reported rounding to the nearest million, **not an instruction to multiply the already expressed numeric value by one million**. Retain units and precision per row; their uniformity in this filing is not a general provider guarantee.

For the February 16–May 10, 2026 quarter, undimensioned revenue is $70.527 billion. The same concept has product revenue of $69.154 billion and membership revenue of $1.373 billion. Summing the total and both components would double count revenue. The filing also has year-to-date and comparative durations, plus balance-sheet instant dates. The earliest returned fact end date is September 1, 2024, but that row was retrieved from the June 2026 filing, not captured in September 2024. Select the exact period and scope before any growth or quality calculation. [Evidence: facts capture](../../data/equities/strategy-lab-capabilities-20260929/filing-facts.json).

A prospective feature can conservatively become usable no earlier than actual first retrieval and the next eligible decision. Historical filing-vintage work must separately establish the document and availability policy for each earlier decision; merely joining a modern fact row onto its historical period end would introduce look-ahead bias. Any date-only availability convention remains a disclosed assumption, not recovered precision.

## Options: useful data exists, historical execution evidence is incomplete

The earlier capture contains **18** daily bars from September 1–25, 2026 for AAPL October 16 C250, and **13** daily bars from September 1–18 for the expired September 18 C340. Both sets have only `begins_at`, OHLC and `session`. The source's exposed historical tool also warns that interpolated bars carry no new information and that option bars carry no volume. An end-of-bar close is not a historical ask at entry or bid at liquidation. [Evidence: options probe](../../data/equities/options-capability-2026-09-28.json).

The two separate quote snapshots **do contain IV, Greeks, volume and open interest**, as well as bid/ask and sizes. Their refresh timestamps are September 25, 2026 at approximately 19:59:59 UTC, while capture occurred September 28. This clarifies the prior review's limitation: historical bar IV/volume is absent; the captured latest-quote fields are not absent. Neither a current IV nor one stale bid/ask pair can be backfilled across all earlier OHLC bars.

The near-strike October 16 C340 quote was bid $7.65 / ask $7.95, with multiplier 100 in its instrument record. One contract at that observed ask is $795 before fees. The expired C340's historical close reaching $0.01 is a price observation, not a complete realized expiry or exercise outcome. Research must retain unavailable/no-affordable-contract decisions, actual deliverables, expiration terms and the chosen treatment of exercise, assignment and corporate actions. Fractional option contracts are not a valid workaround for an eventual $100 whole-contract protocol.

Options research is feasible in stages: use these bars to inspect coverage and descriptive behavior; collect prospective executable quote evidence under frozen rules; or obtain an adequate historical quote dataset separately. This audit does not authorize a purchase and does not equate OHLC-only returns with a realistic bid/ask backtest.

## Concrete next build boundaries

1. Add an immutable prospective financial/filing observation table with actual `retrieved_at`, source hash, filing identity, entity, period, dimensions, units and conservative `available_at`. Keep null symbols and missing concepts visible. Do not insert these observations into past historical decisions.
2. Audit filing timing, source-document identity, amendments and concept coverage before adding value, quality or earnings-event historical variants. Four requested symbols and one filing are a capability sample, not broad-market coverage proof.
3. Establish a first-seen news archive before testing a news event feature. The current price registry remains statistical; no generated sentiment score becomes a probability.
4. Use a separate frozen options research manifest with timestamped contract/quote snapshots, whole-contract affordability and explicit missing outcomes. A realistic historical execution study waits for adequate historical bid/ask and lifecycle data; prospective collection does not need to wait for that historical archive.

These are data contracts and delivery boundaries for the approved research scope. They do not change the nine running paper methods, create an options account, alter capital limits or substitute this small probe for strategy evidence.
