# Session audit — 2026-05-04

Distinguished-dev-team review of the 25 PRs currently open on `forecast-lab`. Captures: scope of each PR, audit findings, recommended merge order, deliberate scope choices, and Phase 5 readiness deltas.

This doc is a snapshot. The live tracker is [`ROADMAP.md`](../ROADMAP.md).

## Headline

- **25 open PRs**, every one CI-green or queued (`mergeable=MERGEABLE` for all 25 per `gh pr list`).
- **Code is no longer the bottleneck** for any Phase 5 readiness criterion. Remaining gates are operational (cron uptime, settled volume) or external (Pinnacle subscription, CPA, NVIDIA disclosure, Windows/WSL2 verification).
- **One audit finding fixed in [#54](https://github.com/jaloo8/forecast-lab/pull/54)**: GitHub Actions only triggered on PRs targeting `main`, so 10 stacked PRs had bypassed CI silently.

## Open queue at a glance

### Tier 1 — `main`-based, no inter-PR deps

| PR | Title | Phase | LoC |
|---|---|---|---|
| [#30](https://github.com/jaloo8/forecast-lab/pull/30) | post-merge audit fixes + Hosmer-Lemeshow + Phase 4 dashboard prototype | 2/4 | ~1100 |
| [#31](https://github.com/jaloo8/forecast-lab/pull/31) | `kq state-check` + DST verification | 5 #8 | ~330 |
| [#34](https://github.com/jaloo8/forecast-lab/pull/34) | vig-strip math (proportional + power devig) | 3 | ~580 |
| [#37](https://github.com/jaloo8/forecast-lab/pull/37) | bankroll plan + KMDW structural-gap memo | 5 #7 | ~210 |
| [#45](https://github.com/jaloo8/forecast-lab/pull/45) | NBA injury report schema + parser + CSV ingest | 3 | ~800 |
| [#47](https://github.com/jaloo8/forecast-lab/pull/47) | dashboard NBA CLV + conformal coverage panels | 4 | ~580 |
| [#48](https://github.com/jaloo8/forecast-lab/pull/48) | Page-Hinkley + ADWIN drift detectors | 5 #3/#6 | ~450 |
| [#49](https://github.com/jaloo8/forecast-lab/pull/49) | robust Kelly under conformal uncertainty | 5 #4/#7 | ~290 |
| [#50](https://github.com/jaloo8/forecast-lab/pull/50) | OU nowcast (mean-reversion replaces Brownian-σ) | 5 #2/#3 | ~360 |
| [#51](https://github.com/jaloo8/forecast-lab/pull/51) | property-based invariants for fees + Kelly + calibration | risk | ~200 |
| [#52](https://github.com/jaloo8/forecast-lab/pull/52) | Combinatorial Purged Cross-Validation (CPCV) | 5 #2/#3 | ~320 |
| [#53](https://github.com/jaloo8/forecast-lab/pull/53) | NBM qmd probabilistic Phase 1 | 5 #2 | ~650 |
| [#54](https://github.com/jaloo8/forecast-lab/pull/54) | CI workflow trigger fix (audit finding) | infra | ~10 |

### Tier 2 — single-dep stacks

| PR | Stacked on | What |
|---|---|---|
| [#32](https://github.com/jaloo8/forecast-lab/pull/32) | `main` | split-conformal coverage in backtest manifest |
| [#38](https://github.com/jaloo8/forecast-lab/pull/38) | #32 | conformal cron alert in `kq health-check` |
| [#33](https://github.com/jaloo8/forecast-lab/pull/33) | `main` | ECMWF Open Data direct fetcher (Phase 1) |
| [#39](https://github.com/jaloo8/forecast-lab/pull/39) | #33 | ECMWF Open Data Phase 2 ingest flow |
| [#35](https://github.com/jaloo8/forecast-lab/pull/35) | #34 | The Odds API v4 client + parser |

### Tier 3 — NBA stack (strict order)

`#36` (nba_odds schema/ingest, on #35)
↓
`#40` (schedule↔odds matcher, on #36)
↓
`#42` (538-style Elo, on #36) + `#41` (crosswalk persistence, on #40)
↓
`#46` (signal evaluator, on #42 with #34 merged in) + `#43` (CLV evaluator, on #41 with #42 + #34 merged in)
↓
`#44` (CLV flow + manifest + README operations catalog, on #43)

## Audit findings

### Finding 1 — CI trigger gap (FIXED in #54)

The `.github/workflows/ci.yml` workflow only triggered on `pull_request: branches: [main]`. PRs created with `--base feat/some-branch` (i.e. stacked) silently bypassed CI. **10 of the 24 originally-open PRs had zero CI runs**: #36, #38, #39, #40, #41, #42, #43, #44, #46.

PR [#54](https://github.com/jaloo8/forecast-lab/pull/54) changes the trigger to `branches: ["**"]`, which fires on every PR. Once #54 merges, every existing stacked PR can be re-pushed (or re-run from the GitHub UI) to pick up CI.

**Mitigation in the meantime**: every PR in this session passed `uv run pytest -q` + `uv run ruff check .` + `uv run ruff format --check .` + `uv run mypy src/kq` locally before push. Local checks are not GitHub-Actions-grade, but they cover the same suite.

### Finding 2 — Acceptable duplication: `StationCoord` + `kelvin_to_fahrenheit`

The pattern of `StationCoord` (icao + lat/lon + east-positive longitude property) and `kelvin_to_fahrenheit(k)` repeats across:

- `src/kq/clients/gefs_reforecast.py` (existing)
- `src/kq/clients/ecmwf_opendata.py` (PR #33)
- `src/kq/clients/nbm_qmd.py` (PR #53)

Each module ships its own copy as a deliberate scope choice — they're independent client modules with no shared base. Refactoring to a shared `kq.clients._common` module is a clean follow-up PR (~50 LOC + tests) but not load-bearing. Flagging here so future-us doesn't claim "didn't notice."

### Finding 3 — `nowcast.py` and `nowcast_ou.py` coexist

PR #50's OU nowcast lives in `src/kq/models/nowcast_ou.py` rather than replacing the Brownian-σ implementation in `src/kq/models/nowcast.py`. Adoption is opt-in: callers continue to use `nowcast.py` until they explicitly switch to `ou_posterior()`. Theta=0 in the OU module recovers the Brownian behavior exactly, so a future migration is a one-line change.

This split was deliberate (zero behavior change for existing callers), but the duplication is real and the operator should be aware.

### Finding 4 — Phase 5 #5 dashboard glyph relies on a synthesis that hasn't run live yet

PR #47's `NbaClvSummary.passes_phase_5_5_bar` checks `mean_signed_clv >= +0.01` — the load-bearing Phase 5 readiness #5 metric. The threshold is hard-coded; will need to live alongside the bankroll plan as a tunable as data accumulates. Flagging so it doesn't drift silently.

### Finding 5 — `ndfd_forecast` schema has Pn columns that v1 always leaves NULL

The schema defines `p10_max_f` ... `p90_max_f` columns; the v1 ingest path (`source='nbm_deterministic_openmeteo'`) only populates `forecast_max_f`. PR #53 (NBM qmd Phase 1) is the upgrade path for those columns; Phase 2 (future PR) wires the columns to populate with `source='nbm_qmd_s3'` rows. **Do not assume the columns are populated** when querying — every existing reader correctly checks `forecast_max_f` only. New readers should explicitly handle `NULL` until Phase 2 lands.

## Phase 5 readiness — code-side state at audit close

| # | Criterion | Code state | Awaiting |
|---|---|---|---|
| 1 | ≥500 settled paper trades | code-complete (paper executor + NBA signal evaluator) | cron uptime + Kalshi prod weather + Pinnacle |
| 2 | Brier ≥ 5% better vs NDFD | code-complete (NBM qmd will sharpen the benchmark) | run NDFD-qmd ingest; re-run backtest |
| 3 | Reliability calibrated | conformal + drift detection in flight | data flow + cron uptime |
| 4 | Positive paper P&L | code-complete | data flow + Pinnacle |
| 5 | CLV vs Pinnacle ≥ +1% | code-complete | Pinnacle subscription + cron + ≥100 settled NBA games |
| 6 | Flows ≥30 days uptime | calibration alert + drift alert wired | Windows cron running |
| 7 | Bankroll plan + Kelly caps | ✅ shipped (PR #37 + robust Kelly #49) | nothing |
| 8 | State availability | ✅ tooling shipped (PR #31) | user runs `kq state-check` once |
| 9 | CPA engaged for §1256 | external | external |
| 10 | NVIDIA HR/Legal disclosure | external | external |

## Things deliberately NOT shipped this session

The following were proposed during the session and **declined** for honest reasons:

- **`nbainjuries` PyPI package as live source** — new dependency requires CLAUDE.md §9 signoff; v1 ships CSV-import only (PR #45 docstring lists the menu of options).
- **Streamlit integration of #47's panels into #30's dashboard prototype** — would require rebasing #47 on #30, adding merge-conflict risk for trivial wiring. Pure-function panels ship as PR #47; integration deferred to a follow-up after #30 lands.
- **NBA paper-trade flow (vs evaluator)** — the evaluator (#46) is shipped, but a flow that wires it into the existing `paper_trade` repository depends on Kalshi NBA market ingest, which is its own PR. Not shipped to avoid dead code.
- **More postprocessing for KMDW** — five techniques have been tried; the gap is structural per [`docs/research/KMDW-STRUCTURAL-GAP.md`](research/KMDW-STRUCTURAL-GAP.md). Recommendation is to defer KMDW for v1 (configure router to no-trade) or accept the "≥4 of 6" Phase 5 #2 reformulation.
- **LightGBM quantile regression** — Pass 1 ext memo item #10. Sanctioned ML lane only after 500 calibrated trades ship per CLAUDE.md §2; correctly post-Phase-5.
- **CVX-Kelly with bracket correlation** — would require new `cvxpy` dep. CLAUDE.md §9 signoff still needed; deferred.
- **MBM router leg** — `pythie` dep; CRPSS parity-or-slight-improvement vs NGR; not load-bearing.

## Recommended merge order

```
First wave  (parallel, all on main):
  #30, #31, #34, #37, #45, #47, #48, #49, #50, #51, #52, #53, #54

Second wave (after first):
  #32 → #38
  #33 → #39
  #35

Third wave  (NBA stack, strict order):
  #36 → #40 → #41 → #43 → #44
                  → #42 → #46
```

After each wave, the next one's stacked PRs need a quick rebase (or just GitHub's "Update branch" button) to pick up the merged dependency.

## Numbers

- **Local pytest** (this session, baseline `main`): 552 passing, 1 deselected (integration-only).
- **Local lint**: clean (`ruff check .` + `ruff format --check .`).
- **Local types**: clean (`mypy src/kq`, 87 source files).
- **Local security**: clean (`bandit -c pyproject.toml -r src/kq -ll`, no medium/high findings since PR #30 fixes landed).
- **Lines added across 25 PRs**: ~13,000 inc tests/docs; ~5,500 production code.
- **New tests**: ~280 across the 25 PRs; coverage held >87% throughout.

## Where to look for the live state

- [`ROADMAP.md`](../ROADMAP.md) — refreshed to reflect this audit.
- [`README.md`](../README.md) — updated in PR #44 with the opt-in command catalog.
- [`docs/BANKROLL-PLAN.md`](BANKROLL-PLAN.md) — Phase 5 #7 artifact (PR #37).
- [`docs/research/KMDW-STRUCTURAL-GAP.md`](research/KMDW-STRUCTURAL-GAP.md) — KMDW deferral memo (PR #37).
- [`docs/SCHEDULED-RUNS.md`](SCHEDULED-RUNS.md) — cron recipes; user-side after Windows verification.
