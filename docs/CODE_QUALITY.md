# Code Quality — honest audit

Snapshot of the actual state of the codebase as of PR G. Refreshed periodically; not a static doc. Each finding has either a fix in this PR, a backlog ticket, or an explicit "deferred / acceptable" annotation.

## Why we don't chase 100% coverage

Coverage gate is **80%** in CI; we're currently at **87%**. We do NOT aim for 100% because:

1. **Stub modules at 0% are intentional.** `clients/nba.py`, `models/nba_elo.py`, `features/nba.py`, `execution/paper.py` all `raise NotImplementedError` — they're Phase 3+ deliverables. Forcing tests on stubs is testing nothing and ages poorly.
2. **Streamlit dashboard is hard to unit-test productively.** Industry pattern is integration tests via Selenium/Playwright; that's CI infrastructure overhead far exceeding the benefit at our stage.
3. **Re-export modules** like `models/weather_ensemble.py` are coverage-meaningless.
4. **The marginal path from 87% to 100% is mostly testing trivial passthroughs**, mock-heavy tests that don't catch real bugs, and `if __name__ == "__main__"` blocks that aren't worth touching.
5. **Mutation testing > coverage padding** for catching real bugs. A test that asserts `x == x` is green and useless. `mutmut` would tell us which assertions actually matter.

**Industry benchmark for production code:** 80–90% line coverage on real (non-stub) code, with high-quality assertions. Coverage % is a *necessary but not sufficient* proxy for correctness.

**Active backlog targets (in priority order):**
- Add `mutmut` mutation testing — kills tests that pass without catching bugs
- Extend Hypothesis property tests beyond fees + Kelly to parsers + NGR fits + CV splits
- Add real-API smoke tests in a weekly CI workflow (separate from PR CI to avoid flakiness from upstream rate limits)

## What's measured today

| Tool | Result | Threshold |
|---|---|---|
| `pytest` | 154 / 154 passing | 100% (already enforced) |
| `pytest-cov` overall | **82%** line, 81% branch | ≥ 80% (now enforced in CI) |
| `ruff check` | clean | clean (enforced) |
| `ruff format --check` | clean | clean (enforced) |
| `mypy --strict` | clean (51 source files) | clean (enforced) |
| `bandit -r src/kq` | 4 findings, all explained below | enforce in CI weekly |
| `pip-audit` | 0 known vulnerabilities | enforce in CI weekly |

## Coverage by module — where the gaps actually are

The 82% overall hides two distinct categories of "uncovered code":

### Category 1 — intentional stubs (low coverage is correct)

| Module | Cov | Why |
|---|---|---|
| `src/kq/clients/nba.py` | 0% | Phase 3 stub |
| `src/kq/models/nba_elo.py` | 0% | Phase 3 stub |
| `src/kq/features/nba.py` | 0% | Phase 3 stub |
| `src/kq/execution/paper.py` | 0% | Phase 2-next stub |
| `src/kq/dashboard/streamlit_app.py` | 0% | Phase 4 stub; Streamlit is hard to unit-test anyway |
| `src/kq/models/weather_ensemble.py` | 0% | Re-export module — coverage is misleading |

These should NOT be tested before they have real implementations. Expect coverage to climb as each phase fills these in.

### Category 2 — flow orchestration (real gap)

| Module | Cov | What's untested |
|---|---|---|
| `flows/ingest_kalshi.py` | 26% | The `for station in STATIONS` loop body — exception handling, partial failures |
| `flows/backfill_weather.py` | 40% | Loop body |
| `flows/backfill_observed.py` | 40% | Loop body |
| `flows/ingest_metar.py` | 48% | Top-level orchestration (the parser is well-covered) |
| `flows/ingest_weather.py` | 46% | Same |
| `flows/ingest_all.py` | 85% | Reasonable; tested via mocked sub-flows |

**Action:** PR G adds 6 tests to lift the worst three (ingest_kalshi, backfill_*) above 70%. Pattern: use `httpx.MockTransport` to simulate the per-station HTTP, then call the flow and assert on the side effects (DuckDB row counts, log calls).

