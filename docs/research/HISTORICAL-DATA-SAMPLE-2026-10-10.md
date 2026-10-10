# Sharadar public-sample validation — 2026-10-10

**Verdict: partially observed; full historical-study suitability NOT validated.** Public access confirms financial/date fields, security metadata including delisted rows, and AAPL dividends. Delisted-company financial/action histories and reconciliation to original filings remain unverified.

## Public-access basis

- Followed the official [homepage](https://sharadar.com/) Sample link to [the sample page](https://sharadar.com/sample). The homepage expressly offers no-signup AAPL requests with `test-api-key`; this is a documented public demo credential, not an invented key.
- The sample advertises the 30 Dow companies and five years. Broader table descriptions on that page are not proof that the free financial/action sample includes all delisted companies.
- No account, subscription, purchase, private credential, or contact was used. Requests stopped on the first entitlement denial; no workaround attempted.

## Observed responses

| Request URL (exact) | HTTP | Observed evidence |
| --- | --- | --- |
| `https://api.sharadar.com/v1.0/data/fundamentals?api_key=test-api-key&from=2021-10-08&ticker=AAPL&limit=1500&format=csv` | 200 | CSV with ARQ rows; example `date=2026-07-31`, `reportperiod=2026-06-27`, `calendardate=2026-06-30`, `lastupdated=2026-07-31`. |
| `https://api.sharadar.com/v1.0/data/tickers?api_key=test-api-key&format=csv&ticker=AAPL` | 200 | Three table-specific rows; `permaticker=199059`, `isdelisted=N`, FIGI/CUSIP, SEC URL containing CIK 0000320193, first/last price dates. |
| `https://api.sharadar.com/v1.0/data/actions?api_key=test-api-key&format=csv&ticker=AAPL&from=2021-10-08` | 200 | 20 dividend rows; latest `2026-08-10,dividend,AAPL,APPLE INC,0.27,N/A,N/A`. No split, merger, or delisting validated by these rows. |
| `https://api.sharadar.com/v1.0/data/tickers?api_key=test-api-key&format=csv&table=stocks&limit=100000` | 200 | 21,007 metadata rows: 14,686 `isdelisted=Y`, 6,321 `N`. Observed examples: ILLR/110814, MAMK/644776, NVNIF/640536 (ticker/permaticker). |
| `https://api.sharadar.com/v1.0/data/actions?api_key=test-api-key&format=csv&ticker=TWTR&from=2021-10-08` | 403 | `{"error":"Exceeds free tier","description":"Please sign up at /subscribe."}`. Stopped here; no TWTR fundamentals request executed. |

These are live-response observations, not independently audited company facts. Raw downloads were not retained; exact URLs above permit reproduction subject to changing data/access.

## Documented meaning versus validation

- [Fundamentals documentation](https://sharadar.com/docs/fundamentals): AR dimensions exclude restatements and index to Form 10 filing dates; MR dimensions incorporate restatements and index to reporting periods. Earlier Form 8 disclosures can precede Form 10 dates. Observed columns support testing this distinction, but no original SEC filing was reconciled here; day-level dates also do not establish intraday availability.
- [Ticker documentation](https://sharadar.com/docs/tickers): `permaticker` is a unique, unchanging **security/share-class** identifier; it is not an issuer identifier. Metadata exposes `isdelisted`, `firstpricedate`, `lastpricedate`, `relatedtickers`, FIGI, CUSIPs and SEC links. Metadata delisting flags do not prove complete historical price or fundamental coverage, and last price date alone is not a delisting reason/date.
- [Action documentation](https://sharadar.com/docs/actions): the full dataset describes listing/delisting dates, delist reasons, ticker changes, splits, spinoffs and acquisition counterparties through `date`, `action`, `value`, `contraticker`, and related name fields. Only AAPL dividends were observed; TWTR action access was denied.

## Concrete missing access and acceptance test

Obtain an authorized evaluation/export entitlement for selected delisted-company financials, prices and corporate actions, including the TWTR case denied above; exact minimum paid tier was not established. Then reconcile AR dates/values to original filings and verify ticker changes, split adjustments, merger proceeds and terminal/delisting handling across stable security IDs. Until those checks pass, do not claim survivorship-safe backtesting, original-filing accuracy, or full study coverage from this sample.
