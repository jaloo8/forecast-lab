# Verified session-data fallback

**Goal:** unblock the approved paper books when Robinhood daily history lags its completed-session statistics and official close. The owner explicitly requested fixing the operational workflow; execution remains paper only.

**Evidence:** September 28 daily history is a zero-volume interpolated placeholder at September 29 01:14 UTC. Regular-session fundamentals contain actual OHLCV, and quotes contain a matching noninterpolated SIP exchange close. Five-minute sums differ materially from official daily volume and sometimes opening prices; do not aggregate them into daily history.

**Design:** an offline adapter creates a new, explicitly labelled derivative capture. Validate aware timestamps, latest completed weekday/date agreement, regular bounds, SIP close provenance, positive finite OHLCV, and complete mandatory-symbol coverage. Replace only missing or synthetic latest-session bars. Keep original captures and real daily history unchanged. Preserve prior accepted fallback values only while daily history is absent; report later conflicting real history as a revision. No intraday fills, fictitious bars, backdated orders, method changes, dependencies, or cap changes.

1. Add failing tests in `tests/test_equity_session_data.py`: valid supplement, missing required evidence, stale/mismatched/future timestamps, invalid OHLCV, duplicate records, unchanged real history, and prior fallback reconciliation.
2. Implement `src/kq/equities/session_data.py`: pure capture transformer plus explicit offline CLI. Run focused tests, Ruff and strict mypy.
3. Capture current public source responses for all required symbols; prepare fresh baseline/research derivatives. Independently review the adapter and use actual captures for end-to-end verification.
4. Hash-verify deployment to the isolated A8 release. Back up authoritative databases on A8, import each lane independently, inspect actual fills/positions/account starts, and mirror consistent backups and reports. Never run the writer against local mirrors.
5. Update runbook, dashboard source labels and existing automation for this reviewed fallback; push small draft PRs. Record actual outcomes and remaining limitations. Full equity regression tests and actual-data dashboard checks must pass before completion.

Validation commands use the existing Python runtime and `PYTHONPATH=src`: `python -m pytest tests/test_equity_session_data.py -q -o addopts=''`, then the equity suite, `python -m ruff check .`, and `python -m mypy src/kq`. No new dependency is required.