## Bandit findings — all explained

| ID | Where | Verdict | What's done |
|---|---|---|---|
| B608 SQL injection | `features/weather.py` | False positive — `where` is built solely from `?` placeholders by `_build_where`, no user values flow via f-string. | `# nosec B608` with explanation |
| B311 random | `_http.py` | False positive — backoff jitter, not crypto. | Bandit config exclusion |
| B403 pickle | `train_weather.py` | We control both writer and reader; pickle stays inside `models/`, never crosses trust boundaries. | `# nosec B403` with explanation |
| B101 assert | `weather_ngr.py:87` | Real lint — `assert` was for mypy type-narrowing only; replaced with `if` clause that's robust under `python -O`. | Code fix |

After this PR: bandit at every severity level produces zero findings (config-suppressed false positives, real ones fixed).

## Dependency hygiene

`pip-audit` is now in the dev deps. Reports zero known CVEs as of this PR. Weekly CI workflow will refresh this; Dependabot already opens PRs for upgrades.

## Honest weak spots NOT addressed in this PR

These are real, low-priority enough to defer with a note:

1. **No mutation testing.** `mutmut` would tell us which assertions actually catch bugs. Worth doing in a follow-up; my guess is fees + Kelly + calibration are over-tested and the parsers are under-tested. Backlog: PR I.

2. **Hypothesis usage is shallow.** Only fees + Kelly use `hypothesis`. Parsers, NGR fits, and CV splits are all good candidates for property-based tests. Backlog.

3. **Real-API smoke tests aren't in CI.** All integration tests use `httpx.MockTransport`. If Open-Meteo or aviationweather.gov change response shapes, our tests stay green and `make ingest-*` breaks. Mitigation: weekly nightly workflow that runs `make ingest-weather && make ingest-metar` against real APIs and posts to a status badge. Backlog: spec out before adding (don't want flaky CI from upstream rate limits).

4. **No async race-condition tests.** I never test what happens when two `OpenMeteoClient.fetch_ensemble` calls share an `httpx.AsyncClient` from concurrent coroutines. In practice we never do this (each ingest is single-coroutine). If we ever add a parallel-stations-fanout, this matters. Backlog when relevant.

5. **DuckDB tz handling has bitten us once already** (the `as_of` shift bug fixed in PR F). All inserts now use UTC-naive `datetime`. There's no automated check that future code keeps this discipline; a custom ruff rule or a `mypy` plugin could enforce it. Low priority, document for now.

6. **Manifest schema is implicit.** `models/manifest.json` has a shape that downstream code (eventually) will consume. Should formalize as a `pydantic` model with version field. Trivial; schedule with backtest engine PR (PR H).

## How to keep this honest

This document is generated/edited by humans, not auto-rendered. It can rot. The defenses:

- **CI does the actual measurement.** Coverage threshold (80%) and bandit clean are CI gates. If the doc says "82% coverage" but CI passes at 60%, the doc is out of date — fix the doc OR drop the threshold (deliberately).
- **Refresh per Phase exit.** Each phase exit criterion in `ROADMAP.md` includes "refresh CODE_QUALITY.md."
- **Each new module gets a coverage row here at PR time.** Reviewer (you) catches missing rows.

## Tools we deliberately are NOT adding

- **SonarQube / Codacy / Snyk SaaS:** overkill for a private solo repo; the same tooling exists locally and free (ruff, mypy, bandit, pip-audit, coverage).
- **`pylint` on top of `ruff`:** ruff covers ~all of pylint's useful checks. Two linters = two configs to maintain.
- **mypy plugins beyond `pydantic`:** the plugin ecosystem is fragile; not worth the maintenance.
- **`pre-commit.ci`:** local pre-commit + GitHub Actions covers it. SaaS adds another auth surface.
- **`commitizen` / conventional commits:** I write descriptive commit messages by hand; tool-enforced format adds friction without obvious benefit at this scale.
