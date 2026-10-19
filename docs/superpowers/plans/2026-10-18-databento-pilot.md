# Databento pilot implementation plan — 2026-10-18

Owner approved the existing three-session pilot, spending strictly less than $10
in credits and no cash, plus the previously proposed inverse-volatility comparison.
This is execution of those approved designs, not a strategy search.

1. Use current isolated worktree; preserve original dirty checkout and A8.
2. Add tested bounded CSV batch acquisition using existing httpx and OptionsCache.
   Only named pilot requests; persist reservation and uncertainty before POST;
   never retry submission. Reconcile vendor job IDs, costs and SHA256 files.
   Verify unexpired credits/account terms before spending; enforce $9.99 overall.
3. Refresh free estimates. Acquire definitions, selected six-contract quote data
   and reusable SPY bars serially; store immutable bytes outside Git. Never use
   the expensive full-chain quote request. Stop on entitlement/cost ambiguity.
4. Inspect actual schema and implement causal quote parsing/replay with failing
   tests for future/stale/crossed quotes, missing definitions and unresolved exits.
   Report all three diagnostic dates, fees, executable spread assumptions and
   exclusions. Do not annualize or call already-viewed dates a holdout.
5. Independently test fixed 12-month inverse-volatility allocation against current
   equal-weight sector variants, same decisions/execution/costs and 2006–2025
   history. No parameter tuning; all available history is exploratory.
6. Run focused checks and final suite once; update evidence/ROADMAP; review and
   publish small PRs, merge only after CI passes. No production deployment.

Files: src/kq/clients/databento_batch.py; scripts/acquire_options_pilot.py;
src/kq/equities/options_cache.py (lower run ceiling); tests/test_databento_batch.py;
options replay module/tests after observing payload; separate sector_study.py,
run_inverse_vol_study.py and test_sector_inverse_vol.py owned by one helper.
No dependencies. Missing portal sign-in is a data-access blocker only; continue
all offline work while waiting. Exact research outputs and vendor receipts remain
local with hashes; no key or market-data payload in Git.
