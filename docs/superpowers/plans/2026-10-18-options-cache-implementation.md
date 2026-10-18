# Options cache and metadata-only estimates implementation plan

Owner approved implementation on October 18, 2026, with **no credit-consuming
requests**. Execute the approved cache design using test-driven development;
one bounded cache worker while the parent handles free metadata estimates.

## Boundaries

- Python 3.12, existing httpx, standard-library SQLite/hashlib; no dependencies.
- Isolated existing checkout; feature branches only; credentials never in Git,
  logs, CLI arguments or output. Raw data stays outside the repository.
- No batch submission/download or time-series endpoint may be called this turn.
- Cash budget zero. Report $125 as owner-confirmed, not API-verified balance.
- Full strategy, production jobs, fee assumptions and A8 accounts unchanged.

## Tasks and files

1. Offline cache: `src/kq/equities/options_cache.py` and
   `tests/test_options_cache.py`. Write failing tests first for canonical
   requests, interval reuse, integrity failure, durable reservations, unknown
   submission state, atomic import/recovery and offline backup/restore.
   Implement SQLite transactions, immutable files, hashes, and local coverage
   queries. No HTTP dependency or automatic fetching in this module.
2. Metadata client: `src/kq/clients/databento_metadata.py` and
   `tests/test_databento_metadata.py`. Allow only named free GET endpoints at
   `https://hist.databento.com/v0/`; refuse billable methods before transport.
   Use Basic auth headers, disabled redirects, bounded timeouts and sanitized
   exceptions. Test the exact allowlist and absence of key leaks with
   `httpx.MockTransport`. Require explicit symbols/start/end for estimates;
   reject ALL_SYMBOLS and unbounded requests. Preserve estimate request hashes.
3. Read-only estimation command: `scripts/estimate_options_data.py` writes a
   timestamped JSON receipt under the durable cache, checks access, and records
   actual metadata.get_cost responses. First inspect discovered datasets,
   schema dates and symbology; never guess entitlement from public marketing.
   Distinguish quotes for the entire SPY parent from selected-contract samples.
   Report underlying-feed limitations and unpriced inputs rather than inventing
   a final package price. No results are historical trading outcomes.
4. Run focused tests with network blocked, lint/format/mypy, then the appropriate
   full regression gates. Review the diff and credential boundaries. Publish
   source/estimate findings and ROADMAP update through PRs, retaining raw local
   receipts. Do not upload account identifiers, keys or vendor payloads.

## Verification commands

```
uv run pytest tests/test_options_cache.py tests/test_databento_metadata.py -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src/kq
uv run pytest -m "not integration" --cov=src/kq --cov-report=term
```

Record actual outputs in the PR. No claim of successful acquisition, license
validation, server backup or extended backtest follows from synthetic tests.
